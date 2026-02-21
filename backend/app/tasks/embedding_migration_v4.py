"""
Speaker embedding migration task for v3→v4 upgrade.

This module provides the migration infrastructure for upgrading speaker
embeddings from PyAnnote v3 (512-dim) to v4 (256-dim WeSpeaker).

Includes safeguards against concurrent migrations and progress tracking via Redis.
WebSocket notifications are sent for real-time progress updates via Redis pub/sub.
"""

import logging

from app.core.celery import celery_app
from app.core.config import settings
from app.core.constants import NOTIFICATION_TYPE_MIGRATION_COMPLETE
from app.core.constants import NOTIFICATION_TYPE_MIGRATION_PROGRESS
from app.db.session_utils import session_scope
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.services.embedding_mode_service import MODE_V4
from app.services.embedding_mode_service import EmbeddingModeService
from app.services.migration_progress_service import migration_progress

logger = logging.getLogger(__name__)


def _send_migration_notification(
    notification_type: str,
    data: dict,
    user_id: int | None = None,
) -> None:
    """Send a migration progress notification via Redis pub/sub for WebSocket delivery.

    Args:
        notification_type: Type of notification (progress or complete).
        data: Notification data payload.
        user_id: Optional user ID to send to specific user.
    """
    try:
        import json

        import redis

        # Use same pattern as transcription notifications
        redis_client = redis.from_url(settings.REDIS_URL)

        # Send to all connected users (admin broadcast)
        # If user_id is provided, send to that user only
        target_user = user_id if user_id else 1  # Default to admin user

        notification = {
            "user_id": target_user,
            "type": notification_type,
            "data": data,
        }

        redis_client.publish("websocket_notifications", json.dumps(notification))
        logger.info(f"Published migration notification via Redis: {notification_type}")

    except Exception as e:
        logger.error(f"Failed to send migration notification: {e}")


def get_migration_status() -> dict:
    """Get the current migration status."""
    from app.services.opensearch_service import get_opensearch_client

    client = get_opensearch_client()
    if not client:
        return {"status": "error", "message": "OpenSearch not available"}

    current_mode = EmbeddingModeService.detect_mode()

    # Check if v4 index exists
    v4_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4"
    v4_exists = client.indices.exists(index=v4_index)

    # Get document counts
    try:
        v3_count = (
            client.count(index=settings.OPENSEARCH_SPEAKER_INDEX)["count"]
            if client.indices.exists(index=settings.OPENSEARCH_SPEAKER_INDEX)
            else 0
        )
        v4_count = client.count(index=v4_index)["count"] if v4_exists else 0
    except Exception:
        v3_count = 0
        v4_count = 0

    return {
        "current_mode": current_mode,
        "v4_index_exists": v4_exists,
        "v3_document_count": v3_count,
        "v4_document_count": v4_count,
        "migration_needed": current_mode == "v3",
        "migration_complete": current_mode == "v4"
        and not client.indices.exists(index=settings.OPENSEARCH_SPEAKER_INDEX + "_v3_backup"),
    }


@celery_app.task(bind=True, name="check_migration_status", queue="utility")
def check_migration_status_task(self):
    """Check the current embedding migration status."""
    return get_migration_status()


@celery_app.task(bind=True, name="migrate_speaker_embeddings_to_v4", queue="cpu")
def migrate_speaker_embeddings_v4_task(self, user_id: int | None = None):
    """
    Orchestrate migration of all speaker embeddings to v4.

    This CPU task coordinates the migration but dispatches actual
    embedding extraction to GPU workers for performance.

    Includes safeguards to prevent concurrent migrations.

    Args:
        user_id: Optional user ID to migrate (None for all users)
    """
    from app.services.opensearch_service import create_speaker_index_v4

    task_id = self.request.id
    logger.info(f"Starting speaker embedding migration to v4: task_id={task_id}")

    # Check if a migration is already running
    if migration_progress.is_running():
        logger.warning("Migration already in progress, skipping")
        return {
            "status": "skipped",
            "message": "A migration is already in progress",
            "existing_status": migration_progress.get_status(),
        }

    # Check current mode
    current_mode = EmbeddingModeService.detect_mode()
    if current_mode == MODE_V4:
        logger.info("Already in v4 mode, no migration needed")
        return {"status": "skipped", "message": "Already using v4 embeddings"}

    # Create the v4 staging index before processing files
    if not create_speaker_index_v4():
        logger.error("Failed to create v4 staging index")
        return {"status": "error", "message": "Failed to create v4 staging index"}

    # Get all completed media files that need migration
    with session_scope() as db:
        query = db.query(MediaFile).filter(MediaFile.status == FileStatus.COMPLETED)
        if user_id:
            query = query.filter(MediaFile.user_id == user_id)
        media_files = query.all()

        total_files = len(media_files)
        logger.info(f"Found {total_files} media files to migrate")

        if total_files == 0:
            return {"status": "success", "message": "No files to migrate", "migrated": 0}

        # Start tracking migration progress in Redis
        migration_progress.start_migration(total_files=total_files, task_id=task_id)

        # Send initial progress notification
        _send_migration_notification(
            NOTIFICATION_TYPE_MIGRATION_PROGRESS,
            {
                "processed_files": 0,
                "total_files": total_files,
                "failed_files": [],
                "progress": 0,
                "running": True,
            },
            user_id,
        )

        # Dispatch extraction tasks for each file
        for i, media_file in enumerate(media_files):
            # Dispatch to GPU queue for actual embedding extraction
            extract_v4_embeddings_task.delay(
                file_uuid=str(media_file.uuid),
                task_index=i,
                total_tasks=total_files,
                user_id=media_file.user_id,
            )

            if (i + 1) % 10 == 0:
                logger.info(f"Dispatched {i + 1}/{total_files} migration tasks")

    return {
        "status": "in_progress",
        "message": f"Dispatched {total_files} migration tasks",
        "total_files": total_files,
        "task_id": task_id,
    }


def _build_speaker_segments(db, media_file_id: int) -> dict[int, list[dict[str, float]]]:
    """Build mapping of speaker ID to their transcript segments.

    Args:
        db: Database session.
        media_file_id: ID of the media file.

    Returns:
        Dictionary mapping speaker_id to list of segment time ranges.
    """
    from app.models.media import TranscriptSegment

    segments = (
        db.query(TranscriptSegment).filter(TranscriptSegment.media_file_id == media_file_id).all()
    )

    speaker_segments: dict[int, list[dict[str, float]]] = {}
    for seg in segments:
        if seg.speaker_id not in speaker_segments:
            speaker_segments[seg.speaker_id] = []
        speaker_segments[seg.speaker_id].append(
            {
                "start": seg.start_time,
                "end": seg.end_time,
            }
        )

    return speaker_segments


def _extract_and_store_speaker_embedding(
    speaker,
    media_file,
    speaker_segments: dict[int, list[dict[str, float]]],
    audio_path: str,
    embedding_service,
) -> bool:
    """Extract embedding for a single speaker and store in OpenSearch.

    Args:
        speaker: Speaker database object.
        media_file: MediaFile database object.
        speaker_segments: Mapping of speaker ID to segments.
        audio_path: Path to audio file.
        embedding_service: SpeakerEmbeddingService instance.

    Returns:
        True if embedding was extracted and stored, False otherwise.
    """
    from app.services.opensearch_service import add_speaker_embedding_v4

    if speaker.id not in speaker_segments:
        return False

    segs = speaker_segments[speaker.id]
    if not segs:
        return False

    # Use longest segments for embedding
    segs.sort(key=lambda x: x["end"] - x["start"], reverse=True)
    selected_segs = segs[:5]  # Up to 5 longest segments

    embeddings = []
    for seg in selected_segs:
        if seg["end"] - seg["start"] < 0.5:  # Skip short segments
            continue
        embedding = embedding_service.extract_embedding_from_file(audio_path, seg)
        if embedding is not None:
            embeddings.append(embedding)

    if not embeddings:
        return False

    # Aggregate and store
    aggregated = embedding_service.aggregate_embeddings(embeddings)

    # Index in OpenSearch (v4 staging index)
    add_speaker_embedding_v4(
        speaker_id=speaker.id,
        speaker_uuid=str(speaker.uuid),
        user_id=media_file.user_id,
        name=speaker.name,
        embedding=aggregated.tolist(),
        profile_id=speaker.profile_id,
        profile_uuid=str(speaker.profile.uuid) if speaker.profile_id and speaker.profile else None,
        media_file_id=media_file.id,
        segment_count=len(embeddings),
    )
    return True


@celery_app.task(bind=True, name="extract_v4_embeddings", queue="gpu")
def extract_v4_embeddings_task(
    self,
    file_uuid: str,
    task_index: int = 0,
    total_tasks: int = 1,
    user_id: int | None = None,
):
    """
    Extract v4 embeddings for a single media file.

    This runs on the GPU queue for optimal performance.
    Updates migration progress in Redis after completion.
    Sends WebSocket notifications for real-time progress.
    """
    import os
    import tempfile

    from app.models.media import Speaker
    from app.services.minio_service import download_file
    from app.services.speaker_embedding_service import SpeakerEmbeddingService
    from app.utils.uuid_helpers import get_file_by_uuid

    logger.info(f"Extracting v4 embeddings for file {file_uuid} ({task_index + 1}/{total_tasks})")

    with session_scope() as db:
        media_file = get_file_by_uuid(db, file_uuid)
        if not media_file:
            logger.error(f"Media file {file_uuid} not found")
            migration_progress.increment_processed(success=False, file_uuid=file_uuid)
            return {"status": "error", "message": "File not found"}

        speakers = db.query(Speaker).filter(Speaker.media_file_id == media_file.id).all()
        if not speakers:
            logger.info(f"No speakers found for file {file_uuid}")
            migration_progress.increment_processed(success=True, file_uuid=file_uuid)
            _check_migration_completion(task_index, total_tasks, user_id)
            return {"status": "skipped", "message": "No speakers to migrate"}

        try:
            file_data, _, _ = download_file(media_file.storage_path)  # type: ignore[arg-type]
        except Exception as e:
            logger.error(f"Failed to download file {file_uuid}: {e}")
            migration_progress.increment_processed(success=False, file_uuid=file_uuid)
            return {"status": "error", "message": f"Download failed: {e}"}

    # Process in temp directory
    with tempfile.TemporaryDirectory() as temp_dir:
        audio_path = os.path.join(temp_dir, "audio.wav")
        with open(audio_path, "wb") as f:
            f.write(file_data.read())

        embedding_service = SpeakerEmbeddingService(mode=MODE_V4)
        migrated_count = 0
        success = True

        try:
            with session_scope() as db:
                speaker_segments = _build_speaker_segments(db, media_file.id)  # type: ignore[arg-type]

                for speaker in speakers:
                    if _extract_and_store_speaker_embedding(
                        speaker, media_file, speaker_segments, audio_path, embedding_service
                    ):
                        migrated_count += 1

                logger.info(f"Migrated {migrated_count} speakers for file {file_uuid}")

        except Exception as e:
            logger.error(f"Error extracting embeddings for {file_uuid}: {e}")
            success = False

        finally:
            embedding_service.cleanup()

    migration_progress.increment_processed(
        success=success, file_uuid=file_uuid if not success else None
    )

    # Check if this was the last task and send progress notification
    _check_migration_completion(task_index, total_tasks, user_id)

    return {
        "status": "success" if success else "error",
        "file_uuid": file_uuid,
        "speakers_migrated": migrated_count,
        "task_index": task_index,
        "total_tasks": total_tasks,
    }


def _check_migration_completion(
    task_index: int, total_tasks: int, user_id: int | None = None
) -> None:
    """
    Check if all migration tasks are complete and mark migration as finished.

    This is called after each task completes to check if we've reached the end.
    Uses the Redis progress tracking to determine if all tasks are done.
    Sends WebSocket notifications for progress updates.
    """
    status = migration_progress.get_status()
    processed = status.get("processed_files", 0)
    total = status.get("total_files", 0)
    failed_files = status.get("failed_files", [])

    # Send progress notification
    progress_data = {
        "processed_files": processed,
        "total_files": total,
        "failed_files": failed_files,
        "progress": processed / total if total > 0 else 0,
        "running": processed < total,
    }
    _send_migration_notification(NOTIFICATION_TYPE_MIGRATION_PROGRESS, progress_data, user_id)

    if processed >= total and total > 0:
        logger.info(f"All {total} migration tasks completed")
        migration_progress.complete_migration(success=True)

        # Send completion notification
        _send_migration_notification(
            NOTIFICATION_TYPE_MIGRATION_COMPLETE,
            {
                "status": "complete",
                "total_files": total,
                "failed_files": failed_files,
                "success_count": total - len(failed_files),
            },
            user_id,
        )


@celery_app.task(bind=True, name="finalize_v4_migration", queue="utility")
def finalize_v4_migration_task(self):
    """
    Finalize the v4 migration by swapping indices.

    This should be called after all extraction tasks complete.
    Clears the migration progress tracking upon successful completion.
    """
    from app.services.opensearch_service import get_opensearch_client

    client = get_opensearch_client()
    if not client:
        return {"status": "error", "message": "OpenSearch not available"}

    try:
        v4_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4"
        backup_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v3_backup"

        # Check v4 index exists and has documents
        if not client.indices.exists(index=v4_index):
            return {"status": "error", "message": "V4 index does not exist"}

        v4_count = client.count(index=v4_index)["count"]
        if v4_count == 0:
            return {"status": "error", "message": "V4 index is empty"}

        # Backup the current v3 index by reindexing to backup
        if client.indices.exists(index=settings.OPENSEARCH_SPEAKER_INDEX):
            # Use reindex API to copy to backup
            client.reindex(
                body={
                    "source": {"index": settings.OPENSEARCH_SPEAKER_INDEX},
                    "dest": {"index": backup_index},
                },
                wait_for_completion=True,
            )
            logger.info(f"Created backup: {backup_index}")

        # Delete old main index
        client.indices.delete(index=settings.OPENSEARCH_SPEAKER_INDEX, ignore=[404])

        # Rename v4 to main using reindex
        client.reindex(
            body={
                "source": {"index": v4_index},
                "dest": {"index": settings.OPENSEARCH_SPEAKER_INDEX},
            },
            wait_for_completion=True,
        )

        # Delete the temp v4 index
        client.indices.delete(index=v4_index, ignore=[404])

        # Clear the mode cache so it re-detects as v4
        EmbeddingModeService.clear_cache()

        # Clear migration progress tracking (migration is fully complete)
        migration_progress.clear_status()

        logger.info("V4 migration finalized successfully")
        return {
            "status": "success",
            "message": "Migration complete",
            "v4_documents": v4_count,
        }

    except Exception as e:
        logger.error(f"Error finalizing migration: {e}")
        return {"status": "error", "message": str(e)}
