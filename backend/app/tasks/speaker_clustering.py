"""Celery tasks for speaker clustering and audio clip extraction."""

import logging

from app.core.celery import celery_app
from app.db.base import get_db

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.speaker_clustering.cluster_speakers_for_file",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="cpu",
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
    queue="cpu",
)
def recluster_all_speakers(self, user_id: int, threshold: float | None = None):
    """Full re-clustering of all speakers for a user.

    Triggered manually from the UI.

    Args:
        user_id: Owner user ID.
        threshold: Optional clustering threshold override.
    """
    db = next(get_db())
    try:
        from app.services.speaker_clustering_service import SpeakerClusteringService

        service = SpeakerClusteringService(db)

        if threshold:
            result = service.batch_recluster(user_id, threshold=threshold)
        else:
            result = service.batch_recluster(user_id)

        logger.info(f"Re-clustering complete for user {user_id}: {result}")
        return result

    except Exception as e:
        logger.error(f"Error re-clustering speakers for user {user_id}: {e}")
        db.rollback()
        raise self.retry(exc=e) from e
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.speaker_clustering.extract_speaker_audio_clips",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="cpu",
)
def extract_speaker_audio_clips(self, file_uuid: str, user_id: int):
    """Extract audio clips for all speakers in a media file.

    Called as part of the post-transcription pipeline.

    Args:
        file_uuid: UUID of the media file.
        user_id: Owner user ID.
    """
    db = next(get_db())
    try:
        from app.models.media import MediaFile
        from app.services.speaker_audio_clip_service import SpeakerAudioClipService

        media_file = db.query(MediaFile).filter(MediaFile.uuid == file_uuid).first()
        if not media_file:
            logger.warning(f"Media file {file_uuid} not found for clip extraction")
            return {"status": "skipped", "reason": "file_not_found"}

        service = SpeakerAudioClipService(db)
        clips = service.extract_clips_for_file(int(media_file.id), user_id)

        result = {
            "status": "completed",
            "file_uuid": file_uuid,
            "clips_extracted": len(clips),
        }
        logger.info(f"Extracted {len(clips)} audio clips for file {file_uuid}")
        return result

    except Exception as e:
        logger.error(f"Error extracting audio clips for file {file_uuid}: {e}")
        db.rollback()
        raise self.retry(exc=e) from e
    finally:
        db.close()
