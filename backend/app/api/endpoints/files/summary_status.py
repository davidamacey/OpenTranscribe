"""
Summary status endpoint for checking AI summary availability and status
"""

import logging

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.models.user import User
from app.services.llm_service import is_llm_available
from app.tasks.summary_retry import retry_summary_if_available

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{file_uuid}/summary-status")
async def get_summary_status(
    file_uuid: str,  # Changed from int to str for UUID
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get the summary status for a file and LLM availability

    Returns:
        - summary_status: 'pending', 'processing', 'completed', 'failed'
        - llm_available: whether LLM service is available
        - can_retry: whether a failed summary can be retried
        - summary_exists: whether a summary already exists
    """
    # Get file by UUID
    from app.utils.uuid_helpers import get_file_by_uuid_with_permission

    media_file = get_file_by_uuid_with_permission(db, file_uuid, current_user.id)
    file_id = media_file.id

    try:
        # Check LLM availability for current user
        llm_available = await is_llm_available(user_id=current_user.id)
    except Exception as e:
        logger.warning(f"Failed to check LLM availability for file {file_id}: {e}")
        llm_available = False

    # Determine if retry is possible
    can_retry = (
        media_file.summary_status == "failed"
        and llm_available
        and media_file.status == "completed"  # Transcription must be complete
    )

    return {
        "file_id": str(media_file.uuid),  # Use UUID for frontend
        "summary_status": media_file.summary_status or "pending",
        "summary_exists": bool(media_file.summary_data or media_file.summary_opensearch_id),
        "llm_available": llm_available,
        "can_retry": can_retry,
        "transcription_status": media_file.status,
        "filename": media_file.filename,
    }


@router.post("/{file_uuid}/retry-summary")
async def retry_summary(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Retry failed summary generation for a file
    """
    # Get file by UUID with permission check
    from app.utils.uuid_helpers import get_file_by_uuid_with_permission

    media_file = get_file_by_uuid_with_permission(db, file_uuid, current_user.id)
    file_id = media_file.id

    # Check if retry is needed and possible
    if media_file.summary_status not in ["failed", "pending"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot retry summary with status: {media_file.summary_status}",
        )

    if media_file.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot generate summary until transcription is completed",
        )

    # Check LLM availability for current user
    try:
        llm_available = await is_llm_available(user_id=current_user.id)
    except Exception as e:
        logger.error(f"Failed to check LLM availability for retry of file {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to verify LLM service availability. Please try again later.",
        ) from e

    if not llm_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service is not available. Please try again later.",
        )

    # Attempt to retry
    success = retry_summary_if_available(db, file_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue summary retry",
        )

    logger.info(f"Summary retry queued for file {file_id} by user {current_user.email}")

    return {
        "status": "success",
        "message": "Summary generation has been queued",
        "file_id": str(media_file.uuid),  # Use UUID for frontend
    }
