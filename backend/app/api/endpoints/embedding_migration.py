"""
API endpoints for speaker embedding migration (v3 to v4).

Includes safeguards against concurrent migrations and progress tracking.
"""

import logging

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_superuser
from app.db.base import get_db
from app.models.user import User
from app.services.embedding_mode_service import EmbeddingModeService
from app.services.migration_lock_service import migration_lock
from app.services.migration_progress_service import migration_progress

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/status")
async def get_migration_status(
    current_user: User = Depends(get_current_active_superuser),
    db: Session = Depends(get_db),
):
    """
    Get the current speaker embedding migration status.

    Returns information about:
    - Current embedding mode (v3 or v4)
    - Whether migration is needed
    - Document counts in each index
    - Progress tracking (if migration is running)
    """
    from app.tasks.embedding_migration_v4 import get_migration_status

    try:
        status = get_migration_status()

        # Add mode info
        status["mode_info"] = EmbeddingModeService.get_mode_info()

        # Add progress tracking info from Redis
        progress = migration_progress.get_status()
        status["progress"] = progress

        # Indicate whether transcription is paused by migration lock
        status["transcription_paused"] = migration_lock.is_active()

        return status

    except Exception as e:
        logger.error("Error getting migration status: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again.",
        ) from e


@router.get("/progress")
async def get_migration_progress(
    current_user: User = Depends(get_current_active_superuser),
    db: Session = Depends(get_db),
):
    """
    Get detailed migration progress information.

    Returns:
    - running: Whether a migration is currently in progress
    - total_files: Total number of files to process
    - processed_files: Number of files processed so far
    - failed_files: List of file UUIDs that failed
    - started_at: When the migration started
    - completed_at: When the migration completed (if finished)
    - last_updated: Last progress update timestamp
    """
    try:
        return migration_progress.get_status()
    except Exception as e:
        logger.error("Error getting migration progress: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again.",
        ) from e


@router.post("/start")
async def start_migration(
    user_id: int | None = None,
    current_user: User = Depends(get_current_active_superuser),
    db: Session = Depends(get_db),
):
    """
    Start the speaker embedding migration from v3 to v4.

    This is an async operation - it dispatches Celery tasks and returns immediately.
    Use the /status or /progress endpoints to monitor progress.

    Args:
        user_id: Optional user ID to migrate (None for all users)

    Returns:
        - status: "started", "skipped", or "error"
        - task_id: Celery task ID (if started)
        - message: Human-readable status message
        - progress: Current progress info (if migration already running)
    """
    from app.tasks.embedding_migration_v4 import migrate_speaker_embeddings_v4_task

    # Check if migration lock is already held (another migration in progress)
    if migration_lock.is_active():
        return {
            "status": "already_running",
            "message": "Migration lock is active — another migration is in progress",
            "transcription_paused": True,
        }

    # Check if a migration is already running
    if migration_progress.is_running():
        progress = migration_progress.get_status()
        return {
            "status": "already_running",
            "message": "A migration is already in progress",
            "progress": progress,
        }

    # Check if already in v4 mode
    current_mode = EmbeddingModeService.detect_mode()
    if current_mode == "v4":
        return {
            "status": "skipped",
            "message": "Already using v4 embeddings, no migration needed",
        }

    try:
        # Dispatch the migration task
        task = migrate_speaker_embeddings_v4_task.delay(user_id=user_id)

        logger.info(f"Started embedding migration task: {task.id}")

        return {
            "status": "started",
            "task_id": task.id,
            "message": "Migration task dispatched. Check /status or /progress for updates.",
        }

    except Exception as e:
        logger.error("Error starting migration: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again.",
        ) from e


@router.post("/stop")
async def stop_migration(
    current_user: User = Depends(get_current_active_superuser),
    db: Session = Depends(get_db),
):
    """
    Force stop a running migration.

    Note: This does not actually stop running Celery tasks - they will continue
    to completion. This endpoint marks the migration as stopped and prevents
    new tasks from being dispatched.

    For a full stop, you would need to revoke the Celery tasks manually.
    """
    try:
        if not migration_progress.is_running():
            return {
                "status": "not_running",
                "message": "No migration is currently running",
            }

        success = migration_progress.force_stop()

        # Release migration lock so transcription can resume
        migration_lock.deactivate()

        if success:
            logger.warning("Migration force stopped by user")
            return {
                "status": "stopped",
                "message": "Migration stopped and transcription lock released.",
            }
        else:
            return {
                "status": "error",
                "message": "Failed to stop migration",
            }

    except Exception as e:
        logger.error("Error stopping migration: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again.",
        ) from e


@router.post("/finalize")
async def finalize_migration(
    current_user: User = Depends(get_current_active_superuser),
    db: Session = Depends(get_db),
):
    """
    Finalize the v4 migration by swapping indices.

    This should be called after all extraction tasks complete.
    It will:
    1. Backup the current v3 index
    2. Swap the v4 index to be the primary
    3. Clear the mode cache
    4. Clear migration progress tracking

    Note: Check /progress endpoint to ensure all tasks are complete before calling.
    """
    from app.tasks.embedding_migration_v4 import finalize_v4_migration_task

    # Check if migration is still running
    progress = migration_progress.get_status()
    if progress.get("running"):
        processed = progress.get("processed_files", 0)
        total = progress.get("total_files", 0)
        return {
            "status": "still_running",
            "message": f"Migration still in progress ({processed}/{total} files processed). "
            "Wait for completion before finalizing.",
            "progress": progress,
        }

    try:
        task = finalize_v4_migration_task.delay()

        logger.info(f"Started finalization task: {task.id}")

        return {
            "status": "started",
            "task_id": task.id,
            "message": "Finalization task dispatched.",
        }

    except Exception as e:
        logger.error("Error starting finalization: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again.",
        ) from e


@router.delete("/progress")
async def clear_progress(
    current_user: User = Depends(get_current_active_superuser),
    db: Session = Depends(get_db),
):
    """
    Clear the migration progress tracking from Redis.

    Use this to reset stale progress data if a migration was interrupted
    and you want to start fresh.

    Warning: Only use this if you are sure no migration is running.
    """
    try:
        if migration_progress.is_running():
            return {
                "status": "error",
                "message": "Cannot clear progress while migration is running. Use /stop first.",
            }

        success = migration_progress.clear_status()

        if success:
            return {
                "status": "cleared",
                "message": "Migration progress tracking cleared.",
            }
        else:
            return {
                "status": "error",
                "message": "Failed to clear progress. Redis may be unavailable.",
            }

    except Exception as e:
        logger.error("Error clearing progress: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again.",
        ) from e


@router.get("/mode")
async def get_embedding_mode(
    current_user: User = Depends(get_current_active_superuser),
    db: Session = Depends(get_db),
):
    """
    Get detailed information about the current embedding mode.
    """
    return EmbeddingModeService.get_mode_info()
