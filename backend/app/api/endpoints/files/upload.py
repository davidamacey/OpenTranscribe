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


def start_transcription_task(file_id: int, file_uuid: str) -> None:
    """
    Start the background transcription and waveform generation tasks in parallel.

    Args:
        file_id: Database ID of the media file
        file_uuid: UUID of the media file to transcribe
    """
    if os.environ.get("SKIP_CELERY", "False").lower() != "true":
        # Launch GPU transcription task
        transcribe_audio_task.delay(file_uuid)
        # Launch CPU waveform generation task in parallel
        generate_waveform_task.delay(file_id=file_id, file_uuid=file_uuid)
        logger.info(
            f"Started parallel tasks for file {file_id}: transcription (GPU) and waveform (CPU)"
        )
    else:
        logger.info("Skipping Celery task in test environment")


async def process_file_upload(
    file: UploadFile,
    db: Session,
    current_user: User,
    existing_file_uuid: Optional[str] = None,
    client_file_hash: Optional[str] = None,
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

    Returns:
        Created MediaFile object with storage path updated

    Raises:
        HTTPException: If there's an error during file processing
    """
    try:
        logger.info(f"File upload request received from user: {current_user.email}")

        # Validate file type first
        validate_file_type(file)
        logger.info(
            f"Processing file - filename: {file.filename}, content_type: {file.content_type}"
        )

        # Get file size from content-length header if available
        file_size = 0
        with contextlib.suppress(ValueError, TypeError):
            file_size = int(file.headers.get("content-length", 0))

        # Check if we should use an existing file record (from prepare_upload)
        if existing_file_uuid:
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
                # Create a new file record if the existing one can't be found
                db_file = create_media_file_record(db, file, current_user, file_size)
            else:
                logger.info(f"Using existing file record with UUID={existing_file_uuid}")
                # Update the status to PENDING (in case it was in a different state)
                db_file.status = FileStatus.PENDING
                db.commit()
        else:
            # Create a new database record
            db_file = create_media_file_record(db, file, current_user, file_size)
            logger.info(f"Created new file record with ID: {db_file.id}")

        # Generate storage path with sanitized filename
        storage_path = get_safe_storage_filename(file.filename, current_user.id, db_file.id)
        temp_file_path: Optional[str] = None

        try:
            # Process file in chunks
            file_content = bytearray()
            total_read = 0

            # Read file in chunks
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                file_content.extend(chunk)
                total_read += len(chunk)
                # Removed debug log for performance

            # Update file size with actual bytes read
            file_size = total_read

            # Prioritize client-provided hash, then existing hash, then calculate as fallback
            if client_file_hash:
                # If client_file_hash starts with 0x, remove it for database consistency
                if client_file_hash.startswith("0x"):
                    client_file_hash = client_file_hash[2:]
                db_file.file_hash = client_file_hash
            elif not db_file.file_hash:
                # No file hash provided - this shouldn't happen with the updated frontend
                logger.warning(
                    f"No file hash provided for {file.filename} - duplicate detection may not work"
                )

            # Upload to storage
            upload_file_to_storage(file_content, file_size, storage_path, file.content_type)

            # For video files, generate and upload a thumbnail
            thumbnail_path = None
            if file.content_type.startswith("video/"):
                try:
                    # We need to save the video temporarily to generate thumbnail
                    import tempfile

                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=os.path.splitext(file.filename)[1]
                    ) as temp_video:
                        temp_video.write(file_content)
                        temp_file_path = temp_video.name

                    # Generate and upload thumbnail
                    thumbnail_path = await generate_and_upload_thumbnail(
                        user_id=current_user.id,
                        media_file_id=db_file.id,
                        video_path=temp_file_path,
                    )

                    if thumbnail_path:
                        logger.info(
                            f"Generated thumbnail for video: {file.filename}, path: {thumbnail_path}"
                        )
                        db_file.thumbnail_path = thumbnail_path
                    else:
                        logger.warning(f"Failed to generate thumbnail for video: {file.filename}")
                finally:
                    # Clean up temporary file
                    if temp_file_path and os.path.exists(temp_file_path):
                        try:
                            os.unlink(temp_file_path)
                            # Removed debug log
                        except Exception as e:
                            logger.warning(
                                f"Failed to remove temporary file {temp_file_path}: {str(e)}"
                            )

            # Update storage path, file size, and thumbnail path in database
            db_file.storage_path = storage_path
            db_file.file_size = file_size
            db.commit()
            db.refresh(db_file)

            # Start background transcription and waveform generation in parallel
            start_transcription_task(db_file.id, str(db_file.uuid))

            logger.info(f"File processed: {file.filename} (ID: {db_file.id})")
            return db_file

        except Exception as upload_error:
            # Clean up the database record if upload fails
            db.delete(db_file)
            db.commit()
            logger.error(f"Upload failed: {str(upload_error)}")

            # Clean up temporary file if it exists
            if temp_file_path and os.path.exists(temp_file_path):
                with contextlib.suppress(Exception):
                    os.unlink(temp_file_path)

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error during file upload: {str(upload_error)}",
            ) from upload_error

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"File upload processing error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing file upload: {str(e)}",
        ) from e
