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
    Complete file upload processing pipeline.
    
    Args:
        file: Uploaded file
        db: Database session
        current_user: Current user
        
    Returns:
        Created MediaFile object with storage path updated
    """
    try:
        logger.info(f"File upload request received from user: {current_user.email}")
        
        # Validate file
        validate_file_type(file)
        logger.info(f"File details - filename: {file.filename}, content_type: {file.content_type}")
        
        # Read file content
        file_content = await file.read()
        file_size = len(file_content)
        
        # Create database record
        db_file = create_media_file_record(db, file, current_user, file_size)
        
        # Generate storage path
        storage_path = f"user_{current_user.id}/file_{db_file.id}/{file.filename}"
        
        # Upload to storage
        upload_file_to_storage(file_content, file_size, storage_path, file.content_type)
        
        # Update storage path in database
        db_file.storage_path = storage_path
        db.commit()
        db.refresh(db_file)
        
        # Start background transcription
        start_transcription_task(db_file.id)
        
        return db_file
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error processing file upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing file upload request"
        )