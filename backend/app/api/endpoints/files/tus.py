"""
TUS 1.0.0 resumable upload endpoints for OpenTranscribe.

Implements the TUS Protocol 1.0.0 (https://tus.io/protocols/resumable-upload.html)
using MinIO S3-compatible multipart storage for server-side chunk assembly.

Endpoints:
    OPTIONS /api/files/tus          - Capability discovery (no auth)
    POST    /api/files/tus          - Create upload resource
    HEAD    /api/files/tus/{id}     - Get upload offset for resume
    PATCH   /api/files/tus/{id}     - Upload chunk
    DELETE  /api/files/tus/{id}     - Abort upload
"""

import base64
import contextlib
import json
import logging
import math
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from uuid import UUID

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from fastapi import status as http_status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.models.upload_session import UploadSession
from app.models.user import User
from app.services.minio_service import MinIOService
from app.utils.file_validation import validate_magic_bytes
from app.utils.filename import get_safe_storage_filename

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TUS protocol constants
# ---------------------------------------------------------------------------
TUS_VERSION = "1.0.0"
TUS_EXTENSION = "creation,termination"
TUS_MAX_SIZE = 16_106_127_360  # 15 GB
MIN_PART_SIZE = 5 * 1024 * 1024  # 5 MB — S3 minimum non-final part size
MAX_CHUNK_SIZE = 100 * 1024 * 1024  # 100 MB — maximum single PATCH body
SESSION_TTL_HOURS = 24
MAX_ACTIVE_SESSIONS_PER_USER = 5

_TUS_HEADERS = {
    "Tus-Resumable": TUS_VERSION,
    "Tus-Version": TUS_VERSION,
    "Tus-Extension": TUS_EXTENSION,
    "Tus-Max-Size": str(TUS_MAX_SIZE),
}

minio_service = MinIOService()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tus_headers(**extra) -> dict:
    """Return TUS protocol headers merged with any additional headers."""
    return {**_TUS_HEADERS, **extra}


def _decode_tus_metadata(header: str) -> dict[str, str]:
    """Decode a TUS Upload-Metadata header value.

    TUS spec: comma-separated 'key base64value' pairs.

    Args:
        header: Raw Upload-Metadata header string.

    Returns:
        Dict of decoded key-value pairs.
    """
    result: dict[str, str] = {}
    if not header:
        return result
    for pair in header.split(","):
        pair = pair.strip()
        if " " not in pair:
            result[pair] = ""
            continue
        key, b64 = pair.split(" ", 1)
        try:
            result[key.strip()] = base64.b64decode(b64.strip()).decode("utf-8", errors="replace")
        except Exception:
            result[key.strip()] = ""
    return result


def _parse_speaker_params(
    metadata: dict[str, str],
) -> tuple[int | None, int | None, int | None]:
    """Parse optional speaker diarization params from TUS Upload-Metadata.

    Args:
        metadata: Decoded TUS metadata dict.

    Returns:
        Tuple of (min_speakers, max_speakers, num_speakers), any may be None.
    """
    min_speakers: int | None = None
    max_speakers: int | None = None
    num_speakers: int | None = None
    with contextlib.suppress(ValueError, TypeError):
        if metadata.get("minSpeakers"):
            min_speakers = int(metadata["minSpeakers"])
        if metadata.get("maxSpeakers"):
            max_speakers = int(metadata["maxSpeakers"])
        if metadata.get("numSpeakers"):
            num_speakers = int(metadata["numSpeakers"])
    return min_speakers, max_speakers, num_speakers


def _parse_extracted_from_video(metadata: dict[str, str]) -> str | None:
    """Parse and validate optional extractedFromVideo JSON from TUS metadata.

    Args:
        metadata: Decoded TUS metadata dict.

    Returns:
        JSON string if present and valid, else None.
    """
    raw = metadata.get("extractedFromVideo")
    if not raw:
        return None
    try:
        json.loads(raw)
        return raw
    except (ValueError, TypeError):
        logger.warning("Invalid extractedFromVideo JSON in TUS metadata, ignoring")
        return None


def _get_session(
    db: Session, upload_id: UUID, user_id: int, for_update: bool = False
) -> UploadSession:
    """Fetch an active UploadSession or raise 404.

    Args:
        db: Database session.
        upload_id: The TUS upload UUID.
        user_id: The requesting user's ID (ownership check).
        for_update: If True, acquire a row-level lock (SELECT FOR UPDATE).

    Returns:
        The UploadSession row.

    Raises:
        HTTPException 404: If session not found or not owned by user.
    """
    query = select(UploadSession).where(
        UploadSession.upload_id == upload_id,
        UploadSession.user_id == user_id,
    )
    if for_update:
        query = query.with_for_update()

    row = db.execute(query).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Upload session not found",
        )
    session: UploadSession = row
    return session


# ---------------------------------------------------------------------------
# OPTIONS /tus
# ---------------------------------------------------------------------------


@router.options("", include_in_schema=False)
@router.options("/", include_in_schema=False)
async def tus_options():
    """TUS capability discovery endpoint (no authentication required).

    Returns the server's TUS capabilities so clients can negotiate
    before creating an upload resource.
    """
    return Response(
        status_code=204,
        headers=_tus_headers(),
    )


# ---------------------------------------------------------------------------
# POST /tus — Create upload resource
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def tus_create(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new TUS upload resource.

    Validates TUS headers, looks up the MediaFile created by POST /files/prepare,
    initiates a MinIO multipart upload, and persists the UploadSession.

    Returns:
        201 with Location header pointing to the new upload resource.
    """
    # ---- 1. Validate TUS protocol version ----
    tus_resumable = request.headers.get("Tus-Resumable", "")
    if tus_resumable != TUS_VERSION:
        raise HTTPException(
            status_code=412,
            detail=f"Tus-Resumable must be {TUS_VERSION}",
        )

    # ---- 2. Parse and validate Upload-Length ----
    upload_length_str = request.headers.get("Upload-Length", "")
    if not upload_length_str:
        raise HTTPException(status_code=400, detail="Upload-Length header is required")
    try:
        total_size = int(upload_length_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Upload-Length must be an integer") from None
    if total_size > TUS_MAX_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File size {total_size} exceeds maximum {TUS_MAX_SIZE} bytes (15 GB)",
        )
    if total_size <= 0:
        # Zero-byte files cannot be assembled via S3 multipart (at least one
        # part of >= 1 byte is required).  Reject explicitly to avoid hanging MinIO.
        raise HTTPException(status_code=400, detail="Upload-Length must be greater than 0")

    # ---- 3. Parse TUS metadata ----
    raw_metadata = request.headers.get("Upload-Metadata", "")
    metadata = _decode_tus_metadata(raw_metadata)

    file_id_str = metadata.get("fileId", "")
    filename = metadata.get("filename", "untitled")
    content_type = metadata.get("filetype", "application/octet-stream")

    if not file_id_str:
        raise HTTPException(status_code=400, detail="Upload-Metadata must include fileId")
    if not content_type.startswith(("audio/", "video/")):
        raise HTTPException(
            status_code=400,
            detail="filetype must be an audio or video MIME type",
        )

    # Parse optional speaker params and extractedFromVideo JSON
    min_speakers, max_speakers, num_speakers = _parse_speaker_params(metadata)
    extracted_from_video_json = _parse_extracted_from_video(metadata)

    # ---- 4. Look up MediaFile ----
    try:
        file_uuid = UUID(file_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid fileId UUID format") from None

    media_file = (
        db.query(MediaFile)
        .filter(MediaFile.uuid == str(file_uuid), MediaFile.user_id == current_user.id)
        .first()
    )
    if media_file is None:
        raise HTTPException(
            status_code=404,
            detail="MediaFile not found or you do not have permission",
        )

    # ---- 5. Per-user active session cap (prevent MinIO multipart abuse) ----
    active_count = (
        db.query(UploadSession)
        .filter(
            UploadSession.user_id == current_user.id,
            UploadSession.status == "active",
        )
        .count()
    )
    if active_count >= MAX_ACTIVE_SESSIONS_PER_USER:
        raise HTTPException(
            status_code=429,
            detail=f"Maximum {MAX_ACTIVE_SESSIONS_PER_USER} concurrent uploads per user",
        )

    # ---- 6. Validate part count (S3 max 10,000 parts) ----
    max_parts = math.ceil(total_size / MIN_PART_SIZE) if total_size > 0 else 1
    if max_parts > 10_000:
        raise HTTPException(
            status_code=400,
            detail="File too large relative to minimum part size (would exceed 10,000 parts)",
        )

    # ---- 7. Generate storage path ----
    storage_path = get_safe_storage_filename(filename, int(current_user.id), int(media_file.id))

    # ---- 8. Initiate MinIO multipart upload ----
    try:
        minio_upload_id = minio_service.create_multipart_upload(storage_path, content_type)
    except Exception as e:
        logger.error(f"Failed to initiate MinIO multipart upload: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to initiate upload storage",
        ) from e

    # ---- 9. Create UploadSession ----
    now = datetime.now(timezone.utc)
    session = UploadSession(
        media_file_id=int(media_file.id),
        user_id=int(current_user.id),
        minio_upload_id=minio_upload_id,
        storage_path=storage_path,
        offset=0,
        total_size=total_size,
        content_type=content_type,
        filename=filename,
        tus_metadata=raw_metadata,
        parts_json="[]",
        chunk_buffer=None,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
        num_speakers=num_speakers,
        extracted_from_video_json=extracted_from_video_json,
        status="active",
        created_at=now,
        expires_at=now + timedelta(hours=SESSION_TTL_HOURS),
        completed_at=None,
    )
    db.add(session)
    try:
        db.commit()
    except IntegrityError:
        # Another concurrent POST already created a session for this MediaFile.
        # Abort the MinIO multipart upload we just initiated before returning.
        db.rollback()
        with contextlib.suppress(Exception):
            minio_service.abort_multipart_upload(storage_path, minio_upload_id)
        raise HTTPException(
            status_code=409,
            detail="An upload session for this file already exists",
        ) from None
    db.refresh(session)

    logger.info(
        "TUS upload created",
        extra={
            "event": "tus_upload_created",
            "upload_id": str(session.upload_id),
            "total_size": total_size,
            "user_id": current_user.id,
            "media_file_id": media_file.id,
        },
    )

    return Response(
        status_code=201,
        headers=_tus_headers(
            Location=f"/api/files/tus/{session.upload_id}",
        ),
    )


# ---------------------------------------------------------------------------
# HEAD /tus/{upload_id} — Get upload offset
# ---------------------------------------------------------------------------


@router.head("/{upload_id}")
async def tus_head(
    upload_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return the current upload offset for resumption.

    Implements 'heal on HEAD': reconciles DB state with MinIO truth after
    a server restart that occurred between upload_part() and the DB commit.
    """
    session = _get_session(db, upload_id, int(current_user.id))

    # ---- Heal on HEAD: reconcile with MinIO truth ----
    if session.status == "active" and session.minio_upload_id:
        try:
            minio_parts = minio_service.list_parts(session.storage_path, session.minio_upload_id)
            db_parts = session.get_parts()

            if len(minio_parts) > len(db_parts):
                # MinIO has more parts than the DB knows about — sync
                healed_offset = sum(p["size"] for p in minio_parts)
                session.set_parts(minio_parts)
                session.offset = healed_offset
                db.commit()
                logger.info(
                    f"Healed TUS session {upload_id}: "
                    f"synced {len(minio_parts)} parts from MinIO, offset={healed_offset}"
                )
        except Exception as e:
            # Non-fatal — return current DB state
            logger.warning(f"Heal-on-HEAD failed for {upload_id}: {e}")

    return Response(
        status_code=200,
        headers=_tus_headers(
            **{
                "Upload-Offset": str(session.offset),
                "Upload-Length": str(session.total_size),
                "Cache-Control": "no-store",
            }
        ),
    )


# ---------------------------------------------------------------------------
# PATCH /tus/{upload_id} — Upload chunk
# ---------------------------------------------------------------------------


@router.patch("/{upload_id}")
async def tus_patch(
    upload_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Upload a chunk of the file at the given offset.

    Handles the 5MB S3 minimum part size constraint by buffering sub-5MB
    chunks in the UploadSession.chunk_buffer column until enough data
    accumulates for a complete part (or the final chunk arrives).

    On completion, assembles the multipart upload, generates thumbnails
    for video files, dispatches Celery tasks, and sends a WebSocket
    file_created notification.
    """
    # ---- 1. Validate Content-Type ----
    # The TUS spec requires exactly "application/offset+octet-stream".
    # Split on ";" to strip optional parameters (e.g. charset) before comparing
    # so that "application/offset+octet-stream; charset=utf-8" is accepted, but
    # "evil-prefix/application/offset+octet-stream" is correctly rejected.
    content_type_header = request.headers.get("Content-Type", "").split(";")[0].strip()
    if content_type_header != "application/offset+octet-stream":
        raise HTTPException(
            status_code=415,
            detail="Content-Type must be application/offset+octet-stream",
        )

    # ---- 2. Parse Upload-Offset ----
    offset_str = request.headers.get("Upload-Offset", "")
    if not offset_str:
        raise HTTPException(status_code=400, detail="Upload-Offset header is required")
    try:
        client_offset = int(offset_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Upload-Offset must be an integer") from None

    # ---- 3. Acquire row-level lock and fetch session ----
    session = _get_session(db, upload_id, int(current_user.id), for_update=True)

    if session.status != "active":
        raise HTTPException(
            status_code=409,
            detail=f"Upload session is {session.status}, not active",
        )

    # ---- 4. Validate offset matches DB state (idempotency + conflict detection) ----
    if client_offset != session.offset:
        raise HTTPException(
            status_code=409,
            detail=f"Upload-Offset {client_offset} does not match session offset {session.offset}",
        )

    # ---- 5. Read request body (with size guard) ----
    buffer_len = len(session.get_chunk_buffer())
    max_read = MAX_CHUNK_SIZE + buffer_len
    chunk_data = await request.body()
    if len(chunk_data) > max_read:
        raise HTTPException(
            status_code=413,
            detail=f"Chunk size exceeds maximum of {MAX_CHUNK_SIZE} bytes",
        )

    # ---- 6. Magic byte validation on first chunk ----
    if session.offset == 0 and chunk_data:
        header_bytes = chunk_data[:512]
        is_valid, result = validate_magic_bytes(header_bytes, session.content_type)
        if not is_valid:
            # Abort the multipart upload and mark session as aborted
            with contextlib.suppress(Exception):
                minio_service.abort_multipart_upload(session.storage_path, session.minio_upload_id)
            session.status = "aborted"
            db.commit()
            raise HTTPException(
                status_code=415,
                detail=f"File content does not match declared MIME type: {result}",
            )

    # ---- 7. 5MB buffer flush logic ----
    combined = session.get_chunk_buffer() + chunk_data
    new_offset = session.offset + len(chunk_data)
    is_final_chunk = new_offset == session.total_size
    parts = session.get_parts()
    new_buffer = b""

    if is_final_chunk:
        # Final chunk — flush everything regardless of size
        if combined:
            part_number = len(parts) + 1
            try:
                etag = minio_service.upload_part(
                    session.storage_path,
                    session.minio_upload_id,
                    part_number,
                    combined,
                )
            except Exception as e:
                logger.error(f"MinIO upload_part failed for {upload_id}: {e}")
                raise HTTPException(
                    status_code=500, detail="Failed to upload chunk to storage"
                ) from e
            parts.append({"part_number": part_number, "etag": etag, "size": len(combined)})
        new_buffer = b""
    else:
        # Non-final chunk — only flush complete 5MB parts
        while len(combined) >= MIN_PART_SIZE:
            part_data = combined[:MIN_PART_SIZE]
            combined = combined[MIN_PART_SIZE:]
            part_number = len(parts) + 1
            try:
                etag = minio_service.upload_part(
                    session.storage_path,
                    session.minio_upload_id,
                    part_number,
                    part_data,
                )
            except Exception as e:
                logger.error(f"MinIO upload_part failed for {upload_id}: {e}")
                raise HTTPException(
                    status_code=500, detail="Failed to upload chunk to storage"
                ) from e
            parts.append({"part_number": part_number, "etag": etag, "size": len(part_data)})
        new_buffer = combined  # < 5MB remainder

    # ---- 8. Update session state atomically ----
    session.set_parts(parts)
    session.chunk_buffer = new_buffer if new_buffer else None
    session.offset = new_offset

    logger.info(
        "TUS chunk received",
        extra={
            "event": "tus_chunk_received",
            "upload_id": str(upload_id),
            "offset": new_offset,
            "part_count": len(parts),
        },
    )

    # ---- 9. Handle upload completion ----
    if is_final_chunk:
        await _complete_upload(db, session)

    db.commit()

    return Response(
        status_code=204,
        headers=_tus_headers(**{"Upload-Offset": str(new_offset)}),
    )


async def _complete_upload(db: Session, session: UploadSession) -> None:
    """Finalize a completed TUS upload.

    Called when the final PATCH chunk brings offset == total_size.
    Completes the MinIO multipart upload, generates video thumbnails,
    updates MediaFile, dispatches Celery tasks, invalidates cache,
    and sends a WebSocket notification.

    Args:
        db: Database session (will be committed by caller).
        session: The UploadSession row (already locked and updated).
    """
    media_file = db.query(MediaFile).filter(MediaFile.id == session.media_file_id).first()
    if media_file is None:
        logger.error(f"MediaFile {session.media_file_id} not found at TUS completion")
        raise HTTPException(status_code=500, detail="Associated media file not found")

    parts = session.get_parts()

    # ---- a. Complete the MinIO multipart upload ----
    try:
        minio_service.complete_multipart_upload(
            session.storage_path, session.minio_upload_id, parts
        )
    except Exception as e:
        logger.error(f"Failed to complete MinIO multipart upload for {session.upload_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to assemble uploaded file") from e

    # ---- b. Generate thumbnail for video files (MUST be before task dispatch) ----
    # generate_and_upload_thumbnail is async and takes (user_id, media_file_id, video_path)
    thumbnail_path: str | None = None
    if session.content_type.startswith("video/"):
        try:
            from app.utils.thumbnail import generate_and_upload_thumbnail

            thumbnail_path = await generate_and_upload_thumbnail(
                user_id=session.user_id,
                media_file_id=session.media_file_id,
                video_path=session.storage_path,
            )
        except Exception as e:
            logger.warning(f"Thumbnail generation failed for {session.upload_id}: {e}")

    # ---- c. Update MediaFile record ----
    media_file.storage_path = session.storage_path
    media_file.file_size = session.total_size
    media_file.status = FileStatus.PENDING
    if thumbnail_path:
        media_file.thumbnail_path = thumbnail_path

    # ---- d. Apply extracted_from_video metadata if present ----
    if session.extracted_from_video_json:
        try:
            extracted_data = json.loads(session.extracted_from_video_json)
            media_file.metadata_important = extracted_data
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to apply extracted_from_video_json: {e}")

    # ---- e. Mark session as completed ----
    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)

    # Flush to DB before dispatching tasks (tasks may query the MediaFile)
    db.flush()

    # ---- f. Invalidate Redis cache (non-fatal) ----
    try:
        from app.services.redis_cache_service import redis_cache

        redis_cache.invalidate_user_files(session.user_id)
    except Exception as e:
        logger.debug(f"Redis cache invalidation failed (non-critical): {e}")

    # ---- g. Dispatch Celery tasks ----
    try:
        from app.tasks.transcription import transcribe_audio_task
        from app.tasks.waveform import generate_waveform_task

        transcribe_audio_task.delay(
            file_uuid=str(media_file.uuid),
            min_speakers=session.min_speakers,
            max_speakers=session.max_speakers,
            num_speakers=session.num_speakers,
        )
        generate_waveform_task.delay(
            file_id=int(media_file.id),
            file_uuid=str(media_file.uuid),
        )
        logger.info(f"Dispatched transcription + waveform tasks for MediaFile {media_file.id}")
    except Exception as e:
        logger.error(f"Failed to dispatch Celery tasks for {session.upload_id}: {e}")
        # Do not raise — the file was uploaded successfully; tasks can be re-dispatched

    # ---- h. Send WebSocket file_created notification (non-fatal) ----
    try:
        from app.api.websockets import send_notification
        from app.services.formatting_service import FormattingService

        await send_notification(
            user_id=session.user_id,
            notification_type="file_created",
            data={
                "file_id": str(media_file.uuid),
                "file": {
                    "uuid": str(media_file.uuid),
                    "filename": media_file.filename,
                    "status": media_file.status.value
                    if hasattr(media_file.status, "value")
                    else str(media_file.status),
                    "display_status": FormattingService.format_status(
                        FileStatus(media_file.status)
                    ),
                    "content_type": media_file.content_type,
                    "file_size": media_file.file_size,
                    "title": media_file.title,
                    "author": getattr(media_file, "author", None),
                    "duration": media_file.duration,
                    "upload_time": media_file.upload_time.isoformat()
                    if media_file.upload_time
                    else None,
                },
            },
        )
    except Exception as e:
        logger.warning(f"Failed to send file_created notification: {e}")

    logger.info(
        "TUS upload completed",
        extra={
            "event": "tus_upload_completed",
            "upload_id": str(session.upload_id),
            "filename": session.filename,
            "total_size": session.total_size,
            "media_file_id": media_file.id,
        },
    )


# ---------------------------------------------------------------------------
# DELETE /tus/{upload_id} — Abort upload
# ---------------------------------------------------------------------------


@router.delete("/{upload_id}")
async def tus_delete(
    upload_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Abort a TUS upload and cancel the MinIO multipart upload.

    The associated MediaFile is left in PENDING status (not deleted) because
    POST /files/prepare created it intentionally; the user may wish to re-upload.
    """
    session = _get_session(db, upload_id, int(current_user.id))

    if session.status == "active" and session.minio_upload_id:
        try:
            minio_service.abort_multipart_upload(session.storage_path, session.minio_upload_id)
        except Exception as e:
            logger.warning(f"Failed to abort MinIO upload for {upload_id}: {e}")

    session.status = "aborted"
    db.commit()

    logger.info(
        "TUS upload aborted",
        extra={
            "event": "tus_upload_aborted",
            "upload_id": str(upload_id),
            "reason": "client DELETE request",
        },
    )

    return Response(
        status_code=204,
        headers=_tus_headers(),
    )
