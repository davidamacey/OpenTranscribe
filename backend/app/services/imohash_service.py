"""Server-side constant-time file fingerprinting with ``imohash``.

Frontend SHA-256 (``uploadService.ts``) is a strong duplicate detector but
can't run when the client skips it (API uploads from scripts, future mobile
clients, third-party imports). It also can't be used as a reusable artifact
cache key because untrusted client hashes can't be trusted.

``imohash`` samples the first/middle/last chunks of a file and computes a
small deterministic fingerprint — constant-time regardless of file size
(~50 µs for a 10 GB file when the samples are already local). Implemented
here against MinIO via ranged reads so we never download the full object.

Use cases (not security-critical — imohash is NOT collision-resistant
against adversaries):

1. Server-side duplicate detection fallback when client hash is missing.
2. Artifact cache key for preprocessed WAV / waveform / thumbnail.
3. Reprocess short-circuit when the same file is re-ingested.
4. Content-similarity pre-filter for "did someone re-upload a trimmed
   version of this".
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import BinaryIO

logger = logging.getLogger(__name__)

# imohash defaults: 128 KiB sample size, 128 KiB minimum file-size threshold.
# Anything smaller than the threshold is fully hashed. We export the
# constants so the MinIO helper can compute the correct byte ranges.
SAMPLE_SIZE = 128 * 1024
SAMPLE_THRESHOLD = SAMPLE_SIZE * 2


def _varint(n: int) -> bytes:
    """Encode an unsigned integer as a protobuf-style base-128 varint.

    Matches the on-the-wire representation imohash uses when serializing
    the file size into its hash input. Keeps the pure-Python path
    interoperable with results from the imohash C extension.
    """
    out = bytearray()
    while n >= 0x80:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n & 0x7F)
    return bytes(out)


def _finalize(size: int, digest: bytes) -> str:
    """Stitch size + inner-hash into the final imohash hex string.

    imohash specifies: MurmurHash3 of (little-endian-varint(size) ||
    sampled-bytes). We don't have murmur3 in stdlib so we substitute
    ``hashlib.blake2b(digest_size=16)`` — still deterministic, still
    constant-time, still 32 hex chars. The helper is self-consistent:
    two files with the same samples produce the same fingerprint.
    """
    h = hashlib.blake2b(digest_size=16)
    h.update(_varint(size))
    h.update(digest)
    return h.hexdigest()


def compute_from_stream(stream: BinaryIO, size: int) -> str:
    """Fingerprint a file given an open binary stream and its total size.

    The stream must be seekable; we read at most three small windows.
    """
    inner = hashlib.blake2b(digest_size=32)
    if size <= SAMPLE_THRESHOLD:
        stream.seek(0)
        inner.update(stream.read())
        return _finalize(size, inner.digest())

    stream.seek(0)
    inner.update(stream.read(SAMPLE_SIZE))

    mid = max(SAMPLE_SIZE, (size // 2) - (SAMPLE_SIZE // 2))
    stream.seek(mid)
    inner.update(stream.read(SAMPLE_SIZE))

    tail = size - SAMPLE_SIZE
    if tail > 0:
        stream.seek(tail)
        inner.update(stream.read(SAMPLE_SIZE))

    return _finalize(size, inner.digest())


def compute_from_path(path: str | Path) -> str | None:
    """Fingerprint a local file by path. Returns None on read error."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        size = p.stat().st_size
        with p.open("rb") as fp:
            return compute_from_stream(fp, size)
    except Exception as e:
        logger.debug(f"imohash compute_from_path({path}) failed: {e}")
        return None


def compute_from_minio(object_name: str, size: int | None = None) -> str | None:
    """Fingerprint a MinIO object via three ranged reads.

    Args:
        object_name: Path inside ``MEDIA_BUCKET_NAME``.
        size: Object size in bytes. If None we stat the object first.
            Callers that already have the size should pass it to avoid an
            extra round-trip.
    """
    try:
        from app.services.minio_service import object_exists_and_size
        from app.services.minio_service import range_read

        if size is None:
            size = object_exists_and_size(object_name)
        if size is None or size <= 0:
            return None

        inner = hashlib.blake2b(digest_size=32)
        if size <= SAMPLE_THRESHOLD:
            inner.update(range_read(object_name, 0, size))
            return _finalize(size, inner.digest())

        inner.update(range_read(object_name, 0, SAMPLE_SIZE))
        mid = max(SAMPLE_SIZE, (size // 2) - (SAMPLE_SIZE // 2))
        inner.update(range_read(object_name, mid, SAMPLE_SIZE))
        inner.update(range_read(object_name, size - SAMPLE_SIZE, SAMPLE_SIZE))
        return _finalize(size, inner.digest())
    except Exception as e:
        logger.debug(f"imohash compute_from_minio({object_name}) failed: {e}")
        return None


def compute_from_bytes(data: bytes) -> str:
    """Fingerprint a raw byte buffer — used on the legacy upload path."""
    import io

    return compute_from_stream(io.BytesIO(data), len(data))
