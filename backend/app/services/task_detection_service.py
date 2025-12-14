"""
Task detection service for identifying problematic tasks and files.

This service is responsible for detecting various types of task and file issues
without performing any recovery actions. It follows the single responsibility principle
by separating detection from recovery.
"""

import logging
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from sqlalchemy.orm import Session

from app.core.task_config import task_recovery_config
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.models.media import Task
from app.utils.task_utils import update_media_file_from_task_status

logger = logging.getLogger(__name__)


class TaskDetectionService:
    """Service for detecting task and file issues."""

    def __init__(self, config=None):
        """Initialize with optional configuration override."""
        self.config = config or task_recovery_config

    def identify_stuck_tasks(self, db: Session) -> list[Task]:
        """
        Identify tasks that appear to be stuck in processing or pending state.

        A task is considered stuck if:
        1. It's in "pending" or "in_progress" state
        2. It was last updated longer ago than the STALENESS_THRESHOLD
        3. It's been running longer than its MAX_TASK_DURATION

        Args:
            db: Database session

        Returns:
            List of stuck tasks
        """
        now = datetime.now(timezone.utc)
        stale_time = now - timedelta(seconds=self.config.STALENESS_THRESHOLD)

        # Find potentially stuck tasks
        potential_stuck_tasks = (
            db.query(Task)
            .filter(
                Task.status.in_(["pending", "in_progress"]),
                Task.updated_at < stale_time,
            )
            .all()
        )

        # Filter based on duration
        stuck_tasks = []
        for task in potential_stuck_tasks:
            if self._is_task_duration_exceeded(task, now):
                stuck_tasks.append(task)

        logger.info(f"Identified {len(stuck_tasks)} stuck tasks")
        return stuck_tasks

    def identify_stuck_files_without_active_celery_tasks(self, db: Session) -> list[MediaFile]:
        """
        Identify files that are stuck in PROCESSING state without any active Celery tasks.

        This method identifies files that are marked as PROCESSING but have:
        1. No tasks in "pending" or "in_progress" state
        2. Been in this state for longer than a threshold time
        3. No recent task updates (indicating Celery worker may have died)

        Args:
            db: Database session

        Returns:
            List of stuck files that need recovery
        """
        now = datetime.now(timezone.utc)
        stuck_threshold = now - timedelta(minutes=5)  # Files stuck for 5+ minutes

        # Get all files currently in PROCESSING state
        processing_files = (
            db.query(MediaFile).filter(MediaFile.status == FileStatus.PROCESSING).all()
        )

        stuck_files = []
        for media_file in processing_files:
            # Check if file has been processing for too long
            if media_file.updated_at and media_file.updated_at < stuck_threshold:
                # Check if there are any active tasks
                active_tasks = (
                    db.query(Task)
                    .filter(
                        Task.media_file_id == media_file.id,
                        Task.status.in_(["pending", "in_progress"]),
                    )
                    .all()
                )

                if not active_tasks:
                    # Before marking the file as stuck, try to reconcile its status from task history.
                    # This prevents false positives where tasks completed but file status wasn't updated.
                    refreshed_file = update_media_file_from_task_status(db, media_file.id)
                    if refreshed_file and refreshed_file.status in [
                        FileStatus.COMPLETED,
                        FileStatus.ERROR,
                    ]:
                        logger.info(
                            f"File {media_file.id} ({media_file.filename}) was marked as processing "
                            f"but all tasks have finished with status {refreshed_file.status.value}; "
                            f"skipping recovery."
                        )
                        continue

                    # File is still marked as processing and has no active tasks - treat as stuck.
                    stuck_files.append(media_file)
                    logger.info(
                        f"Found stuck file {media_file.id} ({media_file.filename}) - "
                        f"processing for {(now - media_file.updated_at).total_seconds() / 60:.1f} minutes "
                        f"with no active tasks"
                    )
                else:
                    # Check if tasks are truly stuck (no recent updates)
                    all_tasks_stale = True
                    for task in active_tasks:
                        if task.updated_at and task.updated_at > stuck_threshold:
                            all_tasks_stale = False
                            break

                    if all_tasks_stale:
                        stuck_files.append(media_file)
                        logger.info(
                            f"Found stuck file {media_file.id} ({media_file.filename}) - "
                            f"has {len(active_tasks)} stale tasks"
                        )

        logger.info(f"Identified {len(stuck_files)} stuck files without active Celery tasks")
        return stuck_files

    def identify_inconsistent_media_files(self, db: Session) -> list[MediaFile]:
        """
        Identify media files with inconsistent states.

        A media file is considered inconsistent if:
        1. It's in PROCESSING state but has no active tasks
        2. It's in PENDING state but has been there for too long
        3. It has completed tasks but is still marked as PROCESSING

        Args:
            db: Database session

        Returns:
            List of media files with inconsistent states
        """
        inconsistent_files = []

        # Check processing files without active tasks
        processing_files = self._find_processing_files_without_tasks(db)
        inconsistent_files.extend(processing_files)

        # Check stale pending files
        stale_pending_files = self._find_stale_pending_files(db)
        inconsistent_files.extend(stale_pending_files)

        logger.info(f"Identified {len(inconsistent_files)} inconsistent files")
        return inconsistent_files

    def identify_orphaned_tasks(self, db: Session) -> list[Task]:
        """
        Identify tasks that were orphaned during system shutdown.

        Args:
            db: Database session

        Returns:
            List of orphaned tasks
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(
            hours=self.config.ORPHANED_TASK_THRESHOLD
        )

        orphaned_tasks = (
            db.query(Task)
            .filter(
                Task.status.in_(["pending", "in_progress"]),
                Task.updated_at < cutoff_time,
            )
            .all()
        )

        logger.info(f"Identified {len(orphaned_tasks)} orphaned tasks")
        return orphaned_tasks

    def identify_abandoned_files(self, db: Session) -> list[MediaFile]:
        """
        Identify files that were abandoned during processing.

        Args:
            db: Database session

        Returns:
            List of abandoned files
        """
        abandoned_files = (
            db.query(MediaFile).filter(MediaFile.status == FileStatus.PROCESSING).all()
        )

        # Filter to only include files with no active tasks
        truly_abandoned = []
        for media_file in abandoned_files:
            active_tasks = (
                db.query(Task)
                .filter(
                    Task.media_file_id == media_file.id,
                    Task.status.in_(["pending", "in_progress"]),
                )
                .count()
            )

            if active_tasks == 0:
                truly_abandoned.append(media_file)

        logger.info(f"Identified {len(truly_abandoned)} abandoned files")
        return truly_abandoned

    def find_user_problem_files(self, db: Session, user_id: int = None) -> list[MediaFile]:
        """
        Find files that may need recovery for a specific user or all users.

        Args:
            db: Database session
            user_id: Optional user ID to filter by

        Returns:
            List of files that may need recovery
        """
        query = db.query(MediaFile)
        if user_id:
            query = query.filter(MediaFile.user_id == user_id)

        problem_files = query.filter(
            MediaFile.status.in_([FileStatus.PROCESSING, FileStatus.PENDING])
        ).all()

        # Filter by age
        aged_files = []
        age_threshold = timedelta(hours=self.config.FILE_RECOVERY_AGE_THRESHOLD)

        for media_file in problem_files:
            file_age = datetime.now(timezone.utc) - media_file.upload_time
            if file_age > age_threshold:
                aged_files.append(media_file)

        logger.info(f"Found {len(aged_files)} problem files for user {user_id or 'all'}")
        return aged_files

    def _is_task_duration_exceeded(self, task: Task, now: datetime) -> bool:
        """Check if a task has exceeded its maximum allowed duration."""
        if not task.created_at:
            return False

        duration = (now - task.created_at).total_seconds()
        max_duration = self.config.MAX_TASK_DURATIONS.get(
            task.task_type, self.config.MAX_TASK_DURATIONS["default"]
        )

        return duration > max_duration

    def _find_processing_files_without_tasks(self, db: Session) -> list[MediaFile]:
        """Find files in PROCESSING state with no active tasks."""
        processing_files = (
            db.query(MediaFile).filter(MediaFile.status == FileStatus.PROCESSING).all()
        )

        files_without_tasks = []
        for media_file in processing_files:
            active_tasks = (
                db.query(Task)
                .filter(
                    Task.media_file_id == media_file.id,
                    Task.status.in_(["pending", "in_progress"]),
                )
                .count()
            )

            if active_tasks == 0:
                files_without_tasks.append(media_file)

        return files_without_tasks

    def _find_stale_pending_files(self, db: Session) -> list[MediaFile]:
        """Find files that have been in PENDING state for too long."""
        stale_time = datetime.now(timezone.utc) - timedelta(hours=1)

        return (
            db.query(MediaFile)
            .filter(
                MediaFile.status == FileStatus.PENDING,
                MediaFile.upload_time < stale_time,
            )
            .all()
        )


# Service instance
task_detection_service = TaskDetectionService()
