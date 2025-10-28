"""
URL processing endpoints for handling YouTube and other external video URLs.

This module provides API endpoints for processing external URLs, primarily YouTube videos,
by dispatching background tasks for non-blocking processing.
"""

import logging
import re
from typing import Union

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from pydantic import BaseModel
from pydantic import Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.models.user import User
from app.schemas.media import MediaFile as MediaFileSchema
from app.services.formatting_service import FormattingService
from app.services.youtube_service import YouTubeService
from app.tasks.youtube_processing import process_youtube_playlist_task
from app.tasks.youtube_processing import process_youtube_url_task

logger = logging.getLogger(__name__)

router = APIRouter()


# Request model for URL processing
class URLProcessingRequest(BaseModel):
    """Request model for processing YouTube URLs (videos or playlists)."""

    url: str = Field(
        description="YouTube video or playlist URL",
        examples=[
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube.com/playlist?list=PLClBBDzHMVijJfoN2EY_3OpmHfRIv4eGO",
        ],
        min_length=1,
    )


# Response models for URL processing
class PlaylistProcessingResponse(BaseModel):
    """Response model for YouTube playlist processing requests."""

    type: str = Field(
        default="playlist", description="Response type indicator", examples=["playlist"]
    )
    status: str = Field(
        default="processing",
        description="Processing status",
        examples=["processing", "completed", "error"],
    )
    message: str = Field(
        description="Human-readable status message",
        examples=["Playlist processing started. Videos will appear as they are extracted."],
    )
    url: str = Field(
        description="Original playlist URL",
        examples=["https://youtube.com/playlist?list=PLClBBDzHMVijJfoN2EY_3OpmHfRIv4eGO"],
    )


# Union type for endpoint response - can be either a MediaFile or PlaylistProcessingResponse
URLProcessingResponse = Union[MediaFileSchema, PlaylistProcessingResponse]


# YouTube URL validation and normalization
YOUTUBE_URL_PATTERN = re.compile(
    r"^https?://(www\.)?(youtube\.com/(watch\?v=|embed/|v/)|youtu\.be/)[\w\-_]+.*$"
)


def normalize_youtube_url(url: str) -> str:
    """Normalize YouTube URL to standard format for duplicate detection.

    Extracts the video ID or playlist ID from various YouTube URL formats and converts them
    to a canonical format for consistent duplicate detection and processing.

    Args:
        url: YouTube URL in any supported format (watch, embed, short, playlist, etc.).

    Returns:
        str: Normalized YouTube URL in standard format.
             Video format: "https://www.youtube.com/watch?v={video_id}"
             Playlist format: "https://www.youtube.com/playlist?list={playlist_id}"

    Example:
        >>> normalize_youtube_url("https://youtu.be/dQw4w9WgXcQ")
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        >>> normalize_youtube_url("https://youtube.com/playlist?list=PLxxx&si=yyy")
        "https://www.youtube.com/playlist?list=PLxxx"
    """
    url = url.strip()

    # Check if it's a playlist URL first
    playlist_match = re.search(r"[?&]list=([\w\-_]+)", url)
    if playlist_match and "youtube.com/playlist" in url:
        playlist_id = playlist_match.group(1)
        return f"https://www.youtube.com/playlist?list={playlist_id}"

    # Extract video ID from various YouTube URL formats
    video_id_patterns = [
        r"youtube\.com/watch\?v=([^&\n]+)",
        r"youtube\.com/embed/([^?\n]+)",
        r"youtube\.com/v/([^?\n]+)",
        r"youtu\.be/([^?\n]+)",
    ]

    for pattern in video_id_patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            return f"https://www.youtube.com/watch?v={video_id}"

    return url


@router.post("/process-url", response_model=URLProcessingResponse)
async def process_youtube_url(
    request_data: URLProcessingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> URLProcessingResponse:
    """
    Process a YouTube URL (video or playlist) by dispatching background tasks.

    Args:
        request_data: URLProcessingRequest containing the YouTube URL
        db: Database session
        current_user: Authenticated user

    Returns:
        Union[MediaFileSchema, PlaylistProcessingResponse]:
            - For single videos: MediaFile object with pending status
            - For playlists: PlaylistProcessingResponse with processing details

    Raises:
        HTTPException:
            - 400 if URL is missing or invalid
            - 409 if URL already exists for user (single videos only)
            - 401 if user is not authenticated
            - 500 for server errors

    Examples:
        Single video request:
            POST /process-url
            {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}

        Playlist request:
            POST /process-url
            {"url": "https://youtube.com/playlist?list=PLClBBDzHMVijJfoN2EY_3OpmHfRIv4eGO"}
    """
    try:
        url = request_data.url

        if not url:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL is required")

        # Normalize and validate URL
        normalized_url = normalize_youtube_url(url)
        youtube_service = YouTubeService()

        if not youtube_service.is_valid_youtube_url(normalized_url):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid YouTube URL"
            )

        # Check if URL is a playlist
        is_playlist = youtube_service.is_playlist_url(normalized_url)

        if is_playlist:
            # Handle playlist processing
            logger.info(f"Detected playlist URL: {normalized_url}")

            try:
                # Dispatch playlist processing task
                task_result = process_youtube_playlist_task.delay(
                    url=normalized_url, user_id=current_user.id
                )
                logger.info(
                    f"Dispatched YouTube playlist processing task {task_result.id} for user {current_user.id}"
                )

                # Return immediate response indicating playlist processing started
                return {
                    "type": "playlist",
                    "status": "processing",
                    "message": "Playlist processing started. Videos will appear as they are extracted.",
                    "url": normalized_url,
                }

            except Exception as e:
                logger.error(f"Failed to dispatch YouTube playlist processing task: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to start playlist processing. Please try again.",
                ) from e

        # Extract video ID for duplicate checking (fast operation)
        try:
            video_info = youtube_service.extract_video_info(normalized_url)
            youtube_id = video_info.get("id")
            video_title = video_info.get("title", "YouTube Video")
        except Exception as e:
            logger.error(f"Error extracting video info from {normalized_url}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to extract video information. Please check the URL.",
            ) from e

        if not youtube_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not extract YouTube video ID",
            )

        # Check for existing video with same YouTube ID (early duplicate detection)
        # Check both metadata_raw and source_url for comprehensive duplicate detection
        existing_video = (
            db.query(MediaFile)
            .filter(
                MediaFile.user_id == current_user.id,
                text("metadata_raw->>'youtube_id' = :youtube_id"),
            )
            .params(youtube_id=youtube_id)
            .first()
        )

        # Also check by source_url as a backup (in case metadata_raw is incomplete)
        if not existing_video:
            existing_video = (
                db.query(MediaFile)
                .filter(
                    MediaFile.user_id == current_user.id,
                    MediaFile.source_url == normalized_url,
                )
                .first()
            )

        if existing_video:
            logger.info(
                f"Found existing YouTube video with ID {youtube_id} for user {current_user.id}: "
                f"MediaFile ID {existing_video.id}, status: {existing_video.status}"
            )
            # Provide different messages based on video status
            if existing_video.status == FileStatus.ERROR:
                error_msg = existing_video.last_error_message or "processing failed"
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"This video already exists in your library but {error_msg}. "
                    f"Please delete it first if you want to re-process it.",
                )
            elif existing_video.status in [FileStatus.PENDING, FileStatus.PROCESSING]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"This YouTube video is already being processed: {existing_video.title or existing_video.filename}",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"This YouTube video already exists in your library: {existing_video.title or existing_video.filename}",
                )

        # Create placeholder MediaFile record for immediate response
        placeholder_metadata = {
            "youtube_id": youtube_id,
            "youtube_url": normalized_url,
            "title": video_title,
            "processing": True,
        }

        media_file = MediaFile(
            user_id=current_user.id,
            filename=video_title[:255],  # Temporary filename, will be updated by YouTube service
            storage_path="",  # Will be set by background task
            file_size=0,  # Will be set by background task
            content_type="video/mp4",  # Default, will be updated
            duration=video_info.get("duration"),
            status=FileStatus.PROCESSING,
            title=video_title,
            author=video_info.get("uploader"),
            description=video_info.get("description"),
            source_url=normalized_url,
            metadata_raw=placeholder_metadata,
            metadata_important=placeholder_metadata,
        )

        # Save placeholder record
        db.add(media_file)
        db.commit()
        db.refresh(media_file)

        # Dispatch background task immediately
        try:
            task_result = process_youtube_url_task.delay(
                url=normalized_url, user_id=current_user.id, file_uuid=str(media_file.uuid)
            )
            logger.info(
                f"Dispatched YouTube processing task {task_result.id} for MediaFile {media_file.id}"
            )
        except Exception as e:
            logger.error(f"Failed to dispatch YouTube processing task: {e}")
            # Clean up the placeholder record
            db.delete(media_file)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to start YouTube processing. Please try again.",
            ) from e

        # Send initial file creation notification for gallery (silent - no notification panel message)
        try:
            from app.api.websockets import send_notification

            await send_notification(
                user_id=current_user.id,
                notification_type="file_created",
                data={
                    "file_id": str(media_file.uuid),  # Use UUID
                    "file": {
                        "id": str(media_file.uuid),  # Use UUID for frontend
                        "filename": media_file.filename,
                        "status": media_file.status.value,
                        "display_status": FormattingService.format_status(media_file.status),
                        "content_type": media_file.content_type,
                        "file_size": media_file.file_size,
                        "title": media_file.title,
                        "author": media_file.author,
                        "duration": media_file.duration,
                        "upload_time": media_file.upload_time.isoformat()
                        if media_file.upload_time
                        else None,
                    },
                },
            )
        except Exception as e:
            logger.warning(f"Failed to send file_created notification: {e}")

        logger.info(f"Created placeholder MediaFile {media_file.id} for YouTube URL processing")
        return media_file

    except HTTPException:
        # Re-raise HTTP exceptions (validation errors, etc.)
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing YouTube URL: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error processing YouTube URL",
        ) from e
