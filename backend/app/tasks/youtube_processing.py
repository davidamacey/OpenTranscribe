"""
YouTube processing task for background video downloading and processing.

This module provides Celery tasks for handling YouTube video downloads and processing
asynchronously to prevent UI blocking during video import operations. It includes
progress tracking, error handling, and automatic transcription initiation.
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
from app.services.youtube_service import YouTubeService
from app.tasks.transcription import transcribe_audio_task
from app.tasks.transcription.notifications import get_file_metadata

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
                "file_id": str(file_id),
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
def process_youtube_url_task(self, url: str, user_id: int, file_id: int) -> YouTubeProcessingResult:
    """Background task to process YouTube URL by downloading and creating media file.

    This task handles asynchronous YouTube video processing to prevent UI blocking.
    It downloads the video, updates the media file record, and starts transcription.

    Args:
        self: Celery task instance (automatically passed when bind=True).
        url: YouTube URL to process.
        user_id: ID of the user who initiated the request.
        file_id: ID of the MediaFile record to update.

    Returns:
        Dict: Processing result containing status, message, and file_id.
              Format: {"status": "success|error", "message": str, "file_id": int}

    Raises:
        Exception: Any error during processing will be caught and returned in result dict.
    """
    try:
        logger.info(f"Starting YouTube processing task for URL: {url}, file_id: {file_id}")

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
                return {"status": "error", "message": "User or file record not found"}

            youtube_service = YouTubeService()

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
                updated_media_file = youtube_service.process_youtube_url_sync(
                    url=url,
                    db=db,
                    user=user,
                    media_file=media_file,
                    progress_callback=progress_callback,
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
                            "id": updated_media_file.id,
                            "filename": updated_media_file.filename,
                            "status": updated_media_file.status.value
                            if updated_media_file.status
                            else "pending",
                            "content_type": updated_media_file.content_type,
                            "file_size": updated_media_file.file_size,
                            "title": updated_media_file.title,
                            "author": updated_media_file.author,
                            "duration": updated_media_file.duration,
                            "thumbnail_url": f"/api/files/{updated_media_file.id}/thumbnail"
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
                                "file_id": str(file_id),
                                "file": file_data,
                                "status": "pending",
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

                # Start transcription task
                try:
                    transcribe_audio_task.delay(file_id)
                    logger.info(f"Started transcription task for MediaFile {file_id}")
                except Exception as e:
                    logger.error(f"Failed to start transcription task for {file_id}: {e}")
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

                return {"status": "error", "message": str(e)}

    except Exception as e:
        logger.error(f"Unexpected error in YouTube processing task: {e}")

        # Send error notification
        send_youtube_notification_via_redis(
            user_id=user_id,
            file_id=file_id,
            status=FileStatus.ERROR,
            message=f"Unexpected error: {str(e)}",
            progress=0,
        )

        return {"status": "error", "message": str(e)}
