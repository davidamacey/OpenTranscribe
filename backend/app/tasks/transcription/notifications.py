import json
import logging

import redis

from app.api.websockets import send_notification
from app.core.config import settings
from app.db.session_utils import session_scope
from app.models.media import FileStatus
from app.models.media import MediaFile

logger = logging.getLogger(__name__)


def get_file_metadata(file_id: int) -> dict:
    """Get basic file metadata for notifications."""
    try:
        with session_scope() as db:
            media_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
            if media_file:
                return {
                    "filename": media_file.filename,
                    "content_type": media_file.content_type,
                    "file_size": media_file.file_size,
                }
    except Exception as e:
        logger.warning(f"Failed to get file metadata for file {file_id}: {e}")

    # Return minimal data if query fails
    return {
        "filename": f"File {file_id}",
        "content_type": "unknown",
        "file_size": 0,
    }


async def send_status_notification(
    user_id: int, file_id: int, status: FileStatus, message: str, progress: int = 0
) -> bool:
    """
    Send a status notification via WebSocket.

    Args:
        user_id: User ID to send notification to
        file_id: File ID
        status: File status
        message: Status message
        progress: Progress percentage (0-100)

    Returns:
        True if notification was sent successfully, False otherwise
    """
    try:
        # Get file metadata
        file_metadata = get_file_metadata(file_id)

        await send_notification(
            user_id,
            "transcription_status",
            {
                "file_id": str(file_id),
                "status": status.value,
                "message": message,
                "progress": progress,
                "filename": file_metadata["filename"],
                "content_type": file_metadata["content_type"],
                "file_size": file_metadata["file_size"],
            },
        )
        return True
    except Exception as e:
        logger.warning(f"Failed to send WebSocket notification: {e}")
        return False


def send_notification_via_redis(
    user_id: int, file_id: int, status: FileStatus, message: str, progress: int = 0
) -> bool:
    """
    Send notification via Redis pub/sub from synchronous context (like Celery worker).

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
            "type": "transcription_status",
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
            f"Published notification via Redis for user {user_id}, file {file_id}: {status.value}"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to send notification via Redis for file {file_id}: {e}")
        return False


def send_notification_with_retry(
    user_id: int,
    file_id: int,
    status: FileStatus,
    message: str,
    progress: int = 0,
    max_retries: int = 3,
) -> bool:
    """
    Send notification with retry logic.

    Args:
        user_id: User ID
        file_id: File ID
        status: File status
        message: Status message
        progress: Progress percentage
        max_retries: Maximum number of retry attempts

    Returns:
        True if notification was eventually sent, False if all retries failed
    """
    for retry in range(max_retries):
        try:
            success = send_notification_via_redis(user_id, file_id, status, message, progress)
            if success:
                logger.info(
                    f"Successfully sent notification for file {file_id} on attempt {retry + 1}"
                )
                return True
            else:
                logger.warning(f"Failed to send notification (attempt {retry + 1}/{max_retries})")
        except Exception as e:
            logger.warning(f"Failed to send notification (attempt {retry + 1}/{max_retries}): {e}")

        if retry < max_retries - 1:  # Don't sleep on the last attempt
            import time

            time.sleep(1)  # Short delay before retry

    logger.error(f"Failed to send notification for file {file_id} after {max_retries} attempts")
    return False


def send_processing_notification(user_id: int, file_id: int) -> None:
    """Send processing started notification."""
    send_notification_with_retry(
        user_id, file_id, FileStatus.PROCESSING, "Transcription started", progress=10
    )


def send_progress_notification(user_id: int, file_id: int, progress: float, message: str) -> None:
    """Send progress update notification."""
    progress_percent = int(progress * 100)
    send_notification_with_retry(
        user_id, file_id, FileStatus.PROCESSING, message, progress=progress_percent
    )


def send_completion_notification(user_id: int, file_id: int) -> None:
    """Send transcription completed notification."""
    send_notification_with_retry(
        user_id,
        file_id,
        FileStatus.COMPLETED,
        "Transcription completed successfully",
        progress=100,
    )

    # Also send a file_updated notification to refresh the gallery item
    try:
        from app.db.session_utils import session_scope

        # Get updated file data for gallery
        with session_scope() as db:
            media_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
            if media_file:
                # Import formatting service to include display_status
                from app.services.formatting_service import FormattingService

                # Create file data for gallery update with all formatted fields
                file_data = {
                    "id": media_file.id,
                    "filename": media_file.filename,
                    "status": media_file.status.value if media_file.status else "completed",
                    "content_type": media_file.content_type,
                    "file_size": media_file.file_size,
                    "title": media_file.title,
                    "author": media_file.author,
                    "duration": media_file.duration,
                    "thumbnail_url": f"/api/files/{media_file.id}/thumbnail"
                    if media_file.thumbnail_path
                    else None,
                    "upload_time": media_file.upload_time.isoformat()
                    if media_file.upload_time
                    else None,
                    # Add formatted fields that the frontend expects
                    "formatted_duration": FormattingService.format_duration(media_file.duration),
                    "formatted_upload_date": FormattingService.format_upload_date(
                        media_file.upload_time
                    ),
                    "formatted_file_age": FormattingService.format_file_age(media_file.upload_time),
                    "formatted_file_size": FormattingService.format_bytes_detailed(
                        media_file.file_size
                    ),
                    "display_status": FormattingService.format_status(media_file.status),
                    "status_badge_class": FormattingService.get_status_badge_class(
                        media_file.status.value
                    ),
                }

                # Send file_updated notification via Redis (since we're in sync context)
                import json

                import redis

                from app.core.config import settings

                redis_client = redis.from_url(settings.REDIS_URL)
                notification = {
                    "user_id": user_id,
                    "type": "file_updated",
                    "data": {
                        "file_id": str(file_id),
                        "file": file_data,
                        "status": "completed",
                        "message": "File processing completed",
                    },
                }
                redis_client.publish("websocket_notifications", json.dumps(notification))
                logger.info(f"Sent file_updated notification for completed file {file_id}")

    except Exception as e:
        logger.error(f"Failed to send file_updated notification for file {file_id}: {e}")


def send_error_notification(user_id: int, file_id: int, error_message: str) -> None:
    """Send transcription error notification."""
    send_notification_with_retry(
        user_id,
        file_id,
        FileStatus.ERROR,
        f"Transcription failed: {error_message}",
        progress=0,
    )
