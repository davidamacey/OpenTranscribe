"""
Summary status endpoint for checking AI summary availability and status
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.models.user import User
from app.models.media import MediaFile
from app.services.llm_service import is_llm_available
from app.tasks.summary_retry import retry_summary_if_available

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{file_id}/summary-status")
async def get_summary_status(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get the summary status for a file and LLM availability
    
    Returns:
        - summary_status: 'pending', 'processing', 'completed', 'failed'
        - llm_available: whether LLM service is available
        - can_retry: whether a failed summary can be retried
        - summary_exists: whether a summary already exists
    """
    # Check if user has access to this file
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
    
    try:
        # Check LLM availability
        llm_available = await is_llm_available()
    except Exception as e:
        logger.warning(f"Failed to check LLM availability for file {file_id}: {e}")
        llm_available = False
    
    # Determine if retry is possible
    can_retry = (
        media_file.summary_status == 'failed' and 
        llm_available and 
        media_file.status == 'completed'  # Transcription must be complete
    )
    
    return {
        "file_id": file_id,
        "summary_status": media_file.summary_status or 'pending',
        "summary_exists": bool(media_file.summary or media_file.summary_opensearch_id),
        "llm_available": llm_available,
        "can_retry": can_retry,
        "transcription_status": media_file.status,
        "filename": media_file.filename
    }


@router.post("/{file_id}/retry-summary")
async def retry_summary(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retry failed summary generation for a file
    """
    # Check if user has access to this file
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
    
    # Check if retry is needed and possible
    if media_file.summary_status not in ['failed', 'pending']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot retry summary with status: {media_file.summary_status}"
        )
    
    if media_file.status != 'completed':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot generate summary until transcription is completed"
        )
    
    # Check LLM availability
    try:
        llm_available = await is_llm_available()
    except Exception as e:
        logger.error(f"Failed to check LLM availability for retry of file {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to verify LLM service availability. Please try again later."
        )
    
    if not llm_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service is not available. Please try again later."
        )
    
    # Attempt to retry
    success = retry_summary_if_available(db, file_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue summary retry"
        )
    
    logger.info(f"Summary retry queued for file {file_id} by user {current_user.email}")
    
    return {
        "status": "success",
        "message": "Summary generation has been queued",
        "file_id": file_id
    }