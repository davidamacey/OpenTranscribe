"""
Utility tasks for maintenance and system health.

This module contains general utility tasks. Recovery-specific tasks
have been moved to app.tasks.recovery for better organization.
"""

import logging

from app.core.celery import celery_app
from app.db.session_utils import session_scope
from app.services.task_detection_service import task_detection_service
from app.services.task_recovery_service import task_recovery_service

logger = logging.getLogger(__name__)


@celery_app.task(name="check_tasks_health", bind=True)
def check_tasks_health(self):
    """
    Periodic task to check for stuck tasks and inconsistent media files.

    This task runs on a schedule to identify and recover:
    1. Tasks that are stuck in processing or pending state
    2. Media files with inconsistent states

    Returns:
        Dictionary with summary of actions taken
    """
    summary = {
        "stuck_tasks_found": 0,
        "stuck_tasks_recovered": 0,
        "inconsistent_files_found": 0,
        "inconsistent_files_fixed": 0,
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
            inconsistent_files = (
                task_detection_service.identify_inconsistent_media_files(db)
            )
            summary["inconsistent_files_found"] = len(inconsistent_files)

            fixed_count = 0
            for media_file in inconsistent_files:
                if task_recovery_service.fix_inconsistent_media_file(db, media_file):
                    fixed_count += 1

            summary["inconsistent_files_fixed"] = fixed_count

            # Log summary
            logger.info(
                f"Task health check completed: "
                f"Found {summary['stuck_tasks_found']} stuck tasks, recovered {summary['stuck_tasks_recovered']}; "
                f"Found {summary['inconsistent_files_found']} inconsistent files, fixed {summary['inconsistent_files_fixed']}"
            )

    except Exception as e:
        logger.error(f"Error in task health check: {str(e)}")
        summary["error"] = str(e)

    return summary


# All recovery tasks have been moved to app.tasks.recovery
