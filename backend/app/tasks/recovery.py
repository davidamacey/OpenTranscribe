"""
Celery tasks for system recovery operations.

This module contains Celery tasks that handle various recovery scenarios,
separated from other utility tasks for better organization.
"""

import logging

from app.core.celery import celery_app
from app.core.task_config import task_recovery_config
from app.db.session_utils import session_scope
from app.services.task_detection_service import task_detection_service
from app.services.task_recovery_service import task_recovery_service
from app.utils.task_lock import with_task_lock

logger = logging.getLogger(__name__)


@celery_app.task(name="startup_recovery", bind=True)
def startup_recovery_task(self):
    """
    Recovery task to run on system startup to handle files/tasks interrupted by
    system crashes, power outages, or Docker shutdowns.

    This task specifically handles:
    1. Files stuck in PROCESSING state with no active tasks
    2. Tasks that were in progress when system went down
    3. Files that should be retried after system recovery

    Returns:
        Dictionary with summary of recovery actions
    """
    summary = {
        "abandoned_files_found": 0,
        "abandoned_files_reset": 0,
        "orphaned_tasks_found": 0,
        "orphaned_tasks_failed": 0,
        "files_retried": 0,
    }

    try:
        with session_scope() as db:
            # Step 1: Handle abandoned files
            abandoned_files = task_detection_service.identify_abandoned_files(db)
            summary["abandoned_files_found"] = len(abandoned_files)

            reset_count = task_recovery_service.reset_abandoned_files(db, abandoned_files)
            summary["abandoned_files_reset"] = reset_count

            # Step 2: Retry abandoned files
            retry_count = 0
            for media_file in abandoned_files[:reset_count]:  # Only retry successfully reset files
                if task_recovery_service.schedule_file_retry(int(media_file.id)):
                    retry_count += 1
            summary["files_retried"] = retry_count

            # Step 3: Handle orphaned tasks
            orphaned_tasks = task_detection_service.identify_orphaned_tasks(db)
            summary["orphaned_tasks_found"] = len(orphaned_tasks)

            failed_count = task_recovery_service.recover_orphaned_tasks(db, orphaned_tasks)
            summary["orphaned_tasks_failed"] = failed_count

            logger.info(
                f"Startup recovery completed: "
                f"Reset {summary['abandoned_files_reset']} abandoned files, "
                f"failed {summary['orphaned_tasks_failed']} orphaned tasks, "
                f"retried {summary['files_retried']} transcriptions"
            )

    except Exception as e:
        logger.error(f"Error in startup recovery: {str(e)}")
        summary["error"] = str(e)  # type: ignore[assignment]

    return summary


@celery_app.task(name="recover_user_files", bind=True)
def recover_user_files_task(self, user_id: int | None = None):
    """
    Task to recover files for a specific user or all users.
    Useful when a user reports missing/stuck files.

    Args:
        user_id: If provided, only recover files for this user. Otherwise recover all.

    Returns:
        Dictionary with summary of recovery actions
    """
    summary = {
        "users_processed": 1 if user_id else 0,
        "files_checked": 0,
        "files_recovered": 0,
        "tasks_retried": 0,
    }

    try:
        with session_scope() as db:
            if not user_id:
                # Count unique users for all files
                from app.models.media import MediaFile

                user_count = db.query(MediaFile.user_id).distinct().count()
                summary["users_processed"] = user_count

            # Find problem files
            problem_files = task_detection_service.find_user_problem_files(db, user_id)
            summary["files_checked"] = len(problem_files)

            # Recover the files
            recovery_stats = task_recovery_service.recover_user_files(db, problem_files)
            summary.update(recovery_stats)

            logger.info(
                f"User file recovery completed: "
                f"Processed {summary['users_processed']} users, "
                f"checked {summary['files_checked']} files, "
                f"recovered {summary['files_recovered']} files, "
                f"retried {summary['tasks_retried']} tasks"
            )

    except Exception as e:
        logger.error(f"Error in user file recovery: {str(e)}")
        summary["error"] = str(e)  # type: ignore[assignment]

    return summary


@celery_app.task(
    name="periodic_health_check",
    bind=True,
    time_limit=task_recovery_config.HEALTH_CHECK_MAX_RUNTIME,
)
@with_task_lock("periodic_health_check", timeout=task_recovery_config.HEALTH_CHECK_MAX_RUNTIME)
def periodic_health_check_task(self):
    """
    Periodic task to check for stuck tasks and inconsistent media files.

    This task runs on a schedule to identify and recover:
    1. Tasks that are stuck in processing or pending state
    2. Media files with inconsistent states
    3. Files stuck in processing without active Celery tasks
    4. Files that failed with GPU Out-of-Memory errors (OOM)

    Returns:
        Dictionary with summary of actions taken
    """
    summary = {
        "stuck_tasks_found": 0,
        "stuck_tasks_recovered": 0,
        "inconsistent_files_found": 0,
        "inconsistent_files_fixed": 0,
        "stuck_files_without_celery_found": 0,
        "stuck_files_without_celery_recovered": 0,
        "oom_files_found": 0,
        "oom_files_retried": 0,
        "oom_files_exhausted": 0,
        "retriable_errors_found": 0,
        "retriable_errors_retried": 0,
        "incomplete_post_transcription_found": 0,
        "post_transcription_tasks_dispatched": 0,
    }

    try:
        with session_scope() as db:
            # Step 1: Identify and recover stuck tasks
            stuck_tasks = task_detection_service.identify_stuck_tasks(db)
            summary["stuck_tasks_found"] = len(stuck_tasks)

            recovered_count = 0
            for task in stuck_tasks:
                if task_recovery_service.recover_stuck_task(db, task):
                    recovered_count += 1

            summary["stuck_tasks_recovered"] = recovered_count

            # Step 2: Identify and fix inconsistent media files
            inconsistent_files = task_detection_service.identify_inconsistent_media_files(db)
            summary["inconsistent_files_found"] = len(inconsistent_files)

            fixed_count = 0
            for media_file in inconsistent_files:
                if task_recovery_service.fix_inconsistent_media_file(db, media_file):
                    fixed_count += 1

            summary["inconsistent_files_fixed"] = fixed_count

            # Step 3: Identify and recover files stuck without active Celery tasks
            stuck_files_without_celery = (
                task_detection_service.identify_stuck_files_without_active_celery_tasks(db)
            )
            summary["stuck_files_without_celery_found"] = len(stuck_files_without_celery)

            if stuck_files_without_celery:
                recovery_stats = task_recovery_service.recover_stuck_files_without_celery_tasks(
                    db, stuck_files_without_celery
                )
                summary["stuck_files_without_celery_recovered"] = recovery_stats["files_recovered"]
                logger.info(
                    f"Recovered {recovery_stats['files_recovered']} stuck files without active Celery tasks"
                )

            # Step 4: Identify and recover files with OOM errors
            if task_recovery_config.OOM_RETRY_ENABLED:
                oom_files = task_detection_service.identify_oom_error_files(db)
                summary["oom_files_found"] = len(oom_files)

                if oom_files:
                    oom_stats = task_recovery_service.recover_oom_error_files(db, oom_files)
                    summary["oom_files_retried"] = oom_stats["files_retried"]
                    summary["oom_files_exhausted"] = oom_stats["files_exhausted"]
                    logger.info(
                        f"OOM Recovery: Found {len(oom_files)} files, "
                        f"retried {oom_stats['files_retried']}, "
                        f"exhausted {oom_stats['files_exhausted']}"
                    )

            # Step 5: Identify and recover retriable ERROR files (staggered batches)
            # YouTube downloads use a strict per-cycle cap to stay within
            # rate limits and avoid bans.  Transcription retries are less
            # sensitive so they get a larger batch.
            from app.core.config import settings as _settings

            yt_batch = _settings.YOUTUBE_RECOVERY_BATCH_SIZE  # default 3
            transcription_batch = 20

            yt_retries, tx_retries = task_detection_service.identify_retriable_error_files_split(
                db,
                youtube_batch_size=yt_batch,
                transcription_batch_size=transcription_batch,
            )
            all_retriable = yt_retries + tx_retries
            summary["retriable_errors_found"] = len(all_retriable)
            summary["retriable_youtube_found"] = len(yt_retries)
            summary["retriable_errors_retried"] = 0

            if all_retriable:
                retry_stats = task_recovery_service.recover_retriable_error_files(db, all_retriable)
                summary["retriable_errors_retried"] = retry_stats["files_retried"]
                logger.info(
                    f"Error Retry: Found {len(yt_retries)} YouTube + "
                    f"{len(tx_retries)} transcription retriable files, "
                    f"retried {retry_stats['files_retried']}, "
                    f"failed {retry_stats['files_failed']}"
                )

            # Step 6: Recover COMPLETED files with incomplete post-transcription processing
            incomplete_files = task_detection_service.identify_incomplete_post_transcription_files(
                db, batch_size=10
            )
            summary["incomplete_post_transcription_found"] = len(incomplete_files)

            if incomplete_files:
                post_stats = task_recovery_service.recover_incomplete_post_transcription_files(
                    db, incomplete_files
                )
                summary["post_transcription_tasks_dispatched"] = post_stats[
                    "total_tasks_dispatched"
                ]
                logger.info(
                    f"Post-transcription recovery: Found {len(incomplete_files)} incomplete files, "
                    f"dispatched {post_stats['total_tasks_dispatched']} tasks"
                )

            # Log summary
            logger.info(
                f"Periodic health check completed: "
                f"Found {summary['stuck_tasks_found']} stuck tasks, recovered {summary['stuck_tasks_recovered']}; "
                f"Found {summary['inconsistent_files_found']} inconsistent files, fixed {summary['inconsistent_files_fixed']}; "
                f"Found {summary['stuck_files_without_celery_found']} stuck files without Celery tasks, recovered {summary['stuck_files_without_celery_recovered']}; "
                f"Found {summary['oom_files_found']} OOM error files, retried {summary['oom_files_retried']}, exhausted {summary['oom_files_exhausted']}; "
                f"Found {summary['retriable_errors_found']} retriable errors, retried {summary['retriable_errors_retried']}; "
                f"Found {summary['incomplete_post_transcription_found']} incomplete post-transcription files, dispatched {summary['post_transcription_tasks_dispatched']} tasks"
            )

    except Exception as e:
        logger.error(f"Error in periodic health check: {str(e)}")
        summary["error"] = str(e)  # type: ignore[assignment]

    return summary
