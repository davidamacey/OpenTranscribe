"""
Celery tasks for file cleanup and system maintenance.
"""

import logging
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any
from zoneinfo import ZoneInfo

from celery import shared_task

from app.core.celery import celery_app
from app.core.constants import UtilityPriority
from app.db.session_utils import session_scope
from app.services.file_cleanup_service import cleanup_service

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="cleanup.run_periodic_cleanup", priority=UtilityPriority.ROUTINE)
def run_periodic_cleanup(self):
    """
    Periodic task to clean up stuck files and maintain system health.

    This task should be run regularly (e.g., every 30 minutes) to:
    - Detect and recover stuck files
    - Mark orphaned files for cleanup
    - Generate system health reports
    """
    try:
        logger.info("Starting periodic cleanup cycle")

        # Run the cleanup cycle
        results = cleanup_service.run_cleanup_cycle()

        # Log results
        logger.info(
            f"Periodic cleanup completed: "
            f"checked {results['stuck_files_checked']} files, "
            f"recovered {results['files_recovered']}, "
            f"marked {results['files_marked_orphaned']} as orphaned"
        )

        if results["cleanup_errors"]:
            logger.warning(
                f"Cleanup had {len(results['cleanup_errors'])} errors: {results['cleanup_errors']}"
            )

        if results["recommendations"]:
            logger.info(f"System health recommendations: {results['recommendations']}")

        return results

    except Exception as e:
        logger.error(f"Critical error in periodic cleanup: {e}")
        # Don't retry automatically to avoid infinite loops
        raise self.retry(countdown=3600, max_retries=3) from e  # Retry in 1 hour


@shared_task(bind=True, name="cleanup.deep_cleanup", priority=UtilityPriority.BACKGROUND)
def run_deep_cleanup(self, dry_run: bool = False):
    """
    Deep cleanup task for removing orphaned files (admin-triggered).

    Args:
        dry_run: If True, only preview what would be cleaned up
    """
    try:
        logger.info(f"Starting deep cleanup (dry_run={dry_run})")

        with session_scope() as db:
            # Force cleanup of orphaned files
            results = cleanup_service.force_cleanup_orphaned_files(db, dry_run=dry_run)

            logger.info(
                f"Deep cleanup completed: "
                f"eligible: {results['eligible_for_deletion']}, "
                f"deleted: {results['successfully_deleted']}, "
                f"errors: {len(results['deletion_errors'])}"
            )

            if results["deletion_errors"]:
                logger.error(f"Deep cleanup errors: {results['deletion_errors']}")

            return results

    except Exception as e:
        logger.error(f"Critical error in deep cleanup: {e}")
        raise


@shared_task(bind=True, name="cleanup.health_check", priority=UtilityPriority.OPERATIONAL)
def system_health_check(self):
    """
    Generate a system health report.
    """
    try:
        logger.info("Running system health check")

        with session_scope() as db:
            stats = cleanup_service.get_cleanup_statistics(db)

            logger.info(
                f"System health check completed: "
                f"health_score={stats['health_score']}, "
                f"stuck_files={stats['stuck_files_detected']}, "
                f"cleanup_eligible={stats['files_eligible_for_cleanup']}"
            )

            # Log warnings for poor health
            if stats["health_score"] in ["poor", "fair"]:
                logger.warning(
                    f"System health is {stats['health_score']}. "
                    f"Consider running manual cleanup or investigating issues."
                )

            return stats

    except Exception as e:
        logger.error(f"Error in system health check: {e}")
        raise


@shared_task(bind=True, name="cleanup.emergency_recovery", priority=UtilityPriority.EMERGENCY)
def emergency_file_recovery(self, file_uuids: list):
    """
    Emergency recovery task for specific files (admin-triggered).

    Args:
        file_uuids: List of file UUIDs to attempt recovery on
    """
    from app.utils.uuid_helpers import get_file_by_uuid

    try:
        logger.info(f"Starting emergency recovery for files: {file_uuids}")

        results: dict[str, Any] = {
            "files_processed": len(file_uuids),
            "recovered": 0,
            "failed": 0,
            "errors": [],
        }

        with session_scope() as db:
            from app.utils.task_utils import recover_stuck_file

            for file_uuid in file_uuids:
                try:
                    # Convert UUID to internal ID
                    media_file = get_file_by_uuid(db, file_uuid)
                    file_id = int(media_file.id)

                    success = recover_stuck_file(db, file_id)
                    if success:
                        results["recovered"] += 1
                        logger.info(f"Successfully recovered file {file_id}")
                    else:
                        results["failed"] += 1
                        logger.warning(f"Failed to recover file {file_id}")
                except Exception as e:
                    results["failed"] += 1
                    error_msg = f"Error recovering file {file_uuid}: {str(e)}"
                    results["errors"].append(error_msg)
                    logger.error(error_msg)

            logger.info(
                f"Emergency recovery completed: "
                f"processed {results['files_processed']}, "
                f"recovered {results['recovered']}, "
                f"failed {results['failed']}"
            )

            return results

    except Exception as e:
        logger.error(f"Critical error in emergency recovery: {e}")
        raise


@celery_app.task(name="cleanup_expired_files", priority=UtilityPriority.ROUTINE)
def cleanup_expired_files(force: bool = False):
    """
    Delete media files that have exceeded the configured retention window.

    Reads retention configuration from system settings, checks whether the
    task is scheduled to run in the current hour (unless force=True), and
    deletes all eligible completed (and optionally error-status) files whose
    age exceeds the configured retention_days threshold.

    Args:
        force: When True, skip the enabled/hour/already-ran-today guards and
               execute the deletion pass unconditionally.

    Returns:
        A dict with one of the following shapes:
        - ``{"status": "disabled"}`` – retention is turned off and force is False.
        - ``{"status": "not_scheduled_now"}`` – current hour does not match the
          configured run_time hour and force is False.
        - ``{"status": "already_ran_today"}`` – the task already completed
          successfully today in the configured timezone and force is False.
        - ``{"status": "completed", "deleted": int, "failed": int}`` – the
          deletion pass finished; deleted/failed counts reflect file outcomes.
        - ``{"status": "error", "error": str}`` – an unexpected exception
          occurred; details are included for diagnostics.
    """
    from app.models.media import FileStatus
    from app.models.media import MediaFile
    from app.services.file_cleanup_service import auto_delete_media_file
    from app.services.system_settings_service import get_retention_config
    from app.services.system_settings_service import set_setting

    try:
        with session_scope() as db:
            config = get_retention_config(db)

            if not force:
                # Guard 1: retention must be enabled
                if not config["retention_enabled"]:
                    logger.debug("cleanup_expired_files: retention disabled, skipping")
                    return {"status": "disabled"}

                # Guard 2: current hour must match the scheduled run hour
                tz = ZoneInfo(config["timezone"])
                now_local = datetime.now(tz)
                scheduled_hour = int(config["run_time"].split(":")[0])
                if now_local.hour != scheduled_hour:
                    logger.debug(
                        f"cleanup_expired_files: not scheduled hour "
                        f"(now={now_local.hour}, scheduled={scheduled_hour}), skipping"
                    )
                    return {"status": "not_scheduled_now"}

                # Guard 3: must not have already run today in this timezone
                last_run_str = config["last_run"]
                if last_run_str is not None:
                    try:
                        last_run_utc = datetime.fromisoformat(last_run_str)
                        last_run_local = last_run_utc.astimezone(tz)
                        if last_run_local.date() == now_local.date():
                            logger.debug("cleanup_expired_files: already ran today, skipping")
                            return {"status": "already_ran_today"}
                    except (ValueError, TypeError) as parse_err:
                        logger.warning(
                            f"cleanup_expired_files: could not parse last_run "
                            f"'{last_run_str}': {parse_err}; proceeding with run"
                        )

            # Build the age cutoff in UTC
            cutoff = datetime.now(timezone.utc) - timedelta(days=config["retention_days"])

            # Determine which statuses are eligible for deletion
            eligible_statuses = [FileStatus.COMPLETED.value]
            if config["delete_error_files"]:
                eligible_statuses.append(FileStatus.ERROR.value)

            # Query files that have aged out; eager-load speakers to avoid N+1 queries
            # when auto_delete_media_file iterates file.speakers for embedding cleanup.
            from sqlalchemy.orm import selectinload

            eligible_files = (
                db.query(MediaFile)
                .options(selectinload(MediaFile.speakers))
                .filter(
                    MediaFile.status.in_(eligible_statuses),
                    ((MediaFile.completed_at.isnot(None)) & (MediaFile.completed_at < cutoff))
                    | ((MediaFile.completed_at.is_(None)) & (MediaFile.upload_time < cutoff)),
                )
                .all()
            )

            logger.info(
                f"cleanup_expired_files: found {len(eligible_files)} file(s) "
                f"eligible for deletion (cutoff={cutoff.isoformat()})"
            )

            deleted = 0
            failed = 0

            for media_file in eligible_files:
                result = auto_delete_media_file(db, media_file)
                if result["deleted"]:
                    deleted += 1
                    logger.info(
                        f"cleanup_expired_files: deleted file id={media_file.id} "
                        f"uuid={media_file.uuid}"
                    )
                else:
                    failed += 1
                    logger.error(
                        f"cleanup_expired_files: failed to delete file "
                        f"id={media_file.id} uuid={media_file.uuid}: {result.get('error')}"
                    )

            # Persist run metadata to system settings — store with explicit UTC offset
            # so the already_ran_today guard parses correctly on any server timezone
            run_timestamp = datetime.now(timezone.utc).isoformat()
            set_setting(
                db,
                "files.retention_last_run",
                run_timestamp,
                "ISO UTC timestamp of the last retention cleanup run",
            )
            set_setting(
                db,
                "files.retention_last_run_deleted",
                deleted,
                "Number of files deleted in the most recent retention cleanup run",
            )

            logger.info(f"cleanup_expired_files: completed — deleted={deleted}, failed={failed}")
            return {"status": "completed", "deleted": deleted, "failed": failed}

    except Exception as exc:
        logger.error(f"cleanup_expired_files: unexpected error: {exc}", exc_info=True)
        return {"status": "error", "error": str(exc)}
