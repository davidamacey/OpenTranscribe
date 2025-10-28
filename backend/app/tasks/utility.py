"""
Utility tasks for maintenance and system health.

This module contains general utility tasks. Recovery-specific tasks
have been moved to app.tasks.recovery for better organization.
"""

import json
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
            inconsistent_files = task_detection_service.identify_inconsistent_media_files(db)
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


@celery_app.task(name="update_gpu_stats", bind=True)
def update_gpu_stats(self):
    """
    Periodic task to update GPU statistics in Redis.

    This task runs on the celery worker (which has GPU access) and stores
    GPU memory stats in Redis so the backend API can retrieve them.

    Uses nvidia-smi to get accurate GPU memory usage including all processes,
    not just PyTorch allocated memory.

    Returns:
        Dictionary with GPU stats or error status
    """
    try:
        import subprocess

        import torch

        if not torch.cuda.is_available():
            gpu_stats = {
                "available": False,
                "name": "No GPU Available",
                "memory_total": "N/A",
                "memory_used": "N/A",
                "memory_free": "N/A",
                "memory_percent": "N/A",
            }
        else:
            # Get GPU device info from PyTorch
            device_id = 0  # Primary GPU
            gpu_properties = torch.cuda.get_device_properties(device_id)

            # Use nvidia-smi for accurate memory usage (includes all processes)
            # Format: memory.used,memory.total,memory.free (in MiB)
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used,memory.total,memory.free",
                    "--format=csv,noheader,nounits",
                    f"--id={device_id}",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            # Parse the output: "used, total, free" in MiB
            memory_values = result.stdout.strip().split(", ")
            memory_used_mib = float(memory_values[0])
            memory_total_mib = float(memory_values[1])
            memory_free_mib = float(memory_values[2])

            # Convert MiB to bytes for formatting
            memory_used = memory_used_mib * 1024 * 1024
            memory_total = memory_total_mib * 1024 * 1024
            memory_free = memory_free_mib * 1024 * 1024

            # Calculate percentage used
            memory_percent = (memory_used / memory_total * 100) if memory_total > 0 else 0

            # Format bytes to human-readable
            def format_bytes(byte_count):
                for unit in ["B", "KB", "MB", "GB", "TB"]:
                    if byte_count < 1024 or unit == "TB":
                        return f"{byte_count:.2f} {unit}"
                    byte_count /= 1024
                return f"{byte_count:.2f} TB"

            gpu_stats = {
                "available": True,
                "name": gpu_properties.name,
                "memory_total": format_bytes(memory_total),
                "memory_used": format_bytes(memory_used),
                "memory_free": format_bytes(memory_free),
                "memory_percent": f"{memory_percent:.1f}%",
            }

        # Store in Redis with 60 second expiration
        redis_client = celery_app.backend.client
        redis_client.setex(
            "gpu_stats",
            60,  # Expire after 60 seconds
            json.dumps(gpu_stats),
        )

        logger.debug(f"Updated GPU stats in Redis: {gpu_stats}")
        return gpu_stats

    except ImportError:
        logger.warning("PyTorch not available for GPU monitoring")
        gpu_stats = {
            "available": False,
            "name": "PyTorch Not Installed",
            "memory_total": "N/A",
            "memory_used": "N/A",
            "memory_free": "N/A",
            "memory_percent": "N/A",
        }
        return gpu_stats
    except Exception as e:
        logger.error(f"Error updating GPU stats: {str(e)}")
        return {
            "available": False,
            "name": "Error",
            "memory_total": "Unknown",
            "memory_used": "Unknown",
            "memory_free": "Unknown",
            "memory_percent": "Unknown",
            "error": str(e),
        }


# All recovery tasks have been moved to app.tasks.recovery
