"""
Task detection service for identifying problematic tasks and files.

This service is responsible for detecting various types of task and file issues
without performing any recovery actions. It follows the single responsibility principle
by separating detection from recovery.
"""

import logging
import os
from dataclasses import dataclass
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


@dataclass
class IncompletePostTranscriptionFile:
    """A COMPLETED file that is missing one or more post-transcription results."""

    media_file_id: int
    file_uuid: str
    user_id: int
    missing_summary: bool = False
    missing_topics: bool = False
    missing_speaker_id: bool = False
    missing_analytics: bool = False
    llm_configured: bool = False


def _get_container_boot_time() -> datetime:
    """Get the time this container/process started.

    Uses /proc/1/stat creation time as a reliable indicator of when
    the container booted. Falls back to 5 minutes ago if unavailable.
    """
    try:
        boot_epoch = os.path.getctime("/proc/1")
        return datetime.fromtimestamp(boot_epoch, tz=timezone.utc)
    except Exception:
        # Fallback: assume booted 5 minutes ago
        return datetime.now(timezone.utc) - timedelta(minutes=5)


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

        # Get all files currently in PROCESSING state that have been downloaded.
        # Playlist placeholder files (file_size = 0) are still in the download queue
        # and should not be treated as stuck.
        processing_files = (
            db.query(MediaFile)
            .filter(
                MediaFile.status == FileStatus.PROCESSING,
                MediaFile.file_size > 0,
            )
            .all()
        )

        stuck_files = []
        for media_file in processing_files:
            # Check if file has been processing for too long
            if media_file.task_last_update and media_file.task_last_update < stuck_threshold:
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
                    refreshed_file = update_media_file_from_task_status(db, int(media_file.id))
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
                        f"processing for {(now - media_file.task_last_update).total_seconds() / 60:.1f} minutes "
                        f"with no active tasks"
                    )
                else:
                    # Check if tasks are truly stuck using boot-time comparison.
                    # Any task updated before this container booted is dead.
                    boot_time = _get_container_boot_time()
                    all_tasks_stale = True
                    for task in active_tasks:
                        if task.updated_at and task.updated_at > boot_time:
                            # Task was updated after boot - it's alive
                            all_tasks_stale = False
                            break
                        # Task updated before boot = dead from previous container

                    if all_tasks_stale:
                        # Before marking as stuck, check if file has completed tasks
                        # (e.g., transcription completed but file status wasn't updated)
                        completed_tasks = (
                            db.query(Task)
                            .filter(
                                Task.media_file_id == media_file.id,
                                Task.status == "completed",
                            )
                            .order_by(Task.completed_at.desc())
                            .first()
                        )

                        if completed_tasks:
                            # File has completed tasks but status wasn't updated
                            # Attempt to reconcile status and skip recovery
                            refreshed_file = update_media_file_from_task_status(
                                db, int(media_file.id)
                            )
                            if refreshed_file and refreshed_file.status in [
                                FileStatus.COMPLETED,
                                FileStatus.ERROR,
                            ]:
                                logger.info(
                                    f"File {media_file.id} ({media_file.filename}) has "
                                    f"completed tasks but status was still PROCESSING. "
                                    f"Reconciled to {refreshed_file.status.value}; "
                                    f"skipping recovery."
                                )
                                continue

                        # File is still marked as processing with stale tasks
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
        return orphaned_tasks  # type: ignore[no-any-return]

    def identify_abandoned_files(self, db: Session) -> list[MediaFile]:
        """
        Identify files that were abandoned during processing.

        Includes:
        - Downloaded files (file_size > 0) stuck in PROCESSING
        - YouTube download files (file_size = 0 but have source_url) stuck in PROCESSING

        Excludes:
        - Playlist placeholder files (file_size = 0, no source_url) that are
          waiting in the download queue

        Args:
            db: Database session

        Returns:
            List of abandoned files
        """
        from sqlalchemy import or_

        abandoned_files = (
            db.query(MediaFile)
            .filter(
                MediaFile.status == FileStatus.PROCESSING,
                or_(
                    MediaFile.file_size > 0,  # Downloaded files
                    MediaFile.source_url.isnot(None),  # YouTube download-in-progress files
                ),
            )
            .all()
        )

        # Filter to only include files with no truly active tasks.
        # Any DB task whose last update is older than this container's boot time
        # is guaranteed to be dead (the worker that was running it is gone).
        boot_time = _get_container_boot_time()
        truly_abandoned = []
        skipped_with_live_tasks = 0

        for media_file in abandoned_files:
            active_db_tasks = (
                db.query(Task)
                .filter(
                    Task.media_file_id == media_file.id,
                    Task.status.in_(["pending", "in_progress"]),
                )
                .all()
            )

            if not active_db_tasks:
                truly_abandoned.append(media_file)
                continue

            # Check if any task was updated AFTER this container booted
            # (meaning it was created/updated by the current worker process)
            has_post_boot_task = any(
                task.updated_at and task.updated_at > boot_time for task in active_db_tasks
            )

            if has_post_boot_task:
                skipped_with_live_tasks += 1
            else:
                # All tasks are from before this boot - they're dead
                logger.info(
                    f"File {media_file.id} ({media_file.filename}) has "
                    f"{len(active_db_tasks)} pre-boot DB tasks - "
                    f"marking as abandoned"
                )
                # Mark stale DB tasks as failed so they don't block future recovery
                for task in active_db_tasks:
                    task.status = "failed"  # type: ignore[assignment]
                    task.error_message = "Celery task lost after system restart"  # type: ignore[assignment]
                    task.completed_at = datetime.now(timezone.utc)  # type: ignore[assignment]
                db.flush()
                truly_abandoned.append(media_file)

        logger.info(
            f"Identified {len(truly_abandoned)} abandoned files "
            f"(skipped {skipped_with_live_tasks} with live Celery tasks)"
        )
        return truly_abandoned

    def identify_oom_error_files(self, db: Session) -> list[MediaFile]:
        """
        Identify ERROR files with OOM errors that are eligible for retry.

        A file is eligible if:
        1. Status is ERROR
        2. last_error_message contains OOM signature ("cuda" + "out of memory")
        3. Sufficient time has passed since last_recovery_attempt (exponential backoff)

        Args:
            db: Database session

        Returns:
            List of files eligible for OOM retry
        """
        now = datetime.now(timezone.utc)

        # Query ERROR files with OOM error messages
        oom_files = (
            db.query(MediaFile)
            .filter(
                MediaFile.status == FileStatus.ERROR,
                MediaFile.last_error_message.ilike("%cuda%"),
                MediaFile.last_error_message.ilike("%out of memory%"),
            )
            .all()
        )

        eligible_files = []
        for media_file in oom_files:
            # Calculate exponential backoff delay: 2^retry_count * 10 minutes
            backoff_minutes = (2**media_file.retry_count) * self.config.OOM_BACKOFF_BASE_MINUTES
            backoff_delay = timedelta(minutes=backoff_minutes)

            # Check if enough time has passed since last recovery attempt
            if media_file.last_recovery_attempt:
                time_since_last_attempt = now - media_file.last_recovery_attempt
                if time_since_last_attempt < backoff_delay:
                    logger.debug(
                        f"Skipping OOM retry for file {media_file.id} - "
                        f"backoff not elapsed ({time_since_last_attempt} < {backoff_delay})"
                    )
                    continue

            eligible_files.append(media_file)

        if eligible_files:
            logger.info(f"Identified {len(eligible_files)} files eligible for OOM retry")

        return eligible_files

    def identify_retriable_error_files(self, db: Session, batch_size: int = 20) -> list[MediaFile]:
        """
        Identify ERROR files eligible for automatic retry.

        Finds files with retriable error categories (auth/rate limit, network,
        temporary, system errors) that haven't exhausted their retries and
        have waited long enough since their last attempt.

        Returns a limited batch to avoid overwhelming external services
        (e.g., YouTube rate limits).

        Args:
            db: Database session
            batch_size: Maximum files to return per check cycle

        Returns:
            List of files eligible for retry (up to batch_size)
        """
        from app.utils.error_classification import ErrorCategory
        from app.utils.error_classification import get_retry_delay
        from app.utils.error_classification import should_retry

        now = datetime.now(timezone.utc)

        # Retriable error categories (exclude OOM - handled separately)
        retriable_categories = [
            ErrorCategory.AUTH_OR_RATE_LIMIT.value,
            ErrorCategory.NETWORK_ERROR.value,
            ErrorCategory.TEMPORARY_SERVICE_ERROR.value,
            ErrorCategory.SYSTEM_ERROR.value,
            ErrorCategory.WORKER_LOST.value,
            ErrorCategory.DUPLICATE_KEY.value,
            ErrorCategory.UNKNOWN.value,
        ]

        # Query ERROR files with retriable categories
        error_files = (
            db.query(MediaFile)
            .filter(
                MediaFile.status == FileStatus.ERROR,
                MediaFile.error_category.in_(retriable_categories),
            )
            .order_by(MediaFile.completed_at.asc())  # Oldest errors first
            .all()
        )

        eligible_files: list[MediaFile] = []
        for media_file in error_files:
            if len(eligible_files) >= batch_size:
                break

            # Check retry count against error classification
            error_category = ErrorCategory(media_file.error_category)
            if not should_retry(error_category, int(media_file.retry_count)):
                continue

            # Enforce retry delay based on error category
            if media_file.completed_at:
                time_since_failure = (now - media_file.completed_at).total_seconds()
                required_delay = get_retry_delay(error_category, int(media_file.retry_count))
                if time_since_failure < required_delay:
                    continue

            eligible_files.append(media_file)

        if eligible_files:
            logger.info(
                f"Identified {len(eligible_files)} retriable ERROR files "
                f"(of {len(error_files)} total retriable errors, "
                f"batch limit: {batch_size})"
            )

        return eligible_files

    def identify_retriable_error_files_split(
        self,
        db: Session,
        youtube_batch_size: int = 3,
        transcription_batch_size: int = 20,
    ) -> tuple[list[MediaFile], list[MediaFile]]:
        """Split retriable errors into YouTube downloads vs transcription retries.

        YouTube downloads (source_url set, no storage_path) are throttled to a
        small batch to respect YouTube rate limits.  Transcription retries are
        less sensitive and use a larger batch.

        Returns:
            Tuple of (youtube_files, transcription_files).
        """
        from app.utils.error_classification import ErrorCategory
        from app.utils.error_classification import get_retry_delay
        from app.utils.error_classification import should_retry

        now = datetime.now(timezone.utc)

        retriable_categories = [
            ErrorCategory.AUTH_OR_RATE_LIMIT.value,
            ErrorCategory.NETWORK_ERROR.value,
            ErrorCategory.TEMPORARY_SERVICE_ERROR.value,
            ErrorCategory.SYSTEM_ERROR.value,
            ErrorCategory.WORKER_LOST.value,
            ErrorCategory.DUPLICATE_KEY.value,
            ErrorCategory.UNKNOWN.value,
        ]

        error_files = (
            db.query(MediaFile)
            .filter(
                MediaFile.status == FileStatus.ERROR,
                MediaFile.error_category.in_(retriable_categories),
            )
            .order_by(MediaFile.completed_at.asc())
            .all()
        )

        youtube_files: list[MediaFile] = []
        transcription_files: list[MediaFile] = []

        for media_file in error_files:
            error_category = ErrorCategory(media_file.error_category)
            if not should_retry(error_category, int(media_file.retry_count)):
                continue

            if media_file.completed_at:
                time_since_failure = (now - media_file.completed_at).total_seconds()
                required_delay = get_retry_delay(error_category, int(media_file.retry_count))
                if time_since_failure < required_delay:
                    continue

            # YouTube download: has source_url but no storage_path (or empty)
            is_youtube = bool(media_file.source_url) and not media_file.storage_path

            if is_youtube:
                if len(youtube_files) < youtube_batch_size:
                    youtube_files.append(media_file)
            else:
                if len(transcription_files) < transcription_batch_size:
                    transcription_files.append(media_file)

            # Stop early if both batches full
            if (
                len(youtube_files) >= youtube_batch_size
                and len(transcription_files) >= transcription_batch_size
            ):
                break

        if youtube_files or transcription_files:
            logger.info(
                f"Retriable split: {len(youtube_files)} YouTube "
                f"(limit {youtube_batch_size}), "
                f"{len(transcription_files)} transcription "
                f"(limit {transcription_batch_size})"
            )

        return youtube_files, transcription_files

    def find_user_problem_files(self, db: Session, user_id: int | None = None) -> list[MediaFile]:
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

    def identify_incomplete_post_transcription_files(
        self, db: Session, batch_size: int = 10
    ) -> list[IncompletePostTranscriptionFile]:
        """
        Identify COMPLETED files missing post-transcription results.

        Checks for missing summaries, topics, speaker identifications, and
        analytics on files that completed transcription at least 30 minutes ago.
        Uses batch queries to avoid N+1 problems.

        Args:
            db: Database session
            batch_size: Maximum files to return per cycle

        Returns:
            List of IncompletePostTranscriptionFile with missing flags set
        """
        from app.models.media import Analytics
        from app.models.media import Speaker
        from app.models.topic import TopicSuggestion

        now = datetime.now(timezone.utc)
        maturity_cutoff = now - timedelta(minutes=30)

        # Query candidates: COMPLETED files that finished >30 min ago
        candidates = (
            db.query(
                MediaFile.id,
                MediaFile.uuid,
                MediaFile.user_id,
                MediaFile.summary_status,
            )
            .filter(
                MediaFile.status == FileStatus.COMPLETED,
                MediaFile.completed_at < maturity_cutoff,
            )
            .order_by(MediaFile.completed_at.asc())
            .limit(batch_size * 3)
            .all()
        )

        if not candidates:
            return []

        file_ids = [c.id for c in candidates]

        # Cache LLM config per unique user_id
        unique_user_ids = {c.user_id for c in candidates}
        llm_configured_by_user: dict[int, bool] = {}
        for uid in unique_user_ids:
            llm_configured_by_user[uid] = self._check_llm_configured_for_user(db, uid)

        # Batch-fetch existence: files with topics
        files_with_topics = set(
            row[0]
            for row in db.query(TopicSuggestion.media_file_id)
            .filter(TopicSuggestion.media_file_id.in_(file_ids))
            .all()
        )

        # Batch-fetch existence: files with analytics
        files_with_analytics = set(
            row[0]
            for row in db.query(Analytics.media_file_id)
            .filter(Analytics.media_file_id.in_(file_ids))
            .all()
        )

        # Batch-fetch existence: files with LLM speaker identifications
        files_with_speaker_id = set(
            row[0]
            for row in db.query(Speaker.media_file_id)
            .filter(
                Speaker.media_file_id.in_(file_ids),
                Speaker.suggestion_source == "llm_analysis",
            )
            .all()
        )

        # Batch-fetch recently-attempted task types for these files
        # Tasks created in the last 30 min that are pending/in_progress or recently completed
        recent_task_cutoff = now - timedelta(minutes=30)
        post_transcription_task_types = [
            "analytics",
            "speaker_identification",
            "summarization",
        ]
        recently_attempted_rows = (
            db.query(Task.media_file_id, Task.task_type)
            .filter(
                Task.media_file_id.in_(file_ids),
                Task.task_type.in_(post_transcription_task_types),
                Task.status.in_(["pending", "in_progress"]),
            )
            .all()
        )
        # Also include tasks created recently (even if completed/failed) to avoid
        # re-dispatching tasks that just ran
        recently_created_rows = (
            db.query(Task.media_file_id, Task.task_type)
            .filter(
                Task.media_file_id.in_(file_ids),
                Task.task_type.in_(post_transcription_task_types),
                Task.created_at > recent_task_cutoff,
            )
            .all()
        )

        recently_attempted: set[tuple[int, str]] = set()
        for row in recently_attempted_rows:
            recently_attempted.add((row[0], row[1]))
        for row in recently_created_rows:
            recently_attempted.add((row[0], row[1]))

        # Evaluate each candidate
        results: list[IncompletePostTranscriptionFile] = []
        for c in candidates:
            if len(results) >= batch_size:
                break

            llm_ok = llm_configured_by_user.get(c.user_id, False)

            missing_summary = (
                llm_ok
                and c.summary_status in (None, "pending", "failed")
                and (c.id, "summarization") not in recently_attempted
            )
            missing_topics = llm_ok and c.id not in files_with_topics
            missing_speaker_id = (
                llm_ok
                and c.id not in files_with_speaker_id
                and (c.id, "speaker_identification") not in recently_attempted
            )
            missing_analytics = (
                c.id not in files_with_analytics and (c.id, "analytics") not in recently_attempted
            )

            if missing_summary or missing_topics or missing_speaker_id or missing_analytics:
                results.append(
                    IncompletePostTranscriptionFile(
                        media_file_id=c.id,
                        file_uuid=str(c.uuid),
                        user_id=c.user_id,
                        missing_summary=missing_summary,
                        missing_topics=missing_topics,
                        missing_speaker_id=missing_speaker_id,
                        missing_analytics=missing_analytics,
                        llm_configured=llm_ok,
                    )
                )

        if results:
            logger.info(
                f"Identified {len(results)} COMPLETED files with incomplete "
                f"post-transcription processing"
            )

        return results

    @staticmethod
    def _check_llm_configured_for_user(db: Session, user_id: int) -> bool:
        """
        Check whether a user has LLM configured (DB-only, no HTTP).

        Checks the UserSetting for an active_llm_config_id, validates
        the corresponding UserLLMSettings record exists, and falls back
        to the system-level LLM_PROVIDER env var.
        """
        from app.models.prompt import UserSetting
        from app.models.user_llm_settings import UserLLMSettings

        # Check user-level config
        active_config_setting = (
            db.query(UserSetting.setting_value)
            .filter(
                UserSetting.user_id == user_id,
                UserSetting.setting_key == "active_llm_config_id",
            )
            .first()
        )
        if active_config_setting and active_config_setting[0]:
            try:
                config_id = int(active_config_setting[0])
                exists = (
                    db.query(UserLLMSettings.id).filter(UserLLMSettings.id == config_id).first()
                )
                if exists:
                    return True
            except (ValueError, TypeError):
                pass

        # Fall back to system-level env var
        from app.core.config import settings

        return bool(settings.LLM_PROVIDER)

    def _is_task_duration_exceeded(self, task: Task, now: datetime) -> bool:
        """Check if a task has exceeded its maximum allowed duration."""
        if not task.created_at:
            return False

        duration = (now - task.created_at).total_seconds()
        task_durations = self.config.MAX_TASK_DURATIONS
        if task_durations is None:
            return False
        max_duration = task_durations.get(str(task.task_type), task_durations["default"])

        return bool(duration > max_duration)

    def _find_processing_files_without_tasks(self, db: Session) -> list[MediaFile]:
        """Find files in PROCESSING state with no live tasks.

        Checks DB task records and compares against container boot time to
        catch files whose workers died (e.g., after container restart).
        """
        from sqlalchemy import or_

        boot_time = _get_container_boot_time()

        processing_files = (
            db.query(MediaFile)
            .filter(
                MediaFile.status == FileStatus.PROCESSING,
                or_(
                    MediaFile.file_size > 0,
                    MediaFile.source_url.isnot(None),
                ),
            )
            .all()
        )

        files_without_tasks = []
        for media_file in processing_files:
            active_db_tasks = (
                db.query(Task)
                .filter(
                    Task.media_file_id == media_file.id,
                    Task.status.in_(["pending", "in_progress"]),
                )
                .all()
            )

            if not active_db_tasks:
                files_without_tasks.append(media_file)
                continue

            # Check if any task was created/updated after boot (i.e., by current workers)
            has_post_boot_task = any(
                task.updated_at and task.updated_at > boot_time for task in active_db_tasks
            )

            if not has_post_boot_task:
                files_without_tasks.append(media_file)

        return files_without_tasks

    def _find_stale_pending_files(self, db: Session) -> list[MediaFile]:
        """Find files that have been in PENDING state for too long."""
        stale_time = datetime.now(timezone.utc) - timedelta(hours=1)

        return (  # type: ignore[no-any-return]
            db.query(MediaFile)
            .filter(
                MediaFile.status == FileStatus.PENDING,
                MediaFile.upload_time < stale_time,
            )
            .all()
        )


# Service instance
task_detection_service = TaskDetectionService()
