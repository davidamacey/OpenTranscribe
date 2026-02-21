"""
Utility tasks for maintenance and system health.

This module contains general utility tasks. Recovery-specific tasks
have been moved to app.tasks.recovery for better organization.
"""

import contextlib
import json
import logging

from app.core.celery import celery_app

logger = logging.getLogger(__name__)


_broadcast_redis_client = None


def _get_broadcast_redis():
    """Get or create a module-level Redis client for WebSocket broadcasts."""
    global _broadcast_redis_client
    if _broadcast_redis_client is None:
        import redis as sync_redis

        from app.core.config import settings

        _broadcast_redis_client = sync_redis.from_url(settings.REDIS_URL)
    return _broadcast_redis_client


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
        import os
        import subprocess

        # Use GPU_DEVICE_ID env var if set, else default to 0
        device_id = int(os.environ.get("GPU_DEVICE_ID", "0"))

        # Use nvidia-smi for all GPU info (no torch dependency needed).
        # This allows the task to run on any worker queue, not just the GPU queue.
        # Query: name, memory.used, memory.total, memory.free, utilization.gpu, temperature.gpu
        # Security: Safe subprocess call with hardcoded system command (nvidia-smi).
        # Only dynamic parameter is device_id (integer), preventing command injection.
        result = subprocess.run(  # noqa: S603 - hardcoded nvidia-smi, integer device_id
            [  # noqa: S607 # nosec B603 B607
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,memory.free,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
                f"--id={device_id}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        # Parse the output: "name, used, total, free, util%, temp" in MiB/%/C
        parts = result.stdout.strip().split(", ")
        gpu_name = parts[0]
        memory_used_mib = float(parts[1])
        memory_total_mib = float(parts[2])
        memory_free_mib = float(parts[3])
        utilization_percent = int(parts[4]) if len(parts) > 4 else None
        temperature_celsius = int(parts[5]) if len(parts) > 5 else None

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
            "name": gpu_name,
            "memory_total": format_bytes(memory_total),
            "memory_used": format_bytes(memory_used),
            "memory_free": format_bytes(memory_free),
            "memory_percent": f"{memory_percent:.1f}%",
            "utilization_percent": f"{utilization_percent}%"
            if utilization_percent is not None
            else "N/A",
            "temperature_celsius": temperature_celsius,
        }

        # Store in Redis with 5-minute expiration (survives gaps between GPU tasks)
        redis_client = celery_app.backend.client
        redis_client.setex(
            "gpu_stats",
            300,  # Expire after 5 minutes
            json.dumps(gpu_stats),
        )

        # Broadcast to all connected WebSocket clients
        try:
            _get_broadcast_redis().publish(
                "websocket_notifications",
                json.dumps(
                    {
                        "type": "gpu_stats_update",
                        "broadcast": True,
                        "data": gpu_stats,
                    }
                ),
            )
            logger.debug("Broadcast GPU stats update via WebSocket")
        except Exception as broadcast_err:
            logger.warning(f"Failed to broadcast GPU stats: {broadcast_err}")

        # Clear debounce lock (best-effort, non-critical)
        with contextlib.suppress(Exception):  # noqa: S110
            redis_client.delete("gpu_stats_pending")

        logger.debug(f"Updated GPU stats in Redis: {gpu_stats}")
        return gpu_stats

    except FileNotFoundError:
        logger.warning("nvidia-smi not found — no GPU available")
        return {
            "available": False,
            "name": "No GPU Available",
            "memory_total": "N/A",
            "memory_used": "N/A",
            "memory_free": "N/A",
            "memory_percent": "N/A",
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
            "error": str(e),
        }


# All recovery tasks have been moved to app.tasks.recovery
