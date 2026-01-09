"""
Media URL processing task for background video downloading and processing.

This module provides Celery tasks for handling media video downloads and processing
asynchronously to prevent UI blocking during video import operations. It includes
progress tracking, error handling, and automatic transcription initiation.

Supports YouTube, Vimeo, Twitter/X, TikTok, and 1800+ other platforms via yt-dlp.
"""

import json
import logging
from typing import TypedDict

import redis

from app.core.celery import celery_app
from app.core.config import settings
from app.db.session_utils import get_refreshed_object
from app.db.session_utils import session_scope
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.models.user import User
from app.services.formatting_service import FormattingService
from app.services.media_download_service import MediaDownloadService
from app.tasks.transcription import transcribe_audio_task
from app.tasks.transcription.notifications import get_file_metadata
from app.tasks.waveform import generate_waveform_task

logger = logging.getLogger(__name__)


def send_youtube_notification_via_redis(
    user_id: int, file_id: int, status: FileStatus, message: str, progress: int = 0
) -> bool:
    """
    Send YouTube processing notification via Redis pub/sub from synchronous context.

    Args:
        user_id: User ID
        file_id: File ID
        status: File status
        message: Status message
        progress: Progress percentage

    Returns:
        True if notification was sent successfully, False otherwise
    """
    try:
        # Create Redis client
        redis_client = redis.from_url(settings.REDIS_URL)

        # Get file metadata
        file_metadata = get_file_metadata(file_id)

        # Prepare notification data
        notification = {
            "user_id": user_id,
            "type": "youtube_processing_status",
            "data": {
                "file_id": file_metadata.get("file_uuid"),  # Use UUID from metadata
                "status": status.value,
                "message": message,
                "progress": progress,
                "filename": file_metadata["filename"],
                "content_type": file_metadata["content_type"],
                "file_size": file_metadata["file_size"],
            },
        }

        # Publish to Redis
        redis_client.publish("websocket_notifications", json.dumps(notification))
        logger.info(
            f"Published YouTube notification via Redis for user {user_id}, file {file_id}: {status.value}"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to send YouTube notification via Redis for file {file_id}: {e}")
        return False


class YouTubeProcessingResult(TypedDict):
    """Result structure for YouTube processing task."""

    status: str  # "success" or "error"
    message: str
    file_id: int


@celery_app.task(name="process_youtube_url_task", bind=True)
def process_youtube_url_task(
    self,
    url: str,
    user_id: int,
    file_uuid: str,
    media_username: str | None = None,
    media_password: str | None = None,
) -> YouTubeProcessingResult:
    """Background task to process YouTube URL by downloading and creating media file.

    This task handles asynchronous YouTube video processing to prevent UI blocking.
    It downloads the video, updates the media file record, and starts transcription.

    Args:
        self: Celery task instance (automatically passed when bind=True).
        url: YouTube URL to process.
        user_id: ID of the user who initiated the request.
        file_uuid: UUID of the MediaFile record to update.

    Returns:
        Dict: Processing result containing status, message, and file_id.
              Format: {"status": "success|error", "message": str, "file_id": int}

    Raises:
        Exception: Any error during processing will be caught and returned in result dict.
    """
    from app.utils.uuid_helpers import get_file_by_uuid

    file_id = None  # Initialize to handle exceptions before file_id is assigned

    try:
        logger.info(f"Starting YouTube processing task for URL: {url}, file_uuid: {file_uuid}")

        # Get internal file ID for database operations
        with session_scope() as db:
            media_file = get_file_by_uuid(db, file_uuid)
            file_id = media_file.id

        # Send initial processing notification
        send_youtube_notification_via_redis(
            user_id=user_id,
            file_id=file_id,
            status=FileStatus.PROCESSING,
            message="Starting YouTube video download...",
            progress=10,
        )

        with session_scope() as db:
            # Get the user and media file records
            user = db.query(User).filter(User.id == user_id).first()
            media_file = get_refreshed_object(db, MediaFile, file_id)

            if not user or not media_file:
                logger.error(f"User {user_id} or MediaFile {file_id} not found")
                send_youtube_notification_via_redis(
                    user_id=user_id,
                    file_id=file_id,
                    status=FileStatus.ERROR,
                    message="User or file record not found",
                    progress=0,
                )
                return {
                    "status": "error",
                    "message": "User or file record not found",
                    "file_id": file_id,
                }

            media_service = MediaDownloadService()

            # Process the YouTube URL
            try:
                # Create progress callback
                def progress_callback(progress, message):
                    send_youtube_notification_via_redis(
                        user_id=user_id,
                        file_id=file_id,
                        status=FileStatus.PROCESSING,
                        message=message,
                        progress=progress,
                    )

                # Process using synchronous version
                updated_media_file = media_service.process_media_url_sync(
                    url=url,
                    db=db,
                    user=user,
                    media_file=media_file,
                    progress_callback=progress_callback,
                    media_username=media_username,
                    media_password=media_password,
                )

                # Update status to pending for transcription
                updated_media_file.status = FileStatus.PENDING
                db.commit()

                # Send completion notification
                send_youtube_notification_via_redis(
                    user_id=user_id,
                    file_id=file_id,
                    status=FileStatus.PENDING,
                    message="YouTube download complete, starting transcription...",
                    progress=100,
                )

                # Also send file_updated notification to refresh the gallery with thumbnail
                try:
                    # Get updated file data for gallery
                    updated_media_file = get_refreshed_object(db, MediaFile, file_id)
                    if updated_media_file:
                        # Create file data for gallery update
                        file_data = {
                            "id": str(updated_media_file.uuid),  # Use UUID for frontend
                            "filename": updated_media_file.filename,
                            "status": updated_media_file.status.value
                            if updated_media_file.status
                            else "pending",
                            "display_status": FormattingService.format_status(
                                updated_media_file.status
                            )
                            if updated_media_file.status
                            else "Pending",
                            "content_type": updated_media_file.content_type,
                            "file_size": updated_media_file.file_size,
                            "title": updated_media_file.title,
                            "author": updated_media_file.author,
                            "duration": updated_media_file.duration,
                            "thumbnail_url": f"/api/files/{updated_media_file.uuid}/thumbnail"  # Use UUID in URL
                            if updated_media_file.thumbnail_path
                            else None,
                            "upload_time": updated_media_file.upload_time.isoformat()
                            if updated_media_file.upload_time
                            else None,
                        }

                        # Send file_updated notification via Redis
                        notification = {
                            "user_id": user_id,
                            "type": "file_updated",
                            "data": {
                                "file_id": str(updated_media_file.uuid),  # Use UUID
                                "file": file_data,
                                "status": updated_media_file.status.value
                                if updated_media_file.status
                                else "pending",
                                "display_status": FormattingService.format_status(
                                    updated_media_file.status
                                )
                                if updated_media_file.status
                                else "Pending",
                                "message": "YouTube processing completed",
                            },
                        }
                        redis_client = redis.from_url(settings.REDIS_URL)
                        redis_client.publish("websocket_notifications", json.dumps(notification))
                        logger.info(
                            f"Sent file_updated notification for YouTube completion: {file_id}"
                        )

                except Exception as e:
                    logger.error(
                        f"Failed to send file_updated notification for YouTube completion {file_id}: {e}"
                    )

                # Start transcription and waveform tasks in parallel
                try:
                    # Launch GPU transcription task
                    transcribe_audio_task.delay(file_uuid)
                    # Launch CPU waveform generation task in parallel
                    generate_waveform_task.delay(file_id=file_id, file_uuid=file_uuid)
                    logger.info(
                        f"Started parallel tasks for MediaFile {file_id}: transcription (GPU) and waveform (CPU)"
                    )
                except Exception as e:
                    logger.error(f"Failed to start tasks for {file_id}: {e}")
                    # Don't fail the whole process if task scheduling fails

                return {
                    "status": "success",
                    "message": "YouTube processing completed",
                    "file_id": file_id,
                }

            except Exception as e:
                logger.error(f"Error processing YouTube URL {url}: {e}")

                # Update media file status to error
                media_file.status = FileStatus.ERROR
                media_file.last_error_message = str(e)
                db.commit()

                # Send error notification
                send_youtube_notification_via_redis(
                    user_id=user_id,
                    file_id=file_id,
                    status=FileStatus.ERROR,
                    message=f"YouTube processing failed: {str(e)}",
                    progress=0,
                )

                return {"status": "error", "message": str(e), "file_id": file_id}

    except Exception as e:
        logger.error(f"Unexpected error in YouTube processing task: {e}")

        # Send error notification only if file_id was assigned
        if file_id is not None:
            send_youtube_notification_via_redis(
                user_id=user_id,
                file_id=file_id,
                status=FileStatus.ERROR,
                message=f"Unexpected error: {str(e)}",
                progress=0,
            )

        return {"status": "error", "message": str(e), "file_id": file_id}


class YouTubePlaylistProcessingResult(TypedDict):
    """Result structure for YouTube playlist processing task."""

    status: str  # "success" or "error"
    message: str
    created_count: int
    skipped_count: int
    total_videos: int


def _send_playlist_notification(
    user_id: int,
    status: str,
    message: str,
    progress: int,
    extra_data: dict | None = None,
) -> None:
    """Send playlist processing notification via Redis.

    Args:
        user_id: User ID to send notification to.
        status: Notification status (processing, completed, error).
        message: Status message.
        progress: Progress percentage (0-100).
        extra_data: Optional additional data to include in notification.
    """
    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        data = {
            "status": status,
            "message": message,
            "progress": progress,
        }
        if extra_data:
            data.update(extra_data)
        notification = {
            "user_id": user_id,
            "type": "playlist_processing_status",
            "data": data,
        }
        redis_client.publish("websocket_notifications", json.dumps(notification))
    except Exception as e:
        logger.error(f"Failed to send playlist notification: {e}")


def _create_playlist_error_result(message: str) -> YouTubePlaylistProcessingResult:
    """Create an error result for playlist processing.

    Args:
        message: Error message.

    Returns:
        YouTubePlaylistProcessingResult with error status.
    """
    return {
        "status": "error",
        "message": message,
        "created_count": 0,
        "skipped_count": 0,
        "total_videos": 0,
    }


def _send_file_created_notification(user_id: int, media_file: MediaFile) -> None:
    """Send file_created notification for a media file.

    Args:
        user_id: User ID to send notification to.
        media_file: MediaFile instance to notify about.
    """
    try:
        file_data = {
            "id": str(media_file.uuid),
            "filename": media_file.filename,
            "status": media_file.status.value if media_file.status else "processing",
            "display_status": FormattingService.format_status(media_file.status)
            if media_file.status
            else "Processing",
            "content_type": media_file.content_type,
            "file_size": media_file.file_size,
            "title": media_file.title,
            "author": media_file.author,
            "duration": media_file.duration,
            "upload_time": media_file.upload_time.isoformat() if media_file.upload_time else None,
        }

        notification = {
            "user_id": user_id,
            "type": "file_created",
            "data": {
                "file_id": str(media_file.uuid),
                "file": file_data,
            },
        }
        redis_client = redis.from_url(settings.REDIS_URL)
        redis_client.publish("websocket_notifications", json.dumps(notification))
    except Exception as e:
        logger.error(f"Failed to send file_created notification for video {media_file.id}: {e}")


def _dispatch_video_task(media_file: MediaFile, user_id: int, db) -> bool:
    """Dispatch processing task for a single video.

    Args:
        media_file: MediaFile instance to process.
        user_id: User ID who initiated the request.
        db: Database session.

    Returns:
        True if task was dispatched successfully, False otherwise.
    """
    try:
        video_url = media_file.source_url
        process_youtube_url_task.delay(
            url=video_url,
            user_id=user_id,
            file_uuid=str(media_file.uuid),
        )
        logger.info(f"Dispatched YouTube processing task for video: {media_file.title}")
        return True
    except Exception as e:
        logger.error(f"Failed to dispatch task for video {media_file.title}: {e}")
        media_file.status = FileStatus.ERROR
        media_file.last_error_message = f"Failed to start processing: {str(e)}"
        db.commit()
        return False


@celery_app.task(name="process_youtube_playlist_task", bind=True)
def process_youtube_playlist_task(self, url: str, user_id: int) -> YouTubePlaylistProcessingResult:
    """Background task to process YouTube playlist by extracting videos and dispatching individual tasks.

    This task handles asynchronous YouTube playlist processing:
    1. Extracts playlist metadata and video list
    2. Creates placeholder MediaFile records for each video
    3. Dispatches individual process_youtube_url_task for each video
    4. Sends progress notifications

    Args:
        self: Celery task instance (automatically passed when bind=True).
        url: YouTube playlist URL to process.
        user_id: ID of the user who initiated the request.

    Returns:
        Dict: Processing result containing status, message, and video counts.
              Format: {"status": "success|error", "message": str, "created_count": int,
                      "skipped_count": int, "total_videos": int}

    Raises:
        Exception: Any error during processing will be caught and returned in result dict.
    """
    logger.info(f"Starting YouTube playlist processing task for URL: {url}")
    _send_playlist_notification(user_id, "processing", "Extracting playlist information...", 5)

    try:
        return _process_playlist_with_db(url, user_id)
    except Exception as e:
        logger.error(f"Unexpected error in YouTube playlist processing task: {e}")
        _send_playlist_notification(user_id, "error", f"Unexpected error: {str(e)}", 0)
        return _create_playlist_error_result(str(e))


def _process_playlist_with_db(url: str, user_id: int) -> YouTubePlaylistProcessingResult:
    """Process playlist within a database session.

    Args:
        url: YouTube playlist URL.
        user_id: User ID.

    Returns:
        YouTubePlaylistProcessingResult with processing outcome.
    """
    with session_scope() as db:
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            logger.error(f"User {user_id} not found")
            return _create_playlist_error_result("User not found")

        def progress_callback(progress, message, data):
            _send_playlist_notification(user_id, "processing", message, progress, data)

        try:
            result = MediaDownloadService().process_youtube_playlist_sync(
                url=url, db=db, user=user, progress_callback=progress_callback
            )
            return _handle_playlist_result(result, user_id, db)
        except Exception as e:
            logger.error(f"Error processing YouTube playlist {url}: {e}")
            _send_playlist_notification(
                user_id, "error", f"Playlist processing failed: {str(e)}", 0
            )
            return _create_playlist_error_result(str(e))


def _handle_playlist_result(result: dict, user_id: int, db) -> YouTubePlaylistProcessingResult:
    """Handle successful playlist extraction result.

    Args:
        result: Result dict from YouTubeService.process_youtube_playlist_sync.
        user_id: User ID.
        db: Database session.

    Returns:
        YouTubePlaylistProcessingResult with success outcome.
    """
    created_media_files = result.get("media_files", [])
    playlist_info = result.get("playlist_info", {})
    created_count = result.get("created_count", 0)
    skipped_count = result.get("skipped_count", 0)
    total_videos = result.get("total_videos", 0)

    playlist_title = playlist_info.get("playlist_title", "Unknown Playlist")
    logger.info(
        f"Playlist '{playlist_title}' extraction complete: {created_count} videos to process, "
        f"{skipped_count} skipped"
    )

    # Send file_created notifications for each video
    for media_file in created_media_files:
        _send_file_created_notification(user_id, media_file)

    # Dispatch individual processing tasks for each video
    dispatched_count = sum(
        1 for media_file in created_media_files if _dispatch_video_task(media_file, user_id, db)
    )

    # Build completion message
    completion_message = (
        f"Playlist '{playlist_title}': {created_count} of {total_videos} videos queued for download"
    )
    if skipped_count > 0:
        completion_message += f" ({skipped_count} already in library)"

    # Send completion notification
    _send_playlist_notification(
        user_id,
        "completed",
        completion_message,
        100,
        {
            "playlist_title": playlist_title,
            "playlist_id": playlist_info.get("playlist_id"),
            "created_count": created_count,
            "skipped_count": skipped_count,
            "total_videos": total_videos,
            "dispatched_count": dispatched_count,
        },
    )

    return {
        "status": "success",
        "message": completion_message,
        "created_count": created_count,
        "skipped_count": skipped_count,
        "total_videos": total_videos,
    }
