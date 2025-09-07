import logging
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any
from typing import Optional

from celery.result import AsyncResult
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.celery import celery_app
from app.db.session_utils import get_refreshed_object
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.models.media import Task

logger = logging.getLogger(__name__)

# Task status constants
TASK_STATUS_PENDING = "pending"
TASK_STATUS_IN_PROGRESS = "in_progress"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"


def create_task_record(
    db: Session, celery_task_id: str, user_id: int, media_file_id: int, task_type: str
) -> Task:
    """Create a new task record in the database."""
    task = Task(
        id=celery_task_id,
        user_id=user_id,
        media_file_id=media_file_id,
        task_type=task_type,
        status=TASK_STATUS_PENDING,
        progress=0.0,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # Update the media file with active task tracking
    media_file = get_refreshed_object(db, MediaFile, media_file_id)
    if media_file:
        media_file.active_task_id = celery_task_id
        media_file.task_started_at = datetime.now(timezone.utc)
        media_file.task_last_update = datetime.now(timezone.utc)
        media_file.cancellation_requested = False
        if media_file.status == FileStatus.PENDING:
            media_file.status = FileStatus.PROCESSING
        db.commit()

    return task


def update_task_status(
    db: Session,
    task_id: str,
    status: str,
    progress: float = None,
    error_message: str = None,
    completed: bool = False,
) -> Optional[Task]:
    """Update task status in the database."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        logger.warning(f"Task {task_id} not found")
        return None

    # Log state transition for debugging
    logger.debug(f"Task {task_id} state change: {task.status} -> {status}")

    # Update task fields
    task.status = status
    if progress is not None:
        task.progress = progress
    if error_message:
        task.error_message = error_message
    if completed:
        task.completed_at = datetime.now(timezone.utc)

    # Always update the timestamp for task state changes
    task.updated_at = datetime.now(timezone.utc)

    # Update media file task tracking
    if task.media_file_id:
        media_file = get_refreshed_object(db, MediaFile, task.media_file_id)
        if media_file:
            media_file.task_last_update = datetime.now(timezone.utc)
            if error_message:
                media_file.last_error_message = error_message

            # Clear active task if completed or failed
            if status in [TASK_STATUS_COMPLETED, TASK_STATUS_FAILED]:
                media_file.active_task_id = None
                media_file.task_started_at = None

    db.commit()
    db.refresh(task)

    # If task is completed or failed, check if we need to update the media file status
    if status in [TASK_STATUS_COMPLETED, TASK_STATUS_FAILED] and task.media_file_id:
        update_media_file_from_task_status(db, task.media_file_id)

    return task


def update_media_file_status(
    db: Session, file_id: int, status: FileStatus
) -> Optional[MediaFile]:
    """Update media file status."""
    media_file = get_refreshed_object(db, MediaFile, file_id)
    if not media_file:
        logger.warning(f"Media file {file_id} not found")
        return None

    # Log state transition for debugging
    logger.debug(f"Media file {file_id} state change: {media_file.status} -> {status}")

    # Update status and timestamps
    media_file.status = status

    # Set completed_at timestamp if status is COMPLETED or ERROR
    if (
        status in [FileStatus.COMPLETED, FileStatus.ERROR]
        and not media_file.completed_at
    ):
        media_file.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(media_file)
    return media_file


def update_media_file_from_task_status(
    db: Session, file_id: int
) -> Optional[MediaFile]:
    """Check task statuses and update media file status accordingly.

    This function checks all tasks associated with a media file and updates
    the media file status based on task statuses:
    - If all tasks are completed, mark the file as COMPLETED
    - If any task is failed and no tasks are pending/in_progress, mark as ERROR
    - If any tasks are still pending/in_progress, leave as PROCESSING

    Args:
        db: Database session
        file_id: ID of the media file to check

    Returns:
        Updated MediaFile object or None if not found
    """
    media_file = get_refreshed_object(db, MediaFile, file_id)
    if not media_file:
        logger.warning(f"Media file {file_id} not found")
        return None

    # Skip if the file is already in a terminal state
    if media_file.status in [FileStatus.COMPLETED, FileStatus.ERROR]:
        return media_file

    # Get all tasks for this media file
    tasks = db.query(Task).filter(Task.media_file_id == file_id).all()
    if not tasks:
        logger.warning(f"No tasks found for media file {file_id}")
        return media_file

    # Count task statuses
    counts = {
        TASK_STATUS_PENDING: 0,
        TASK_STATUS_IN_PROGRESS: 0,
        TASK_STATUS_COMPLETED: 0,
        TASK_STATUS_FAILED: 0,
    }

    for task in tasks:
        counts[task.status] = counts.get(task.status, 0) + 1

    # Determine the appropriate media file status
    if counts[TASK_STATUS_PENDING] > 0 or counts[TASK_STATUS_IN_PROGRESS] > 0:
        # Still has active tasks
        new_status = FileStatus.PROCESSING
    elif counts[TASK_STATUS_FAILED] > 0 and counts[TASK_STATUS_COMPLETED] == 0:
        # All finished tasks failed
        new_status = FileStatus.ERROR
    else:
        # All tasks completed successfully
        new_status = FileStatus.COMPLETED

    # Only update if status is changing
    if media_file.status != new_status:
        return update_media_file_status(db, file_id, new_status)

    return media_file


def get_task_summary_for_media_file(db: Session, file_id: int) -> dict[str, Any]:
    """Get a summary of task statuses for a media file.

    Args:
        db: Database session
        file_id: ID of the media file to check

    Returns:
        Dictionary with task status counts and overall progress
    """
    tasks = db.query(Task).filter(Task.media_file_id == file_id).all()

    summary = {
        "total": len(tasks),
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
        "overall_progress": 0.0,
    }

    if not tasks:
        return summary

    # Count tasks by status and calculate overall progress
    total_progress = 0.0
    for task in tasks:
        summary[task.status] = summary.get(task.status, 0) + 1
        total_progress += task.progress

    summary["overall_progress"] = total_progress / len(tasks)

    return summary


def cancel_active_task(db: Session, file_id: int) -> bool:
    """Cancel the active task for a media file.

    Args:
        db: Database session
        file_id: ID of the media file

    Returns:
        True if task was cancelled, False otherwise
    """
    media_file = get_refreshed_object(db, MediaFile, file_id)
    if not media_file or not media_file.active_task_id:
        return False

    try:
        # Revoke the Celery task
        celery_app.control.revoke(media_file.active_task_id, terminate=True)

        # Update task status in database
        task = db.query(Task).filter(Task.id == media_file.active_task_id).first()
        if task:
            task.status = TASK_STATUS_FAILED
            task.error_message = "Task cancelled by user"
            task.completed_at = datetime.now(timezone.utc)

        # Update media file status
        media_file.status = FileStatus.CANCELLED
        media_file.active_task_id = None
        media_file.task_started_at = None
        media_file.cancellation_requested = False

        db.commit()
        logger.info(f"Successfully cancelled task for file {file_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to cancel task for file {file_id}: {e}")
        return False


def check_for_stuck_files(db: Session, stuck_threshold_hours: float = 2.0) -> list[int]:
    """Find files that appear to be stuck in processing or pending.

    Args:
        db: Database session
        stuck_threshold_hours: Hours (float) after which a file is considered stuck

    Returns:
        List of file IDs that appear stuck
    """
    threshold_time = datetime.now(timezone.utc) - timedelta(hours=stuck_threshold_hours)

    # Check for stuck processing files
    processing_stuck_files = (
        db.query(MediaFile)
        .filter(
            MediaFile.status == FileStatus.PROCESSING,
            or_(
                MediaFile.task_last_update < threshold_time,
                MediaFile.task_last_update.is_(None),
            ),
        )
        .all()
    )

    # Check for stuck pending files (uploaded but never started processing)
    pending_stuck_files = (
        db.query(MediaFile)
        .filter(
            MediaFile.status == FileStatus.PENDING,
            MediaFile.upload_time < threshold_time,
        )
        .all()
    )

    # Check for failed files that can be immediately retried (no time threshold needed)
    failed_files = (
        db.query(MediaFile)
        .filter(
            MediaFile.status == FileStatus.ERROR,
            MediaFile.retry_count < MediaFile.max_retries,
        )
        .all()
    )

    # Check for orphaned files that need recovery
    orphaned_files = (
        db.query(MediaFile).filter(MediaFile.status == FileStatus.ORPHANED).all()
    )

    # Combine all lists
    stuck_files = (
        processing_stuck_files + pending_stuck_files + failed_files + orphaned_files
    )

    stuck_file_ids = []
    for file in stuck_files:
        # Double-check by querying Celery task status if we have an active task ID
        if file.active_task_id:
            try:
                task_result = AsyncResult(file.active_task_id)
                if task_result.state in ["FAILURE", "REVOKED", "RETRY"]:
                    stuck_file_ids.append(file.id)
                elif task_result.state == "SUCCESS":
                    # Task completed but file status wasn't updated
                    file.status = FileStatus.COMPLETED
                    file.active_task_id = None
                    file.task_started_at = None
                    db.commit()
            except Exception as e:
                logger.warning(
                    f"Could not check task status for {file.active_task_id}: {e}"
                )
                stuck_file_ids.append(file.id)
        else:
            # No active task but still processing - definitely stuck
            # OR it's a pending file that never started processing
            stuck_file_ids.append(file.id)

    return stuck_file_ids


def recover_stuck_file(db: Session, file_id: int) -> bool:
    """Attempt to recover a stuck file.

    Args:
        db: Database session
        file_id: ID of the stuck file

    Returns:
        True if recovery was successful, False otherwise
    """
    media_file = get_refreshed_object(db, MediaFile, file_id)
    if not media_file:
        return False

    try:
        # Cancel any active task
        if media_file.active_task_id:
            cancel_active_task(db, file_id)

        # Update file status based on current state and what we can determine
        if media_file.status == FileStatus.PENDING:
            # File never started processing - trigger a new transcription task
            logger.info(f"File {file_id} stuck in pending, restarting processing")

            # Start new transcription task
            import os

            if os.environ.get("SKIP_CELERY", "False").lower() != "true":
                from app.tasks.transcription import transcribe_audio_task

                task = transcribe_audio_task.delay(file_id)
                logger.info(
                    f"Started recovery task {task.id} for pending file {file_id}"
                )

            # File status will be updated by the task
            return True

        elif (
            media_file.status == FileStatus.ERROR
            and media_file.retry_count < media_file.max_retries
        ):
            # Failed file that can be retried - use the reset and retry logic
            logger.info(
                f"File {file_id} failed, attempting retry (attempt {media_file.retry_count + 1})"
            )

            # Reset for retry
            success = reset_file_for_retry(db, file_id, reset_retry_count=False)
            if success:
                # Start new transcription task
                import os

                if os.environ.get("SKIP_CELERY", "False").lower() != "true":
                    from app.tasks.transcription import transcribe_audio_task

                    task = transcribe_audio_task.delay(file_id)
                    logger.info(
                        f"Started retry task {task.id} for failed file {file_id}"
                    )
                return True
            return False

        elif media_file.status == FileStatus.ORPHANED:
            # Orphaned file - try to restart processing
            logger.info(f"File {file_id} orphaned, attempting recovery restart")

            # Reset status to pending and try again
            media_file.status = FileStatus.PENDING
            media_file.active_task_id = None
            media_file.task_started_at = None
            db.commit()

            # Start new transcription task
            import os

            if os.environ.get("SKIP_CELERY", "False").lower() != "true":
                from app.tasks.transcription import transcribe_audio_task

                task = transcribe_audio_task.delay(file_id)
                logger.info(
                    f"Started recovery task {task.id} for orphaned file {file_id}"
                )
            return True

        elif media_file.transcript_segments:
            # Has transcript data, mark as completed
            media_file.status = FileStatus.COMPLETED
            media_file.completed_at = datetime.now(timezone.utc)
        else:
            # No transcript data, mark as orphaned for potential retry
            media_file.status = FileStatus.ORPHANED
            media_file.force_delete_eligible = True

        # Update recovery tracking
        media_file.recovery_attempts += 1
        media_file.last_recovery_attempt = datetime.now(timezone.utc)
        media_file.active_task_id = None
        media_file.task_started_at = None

        db.commit()
        logger.info(f"Recovered stuck file {file_id}, new status: {media_file.status}")
        return True

    except Exception as e:
        logger.error(f"Failed to recover stuck file {file_id}: {e}")
        return False


def is_file_safe_to_delete(db: Session, file_id: int) -> tuple[bool, str]:
    """Check if a file is safe to delete (no active processing).

    Args:
        db: Database session
        file_id: ID of the file to check

    Returns:
        Tuple of (is_safe, reason)
    """
    media_file = get_refreshed_object(db, MediaFile, file_id)
    if not media_file:
        return False, "File not found"

    # Check if file has an active task
    if media_file.active_task_id and media_file.status == FileStatus.PROCESSING:
        # Double-check with Celery
        try:
            task_result = AsyncResult(media_file.active_task_id)
            if task_result.state in ["PENDING", "STARTED", "RETRY"]:
                return (
                    False,
                    f"File is currently being processed (task: {media_file.active_task_id})",
                )
        except Exception:
            # If we can't check task status, assume it's safe
            pass

    # Safe to delete in these states
    safe_states = [
        FileStatus.COMPLETED,
        FileStatus.ERROR,
        FileStatus.CANCELLED,
        FileStatus.ORPHANED,
    ]
    if media_file.status in safe_states:
        return True, "File is not actively processing"

    # Pending files might be picked up soon
    if media_file.status == FileStatus.PENDING:
        return True, "File is pending but not yet processing"

    return False, f"File status is {media_file.status}"


def reset_file_for_retry(
    db: Session, file_id: int, reset_retry_count: bool = False
) -> bool:
    """Reset a file for retry processing.

    Args:
        db: Database session
        file_id: ID of the file to reset
        reset_retry_count: Whether to reset the retry count to 0

    Returns:
        True if reset was successful, False otherwise
    """
    media_file = get_refreshed_object(db, MediaFile, file_id)
    if not media_file:
        return False

    try:
        # Cancel any active task first
        if media_file.active_task_id:
            cancel_active_task(db, file_id)

        # Reset retry count if requested
        if reset_retry_count:
            media_file.retry_count = 0
        else:
            media_file.retry_count += 1

        # Reset file state
        media_file.status = FileStatus.PENDING
        media_file.active_task_id = None
        media_file.task_started_at = None
        media_file.task_last_update = None
        media_file.cancellation_requested = False
        media_file.last_error_message = None
        media_file.force_delete_eligible = False

        # Clear existing transcript data for clean retry
        from app.models.media import Analytics
        from app.models.media import Speaker
        from app.models.media import TranscriptSegment

        # Delete existing transcript segments
        db.query(TranscriptSegment).filter(
            TranscriptSegment.media_file_id == file_id
        ).delete()

        # Delete existing speakers
        db.query(Speaker).filter(Speaker.media_file_id == file_id).delete()

        # Delete existing analytics
        db.query(Analytics).filter(Analytics.media_file_id == file_id).delete()

        # Clear related task records for clean slate
        db.query(Task).filter(Task.media_file_id == file_id).delete()

        db.commit()
        logger.info(
            f"Reset file {file_id} for retry (attempt {media_file.retry_count})"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to reset file {file_id} for retry: {e}")
        db.rollback()
        return False
