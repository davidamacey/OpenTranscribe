import logging
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.media import MediaFile, FileStatus
from app.tasks.transcription import transcribe_audio_task

logger = logging.getLogger(__name__)


def clear_existing_transcription_data(db: Session, media_file: MediaFile) -> None:
    """
    Clear existing transcription data for reprocessing.
    
    Args:
        db: Database session
        media_file: MediaFile to clear data for
    """
    try:
        # Clear transcript-related fields that exist on the MediaFile model
        media_file.summary = None
        media_file.translated_text = None
        
        # Clear existing transcript segments 
        from app.models.media import TranscriptSegment, Speaker, Analytics
        
        # Delete existing transcript segments (this will cascade and handle relationships)
        existing_segments = db.query(TranscriptSegment).filter(TranscriptSegment.media_file_id == media_file.id).all()
        for segment in existing_segments:
            db.delete(segment)
        
        # Clear any existing speaker data
        existing_speakers = db.query(Speaker).filter(Speaker.media_file_id == media_file.id).all()
        for speaker in existing_speakers:
            db.delete(speaker)
            
        # Clear any existing analytics data
        existing_analytics = db.query(Analytics).filter(Analytics.media_file_id == media_file.id).first()
        if existing_analytics:
            db.delete(existing_analytics)
        
        db.commit()
        logger.info(f"Cleared existing transcription data for file {media_file.id}")
        
    except Exception as e:
        logger.error(f"Error clearing transcription data for file {media_file.id}: {e}")
        db.rollback()
        raise


def start_reprocessing_task(file_id: int) -> None:
    """
    Start the background reprocessing task.
    
    Args:
        file_id: ID of the media file to reprocess
    """
    import os
    
    if os.environ.get('SKIP_CELERY', 'False').lower() != 'true':
        # Use the same transcription task - it will handle reprocessing
        transcribe_audio_task.delay(file_id)
    else:
        logger.info("Skipping Celery task in test environment")


async def process_file_reprocess(file_id: int, db: Session, current_user: User) -> MediaFile:
    """
    Process file reprocessing request.
    
    Args:
        file_id: ID of the file to reprocess
        db: Database session
        current_user: Current user
        
    Returns:
        Updated MediaFile object
        
    Raises:
        HTTPException: If file not found or user doesn't have permission
    """
    try:
        # Get the file
        media_file = db.query(MediaFile).filter(
            MediaFile.id == file_id,
            MediaFile.user_id == current_user.id
        ).first()
        
        if not media_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found or you don't have permission to access it"
            )
        
        # Check if file is in a state that can be reprocessed
        if media_file.status == FileStatus.PROCESSING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is currently being processed. Please wait for it to complete."
            )
        
        # Check if file exists in storage
        if not media_file.storage_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File storage path not found. Cannot reprocess."
            )
        
        logger.info(f"Starting reprocessing for file {file_id} by user {current_user.email}")
        
        # Clear existing transcription data
        clear_existing_transcription_data(db, media_file)
        
        # Reset file status to pending
        media_file.status = FileStatus.PENDING
        
        db.commit()
        db.refresh(media_file)
        
        # Start background reprocessing task
        start_reprocessing_task(media_file.id)
        
        logger.info(f"Reprocessing task started for file {file_id}")
        
        return media_file
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error processing reprocess request for file {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing reprocess request"
        )