"""
Celery Task for AI Tag and Collection Suggestions

Automatically generates AI-powered tag and collection suggestions from
transcripts after transcription completes. Only runs if LLM provider
is configured for the user.
"""

import json
import logging

import redis

from app.core.celery import celery_app
from app.core.config import settings
from app.db.base import SessionLocal
from app.services.topic_extraction_service import TopicExtractionService

logger = logging.getLogger(__name__)


def send_topic_extraction_notification(
    user_id: int,
    file_id: int,
    status: str,
    message: str,
    suggestion_id: str = None,
) -> bool:
    """
    Send AI suggestion extraction status notification via Redis pub/sub.

    Args:
        user_id: User ID
        file_id: File ID
        status: Extraction status ('processing', 'completed', 'failed')
        message: Status message
        suggestion_id: TopicSuggestion UUID (when completed)

    Returns:
        True if notification was sent successfully
    """
    try:
        # Create Redis client
        redis_client = redis.from_url(settings.REDIS_URL)

        # Get file metadata
        from app.tasks.transcription.notifications import get_file_metadata

        file_metadata = get_file_metadata(file_id)

        # Prepare notification data
        notification_data = {
            "file_id": file_metadata.get("file_uuid"),  # Use UUID
            "status": status,
            "message": message,
            "filename": file_metadata["filename"],
        }

        if status == "completed" and suggestion_id:
            notification_data["suggestion_id"] = suggestion_id

        notification = {
            "user_id": user_id,
            "type": "topic_extraction_status",
            "data": notification_data,
        }

        # Publish to Redis
        redis_client.publish("websocket_notifications", json.dumps(notification))
        logger.info(
            f"Published topic extraction notification for user {user_id}, file {file_id}: {status}"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to send topic extraction notification for file {file_id}: {e}")
        return False


@celery_app.task(bind=True, name="extract_topics_from_transcript")
def extract_topics_task(self, file_uuid: str, force_regenerate: bool = False):
    """
    Extract AI tag and collection suggestions from a completed transcript.

    This task runs AFTER transcription has been completed. It's typically
    triggered automatically by the transcription workflow, but can also be
    manually triggered via the API.

    Args:
        file_uuid: UUID of the MediaFile to extract suggestions from
        force_regenerate: If True, re-extract even if suggestions exist

    Returns:
        dict: Contains status, suggestion_id, tag_count, and collection_count
    """
    from app.utils.uuid_helpers import get_file_by_uuid

    db = SessionLocal()

    try:
        # Get media file from database
        media_file = get_file_by_uuid(db, file_uuid)
        if not media_file:
            raise ValueError(f"Media file with UUID {file_uuid} not found")

        file_id = media_file.id
        user_id = media_file.user_id

        logger.info(f"Starting topic extraction for file {file_id} (user {user_id})")

        # Send initial processing notification
        send_topic_extraction_notification(
            user_id=user_id,
            file_id=file_id,
            status="processing",
            message="Preparing AI analysis...",
        )

        # Create topic extraction service
        extraction_service = TopicExtractionService.create_from_settings(user_id=user_id, db=db)

        if not extraction_service:
            logger.info(f"LLM not configured for user {user_id}, skipping topic extraction")
            # Send notification that LLM is not configured
            send_topic_extraction_notification(
                user_id=user_id,
                file_id=file_id,
                status="not_configured",
                message="Topic extraction not available - no LLM provider configured in settings",
            )
            return {
                "status": "skipped",
                "reason": "LLM not configured",
            }

        # Send notification before LLM processing
        send_topic_extraction_notification(
            user_id=user_id,
            file_id=file_id,
            status="processing",
            message="Analyzing transcript with AI...",
        )

        # Create a notification callback for the service to use
        def notify_progress(message: str):
            send_topic_extraction_notification(
                user_id=user_id,
                file_id=file_id,
                status="processing",
                message=message,
            )

        # Extract topics with progress callback
        suggestion = extraction_service.extract_topics(
            media_file_id=file_id,
            force_regenerate=force_regenerate,
            progress_callback=notify_progress,
        )

        if not suggestion:
            error_msg = "Failed to extract topics from transcript"
            logger.error(f"{error_msg} for file {file_id}")

            # Send failure notification
            send_topic_extraction_notification(
                user_id=user_id,
                file_id=file_id,
                status="failed",
                message=error_msg,
            )

            return {
                "status": "failed",
                "error": error_msg,
            }

        # Send notification that AI processing is complete, now storing results
        send_topic_extraction_notification(
            user_id=user_id,
            file_id=file_id,
            status="processing",
            message="Saving AI suggestions...",
        )

        # Count suggestions
        tag_count = len(suggestion.suggested_tags or [])
        collection_count = len(suggestion.suggested_collections or [])

        # Send completion notification
        send_topic_extraction_notification(
            user_id=user_id,
            file_id=file_id,
            status="completed",
            message=f"Found {tag_count} tags and {collection_count} collections",
            suggestion_id=str(suggestion.uuid),
        )

        logger.info(
            f"Successfully extracted {tag_count} tags and {collection_count} collections for file {file_id}"
        )

        return {
            "status": "completed",
            "suggestion_id": str(suggestion.uuid),
            "tag_count": tag_count,
            "collection_count": collection_count,
        }

    except Exception as e:
        error_msg = f"Error extracting topics: {str(e)}"
        logger.error(f"{error_msg} for file {file_uuid}")

        # Send failure notification
        try:
            media_file = get_file_by_uuid(db, file_uuid)
            if media_file:
                send_topic_extraction_notification(
                    user_id=media_file.user_id,
                    file_id=media_file.id,
                    status="failed",
                    message=error_msg,
                )
        except Exception as notify_err:
            # Log but don't raise - notification failures shouldn't mask the original error
            logger.debug(f"Failed to send topic extraction failure notification: {notify_err}")

        return {
            "status": "failed",
            "error": error_msg,
        }

    finally:
        db.close()


@celery_app.task(bind=True, name="batch_extract_topics")
def batch_extract_topics_task(self, file_uuids: list[str], force_regenerate: bool = False):
    """
    Extract AI suggestions for multiple files in batch.

    Args:
        file_uuids: List of file UUIDs to process
        force_regenerate: If True, re-extract even if suggestions exist

    Returns:
        dict: Contains total, completed, failed, skipped counts and details for each file
    """
    results = {
        "total": len(file_uuids),
        "completed": 0,
        "failed": 0,
        "skipped": 0,
        "details": [],
    }

    for file_uuid in file_uuids:
        try:
            result = extract_topics_task(file_uuid, force_regenerate)

            if result["status"] == "completed":
                results["completed"] += 1
            elif result["status"] == "failed":
                results["failed"] += 1
            elif result["status"] == "skipped":
                results["skipped"] += 1

            results["details"].append(
                {
                    "file_uuid": file_uuid,
                    "status": result["status"],
                    "suggestion_id": result.get("suggestion_id"),
                    "error": result.get("error"),
                }
            )

        except Exception as e:
            logger.error(f"Error in batch processing file {file_uuid}: {e}")
            results["failed"] += 1
            results["details"].append(
                {
                    "file_uuid": file_uuid,
                    "status": "failed",
                    "error": str(e),
                }
            )

    logger.info(
        f"Batch topic extraction completed: {results['completed']} succeeded, "
        f"{results['failed']} failed, {results['skipped']} skipped"
    )

    return results
