"""System endpoints accessible to all authenticated users."""

import logging
import platform
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session

from app.api.endpoints.admin import get_cpu_usage
from app.api.endpoints.admin import get_disk_usage
from app.api.endpoints.admin import get_gpu_usage
from app.api.endpoints.admin import get_memory_usage
from app.api.endpoints.admin import get_system_uptime
from app.api.endpoints.auth import get_current_user
from app.db.base import get_db
from app.models.media import MediaFile
from app.models.media import Speaker
from app.models.media import TranscriptSegment
from app.models.user import User
from app.services.protected_media_providers import get_protected_media_auth_config

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/stats", response_model=dict[str, Any])
async def get_system_stats(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    Get system statistics accessible to all authenticated users.

    Returns system health metrics (CPU, memory, disk, GPU) and aggregate
    statistics about files, tasks, and models.
    """
    logger.info(f"System stats requested by user {current_user.email}")

    try:
        # System statistics
        try:
            system_stats = {
                "cpu": get_cpu_usage(),
                "memory": get_memory_usage(),
                "disk": get_disk_usage(),
                "gpu": get_gpu_usage(),
                "uptime": get_system_uptime(),
            }
        except Exception as e:
            logger.error(f"Error getting system stats: {e}")
            system_stats = {
                "cpu": {
                    "total_percent": "Unknown",
                    "per_cpu": [],
                    "logical_cores": 0,
                    "physical_cores": 0,
                },
                "gpu": {
                    "available": False,
                    "name": "Error",
                    "memory_total": "Unknown",
                    "memory_used": "Unknown",
                    "memory_free": "Unknown",
                    "memory_percent": "Unknown",
                },
                "memory": {
                    "total": "Unknown",
                    "available": "Unknown",
                    "used": "Unknown",
                    "percent": "Unknown",
                },
                "disk": {
                    "total": "Unknown",
                    "used": "Unknown",
                    "free": "Unknown",
                    "percent": "Unknown",
                },
                "uptime": "Unknown",
            }

        # Get user statistics (only counts, not sensitive data)
        from datetime import datetime
        from datetime import timedelta
        from datetime import timezone

        total_users = db.query(User).count()

        # Calculate new users in last 7 days
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        new_users = db.query(User).filter(User.created_at >= seven_days_ago).count()

        # Get file statistics
        from sqlalchemy.sql import func

        total_files = db.query(MediaFile).count()

        # Calculate new files in last 7 days
        new_files = db.query(MediaFile).filter(MediaFile.upload_time >= seven_days_ago).count()

        # Get total duration (in seconds)
        total_duration_result = db.query(func.sum(MediaFile.duration)).scalar()
        total_duration = total_duration_result if total_duration_result else 0

        # Get transcript statistics
        total_segments = db.query(TranscriptSegment).count()

        # Get speaker statistics
        total_speakers = db.query(Speaker).count()

        # Get task statistics
        from app.models.media import Task
        from app.utils.task_utils import TASK_STATUS_COMPLETED
        from app.utils.task_utils import TASK_STATUS_FAILED
        from app.utils.task_utils import TASK_STATUS_IN_PROGRESS
        from app.utils.task_utils import TASK_STATUS_PENDING

        total_tasks = db.query(Task).count()
        pending_tasks = db.query(Task).filter(Task.status == TASK_STATUS_PENDING).count()
        running_tasks = db.query(Task).filter(Task.status == TASK_STATUS_IN_PROGRESS).count()
        completed_tasks = db.query(Task).filter(Task.status == TASK_STATUS_COMPLETED).count()
        failed_tasks = db.query(Task).filter(Task.status == TASK_STATUS_FAILED).count()

        # Calculate success rate
        success_rate = 0
        if total_tasks > 0:
            success_rate = round((completed_tasks / total_tasks) * 100, 2)

        # Calculate average processing time for completed tasks
        avg_processing_time = 0
        completed_task_list = (
            db.query(Task)
            .filter(
                Task.status == TASK_STATUS_COMPLETED,
                Task.created_at.isnot(None),
                Task.completed_at.isnot(None),
            )
            .all()
        )

        if completed_task_list:
            total_time = sum(
                (task.completed_at - task.created_at).total_seconds()
                for task in completed_task_list
                if task.completed_at and task.created_at
            )
            avg_processing_time = (
                total_time / len(completed_task_list) if completed_task_list else 0
            )

        # Get recent tasks (last 10)
        recent_tasks = db.query(Task).order_by(Task.created_at.desc()).limit(10).all()
        recent = []
        for task in recent_tasks:
            elapsed = 0
            if task.completed_at and task.created_at:
                elapsed = (task.completed_at - task.created_at).total_seconds()
            elif task.created_at:
                # Make sure both datetimes are timezone-aware
                now = datetime.now(timezone.utc)
                created_at = task.created_at
                # Convert created_at to timezone-aware if it's naive
                if created_at and created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                elapsed = (now - created_at).total_seconds() if created_at else 0
            recent.append(
                {
                    "id": task.id,
                    "type": getattr(task, "task_type", ""),
                    "status": task.status,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "elapsed": int(elapsed) if elapsed else 0,
                }
            )

        # Get AI model configuration
        from app.core.config import settings

        models_info = {
            "whisper": {
                "name": settings.WHISPER_MODEL,
                "description": f"Whisper {settings.WHISPER_MODEL}",
                "purpose": "Speech Recognition & Transcription",
            },
            "diarization": {
                "name": settings.PYANNOTE_MODEL,
                "description": "PyAnnote Speaker Diarization 3.1",
                "purpose": "Speaker Identification & Segmentation",
            },
            "alignment": {
                "name": "Wav2Vec2 (Language-Adaptive)",
                "description": "WhisperX Alignment Model",
                "purpose": "Word-Level Timestamp Alignment",
            },
        }

        # Construct the response
        stats = {
            "users": {
                "total": total_users,
                "new": new_users,
            },
            "files": {
                "total": total_files,
                "new": new_files,
                "total_duration": round(total_duration, 2) if total_duration else 0,
                "segments": total_segments,
            },
            "transcripts": {"total_segments": total_segments},
            "speakers": {
                "total": total_speakers,
                "avg_per_file": round(total_speakers / total_files, 2) if total_files > 0 else 0,
            },
            "models": models_info,
            "system": {
                "version": "1.0.0",
                "uptime": system_stats["uptime"],
                "memory": system_stats["memory"],
                "cpu": system_stats["cpu"],
                "disk": system_stats["disk"],
                "gpu": system_stats["gpu"],
                "platform": platform.platform(),
                "python_version": platform.python_version(),
            },
            "tasks": {
                "total": total_tasks,
                "pending": pending_tasks,
                "running": running_tasks,
                "completed": completed_tasks,
                "failed": failed_tasks,
                "success_rate": success_rate,
                "avg_processing_time": round(avg_processing_time, 2),
                "recent": recent,
            },
        }

        return stats
    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving system statistics: {str(e)}",
        ) from e


@router.get("/config/protected-media-auth", response_model=list[dict[str, Any]])
async def get_protected_media_auth(current_user: User = Depends(get_current_user)):
    """Return public auth configuration for protected media providers.

    Used by the frontend to decide when to prompt for username/password
    (or other credentials) when processing media URLs.
    """
    try:
        return get_protected_media_auth_config()
    except Exception as e:
        logger.error(f"Error getting protected media auth config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving protected media configuration",
        ) from e
