import contextlib
import io
import logging
import os
from typing import Optional

from fastapi import HTTPException
from fastapi import UploadFile
from fastapi import status
from sqlalchemy.orm import Session

from app.core.constants import UPLOAD_CHUNK_SIZE
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.models.user import User
from app.services.minio_service import upload_file
from app.tasks.transcription import transcribe_audio_task
from app.tasks.waveform import generate_waveform_task
from app.utils.filename import get_safe_storage_filename
from app.utils.filename import sanitize_filename
from app.utils.thumbnail import generate_and_upload_thumbnail

logger = logging.getLogger(__name__)


def validate_file_type(file: UploadFile) -> None:
    """
    Validate that the uploaded file is an audio or video format.

    Args:
        file: The uploaded file

    Raises:
        HTTPException: If file type is not allowed
    """
    if not file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file was uploaded. Please select a file.",
        )

    allowed_types = ["audio/", "video/"]
    if not any(file.content_type.startswith(t) for t in allowed_types):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an audio or video format",
        )


def create_media_file_record(
    db: Session, file: UploadFile, current_user: User, file_size: int
) -> MediaFile:
    """
    Create a MediaFile database record.

    Args:
        db: Database session
        file: Uploaded file
        current_user: Current user
        file_size: Size of the file in bytes

    Returns:
        Created MediaFile object
    """
    try:
        if not hasattr(FileStatus, "PENDING"):
            raise ValueError("FileStatus enum is not properly defined or imported")

        # Check if file has file_hash attribute (from FileMetadata object)
        file_hash = getattr(file, "file_hash", None)

        # Create MediaFile record with essential metadata
        # Sanitize filename to prevent issues with special characters
        sanitized_filename = sanitize_filename(file.filename)

        db_file = MediaFile(
            filename=sanitized_filename,
            user_id=current_user.id,
            storage_path="",  # Will be updated after upload
            file_size=file_size,
            content_type=file.content_type,
            status=FileStatus.PENDING,
            is_public=False,
            duration=None,
            language=None,
            summary_data=None,
            translated_text=None,
            file_hash=file_hash,
            thumbnail_path=None,
        )

        db.add(db_file)
        db.commit()
        db.refresh(db_file)

        return db_file

    except Exception as e:
        logger.error(f"Error creating MediaFile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating media file record: {str(e)}",
        ) from e


def upload_file_to_storage(
    file_content: bytes, file_size: int, storage_path: str, content_type: str
) -> None:
    """
    Upload file content to MinIO storage.

    Args:
        file_content: File content as bytes
        file_size: Size of the file
        storage_path: Storage path in MinIO
        content_type: MIME type of the file
    """
    if os.environ.get("SKIP_S3", "False").lower() != "true":
        upload_file(
            file_content=io.BytesIO(file_content),
            file_size=file_size,
            object_name=storage_path,
            content_type=content_type,
        )
    else:
        logger.info("Skipping S3 upload in test environment")


def start_transcription_task(
    file_id: int,
    file_uuid: str,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
    num_speakers: Optional[int] = None,
) -> None:
    """
    Start the background transcription and waveform generation tasks in parallel.

    Args:
        file_id: Database ID of the media file
        file_uuid: UUID of the media file to transcribe
        min_speakers: Optional minimum number of speakers for diarization
        max_speakers: Optional maximum number of speakers for diarization
        num_speakers: Optional fixed number of speakers for diarization
    """
    if os.environ.get("SKIP_CELERY", "False").lower() != "true":
        # Launch GPU transcription task with speaker parameters
        transcribe_audio_task.delay(
            file_uuid,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            num_speakers=num_speakers,
        )
        # Launch CPU waveform generation task in parallel
        generate_waveform_task.delay(file_id=file_id, file_uuid=file_uuid)
        logger.info(
            f"Started parallel tasks for file {file_id}: transcription (GPU) and waveform (CPU)"
        )
    else:
        logger.info("Skipping Celery task in test environment")


def _get_or_create_file_record(
    db: Session,
    file: UploadFile,
    current_user: User,
    file_size: int,
    existing_file_uuid: Optional[str],
) -> MediaFile:
    """
    Get an existing file record or create a new one.

    Args:
        db: Database session
        file: Uploaded file
        current_user: Current user
        file_size: Size of the file in bytes
        existing_file_uuid: Optional UUID of existing file record

    Returns:
        MediaFile database record
    """
    if not existing_file_uuid:
        db_file = create_media_file_record(db, file, current_user, file_size)
        logger.info(f"Created new file record with ID: {db_file.id}")
        return db_file

    # Look up file by UUID
    db_file = (
        db.query(MediaFile)
        .filter(
            MediaFile.uuid == existing_file_uuid,
            MediaFile.user_id == current_user.id,
        )
        .first()
    )

    if not db_file:
        logger.warning(
            f"Existing file UUID {existing_file_uuid} not found for user {current_user.id}"
        )
        return create_media_file_record(db, file, current_user, file_size)

    logger.info(f"Using existing file record with UUID={existing_file_uuid}")
    db_file.status = FileStatus.PENDING
    db.commit()
    return db_file


async def _read_file_content(file: UploadFile) -> tuple[bytearray, int]:
    """
    Read file content in chunks.

    Args:
        file: Uploaded file

    Returns:
        Tuple of (file_content, total_size)
    """
    file_content = bytearray()
    total_read = 0

    while True:
        chunk = await file.read(UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        file_content.extend(chunk)
        total_read += len(chunk)

    return file_content, total_read


def _update_file_hash(db_file: MediaFile, client_file_hash: Optional[str], filename: str) -> None:
    """
    Update file hash on the database record.

    Args:
        db_file: MediaFile database record
        client_file_hash: Optional file hash from client
        filename: Original filename for logging
    """
    if client_file_hash:
        # Remove 0x prefix if present for database consistency
        if client_file_hash.startswith("0x"):
            client_file_hash = client_file_hash[2:]
        db_file.file_hash = client_file_hash
    elif not db_file.file_hash:
        logger.warning(f"No file hash provided for {filename} - duplicate detection may not work")


def _cleanup_temp_file(temp_file_path: Optional[str]) -> None:
    """
    Clean up a temporary file if it exists.

    Args:
        temp_file_path: Path to temporary file
    """
    if temp_file_path and os.path.exists(temp_file_path):
        with contextlib.suppress(Exception):
            os.unlink(temp_file_path)


async def _generate_video_thumbnail(
    file_content: bytearray,
    filename: str,
    current_user: User,
    db_file: MediaFile,
) -> tuple[Optional[str], Optional[str]]:
    """
    Generate and upload a thumbnail for video files.

    Args:
        file_content: Video file content
        filename: Original filename
        current_user: Current user
        db_file: MediaFile database record

    Returns:
        Tuple of (thumbnail_path, temp_file_path)
    """
    import tempfile

    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(filename)[1]
        ) as temp_video:
            temp_video.write(file_content)
            temp_file_path = temp_video.name

        thumbnail_path = await generate_and_upload_thumbnail(
            user_id=current_user.id,
            media_file_id=db_file.id,
            video_path=temp_file_path,
        )

        if thumbnail_path:
            logger.info(f"Generated thumbnail for video: {filename}, path: {thumbnail_path}")
        else:
            logger.warning(f"Failed to generate thumbnail for video: {filename}")

        return thumbnail_path, temp_file_path
    except Exception as e:
        logger.warning(f"Error generating thumbnail for {filename}: {e}")
        return None, temp_file_path


async def process_file_upload(
    file: UploadFile,
    db: Session,
    current_user: User,
    existing_file_uuid: Optional[str] = None,
    client_file_hash: Optional[str] = None,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
    num_speakers: Optional[int] = None,
) -> MediaFile:
    """
    Complete file upload processing pipeline with chunked upload support for large files.
    Includes file hash calculation for duplicate detection and thumbnail generation for video files.

    Args:
        file: Uploaded file
        db: Database session
        current_user: Current user
        existing_file_uuid: Optional UUID of existing file record from prepare_upload
        client_file_hash: Optional file hash calculated by the client (preferred method)
        min_speakers: Optional minimum number of speakers for diarization
        max_speakers: Optional maximum number of speakers for diarization
        num_speakers: Optional fixed number of speakers for diarization

    Returns:
        Created MediaFile object with storage path updated

    Raises:
        HTTPException: If there's an error during file processing
    """
    logger.info(f"File upload request received from user: {current_user.email}")

    # Validate file type first
    validate_file_type(file)
    logger.info(f"Processing file - filename: {file.filename}, content_type: {file.content_type}")

    # Get file size from content-length header if available
    file_size = 0
    with contextlib.suppress(ValueError, TypeError):
        file_size = int(file.headers.get("content-length", 0))

    # Get or create file record
    db_file = _get_or_create_file_record(db, file, current_user, file_size, existing_file_uuid)

    # Generate storage path with sanitized filename
    storage_path = get_safe_storage_filename(file.filename, current_user.id, db_file.id)
    temp_file_path: Optional[str] = None

    try:
        # Read file content in chunks
        file_content, file_size = await _read_file_content(file)

        # Update file hash
        _update_file_hash(db_file, client_file_hash, file.filename)

        # Upload to storage
        upload_file_to_storage(file_content, file_size, storage_path, file.content_type)

        # For video files, generate and upload a thumbnail
        if file.content_type.startswith("video/"):
            thumbnail_path, temp_file_path = await _generate_video_thumbnail(
                file_content, file.filename, current_user, db_file
            )
            if thumbnail_path:
                db_file.thumbnail_path = thumbnail_path
            _cleanup_temp_file(temp_file_path)

        # Update storage path, file size, and thumbnail path in database
        db_file.storage_path = storage_path
        db_file.file_size = file_size
        db.commit()
        db.refresh(db_file)

        # Start background transcription and waveform generation in parallel
        start_transcription_task(
            db_file.id, str(db_file.uuid), min_speakers, max_speakers, num_speakers
        )

        logger.info(f"File processed: {file.filename} (ID: {db_file.id})")
        return db_file

    except HTTPException:
        # Re-raise HTTP exceptions after cleanup
        db.delete(db_file)
        db.commit()
        _cleanup_temp_file(temp_file_path)
        raise
    except Exception as e:
        # Clean up on failure
        db.delete(db_file)
        db.commit()
        _cleanup_temp_file(temp_file_path)
        logger.error(f"Upload failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during file upload: {str(e)}",
        ) from e
