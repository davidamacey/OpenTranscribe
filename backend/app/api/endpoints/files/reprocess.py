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
        media_file.summary_opensearch_id = None  # Clear OpenSearch summary ID for regeneration
        media_file.summary_status = 'pending'  # Reset summary status for regeneration
        media_file.translated_text = None
        media_file.waveform_data = None  # Clear waveform data for regeneration
        
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
    Process file reprocessing request with enhanced error handling.
    
    Args:
        file_id: ID of the file to reprocess
        db: Database session
        current_user: Current user
        
    Returns:
        Updated MediaFile object
        
    Raises:
        HTTPException: If file not found or user doesn't have permission
    """
    from app.utils.task_utils import reset_file_for_retry, cancel_active_task
    
    try:
        # Get the file (allow admin to reprocess any file)
        is_admin = current_user.role == "admin"
        query = db.query(MediaFile).filter(MediaFile.id == file_id)
        if not is_admin:
            query = query.filter(MediaFile.user_id == current_user.id)
        
        media_file = query.first()
        
        if not media_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found or you don't have permission to access it"
            )
        
        # Check if file is currently processing
        if media_file.status == FileStatus.PROCESSING and media_file.active_task_id:
            # Cancel active task first
            logger.info(f"Cancelling active task {media_file.active_task_id} before reprocessing file {file_id}")
            cancel_active_task(db, file_id)
        
        # Check if file exists in storage
        if not media_file.storage_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File storage path not found. Cannot reprocess."
            )
        
        # Check retry limits (unless admin)
        if not is_admin and media_file.retry_count >= media_file.max_retries:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File has reached maximum retry attempts ({media_file.max_retries}). Contact admin for help."
            )
        
        logger.info(f"Starting reprocessing for file {file_id} by user {current_user.email}")
        
        # Use the enhanced retry logic
        success = reset_file_for_retry(db, file_id, reset_retry_count=False)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reset file for reprocessing"
            )
        
        # Refresh the file object
        db.refresh(media_file)
        
        # Start background reprocessing task
        start_reprocessing_task(media_file.id)
        
        logger.info(f"Reprocessing task started for file {file_id} (attempt {media_file.retry_count})")
        
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