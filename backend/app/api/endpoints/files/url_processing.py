"""
URL processing endpoints for handling YouTube and other external video URLs.

This module provides API endpoints for processing external URLs, primarily YouTube videos,
by dispatching background tasks for non-blocking processing.
"""

import logging
import re
from typing import Any
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


def _validate_youtube_url(url: str) -> tuple[str, YouTubeService]:
    """Validate and normalize a YouTube URL.

    Args:
        url: Raw YouTube URL from the request.

    Returns:
        Tuple of (normalized_url, youtube_service).

    Raises:
        HTTPException: If URL is missing or invalid.
    """
    if not url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL is required")

    normalized_url = normalize_youtube_url(url)
    youtube_service = YouTubeService()

    if not youtube_service.is_valid_youtube_url(normalized_url):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid YouTube URL")

    return normalized_url, youtube_service


def _handle_playlist_processing(normalized_url: str, user_id: int) -> PlaylistProcessingResponse:
    """Handle playlist URL processing by dispatching a background task.

    Args:
        normalized_url: Normalized YouTube playlist URL.
        user_id: ID of the user requesting processing.

    Returns:
        PlaylistProcessingResponse with processing status.

    Raises:
        HTTPException: If task dispatch fails.
    """
    logger.info(f"Detected playlist URL: {normalized_url}")

    try:
        task_result = process_youtube_playlist_task.delay(url=normalized_url, user_id=user_id)
        logger.info(
            f"Dispatched YouTube playlist processing task {task_result.id} for user {user_id}"
        )

        return PlaylistProcessingResponse(
            type="playlist",
            status="processing",
            message="Playlist processing started. Videos will appear as they are extracted.",
            url=normalized_url,
        )

    except Exception as e:
        logger.error(f"Failed to dispatch YouTube playlist processing task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start playlist processing. Please try again.",
        ) from e


def _extract_video_info(
    youtube_service: YouTubeService, normalized_url: str
) -> tuple[str, str, dict[str, Any]]:
    """Extract video ID and title from a YouTube URL.

    Args:
        youtube_service: YouTubeService instance.
        normalized_url: Normalized YouTube video URL.

    Returns:
        Tuple of (youtube_id, video_title, video_info).

    Raises:
        HTTPException: If video info extraction fails.
    """
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

    return youtube_id, video_title, video_info


def _check_duplicate_video(db: Session, user_id: int, youtube_id: str, normalized_url: str) -> None:
    """Check if the video already exists for this user.

    Args:
        db: Database session.
        user_id: User ID to check against.
        youtube_id: YouTube video ID.
        normalized_url: Normalized YouTube URL.

    Raises:
        HTTPException: If a duplicate video is found (409 Conflict).
    """
    # Check by metadata_raw first
    existing_video = (
        db.query(MediaFile)
        .filter(
            MediaFile.user_id == user_id,
            text("metadata_raw->>'youtube_id' = :youtube_id"),
        )
        .params(youtube_id=youtube_id)
        .first()
    )

    # Also check by source_url as a backup
    if not existing_video:
        existing_video = (
            db.query(MediaFile)
            .filter(
                MediaFile.user_id == user_id,
                MediaFile.source_url == normalized_url,
            )
            .first()
        )

    if not existing_video:
        return

    logger.info(
        f"Found existing YouTube video with ID {youtube_id} for user {user_id}: "
        f"MediaFile ID {existing_video.id}, status: {existing_video.status}"
    )

    _raise_duplicate_error(existing_video)


def _raise_duplicate_error(existing_video: MediaFile) -> None:
    """Raise appropriate HTTPException for a duplicate video.

    Args:
        existing_video: The existing MediaFile record.

    Raises:
        HTTPException: 409 Conflict with status-specific message.
    """
    if existing_video.status == FileStatus.ERROR:
        error_msg = existing_video.last_error_message or "processing failed"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This video already exists in your library but {error_msg}. "
            f"Please delete it first if you want to re-process it.",
        )

    if existing_video.status in [FileStatus.PENDING, FileStatus.PROCESSING]:
        video_name = existing_video.title or existing_video.filename
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This YouTube video is already being processed: {video_name}",
        )

    video_name = existing_video.title or existing_video.filename
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"This YouTube video already exists in your library: {video_name}",
    )


def _create_media_file_record(
    db: Session,
    user_id: int,
    normalized_url: str,
    youtube_id: str,
    video_title: str,
    video_info: dict[str, Any],
) -> MediaFile:
    """Create a placeholder MediaFile record for the YouTube video.

    Args:
        db: Database session.
        user_id: User ID.
        normalized_url: Normalized YouTube URL.
        youtube_id: YouTube video ID.
        video_title: Video title.
        video_info: Full video info dict from YouTube.

    Returns:
        Created MediaFile instance.
    """
    placeholder_metadata = {
        "youtube_id": youtube_id,
        "youtube_url": normalized_url,
        "title": video_title,
        "processing": True,
    }

    media_file = MediaFile(
        user_id=user_id,
        filename=video_title[:255],
        storage_path="",
        file_size=0,
        content_type="video/mp4",
        duration=video_info.get("duration"),
        status=FileStatus.PROCESSING,
        title=video_title,
        author=video_info.get("uploader"),
        description=video_info.get("description"),
        source_url=normalized_url,
        metadata_raw=placeholder_metadata,
        metadata_important=placeholder_metadata,
    )

    db.add(media_file)
    db.commit()
    db.refresh(media_file)

    return media_file


def _dispatch_video_task(
    db: Session, media_file: MediaFile, normalized_url: str, user_id: int
) -> None:
    """Dispatch the YouTube video processing background task.

    Args:
        db: Database session.
        media_file: MediaFile record to process.
        normalized_url: Normalized YouTube URL.
        user_id: User ID.

    Raises:
        HTTPException: If task dispatch fails.
    """
    try:
        task_result = process_youtube_url_task.delay(
            url=normalized_url, user_id=user_id, file_uuid=str(media_file.uuid)
        )
        logger.info(
            f"Dispatched YouTube processing task {task_result.id} for MediaFile {media_file.id}"
        )
    except Exception as e:
        logger.error(f"Failed to dispatch YouTube processing task: {e}")
        db.delete(media_file)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start YouTube processing. Please try again.",
        ) from e


async def _send_file_created_notification(media_file: MediaFile, user_id: int) -> None:
    """Send WebSocket notification for newly created file.

    Args:
        media_file: The created MediaFile.
        user_id: User ID to notify.
    """
    try:
        from app.api.websockets import send_notification

        await send_notification(
            user_id=user_id,
            notification_type="file_created",
            data={
                "file_id": str(media_file.uuid),
                "file": {
                    "uuid": str(media_file.uuid),
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
        # Validate and normalize URL
        normalized_url, youtube_service = _validate_youtube_url(request_data.url)

        # Handle playlist processing (early return)
        if youtube_service.is_playlist_url(normalized_url):
            return _handle_playlist_processing(normalized_url, current_user.id)

        # Extract video info
        youtube_id, video_title, video_info = _extract_video_info(youtube_service, normalized_url)

        # Check for duplicate video
        _check_duplicate_video(db, current_user.id, youtube_id, normalized_url)

        # Create placeholder MediaFile record
        media_file = _create_media_file_record(
            db, current_user.id, normalized_url, youtube_id, video_title, video_info
        )

        # Dispatch background task
        _dispatch_video_task(db, media_file, normalized_url, current_user.id)

        # Send WebSocket notification
        await _send_file_created_notification(media_file, current_user.id)

        logger.info(f"Created placeholder MediaFile {media_file.id} for YouTube URL processing")
        return media_file

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing YouTube URL: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error processing YouTube URL",
        ) from e
