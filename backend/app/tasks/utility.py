"""
Utility tasks for maintenance and system health.

This module contains general utility tasks. Recovery-specific tasks
have been moved to app.tasks.recovery for better organization.
"""

import contextlib
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
        summary["error"] = str(e)  # type: ignore[assignment]

    return summary


@celery_app.task(name="update_gpu_stats", bind=True)
def update_gpu_stats(self):
    """
    Periodic task to update GPU statistics in Redis.

    On DGX Spark / GB10, nvidia-smi framebuffer memory stats can be unavailable
    because the platform uses unified memory. In that case we fall back to
    torch.cuda.mem_get_info() and clearly label the source.
    """

    def safe_float(value):
        if value is None:
            return None
        value = str(value).strip()
        if value in {"[N/A]", "N/A", "", "Unknown", "Not Supported"}:
            return None
        try:
            return float(value)
        except Exception:
            return None

    def format_bytes(byte_count):
        if byte_count is None:
            return "N/A"
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if byte_count < 1024 or unit == "TB":
                return f"{byte_count:.2f} {unit}"
            byte_count /= 1024
        return f"{byte_count:.2f} TB"

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
                "memory_source": "none",
            }
        else:
            device_id = 0
            gpu_properties = torch.cuda.get_device_properties(device_id)

            memory_total = None
            memory_used = None
            memory_free = None
            memory_percent = None
            memory_source = None
            memory_note = None

            # 1) Preferred fallback on DGX Spark / GB10:
            # CUDA-visible memory via PyTorch
            try:
                free_bytes, total_bytes = torch.cuda.mem_get_info(device_id)
                memory_free = float(free_bytes)
                memory_total = float(total_bytes)
                memory_used = memory_total - memory_free
                if memory_total > 0:
                    memory_percent = memory_used / memory_total * 100
                memory_source = "cudaMemGetInfo"
                memory_note = "CUDA-visible memory on unified-memory system"
            except Exception:
                pass

            # 2) Try nvidia-smi only if CUDA mem info did not work
            if memory_total is None:
                try:
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

                    raw_values = [v.strip() for v in result.stdout.strip().split(",")]

                    memory_used_mib = safe_float(raw_values[0]) if len(raw_values) > 0 else None
                    memory_total_mib = safe_float(raw_values[1]) if len(raw_values) > 1 else None
                    memory_free_mib = safe_float(raw_values[2]) if len(raw_values) > 2 else None

                    memory_used = (
                        memory_used_mib * 1024 * 1024 if memory_used_mib is not None else None
                    )
                    memory_total = (
                        memory_total_mib * 1024 * 1024 if memory_total_mib is not None else None
                    )
                    memory_free = (
                        memory_free_mib * 1024 * 1024 if memory_free_mib is not None else None
                    )

                    if memory_used is not None and memory_total not in (None, 0):
                        memory_percent = memory_used / memory_total * 100

                    memory_source = "nvidia-smi"
                except Exception:
                    pass

            # 3) Final fallback for DGX Spark / GB10 UMA
            if memory_total is None:
                memory_source = "unified-memory"
                memory_note = (
                    "DGX Spark / GB10 uses unified memory; nvidia-smi framebuffer "
                    "memory stats may be unavailable"
                )

            gpu_stats = {
                "available": True,
                "name": gpu_properties.name,
                "memory_total": format_bytes(memory_total),
                "memory_used": format_bytes(memory_used),
                "memory_free": format_bytes(memory_free),
                "memory_percent": f"{memory_percent:.1f}%" if memory_percent is not None else "N/A",
                "memory_source": memory_source or "unknown",
                "memory_note": memory_note,
            }

        redis_client = celery_app.backend.client
        redis_client.setex("gpu_stats", 60, json.dumps(gpu_stats))

        try:
            import redis as sync_redis
            from app.core.config import settings

            broadcast_client = sync_redis.from_url(settings.REDIS_URL)
            broadcast_client.publish(
                "websocket_notifications",
                json.dumps(
                    {
                        "type": "gpu_stats_update",
                        "broadcast": True,
                        "data": gpu_stats,
                    }
                ),
            )
        except Exception as broadcast_err:
            logger.warning(f"Failed to broadcast GPU stats: {broadcast_err}")

        with contextlib.suppress(Exception):
            redis_client.delete("gpu_stats_pending")

        logger.debug(f"Updated GPU stats in Redis: {gpu_stats}")
        return gpu_stats

    except ImportError:
        logger.warning("PyTorch not available for GPU monitoring")
        return {
            "available": False,
            "name": "PyTorch Not Installed",
            "memory_total": "N/A",
            "memory_used": "N/A",
            "memory_free": "N/A",
            "memory_percent": "N/A",
            "memory_source": "none",
        }
    except Exception as e:
        logger.error(f"Error updating GPU stats: {str(e)}")
        return {
            "available": False,
            "name": "Error",
            "memory_total": "Unknown",
            "memory_used": "Unknown",
            "memory_free": "Unknown",
            "memory_percent": "Unknown",
            "memory_source": "error",
            "error": str(e),
        }
        
# All recovery tasks have been moved to app.tasks.recovery
