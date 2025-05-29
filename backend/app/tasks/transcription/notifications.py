import asyncio
import logging
from typing import Dict, Any

from app.api.websockets import send_notification
from app.models.media import FileStatus

logger = logging.getLogger(__name__)


async def send_status_notification(user_id: int, file_id: int, status: FileStatus, 
                                 message: str, progress: int = 0) -> bool:
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
        await send_notification(
            user_id,
            "transcription_status",
            {
                "file_id": str(file_id),
                "status": status.value,
                "message": message,
                "progress": progress
            }
        )
        return True
    except Exception as e:
        logger.warning(f"Failed to send WebSocket notification: {e}")
        return False


def send_notification_with_retry(user_id: int, file_id: int, status: FileStatus, 
                                message: str, progress: int = 0, max_retries: int = 3) -> bool:
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
            asyncio.run(send_status_notification(user_id, file_id, status, message, progress))
            logger.info(f"Successfully sent notification for file {file_id} on attempt {retry + 1}")
            return True
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
        user_id, file_id, FileStatus.PROCESSING,
        "Transcription started", progress=10
    )


def send_completion_notification(user_id: int, file_id: int) -> None:
    """Send transcription completed notification."""
    send_notification_with_retry(
        user_id, file_id, FileStatus.COMPLETED,
        "Transcription completed successfully", progress=100
    )


def send_error_notification(user_id: int, file_id: int, error_message: str) -> None:
    """Send transcription error notification."""
    send_notification_with_retry(
        user_id, file_id, FileStatus.ERROR,
        f"Transcription failed: {error_message}", progress=0
    )