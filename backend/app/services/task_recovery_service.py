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
from app.services import system_settings_service
from app.utils.error_classification import categorize_error
from app.utils.error_classification import get_retry_delay
from app.utils.error_classification import should_retry
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
                task_id=str(task.id),
                status="failed",
                error_message="Task recovered after being stuck in processing",
                completed=True,
            )

            # Check if we need to update the media file status
            media_file = get_refreshed_object(db, MediaFile, int(task.media_file_id))
            if not media_file:
                logger.error(f"Media file {task.media_file_id} not found for task {task.id}")
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
            logger.error(f"Error fixing inconsistent media file {media_file.id}: {str(e)}")
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

                task.status = "failed"  # type: ignore[assignment]
                task.error_message = "Task interrupted by system restart"  # type: ignore[assignment]
                task.completed_at = datetime.now(timezone.utc)  # type: ignore[assignment]
                task.updated_at = datetime.now(timezone.utc)  # type: ignore[assignment]

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

    def reset_abandoned_files(self, db: Session, abandoned_files: list[MediaFile]) -> int:
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
                logger.info(f"Resetting abandoned file {media_file.id}: {media_file.filename}")
                update_media_file_status(db, int(media_file.id), FileStatus.PENDING)
                reset_count += 1

            except Exception as e:
                logger.error(f"Error resetting abandoned file {media_file.id}: {e}")

        return reset_count

    def schedule_file_retry(self, media_file_id: int) -> bool:
        """
        Schedule a retry for a file, dispatching the appropriate task type.

        For files that failed during YouTube download (have source_url but no
        storage_path), dispatches process_youtube_url_task. For files that have
        been downloaded, dispatches transcribe_audio_task.

        Args:
            media_file_id: ID of the media file to retry

        Returns:
            bool: True if retry was scheduled successfully
        """
        try:
            from app.db.base import SessionLocal
            from app.models.media import MediaFile

            db = SessionLocal()
            try:
                media_file = db.query(MediaFile).filter(MediaFile.id == media_file_id).first()
                if not media_file:
                    logger.error(f"File {media_file_id} not found for retry")
                    return False

                file_uuid = str(media_file.uuid)
                source_url = str(media_file.source_url) if media_file.source_url else None
                storage_path = str(media_file.storage_path) if media_file.storage_path else None
                user_id = int(media_file.user_id)
            finally:
                db.close()

            # If file has a source URL but no storage path, it failed during download
            if source_url and not storage_path:
                from app.tasks.youtube_processing import process_youtube_url_task

                result = process_youtube_url_task.delay(
                    url=source_url,
                    user_id=user_id,
                    file_uuid=file_uuid,
                )
                logger.info(
                    f"Scheduled YouTube download retry for file {media_file_id}, "
                    f"task ID: {result.id}"
                )
            else:
                from app.tasks.transcription import transcribe_audio_task

                result = transcribe_audio_task.delay(file_uuid)
                logger.info(
                    f"Scheduled transcription retry for file {media_file_id}, task ID: {result.id}"
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
                # Classify the error
                error_category = categorize_error(media_file.last_error_message or "")
                media_file.error_category = error_category.value  # type: ignore[assignment]

                # Enforce retry delay based on error category
                if media_file.completed_at:
                    time_since_failure = (
                        datetime.now(timezone.utc) - media_file.completed_at
                    ).total_seconds()
                    required_delay = get_retry_delay(error_category, int(media_file.retry_count))
                    if time_since_failure < required_delay:
                        logger.debug(
                            f"Skipping file {media_file.id} - retry delay not met "
                            f"({time_since_failure:.0f}s < {required_delay}s)"
                        )
                        db.commit()
                        continue

                # Check if retry is allowed based on error classification
                if not should_retry(error_category, int(media_file.retry_count)):
                    logger.info(
                        f"Skipping retry for file {media_file.id} - "
                        f"error category {error_category.value}, "
                        f"retry count: {media_file.retry_count}"
                    )
                    update_media_file_status(db, int(media_file.id), FileStatus.ERROR)
                    db.commit()
                    continue

                # Also check system-level retry settings
                if not system_settings_service.should_retry_file(db, int(media_file.retry_count)):
                    logger.info(
                        f"Skipping retry for file {media_file.id} - system retry limit reached "
                        f"(count: {media_file.retry_count})"
                    )
                    update_media_file_status(db, int(media_file.id), FileStatus.ERROR)
                    db.commit()
                    continue

                logger.info(
                    f"Recovering stuck file {media_file.id} ({media_file.filename}) "
                    f"- error: {error_category.value}"
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
                        task_id=str(task.id),
                        status="failed",
                        error_message="Task recovered - no active Celery worker found",
                        completed=True,
                    )
                    stats["tasks_failed"] += 1

                # Increment retry count and reset file status to pending for retry
                media_file.retry_count += 1  # type: ignore[assignment]
                update_media_file_status(db, int(media_file.id), FileStatus.PENDING)
                stats["files_recovered"] += 1

                # Schedule new transcription task
                if self.schedule_file_retry(int(media_file.id)):
                    stats["tasks_retried"] += 1
                    logger.info(f"Successfully scheduled retry for stuck file {media_file.id}")
                else:
                    logger.error(f"Failed to schedule retry for stuck file {media_file.id}")

            except Exception as e:
                logger.error(f"Error recovering stuck file {media_file.id}: {e}")

        return stats

    def recover_user_files(self, db: Session, problem_files: list[MediaFile]) -> dict[str, int]:
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
                # Check if retry is allowed based on system settings
                if not system_settings_service.should_retry_file(db, int(media_file.retry_count)):
                    logger.info(
                        f"Skipping retry for file {media_file.id} - retry limit reached "
                        f"(count: {media_file.retry_count})"
                    )
                    continue

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
                    media_file.retry_count += 1  # type: ignore[assignment]
                    update_media_file_status(db, int(media_file.id), FileStatus.PENDING)
                    stats["files_recovered"] += 1

                    if self.schedule_file_retry(int(media_file.id)):
                        stats["tasks_retried"] += 1

                elif media_file.status == FileStatus.PENDING and file_age > timedelta(
                    hours=self.config.PENDING_FILE_RETRY_THRESHOLD
                ):
                    # File has been pending too long, retry it
                    media_file.retry_count += 1  # type: ignore[assignment]
                    if self.schedule_file_retry(int(media_file.id)):
                        stats["tasks_retried"] += 1

            except Exception as e:
                logger.error(f"Error recovering file {media_file.id}: {e}")

        return stats

    def recover_oom_error_files(self, db: Session, oom_files: list[MediaFile]) -> dict[str, int]:
        """
        Recover files that failed with OOM errors by retrying them.

        Args:
            db: Database session
            oom_files: List of files with OOM errors identified by detection service

        Returns:
            Dict with recovery statistics: files_checked, files_retried, files_exhausted
        """
        stats = {
            "files_checked": 0,
            "files_retried": 0,
            "files_exhausted": 0,
        }

        for media_file in oom_files:
            stats["files_checked"] += 1

            # Check if retry is allowed based on system settings
            if not system_settings_service.should_retry_file(db, int(media_file.retry_count)):
                logger.warning(
                    f"OOM retry limit exhausted for file {media_file.id} ({media_file.filename}) - "
                    f"retry_count: {media_file.retry_count}, max_retries: {media_file.max_retries}"
                )
                stats["files_exhausted"] += 1
                # File stays in ERROR status (already there)
                continue

            try:
                logger.info(
                    f"Retrying OOM error for file {media_file.id} ({media_file.filename}) - "
                    f"attempt {media_file.retry_count + 1}/{media_file.max_retries}"
                )

                # Update recovery tracking fields
                media_file.retry_count += 1  # type: ignore[assignment]
                media_file.recovery_attempts += 1  # type: ignore[assignment]
                media_file.last_recovery_attempt = datetime.now(timezone.utc)  # type: ignore[assignment]
                db.commit()

                # Reset status to PENDING for retry
                update_media_file_status(db, int(media_file.id), FileStatus.PENDING)

                # Schedule new transcription task
                if self.schedule_file_retry(int(media_file.id)):
                    stats["files_retried"] += 1

                    # Send notification to user about retry attempt
                    try:
                        from app.tasks.transcription.notifications import (
                            send_notification_via_redis,
                        )

                        send_notification_via_redis(
                            int(media_file.user_id),
                            int(media_file.id),
                            FileStatus.PROCESSING,
                            f"Retrying after GPU memory error (attempt {media_file.retry_count}/{media_file.max_retries})",
                            progress=0,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to send notification for OOM retry {media_file.id}: {e}"
                        )

                    logger.info(
                        f"Successfully scheduled OOM retry for file {media_file.id} - "
                        f"next backoff delay: {2**media_file.retry_count * 10} minutes"
                    )
                else:
                    logger.error(f"Failed to schedule OOM retry for file {media_file.id}")

            except Exception as e:
                logger.error(f"Error recovering OOM file {media_file.id}: {e}")

        return stats

    def recover_retriable_error_files(
        self, db: Session, error_files: list[MediaFile]
    ) -> dict[str, int]:
        """
        Recover ERROR files with retriable errors by resetting and re-queuing.

        Uses staggered processing (called with batch-limited lists) to avoid
        overwhelming external services like YouTube.

        Args:
            db: Database session
            error_files: List of retriable ERROR files from detection service

        Returns:
            Dict with recovery statistics
        """
        stats = {"files_checked": 0, "files_retried": 0, "files_failed": 0}

        for media_file in error_files:
            stats["files_checked"] += 1

            try:
                logger.info(
                    f"Retrying ERROR file {media_file.id} ({media_file.filename}) - "
                    f"category: {media_file.error_category}, "
                    f"attempt {int(media_file.retry_count) + 1}"
                )

                # Increment retry count and reset status
                media_file.retry_count += 1  # type: ignore[assignment]
                media_file.recovery_attempts += 1  # type: ignore[assignment]
                media_file.last_recovery_attempt = datetime.now(timezone.utc)  # type: ignore[assignment]

                # Clear old task records and reset to PENDING
                stale_tasks = db.query(Task).filter(Task.media_file_id == media_file.id).all()
                for task in stale_tasks:
                    task.status = "failed"  # type: ignore[assignment]
                    task.error_message = "Reset for automatic retry"  # type: ignore[assignment]
                    task.completed_at = datetime.now(timezone.utc)  # type: ignore[assignment]

                media_file.active_task_id = None  # type: ignore[assignment]
                media_file.task_started_at = None  # type: ignore[assignment]
                update_media_file_status(db, int(media_file.id), FileStatus.PENDING)

                # Schedule the appropriate retry task
                if self.schedule_file_retry(int(media_file.id)):
                    stats["files_retried"] += 1
                    logger.info(
                        f"Scheduled retry for ERROR file {media_file.id} "
                        f"(category: {media_file.error_category})"
                    )
                else:
                    stats["files_failed"] += 1
                    logger.error(f"Failed to schedule retry for ERROR file {media_file.id}")

            except Exception as e:
                stats["files_failed"] += 1
                logger.error(f"Error recovering ERROR file {media_file.id}: {e}")

        return stats

    def recover_incomplete_post_transcription_files(
        self,
        db: Session,
        incomplete_files: list,
    ) -> dict[str, int]:
        """
        Dispatch missing post-transcription tasks for COMPLETED files.

        For each file, dispatches whichever tasks are missing (analytics,
        speaker ID, summary, topics). Each dispatch is individually
        try/excepted so one failure doesn't block others.

        Args:
            db: Database session
            incomplete_files: List of IncompletePostTranscriptionFile from detection

        Returns:
            Dict with dispatch statistics
        """
        stats = {
            "files_processed": 0,
            "summaries_dispatched": 0,
            "topics_dispatched": 0,
            "speaker_id_dispatched": 0,
            "analytics_dispatched": 0,
            "total_tasks_dispatched": 0,
            "dispatch_errors": 0,
        }

        for incomplete in incomplete_files:
            stats["files_processed"] += 1
            file_uuid = incomplete.file_uuid

            # 1. Analytics (no LLM needed)
            if incomplete.missing_analytics:
                try:
                    from app.tasks.analytics import analyze_transcript_task

                    result = analyze_transcript_task.delay(file_uuid=file_uuid)
                    stats["analytics_dispatched"] += 1
                    stats["total_tasks_dispatched"] += 1
                    logger.info(
                        f"[Post-transcription recovery] Dispatched analytics task "
                        f"{result.id} for file {incomplete.media_file_id}"
                    )
                except Exception as e:
                    stats["dispatch_errors"] += 1
                    logger.error(
                        f"[Post-transcription recovery] Failed to dispatch analytics "
                        f"for file {incomplete.media_file_id}: {e}"
                    )

            # 2. Speaker identification (before summary so names are available)
            if incomplete.missing_speaker_id:
                try:
                    from app.tasks.speaker_tasks import identify_speakers_llm_task

                    result = identify_speakers_llm_task.delay(file_uuid=file_uuid)
                    stats["speaker_id_dispatched"] += 1
                    stats["total_tasks_dispatched"] += 1
                    logger.info(
                        f"[Post-transcription recovery] Dispatched speaker ID task "
                        f"{result.id} for file {incomplete.media_file_id}"
                    )
                except Exception as e:
                    stats["dispatch_errors"] += 1
                    logger.error(
                        f"[Post-transcription recovery] Failed to dispatch speaker ID "
                        f"for file {incomplete.media_file_id}: {e}"
                    )

            # 3. Summarization
            if incomplete.missing_summary:
                try:
                    from app.tasks.summarization import summarize_transcript_task

                    result = summarize_transcript_task.delay(file_uuid=file_uuid)
                    stats["summaries_dispatched"] += 1
                    stats["total_tasks_dispatched"] += 1
                    logger.info(
                        f"[Post-transcription recovery] Dispatched summary task "
                        f"{result.id} for file {incomplete.media_file_id}"
                    )
                except Exception as e:
                    stats["dispatch_errors"] += 1
                    logger.error(
                        f"[Post-transcription recovery] Failed to dispatch summary "
                        f"for file {incomplete.media_file_id}: {e}"
                    )

            # 4. Topic extraction
            if incomplete.missing_topics:
                try:
                    from app.tasks.topic_extraction import extract_topics_task

                    result = extract_topics_task.delay(file_uuid=file_uuid, force_regenerate=False)
                    stats["topics_dispatched"] += 1
                    stats["total_tasks_dispatched"] += 1
                    logger.info(
                        f"[Post-transcription recovery] Dispatched topic extraction task "
                        f"{result.id} for file {incomplete.media_file_id}"
                    )
                except Exception as e:
                    stats["dispatch_errors"] += 1
                    logger.error(
                        f"[Post-transcription recovery] Failed to dispatch topics "
                        f"for file {incomplete.media_file_id}: {e}"
                    )

        logger.info(
            f"[Post-transcription recovery] Processed {stats['files_processed']} files, "
            f"dispatched {stats['total_tasks_dispatched']} tasks "
            f"(analytics={stats['analytics_dispatched']}, "
            f"speaker_id={stats['speaker_id_dispatched']}, "
            f"summaries={stats['summaries_dispatched']}, "
            f"topics={stats['topics_dispatched']}), "
            f"errors={stats['dispatch_errors']}"
        )

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
            # Classify the error and decide whether to retry
            error_category = categorize_error(media_file.last_error_message or "")
            media_file.error_category = error_category.value  # type: ignore[assignment]

            if should_retry(error_category, int(media_file.retry_count)):
                logger.info(
                    f"Retriable error for file {media_file.id} "
                    f"({error_category.value}), resetting to PENDING"
                )
                media_file.retry_count += 1  # type: ignore[assignment]
                update_media_file_status(db, int(media_file.id), FileStatus.PENDING)
                self.schedule_file_retry(int(media_file.id))
            else:
                update_media_file_status(db, int(media_file.id), FileStatus.ERROR)
                db.commit()
                logger.info(
                    f"Updated media file {media_file.id} status to ERROR "
                    f"after task recovery ({error_category.value})"
                )

    def _handle_file_with_no_tasks(self, db: Session, media_file: MediaFile) -> bool:
        """Handle media file that has no associated tasks."""
        if media_file.status == FileStatus.PROCESSING:
            update_media_file_status(db, int(media_file.id), FileStatus.ERROR)
            logger.info(
                f"Media file {media_file.id} had no tasks but was PROCESSING - marked as ERROR"
            )
        return True

    def _update_file_based_on_tasks(
        self, db: Session, media_file: MediaFile, tasks: list[Task]
    ) -> bool:
        """Update file status based on its associated tasks."""
        from app.models.media import TranscriptSegment

        task_counts = {"pending": 0, "in_progress": 0, "completed": 0, "failed": 0}
        for task in tasks:
            task_counts[str(task.status)] = task_counts.get(str(task.status), 0) + 1

        # Decision logic based on task statuses
        if task_counts["pending"] == 0 and task_counts["in_progress"] == 0:
            # No active tasks — check if file actually has transcript segments
            # before marking as COMPLETED (a completed download task alone
            # doesn't mean transcription succeeded)
            has_segments = (
                db.query(TranscriptSegment)
                .filter(TranscriptSegment.media_file_id == media_file.id)
                .limit(1)
                .count()
                > 0
            )

            if task_counts["completed"] > 0 and has_segments:
                # Has completed tasks AND transcript segments = truly complete
                update_media_file_status(db, int(media_file.id), FileStatus.COMPLETED)
                logger.info(
                    f"Media file {media_file.id} had completed tasks with segments - marked as COMPLETED"
                )
            elif task_counts["failed"] > 0:
                # Has failed tasks (and either no completed tasks or no segments)
                update_media_file_status(db, int(media_file.id), FileStatus.ERROR)
                logger.info(f"Media file {media_file.id} has failed tasks - marked as ERROR")
            elif task_counts["completed"] > 0 and not has_segments:
                # Completed tasks but no segments = partial completion, needs retry
                update_media_file_status(db, int(media_file.id), FileStatus.ERROR)
                logger.info(
                    f"Media file {media_file.id} had completed tasks but no transcript "
                    f"segments - marked as ERROR for retry"
                )
        elif media_file.status == FileStatus.PENDING and (
            task_counts["in_progress"] > 0 or task_counts["completed"] > 0
        ):
            # Tasks are running but file still shows pending
            update_media_file_status(db, int(media_file.id), FileStatus.PROCESSING)
            logger.info(
                f"Media file {media_file.id} had active tasks but was PENDING - marked as PROCESSING"
            )

        return True


# Service instance
task_recovery_service = TaskRecoveryService()
