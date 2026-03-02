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


def _query_single_gpu(device_id: int, subprocess_mod, format_bytes) -> dict | None:
    """Query nvidia-smi for one GPU device and return a parsed stats dict.

    Args:
        device_id: NVIDIA device index to query.
        subprocess_mod: The subprocess module (passed in to avoid re-import).
        format_bytes: Byte-formatting helper (passed in to avoid closure issues).

    Returns:
        Dict of GPU stats, or None if the query fails.
    """
    try:
        result = subprocess_mod.run(  # noqa: S603 # nosec B603 B607
            [  # noqa: S607
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,memory.free,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
                f"--id={device_id}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        parts = result.stdout.strip().split(", ")
        gpu_name = parts[0]
        memory_used_mib = float(parts[1])
        memory_total_mib = float(parts[2])
        memory_free_mib = float(parts[3])
        utilization_percent = int(parts[4]) if len(parts) > 4 else None
        temperature_celsius = int(parts[5]) if len(parts) > 5 else None

        memory_used = memory_used_mib * 1024 * 1024
        memory_total = memory_total_mib * 1024 * 1024
        memory_free = memory_free_mib * 1024 * 1024
        memory_percent = (memory_used / memory_total * 100) if memory_total > 0 else 0

        return {
            "available": True,
            "device_id": device_id,
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
    except Exception as e:
        logger.warning(f"nvidia-smi query for device {device_id} failed: {e}")
        return None


@celery_app.task(name="system.update_gpu_stats", bind=True)
def update_gpu_stats(self):
    """Periodic task to update GPU statistics in Redis.

    Runs on the cpu worker (which has 'count: all' NVIDIA device access via
    docker-compose.gpu.yml) so it fires independently of long-running GPU
    transcription tasks that hold the gpu queue at concurrency=1.

    Collects stats for every GPU the app is actively using:
      - Normal mode:      GPU_DEVICE_ID only
      - GPU-scale mode:   GPU_SCALE_DEVICE_ID (scaled worker) +
                          GPU_DEVICE_ID (default worker, when GPU_SCALE_DEFAULT_WORKER=1)

    Stores a JSON array in Redis key "gpu_stats" and broadcasts it via WebSocket
    so the frontend can cycle through all active GPUs.

    Returns:
        List of GPU stat dicts (one per active device).
    """
    try:
        import os
        import subprocess

        def format_bytes(byte_count):
            for unit in ["B", "KB", "MB", "GB", "TB"]:
                if byte_count < 1024 or unit == "TB":
                    return f"{byte_count:.2f} {unit}"
                byte_count /= 1024
            return f"{byte_count:.2f} TB"

        # Determine which GPU devices the app workers are using.
        # All values come from .env via env_file on the cpu-worker service.
        gpu_scale_enabled = os.environ.get("GPU_SCALE_ENABLED", "false").lower() == "true"
        scale_device_id = int(os.environ.get("GPU_SCALE_DEVICE_ID", "2"))
        default_device_id = int(os.environ.get("GPU_DEVICE_ID", "0"))
        scale_default_worker = os.environ.get("GPU_SCALE_DEFAULT_WORKER", "0") == "1"

        if gpu_scale_enabled:
            # Scaled worker is always the primary; add default worker if also active.
            device_ids = [scale_device_id]
            if scale_default_worker and default_device_id != scale_device_id:
                device_ids.append(default_device_id)
        else:
            device_ids = [default_device_id]

        gpu_stats_list = []
        for device_id in device_ids:
            stats = _query_single_gpu(device_id, subprocess, format_bytes)
            if stats:
                gpu_stats_list.append(stats)

        if not gpu_stats_list:
            gpu_stats_list = [
                {
                    "available": False,
                    "device_id": device_ids[0] if device_ids else 0,
                    "name": "No GPU Available",
                    "memory_total": "N/A",
                    "memory_used": "N/A",
                    "memory_free": "N/A",
                    "memory_percent": "N/A",
                }
            ]

        # Store array in Redis (10-min TTL; beat runs every 5 min)
        redis_client = celery_app.backend.client
        redis_client.setex("gpu_stats", 600, json.dumps(gpu_stats_list))

        # Broadcast array to all connected WebSocket clients
        try:
            _get_broadcast_redis().publish(
                "websocket_notifications",
                json.dumps(
                    {
                        "type": "gpu_stats_update",
                        "broadcast": True,
                        "data": gpu_stats_list,
                    }
                ),
            )
            logger.debug(f"Broadcast GPU stats for {len(gpu_stats_list)} device(s)")
        except Exception as broadcast_err:
            logger.warning(f"Failed to broadcast GPU stats: {broadcast_err}")

        # Clear debounce lock (best-effort, non-critical)
        with contextlib.suppress(Exception):  # noqa: S110
            redis_client.delete("gpu_stats_pending")

        logger.debug(f"Updated GPU stats in Redis: {gpu_stats_list}")
        return gpu_stats_list

    except FileNotFoundError:
        logger.warning("nvidia-smi not found — no GPU available")
        fallback = [
            {
                "available": False,
                "device_id": 0,
                "name": "No GPU Available",
                "memory_total": "N/A",
                "memory_used": "N/A",
                "memory_free": "N/A",
                "memory_percent": "N/A",
            }
        ]
        with contextlib.suppress(Exception):
            celery_app.backend.client.setex("gpu_stats", 600, json.dumps(fallback))
        return fallback
    except Exception as e:
        logger.error(f"Error updating GPU stats: {str(e)}")
        fallback = [
            {
                "available": False,
                "device_id": 0,
                "name": "Error",
                "memory_total": "Unknown",
                "memory_used": "Unknown",
                "memory_free": "Unknown",
                "memory_percent": "Unknown",
                "error": str(e),
            }
        ]
        with contextlib.suppress(Exception):
            celery_app.backend.client.setex("gpu_stats", 600, json.dumps(fallback))
        return fallback


# All recovery tasks have been moved to app.tasks.recovery
