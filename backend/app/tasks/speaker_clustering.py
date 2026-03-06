"""Celery tasks for speaker clustering and audio clip extraction."""

import json
import logging

import redis

from app.core.celery import celery_app
from app.core.config import settings
from app.core.constants import NOTIFICATION_TYPE_CLUSTERING_COMPLETE
from app.core.constants import NOTIFICATION_TYPE_CLUSTERING_FILE_COMPLETE
from app.core.constants import NOTIFICATION_TYPE_CLUSTERING_PROGRESS
from app.db.base import get_db

logger = logging.getLogger(__name__)

# Shared Redis connection for WebSocket notifications.
# Lazily initialized on first use to avoid import-time errors.
_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    """Return a shared Redis connection, creating it on first call."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(settings.CELERY_BROKER_URL)
    try:
        _redis_client.ping()
    except (redis.ConnectionError, redis.TimeoutError):
        # Reconnect on stale/broken connection
        _redis_client = redis.Redis.from_url(settings.CELERY_BROKER_URL)
    return _redis_client


def _send_clustering_progress(
    user_id: int,
    step: int,
    total_steps: int,
    message: str,
    progress: float,
    running: bool = True,
):
    """Send clustering progress via WebSocket notification."""
    try:
        r = _get_redis()
        r.publish(
            "websocket_notifications",
            json.dumps(
                {
                    "user_id": user_id,
                    "type": NOTIFICATION_TYPE_CLUSTERING_PROGRESS,
                    "data": {
                        "step": step,
                        "total_steps": total_steps,
                        "message": message,
                        "progress": progress,
                        "running": running,
                    },
                }
            ),
        )
    except Exception as e:
        logger.debug(f"Failed to send clustering progress: {e}")


def _send_clustering_complete(user_id: int, result: dict):
    """Send clustering complete notification via WebSocket."""
    try:
        r = _get_redis()
        r.publish(
            "websocket_notifications",
            json.dumps(
                {
                    "user_id": user_id,
                    "type": NOTIFICATION_TYPE_CLUSTERING_COMPLETE,
                    "data": result,
                }
            ),
        )
    except Exception as e:
        logger.debug(f"Failed to send clustering complete: {e}")


def _send_clustering_file_complete(user_id: int, file_uuid: str, clusters_assigned: int):
    """Send per-file clustering complete notification via WebSocket."""
    try:
        r = _get_redis()
        r.publish(
            "websocket_notifications",
            json.dumps(
                {
                    "user_id": user_id,
                    "type": NOTIFICATION_TYPE_CLUSTERING_FILE_COMPLETE,
                    "data": {
                        "file_uuid": file_uuid,
                        "clusters_assigned": clusters_assigned,
                    },
                }
            ),
        )
    except Exception as e:
        logger.debug(f"Failed to send clustering file complete: {e}")


def _send_clustering_error(user_id: int, error_message: str):
    """Send clustering error notification via WebSocket."""
    try:
        r = _get_redis()
        r.publish(
            "websocket_notifications",
            json.dumps(
                {
                    "user_id": user_id,
                    "type": NOTIFICATION_TYPE_CLUSTERING_COMPLETE,
                    "data": {
                        "status": "error",
                        "error": error_message,
                        "running": False,
                    },
                }
            ),
        )
    except Exception as e:
        logger.debug(f"Failed to send clustering error: {e}")


@celery_app.task(
    name="app.tasks.speaker_clustering.cluster_speakers_for_file",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    priority=3,  # Automatic post-transcription clustering — lower than manual recluster
    queue="cpu",
    acks_late=True,
    reject_on_worker_lost=True,
)
def cluster_speakers_for_file(self, file_uuid: str, user_id: int):
    """Cluster speakers in a media file after transcription.

    Called as part of the post-transcription pipeline.

    Args:
        file_uuid: UUID of the media file.
        user_id: Owner user ID.
    """
    db = next(get_db())
    try:
        from app.models.media import MediaFile
        from app.services.speaker_clustering_service import SpeakerClusteringService

        media_file = db.query(MediaFile).filter(MediaFile.uuid == file_uuid).first()
        if not media_file:
            logger.warning(f"Media file {file_uuid} not found for clustering")
            return {"status": "skipped", "reason": "file_not_found"}

        service = SpeakerClusteringService(db)
        clusters = service.cluster_speakers_for_file(int(media_file.id), user_id)

        result = {
            "status": "completed",
            "file_uuid": file_uuid,
            "clusters_assigned": len(clusters),
        }
        logger.info(f"Clustered speakers for file {file_uuid}: {len(clusters)} cluster assignments")

        _send_clustering_file_complete(user_id, file_uuid, len(clusters))

        return result

    except Exception as e:
        logger.error(f"Error clustering speakers for file {file_uuid}: {e}")
        db.rollback()
        raise self.retry(exc=e) from e
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.speaker_clustering.recluster_all_speakers",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    priority=0,
    queue="gpu",
    acks_late=True,
    reject_on_worker_lost=True,
)
def recluster_all_speakers(self, user_id: int, threshold: float | None = None):
    """Full re-clustering of all speakers for a user.

    Triggered manually from the UI. Uses a per-user Redis lock to prevent
    concurrent re-clustering runs.

    Args:
        user_id: Owner user ID.
        threshold: Optional clustering threshold override.
    """
    from app.utils.task_lock import task_lock_manager

    lock_key = f"recluster_speakers_user_{user_id}"

    with task_lock_manager.acquire_lock(lock_key, timeout=600) as acquired:
        if not acquired:
            logger.info("Recluster lock held for user %d — retrying in 60s", user_id)
            raise self.retry(countdown=60, max_retries=30)

        db = next(get_db())
        try:
            from app.services.speaker_clustering_service import SpeakerClusteringService

            service = SpeakerClusteringService(db)

            def progress_cb(step: int, total: int, message: str, progress: float):
                _send_clustering_progress(user_id, step, total, message, progress)

            kwargs: dict = {"progress_callback": progress_cb}
            if threshold is not None:
                kwargs["threshold"] = threshold

            result = service.batch_recluster(user_id, **kwargs)

            logger.info(
                "Re-clustering complete for user %d: status=%s, "
                "clusters_created=%s, speakers_assigned=%s, singletons=%s",
                user_id,
                result.get("status"),
                result.get("clusters_created"),
                result.get("speakers_assigned"),
                result.get("singletons"),
            )

            _send_clustering_complete(user_id, result)

            return result

        except Exception as e:
            logger.error(f"Error re-clustering speakers for user {user_id}: {e}")
            db.rollback()
            if self.request.retries >= self.max_retries:
                _send_clustering_error(user_id, str(e))
                raise
            raise self.retry(exc=e) from e
        finally:
            db.close()
