"""
API endpoints for AI tag and collection suggestions

Simplified endpoints for:
- Getting AI suggestions for a media file
- Extracting/regenerating suggestions
- Applying approved suggestions
- Batch extraction
"""

import logging

from fastapi import APIRouter
from fastapi import Body
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.models.topic import TopicSuggestion
from app.models.user import User
from app.schemas.topic import ApplyTopicSuggestionsRequest
from app.schemas.topic import ExtractTopicsRequest
from app.schemas.topic import SuggestedCollection
from app.schemas.topic import SuggestedTag
from app.schemas.topic import TopicSuggestionResponse
from app.services.topic_extraction_service import TopicExtractionService
from app.tasks.topic_extraction import extract_topics_task
from app.utils.uuid_helpers import get_file_by_uuid_with_permission

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{file_uuid}/suggestions", response_model=TopicSuggestionResponse)
async def get_topic_suggestions(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get AI tag and collection suggestions for a media file

    Args:
        file_uuid: Media file UUID
        db: Database session
        current_user: Authenticated user

    Returns:
        Tag and collection suggestions from AI
    """
    # Get file and verify permission
    media_file = get_file_by_uuid_with_permission(db, file_uuid, current_user.id)
    file_id = media_file.id

    # Get suggestion from PostgreSQL
    suggestion = db.query(TopicSuggestion).filter(TopicSuggestion.media_file_id == file_id).first()

    if not suggestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No AI suggestions found for file {file_uuid}. Run extraction first.",
        )

    # Convert JSONB to Pydantic models
    suggested_tags = [SuggestedTag(**tag) for tag in (suggestion.suggested_tags or [])]
    suggested_collections = [
        SuggestedCollection(**coll) for coll in (suggestion.suggested_collections or [])
    ]

    # Build response
    return TopicSuggestionResponse(
        uuid=suggestion.uuid,
        media_file_id=media_file.uuid,
        user_id=current_user.uuid,
        suggested_tags=suggested_tags,
        suggested_collections=suggested_collections,
        status=suggestion.status,
        created_at=suggestion.created_at,
    )


@router.post("/{file_uuid}/extract", status_code=status.HTTP_202_ACCEPTED)
async def extract_topics(
    file_uuid: str,
    request_data: ExtractTopicsRequest = Body(default=ExtractTopicsRequest()),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Extract AI suggestions from a transcript (or regenerate existing)

    This endpoint triggers the Celery task for extraction.
    Results will be delivered via WebSocket notification.

    Args:
        file_uuid: Media file UUID
        request_data: Extraction request parameters
        db: Database session
        current_user: Authenticated user

    Returns:
        Acknowledgment that extraction has been triggered
    """
    # Get file and verify permission
    media_file = get_file_by_uuid_with_permission(db, file_uuid, current_user.id)

    # Check if file has transcript
    if not media_file.transcript_segments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File has no transcript. Complete transcription first.",
        )

    # Check if LLM is configured
    extraction_service = TopicExtractionService.create_from_settings(user_id=current_user.id, db=db)

    if not extraction_service:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LLM provider not configured. Configure LLM settings first.",
        )

    # Check if suggestion already exists
    existing = (
        db.query(TopicSuggestion).filter(TopicSuggestion.media_file_id == media_file.id).first()
    )

    if existing and not request_data.force_regenerate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI suggestions already exist. Use force_regenerate=true to re-extract.",
        )

    # Trigger Celery task
    task = extract_topics_task.delay(
        file_uuid=file_uuid,
        force_regenerate=request_data.force_regenerate,
    )

    logger.info(f"Triggered AI suggestion extraction for file {file_uuid}, task_id: {task.id}")

    return {
        "message": "AI suggestion extraction started",
        "task_id": task.id,
        "file_uuid": file_uuid,
    }


@router.post("/{file_uuid}/apply", response_model=dict)
async def apply_topic_suggestions(
    file_uuid: str,
    request_data: ApplyTopicSuggestionsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Apply user-approved AI suggestions

    This endpoint tracks what the user has accepted for analytics.
    The actual tag/collection creation happens in the frontend.

    Args:
        file_uuid: Media file UUID
        request_data: User's acceptance decisions
        db: Database session
        current_user: Authenticated user

    Returns:
        Summary of actions taken
    """
    # Get file and verify permission
    media_file = get_file_by_uuid_with_permission(db, file_uuid, current_user.id)
    file_id = media_file.id

    # Get suggestion
    suggestion = db.query(TopicSuggestion).filter(TopicSuggestion.media_file_id == file_id).first()

    if not suggestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No AI suggestions found for file {file_uuid}",
        )

    # Track user decisions
    extraction_service = TopicExtractionService(db)
    success = extraction_service.apply_suggestions(
        suggestion_id=suggestion.id,
        accepted_collections=request_data.accepted_collections,
        accepted_tags=request_data.accepted_tags,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to track suggestions",
        )

    return {
        "message": "Suggestions tracked successfully",
        "collections_added": len(request_data.accepted_collections),
        "tags_added": len(request_data.accepted_tags),
    }


@router.delete("/{file_uuid}/suggestions", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_topic_suggestions(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Dismiss/reject AI suggestions

    Updates suggestion status to 'rejected' but keeps the data for
    future analysis and improvement.

    Args:
        file_uuid: Media file UUID
        db: Database session
        current_user: Authenticated user
    """
    # Get file and verify permission
    media_file = get_file_by_uuid_with_permission(db, file_uuid, current_user.id)
    file_id = media_file.id

    # Get suggestion
    suggestion = db.query(TopicSuggestion).filter(TopicSuggestion.media_file_id == file_id).first()

    if not suggestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No AI suggestions found for file {file_uuid}",
        )

    # Update status
    suggestion.status = "rejected"
    suggestion.user_decisions = {"rejected": True}
    db.commit()

    logger.info(f"Dismissed AI suggestions for file {file_uuid}")


@router.post("/batch-extract", status_code=status.HTTP_202_ACCEPTED)
async def batch_extract_topics(
    file_uuids: list[str] = Body(..., embed=True),
    force_regenerate: bool = Body(False, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Extract AI suggestions for multiple files in batch

    Args:
        file_uuids: List of file UUIDs to process
        force_regenerate: Force re-extraction for all files
        db: Database session
        current_user: Authenticated user

    Returns:
        Acknowledgment that batch processing has been triggered
    """
    # Verify all files exist and belong to user
    verified_uuids = []
    for file_uuid in file_uuids:
        try:
            media_file = get_file_by_uuid_with_permission(db, file_uuid, current_user.id)
            if media_file.transcript_segments:
                verified_uuids.append(file_uuid)
            else:
                logger.warning(f"Skipping file {file_uuid} - no transcript available")
        except HTTPException as e:
            logger.warning(f"Skipping file {file_uuid} - {e.detail}")

    if not verified_uuids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid files found for processing",
        )

    # Check if LLM is configured
    extraction_service = TopicExtractionService.create_from_settings(user_id=current_user.id, db=db)

    if not extraction_service:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LLM provider not configured. Configure LLM settings first.",
        )

    # Trigger batch task
    from app.tasks.topic_extraction import batch_extract_topics_task

    task = batch_extract_topics_task.delay(
        file_uuids=verified_uuids,
        force_regenerate=force_regenerate,
    )

    logger.info(
        f"Triggered batch AI suggestion extraction for {len(verified_uuids)} files, task_id: {task.id}"
    )

    return {
        "message": "Batch AI suggestion extraction started",
        "task_id": task.id,
        "file_count": len(verified_uuids),
        "files": verified_uuids,
    }
