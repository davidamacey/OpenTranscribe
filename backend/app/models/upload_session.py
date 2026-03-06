"""
SQLAlchemy model for TUS upload sessions.

Tracks state for resumable file uploads using the TUS 1.0.0 protocol
with MinIO S3-compatible multipart storage as the backend.
"""

import contextlib
import json
from uuid import uuid4

from sqlalchemy import BigInteger
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import LargeBinary
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.base import Base


class UploadSession(Base):
    """TUS upload session tracking table.

    Each row represents one in-flight or completed resumable upload.
    The row is created on TUS POST and updated on each PATCH.

    Attributes:
        id: Internal auto-increment primary key.
        upload_id: Externally-visible UUID (the TUS resource ID in the Location header).
        media_file_id: FK to the MediaFile record created by POST /files/prepare.
        user_id: FK to the owning user.
        minio_upload_id: The S3 UploadId string returned by create_multipart_upload.
        storage_path: Final MinIO object path for the assembled file.
        offset: Total bytes successfully received and persisted to MinIO so far.
        total_size: File size as declared in the TUS Upload-Length header.
        content_type: MIME type from TUS metadata.
        filename: Original filename from TUS metadata (sanitized).
        tus_metadata: Raw Upload-Metadata header value for audit purposes.
        parts_json: JSON array of {part_number, etag, size} for multipart assembly.
        chunk_buffer: Sub-5MB partial chunk awaiting a complete 5MB part flush.
        min_speakers: Speaker diarization min from TUS metadata.
        max_speakers: Speaker diarization max from TUS metadata.
        num_speakers: Exact speaker count override from TUS metadata.
        extracted_from_video_json: Base64-decoded JSON from TUS metadata for video extraction.
        status: 'active' | 'completed' | 'aborted'.
        created_at: Timestamp of TUS POST.
        expires_at: Session expiry time (created_at + 24h). Cleanup task uses this.
        completed_at: Timestamp of final successful PATCH (when complete).
    """

    __tablename__ = "upload_session"

    id = Column(Integer, primary_key=True, index=True)
    upload_id = Column(
        UUID(as_uuid=True),
        unique=True,
        default=uuid4,
        index=True,
        nullable=False,
    )
    media_file_id = Column(
        Integer,
        ForeignKey("media_file.id", ondelete="CASCADE"),
        # UNIQUE prevents two concurrent TUS sessions for the same MediaFile.
        # A second POST for the same fileId will hit this constraint rather than
        # silently creating a duplicate MinIO multipart upload.
        unique=True,
        index=True,
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # S3 UploadId — not a UUID, can be an arbitrarily long opaque string
    minio_upload_id = Column(String(1024), nullable=True)
    # Final MinIO object path (e.g. user_1/file_42/video.mp4)
    storage_path = Column(String(1024), nullable=False)
    # Bytes successfully received and pushed to MinIO
    offset = Column("offset", BigInteger, default=0, nullable=False)
    # Total file size from Upload-Length header
    total_size = Column(BigInteger, nullable=False)
    content_type = Column(String(256), default="application/octet-stream", nullable=False)
    filename = Column(String(512), nullable=False)
    # Raw Upload-Metadata header for audit
    tus_metadata = Column(Text, nullable=True)
    # JSON: [{"part_number": int, "etag": str, "size": int}, ...]
    parts_json = Column(Text, default="[]", nullable=False)
    # Sub-5MB partial chunk held between PATCH calls (S3 minimum part size constraint)
    chunk_buffer = Column(LargeBinary, nullable=True)
    # Speaker diarization parameters from TUS metadata
    min_speakers = Column(Integer, nullable=True)
    max_speakers = Column(Integer, nullable=True)
    num_speakers = Column(Integer, nullable=True)
    # JSON string decoded from base64 TUS metadata (for extracted-from-video uploads)
    extracted_from_video_json = Column(Text, nullable=True)
    # 'active' | 'completed' | 'aborted'
    status = Column(String(32), default="active", nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # created_at + 24h — cleanup task aborts sessions past this time
    expires_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def get_parts(self) -> list[dict]:
        """Deserialise parts_json → list of dicts."""
        try:
            result = json.loads(self.parts_json or "[]")
            return list(result)
        except (ValueError, TypeError):
            return []

    def set_parts(self, parts: list[dict]) -> None:
        """Serialise parts list → parts_json."""
        self.parts_json = json.dumps(parts)

    def get_chunk_buffer(self) -> bytes:
        """Return chunk_buffer as bytes (never None)."""
        return self.chunk_buffer or b""

    @property
    def is_complete(self) -> bool:
        """True when all bytes have been received."""
        return bool(self.offset == self.total_size)


# ---------------------------------------------------------------------------
# SQLAlchemy event: abort MinIO multipart upload on session deletion
# ---------------------------------------------------------------------------


@event.listens_for(UploadSession, "before_delete")
def _abort_minio_on_delete(mapper, connection, target: UploadSession):
    """Abort the MinIO multipart upload when an UploadSession row is deleted.

    This prevents orphaned incomplete multipart uploads from accumulating in
    MinIO when a MediaFile is deleted while an upload is still in progress.
    """
    if target.status == "active" and target.minio_upload_id and target.storage_path:
        with contextlib.suppress(Exception):
            from app.services.minio_service import MinIOService

            svc = MinIOService()
            svc.abort_multipart_upload(target.storage_path, target.minio_upload_id)
