"""
URL processing endpoints for handling YouTube and other external video URLs.

This module provides API endpoints for processing external URLs, primarily YouTube videos,
by downloading and integrating them into the media processing pipeline.
"""
import logging

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from fastapi import status
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.models.user import User
from app.schemas.media import MediaFile as MediaFileSchema
from app.services.youtube_service import YouTubeService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/process-url", response_model=MediaFileSchema)
async def process_youtube_url(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Process a YouTube URL by downloading the video and adding it to the user's media library.

    Request body should contain:
    {
        "url": "https://www.youtube.com/watch?v=..."
    }

    Returns:
        MediaFile object representing the processed video

    Raises:
        HTTPException:
            - 400 if URL is missing or invalid
            - 401 if user is not authenticated
            - 500 for server errors during processing
    """
    try:
        # Parse request body
        body = await request.json()
        url = body.get('url')

        if not url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="URL is required"
            )

        # Process the YouTube URL using the service
        youtube_service = YouTubeService()
        media_file = await youtube_service.process_youtube_url(url, db, current_user)

        logger.info(f"Successfully processed YouTube URL for user {current_user.id}: {media_file.id}")
        return media_file

    except HTTPException:
        # Re-raise HTTP exceptions (validation errors, etc.)
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing YouTube URL: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error processing YouTube URL"
        )
