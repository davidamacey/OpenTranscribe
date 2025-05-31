import os
import io
import logging
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.media import MediaFile, FileStatus
from app.services.minio_service import upload_file
from app.tasks.transcription import transcribe_audio_task

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
            detail="No file was uploaded. Please select a file."
        )
    
    allowed_types = ["audio/", "video/"]
    if not any(file.content_type.startswith(t) for t in allowed_types):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an audio or video format"
        )


def create_media_file_record(db: Session, file: UploadFile, current_user: User, 
                           file_size: int) -> MediaFile:
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
        if not hasattr(FileStatus, 'PENDING'):
            raise ValueError("FileStatus enum is not properly defined or imported")
            
        logger.info(f"Creating MediaFile with filename={file.filename}, size={file_size}, type={file.content_type}")
        
        db_file = MediaFile(
            filename=file.filename,
            user_id=current_user.id,
            storage_path="",  # Will be updated after upload
            file_size=file_size,
            content_type=file.content_type,
            status=FileStatus.PENDING,
            is_public=False,
            duration=None,
            language=None,
            summary=None,
            translated_text=None
        )
        
        db.add(db_file)
        db.commit()
        db.refresh(db_file)
        
        return db_file
        
    except Exception as e:
        logger.error(f"Error creating MediaFile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating media file record: {str(e)}"
        )


def upload_file_to_storage(file_content: bytes, file_size: int, storage_path: str, 
                         content_type: str) -> None:
    """
    Upload file content to MinIO storage.
    
    Args:
        file_content: File content as bytes
        file_size: Size of the file
        storage_path: Storage path in MinIO
        content_type: MIME type of the file
    """
    if os.environ.get('SKIP_S3', 'False').lower() != 'true':
        upload_file(
            file_content=io.BytesIO(file_content),
            file_size=file_size,
            object_name=storage_path,
            content_type=content_type
        )
    else:
        logger.info("Skipping S3 upload in test environment")


def start_transcription_task(file_id: int) -> None:
    """
    Start the background transcription task.
    
    Args:
        file_id: ID of the media file to transcribe
    """
    if os.environ.get('SKIP_CELERY', 'False').lower() != 'true':
        transcribe_audio_task.delay(file_id)
    else:
        logger.info("Skipping Celery task in test environment")


async def process_file_upload(file: UploadFile, db: Session, current_user: User) -> MediaFile:
    """
    Complete file upload processing pipeline with chunked upload support for large files.
    
    Args:
        file: Uploaded file
        db: Database session
        current_user: Current user
        
    Returns:
        Created MediaFile object with storage path updated
        
    Raises:
        HTTPException: If there's an error during file processing
    """
    try:
        logger.info(f"File upload request received from user: {current_user.email}")
        
        # Validate file type first
        validate_file_type(file)
        logger.info(f"Processing file - filename: {file.filename}, content_type: {file.content_type}")
        
        # Get file size from content-length header if available
        file_size = 0
        try:
            file_size = int(file.headers.get('content-length', 0))
        except (ValueError, TypeError):
            # If we can't get size from headers, we'll calculate it while reading chunks
            pass
            
        # Create database record first to get file ID
        db_file = create_media_file_record(db, file, current_user, file_size)
        logger.info(f"Created file record with ID: {db_file.id}")
        
        # Generate storage path
        storage_path = f"user_{current_user.id}/file_{db_file.id}/{file.filename}"
        
        try:
            # Process file in chunks (10MB chunks by default)
            chunk_size = 10 * 1024 * 1024  # 10MB chunks
            file_content = bytearray()
            total_read = 0
            
            # Read file in chunks
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                file_content.extend(chunk)
                total_read += len(chunk)
                logger.debug(f"Read {total_read} bytes of {file.filename}")
            
            # Update file size with actual bytes read
            file_size = total_read
            
            # Upload to storage
            upload_file_to_storage(file_content, file_size, storage_path, file.content_type)
            
            # Update storage path and file size in database
            db_file.storage_path = storage_path
            db_file.file_size = file_size
            db.commit()
            db.refresh(db_file)
            
            # Start background transcription
            start_transcription_task(db_file.id)
            
            logger.info(f"Successfully processed file {file.filename} (ID: {db_file.id}), size: {file_size} bytes")
            return db_file
            
        except Exception as upload_error:
            # Clean up the database record if upload fails
            db.delete(db_file)
            db.commit()
            logger.error(f"Error during file upload: {str(upload_error)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error during file upload: {str(upload_error)}"
            )
            
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error processing file upload: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing file upload: {str(e)}"
        )