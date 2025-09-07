"""
Celery tasks for file cleanup and system maintenance.
"""

import logging

from celery import shared_task

from app.db.session_utils import session_scope
from app.services.file_cleanup_service import cleanup_service

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="cleanup.run_periodic_cleanup")
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
        raise self.retry(countdown=3600, max_retries=3)  # Retry in 1 hour


@shared_task(bind=True, name="cleanup.deep_cleanup")
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


@shared_task(bind=True, name="cleanup.health_check")
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


@shared_task(bind=True, name="cleanup.emergency_recovery")
def emergency_file_recovery(self, file_ids: list):
    """
    Emergency recovery task for specific files (admin-triggered).

    Args:
        file_ids: List of file IDs to attempt recovery on
    """
    try:
        logger.info(f"Starting emergency recovery for files: {file_ids}")

        results = {
            "files_processed": len(file_ids),
            "recovered": 0,
            "failed": 0,
            "errors": [],
        }

        with session_scope() as db:
            from app.utils.task_utils import recover_stuck_file

            for file_id in file_ids:
                try:
                    success = recover_stuck_file(db, file_id)
                    if success:
                        results["recovered"] += 1
                        logger.info(f"Successfully recovered file {file_id}")
                    else:
                        results["failed"] += 1
                        logger.warning(f"Failed to recover file {file_id}")
                except Exception as e:
                    results["failed"] += 1
                    error_msg = f"Error recovering file {file_id}: {str(e)}"
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
