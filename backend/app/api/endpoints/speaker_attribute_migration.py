"""
API endpoints for bulk speaker attribute detection migration.

Allows admins to trigger bulk processing of existing files for
speaker gender/age detection.
"""

import json
import logging

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_superuser
from app.db.base import get_db
from app.models.user import User
from app.tasks.speaker_attribute_migration_task import attribute_migration_progress

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/status")
async def get_attribute_migration_status(
    current_user: User = Depends(get_current_active_superuser),
    db: Session = Depends(get_db),
):
    """Get the current speaker attribute migration status.

    Returns file counts (total, processed, pending) and progress info.
    """
    from app.tasks.speaker_attribute_migration_task import _get_files_needing_attribute_detection

    try:
        files_needing_processing = _get_files_needing_attribute_detection(db)
        pending_count = len(files_needing_processing)

        from sqlalchemy import exists

        from app.models.media import FileStatus
        from app.models.media import MediaFile
        from app.models.media import Speaker as SpeakerModel

        total_with_speakers = (
            db.query(MediaFile)
            .filter(
                MediaFile.status == FileStatus.COMPLETED,
                exists().where(SpeakerModel.media_file_id == MediaFile.id),
            )
            .count()
        )

        # Get progress from Redis
        progress = attribute_migration_progress.get_status()

        # Include ETA from the unified progress tracker (if running)
        if progress.get("running"):
            from app.services.progress_tracker import ProgressTracker

            tracker_state = ProgressTracker.get_state("attribute_migration", current_user.id)
            if tracker_state and tracker_state.eta_seconds is not None:
                progress["eta_seconds"] = tracker_state.eta_seconds

        return {
            "total_files": total_with_speakers,
            "pending_files": pending_count,
            "progress": progress,
        }

    except Exception as e:
        logger.error("Error getting attribute migration status: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again.",
        ) from e


@router.post("/start")
async def start_attribute_migration(
    force: bool = False,
    current_user: User = Depends(get_current_active_superuser),
    db: Session = Depends(get_db),
):
    """Start bulk speaker attribute detection.

    Args:
        force: If True, reset all speaker attributes and reprocess all files.
    """
    from app.tasks.speaker_attribute_migration_task import migrate_speaker_attributes_task

    # Guard: THIS migration type already running
    if attribute_migration_progress.is_running():
        return {
            "status": "already_running",
            "message": "Speaker attribute migration is already in progress",
            "progress": attribute_migration_progress.get_status(),
        }

    try:
        # Dispatch — lock is ref-counted, multiple migrations can coexist
        task = migrate_speaker_attributes_task.delay(user_id=current_user.id, force=force)

        logger.info("Started speaker attribute migration task: %s", task.id)
        return {
            "status": "started",
            "task_id": task.id,
            "message": "Speaker attribute migration dispatched.",
        }

    except Exception as e:
        logger.error("Error starting attribute migration: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again.",
        ) from e


@router.post("/stop")
async def stop_attribute_migration(
    current_user: User = Depends(get_current_active_superuser),
    db: Session = Depends(get_db),
):
    """Stop a running speaker attribute migration.

    Marks migration as stopped and revokes pending batch tasks so they
    don't continue processing on the GPU queue.
    """
    try:
        if not attribute_migration_progress.is_running():
            return {
                "status": "not_running",
                "message": "No attribute migration is currently running",
            }

        success = attribute_migration_progress.force_stop()

        # Revoke pending batch tasks from the GPU queue
        revoked = 0
        try:
            r = attribute_migration_progress.redis_client
            if r:
                batch_ids_json = r.get(f"{attribute_migration_progress.key_prefix}:batch_task_ids")
                if batch_ids_json:
                    batch_ids = json.loads(batch_ids_json)
                    from app.core.celery import celery_app

                    for tid in batch_ids:
                        celery_app.control.revoke(tid, terminate=False)
                        revoked += 1
                    r.delete(f"{attribute_migration_progress.key_prefix}:batch_task_ids")
                    logger.info("Revoked %d pending batch tasks", revoked)
        except Exception as e:
            logger.warning("Failed to revoke batch tasks: %s", e)

        if success:
            logger.warning("Speaker attribute migration stopped by user")
            return {
                "status": "stopped",
                "message": f"Speaker attribute migration stopped. {revoked} pending tasks revoked.",
            }
        else:
            return {
                "status": "error",
                "message": "Failed to stop migration",
            }

    except Exception as e:
        logger.error("Error stopping attribute migration: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again.",
        ) from e


@router.delete("/progress")
async def clear_attribute_progress(
    current_user: User = Depends(get_current_active_superuser),
    db: Session = Depends(get_db),
):
    """Clear stale attribute migration progress data from Redis."""
    try:
        if attribute_migration_progress.is_running():
            return {
                "status": "error",
                "message": "Cannot clear progress while migration is running.",
            }

        success = attribute_migration_progress.clear_status()

        if success:
            return {"status": "cleared", "message": "Progress tracking cleared."}
        else:
            return {"status": "error", "message": "Failed to clear progress."}

    except Exception as e:
        logger.error("Error clearing attribute progress: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again.",
        ) from e
