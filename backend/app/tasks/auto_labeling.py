"""
Celery tasks for auto-labeling: batch grouping and retroactive apply.
"""

import json
import logging

import redis

from app.core.celery import celery_app
from app.core.config import settings
from app.core.constants import NOTIFICATION_TYPE_AUTO_LABEL_STATUS
from app.db.base import SessionLocal

logger = logging.getLogger(__name__)


def send_auto_label_notification(
    user_id: int,
    status: str,
    message: str,
    data: dict | None = None,
    file_id: str = "auto_label_batch",
) -> bool:
    """Send auto-label status notification via Redis pub/sub.

    Args:
        user_id: Target user ID for the notification.
        status: Notification status (processing, completed, failed).
        message: Human-readable status message.
        data: Optional additional data payload.
        file_id: Synthetic file ID for progressive notification grouping.
            Use "batch_grouping" for grouping tasks,
            "retroactive_apply" for retroactive apply tasks.
    """
    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        notification = {
            "user_id": user_id,
            "type": NOTIFICATION_TYPE_AUTO_LABEL_STATUS,
            "data": {
                "status": status,
                "message": message,
                "file_id": file_id,
                **(data or {}),
            },
        }
        redis_client.publish("websocket_notifications", json.dumps(notification))
        return True
    except Exception as e:
        logger.error(f"Failed to send auto-label notification: {e}")
        return False


@celery_app.task(name="ai.group_batch_files")
def group_batch_files_task(batch_id: int, user_id: int):
    """Group batch files by shared topics into collections.

    Triggered after all files in a batch complete topic extraction.
    """
    db = SessionLocal()
    try:
        from app.services.auto_label_service import AutoLabelService

        service = AutoLabelService(db)

        # Check user settings
        user_settings = service.get_user_auto_label_settings(user_id)
        if not user_settings.get("enabled") or not user_settings.get("bulk_grouping_enabled"):
            logger.info(f"Batch grouping disabled for user {user_id}, skipping")
            return {"status": "skipped", "reason": "disabled"}

        send_auto_label_notification(
            user_id=user_id,
            status="processing",
            message="Grouping files by shared topics...",
            file_id="batch_grouping",
        )

        result = service.group_batch_by_topics(batch_id, user_id)

        send_auto_label_notification(
            user_id=user_id,
            status="completed",
            message=f"Created {result['collections_created']} collections from shared topics",
            data=result,
            file_id="batch_grouping",
        )

        return {"status": "completed", **result}

    except Exception as e:
        logger.error(f"Error in batch grouping task: {e}", exc_info=True)
        send_auto_label_notification(
            user_id=user_id,
            status="failed",
            message="Batch file grouping failed",
            file_id="batch_grouping",
        )
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()


@celery_app.task(name="ai.retroactive_auto_label")
def retroactive_auto_label_task(
    user_id: int,
    file_uuids: list[str] | None = None,
):
    """Apply auto-labeling to existing files with pending suggestions.

    Args:
        user_id: User ID
        file_uuids: Optional list of specific file UUIDs to process
    """
    db = SessionLocal()
    try:
        from app.services.auto_label_service import AutoLabelService

        service = AutoLabelService(db)
        user_settings = service.get_user_auto_label_settings(user_id)
        threshold = user_settings.get("confidence_threshold", 0.75)

        # Resolve file UUIDs to IDs if provided
        file_ids = None
        if file_uuids:
            from app.models.media import MediaFile

            files = db.query(MediaFile).filter(MediaFile.uuid.in_(file_uuids)).all()
            file_ids = [f.id for f in files]

        send_auto_label_notification(
            user_id=user_id,
            status="processing",
            message="Starting auto-labeling of existing files...",
            file_id="retroactive_apply",
        )

        def progress_callback(processed, total, filename):
            if processed == 1 or processed % 5 == 0 or processed == total:
                send_auto_label_notification(
                    user_id=user_id,
                    status="processing",
                    message=f"Processing {processed}/{total}: {filename}",
                    data={"processed": processed, "total": total},
                    file_id="retroactive_apply",
                )

        result = service.retroactive_apply(
            user_id=user_id,
            confidence_threshold=threshold,
            file_ids=file_ids,
            progress_callback=progress_callback,
        )

        send_auto_label_notification(
            user_id=user_id,
            status="completed",
            message=(
                f"Auto-labeled {result['files_processed']} files: "
                f"{result['tags_applied']} tags, {result['collections_applied']} collections applied"
            ),
            data=result,
            file_id="retroactive_apply",
        )

        return {"status": "completed", **result}

    except Exception as e:
        logger.error(f"Error in retroactive auto-label task: {e}", exc_info=True)
        send_auto_label_notification(
            user_id=user_id,
            status="failed",
            message="Auto-labeling failed",
            file_id="retroactive_apply",
        )
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()
