"""
Task recovery service for handling recovery operations.

This service is responsible for performing recovery actions on tasks and files
identified as problematic. It follows the single responsibility principle
by separating recovery actions from detection.
"""

import logging
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from sqlalchemy.orm import Session

from app.core.task_config import task_recovery_config
from app.db.session_utils import get_refreshed_object
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.models.media import Task
from app.utils.task_utils import update_media_file_status
from app.utils.task_utils import update_task_status

logger = logging.getLogger(__name__)


class TaskRecoveryService:
    """Service for performing task and file recovery operations."""

    def __init__(self, config=None):
        """Initialize with optional configuration override."""
        self.config = config or task_recovery_config

    def recover_stuck_task(self, db: Session, task: Task) -> bool:
        """
        Attempt to recover a stuck task.

        Args:
            db: Database session
            task: The stuck task to recover

        Returns:
            bool: True if recovery was successful, False otherwise
        """
        try:
            logger.info(
                f"Recovering stuck task {task.id} of type {task.task_type} "
                f"for media file {task.media_file_id}"
            )

            # Update task status to failed
            update_task_status(
                db=db,
                task_id=task.id,
                status="failed",
                error_message="Task recovered after being stuck in processing",
                completed=True,
            )

            # Check if we need to update the media file status
            media_file = get_refreshed_object(db, MediaFile, task.media_file_id)
            if not media_file:
                logger.error(
                    f"Media file {task.media_file_id} not found for task {task.id}"
                )
                return False

            # Update media file status if no other active tasks
            self._update_media_file_if_no_active_tasks(db, media_file)

            return True

        except Exception as e:
            logger.error(f"Error recovering stuck task {task.id}: {str(e)}")
            return False

    def fix_inconsistent_media_file(self, db: Session, media_file: MediaFile) -> bool:
        """
        Fix inconsistent media file state.

        Args:
            db: Database session
            media_file: The media file with inconsistent state

        Returns:
            bool: True if fix was successful, False otherwise
        """
        try:
            logger.info(f"Fixing inconsistent state for media file {media_file.id}")

            # Get all tasks for this media file
            tasks = db.query(Task).filter(Task.media_file_id == media_file.id).all()

            if not tasks:
                return self._handle_file_with_no_tasks(db, media_file)

            # Analyze task statuses and update file accordingly
            return self._update_file_based_on_tasks(db, media_file, tasks)

        except Exception as e:
            logger.error(
                f"Error fixing inconsistent media file {media_file.id}: {str(e)}"
            )
            return False

    def recover_orphaned_tasks(self, db: Session, orphaned_tasks: list[Task]) -> int:
        """
        Recover multiple orphaned tasks.

        Args:
            db: Database session
            orphaned_tasks: List of orphaned tasks

        Returns:
            int: Number of successfully recovered tasks
        """
        recovered_count = 0

        for task in orphaned_tasks:
            try:
                logger.info(f"Marking orphaned task {task.id} as failed")

                task.status = "failed"
                task.error_message = "Task interrupted by system restart"
                task.completed_at = datetime.now(timezone.utc)
                task.updated_at = datetime.now(timezone.utc)

                recovered_count += 1

            except Exception as e:
                logger.error(f"Error recovering orphaned task {task.id}: {e}")

        try:
            db.commit()
        except Exception as e:
            logger.error(f"Error committing orphaned task recovery: {e}")
            db.rollback()
            return 0

        return recovered_count

    def reset_abandoned_files(
        self, db: Session, abandoned_files: list[MediaFile]
    ) -> int:
        """
        Reset abandoned files to PENDING status for retry.

        Args:
            db: Database session
            abandoned_files: List of abandoned files

        Returns:
            int: Number of successfully reset files
        """
        reset_count = 0

        for media_file in abandoned_files:
            try:
                logger.info(
                    f"Resetting abandoned file {media_file.id}: {media_file.filename}"
                )
                update_media_file_status(db, media_file.id, FileStatus.PENDING)
                reset_count += 1

            except Exception as e:
                logger.error(f"Error resetting abandoned file {media_file.id}: {e}")

        return reset_count

    def schedule_file_retry(self, media_file_id: int) -> bool:
        """
        Schedule a transcription retry for a file.

        Args:
            media_file_id: ID of the media file to retry

        Returns:
            bool: True if retry was scheduled successfully
        """
        try:
            from app.tasks.transcription import transcribe_audio_task

            result = transcribe_audio_task.delay(media_file_id)
            logger.info(
                f"Scheduled retry for file {media_file_id}, task ID: {result.id}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to schedule retry for file {media_file_id}: {e}")
            return False

    def recover_stuck_files_without_celery_tasks(
        self, db: Session, stuck_files: list[MediaFile]
    ) -> dict[str, int]:
        """
        Recover files that are stuck in processing state without active Celery tasks.

        Args:
            db: Database session
            stuck_files: List of stuck files identified by detection service

        Returns:
            Dict with recovery statistics
        """
        stats = {"files_recovered": 0, "tasks_retried": 0, "tasks_failed": 0}

        for media_file in stuck_files:
            try:
                logger.info(
                    f"Recovering stuck file {media_file.id} ({media_file.filename})"
                )

                # Mark any existing tasks as failed
                stale_tasks = (
                    db.query(Task)
                    .filter(
                        Task.media_file_id == media_file.id,
                        Task.status.in_(["pending", "in_progress"]),
                    )
                    .all()
                )

                for task in stale_tasks:
                    update_task_status(
                        db=db,
                        task_id=task.id,
                        status="failed",
                        error_message="Task recovered - no active Celery worker found",
                        completed=True,
                    )
                    stats["tasks_failed"] += 1

                # Reset file status to pending for retry
                update_media_file_status(db, media_file.id, FileStatus.PENDING)
                stats["files_recovered"] += 1

                # Schedule new transcription task
                if self.schedule_file_retry(media_file.id):
                    stats["tasks_retried"] += 1
                    logger.info(
                        f"Successfully scheduled retry for stuck file {media_file.id}"
                    )
                else:
                    logger.error(
                        f"Failed to schedule retry for stuck file {media_file.id}"
                    )

            except Exception as e:
                logger.error(f"Error recovering stuck file {media_file.id}: {e}")

        return stats

    def recover_user_files(
        self, db: Session, problem_files: list[MediaFile]
    ) -> dict[str, int]:
        """
        Recover problem files for users.

        Args:
            db: Database session
            problem_files: List of problem files to recover

        Returns:
            Dict with recovery statistics
        """
        stats = {"files_recovered": 0, "tasks_retried": 0}

        for media_file in problem_files:
            try:
                active_tasks = (
                    db.query(Task)
                    .filter(
                        Task.media_file_id == media_file.id,
                        Task.status.in_(["pending", "in_progress"]),
                    )
                    .count()
                )

                file_age = datetime.now(timezone.utc) - media_file.upload_time

                if active_tasks == 0 and media_file.status == FileStatus.PROCESSING:
                    # File is stuck, recover it
                    update_media_file_status(db, media_file.id, FileStatus.PENDING)
                    stats["files_recovered"] += 1

                    if self.schedule_file_retry(media_file.id):
                        stats["tasks_retried"] += 1

                elif media_file.status == FileStatus.PENDING and file_age > timedelta(
                    hours=self.config.PENDING_FILE_RETRY_THRESHOLD
                ):
                    # File has been pending too long, retry it
                    if self.schedule_file_retry(media_file.id):
                        stats["tasks_retried"] += 1

            except Exception as e:
                logger.error(f"Error recovering file {media_file.id}: {e}")

        return stats

    def _update_media_file_if_no_active_tasks(self, db: Session, media_file: MediaFile):
        """Update media file status if no active tasks remain."""
        active_tasks = (
            db.query(Task)
            .filter(
                Task.media_file_id == media_file.id,
                Task.status.in_(["pending", "in_progress"]),
            )
            .count()
        )

        if active_tasks == 0 and media_file.status == FileStatus.PROCESSING:
            update_media_file_status(db, media_file.id, FileStatus.ERROR)
            logger.info(
                f"Updated media file {media_file.id} status to ERROR after task recovery"
            )

    def _handle_file_with_no_tasks(self, db: Session, media_file: MediaFile) -> bool:
        """Handle media file that has no associated tasks."""
        if media_file.status == FileStatus.PROCESSING:
            update_media_file_status(db, media_file.id, FileStatus.ERROR)
            logger.info(
                f"Media file {media_file.id} had no tasks but was PROCESSING - marked as ERROR"
            )
        return True

    def _update_file_based_on_tasks(
        self, db: Session, media_file: MediaFile, tasks: list[Task]
    ) -> bool:
        """Update file status based on its associated tasks."""
        task_counts = {"pending": 0, "in_progress": 0, "completed": 0, "failed": 0}
        for task in tasks:
            task_counts[task.status] = task_counts.get(task.status, 0) + 1

        # Decision logic based on task statuses
        if task_counts["pending"] == 0 and task_counts["in_progress"] == 0:
            # No active tasks
            if task_counts["failed"] > 0 and task_counts["completed"] == 0:
                # All tasks failed
                update_media_file_status(db, media_file.id, FileStatus.ERROR)
                logger.info(
                    f"Media file {media_file.id} all tasks failed - marked as ERROR"
                )
            elif task_counts["completed"] > 0:
                # Some tasks completed successfully
                update_media_file_status(db, media_file.id, FileStatus.COMPLETED)
                logger.info(
                    f"Media file {media_file.id} had completed tasks - marked as COMPLETED"
                )
        elif media_file.status == FileStatus.PENDING and (
            task_counts["in_progress"] > 0 or task_counts["completed"] > 0
        ):
            # Tasks are running but file still shows pending
            update_media_file_status(db, media_file.id, FileStatus.PROCESSING)
            logger.info(
                f"Media file {media_file.id} had active tasks but was PENDING - marked as PROCESSING"
            )

        return True


# Service instance
task_recovery_service = TaskRecoveryService()
