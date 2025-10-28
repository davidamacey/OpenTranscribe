import datetime
import logging
import platform
from typing import Any

import psutil
from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_admin_user
from app.db.base import get_db
from app.models.media import Analytics
from app.models.media import FileTag
from app.models.media import MediaFile
from app.models.media import Speaker
from app.models.media import TranscriptSegment
from app.models.user import User
from app.schemas.user import User as UserSchema
from app.schemas.user import UserCreate

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()


# System statistics utility functions
def get_system_uptime():
    """Get system uptime in a readable format"""
    try:
        # Get boot time and calculate uptime
        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.datetime.now() - boot_time

        # Format as days, hours, minutes, seconds
        days, remainder = divmod(uptime.total_seconds(), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        if days > 0:
            return f"{int(days)}d {int(hours)}h {int(minutes)}m {int(seconds)}s"
        else:
            return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
    except Exception as e:
        logger.error(f"Error getting system uptime: {e}")
        return "Unknown"


def get_memory_usage():
    """Get system memory usage"""
    try:
        # Get virtual memory statistics
        memory = psutil.virtual_memory()

        # Return a dictionary with detailed information
        return {
            "total": format_bytes(memory.total),
            "available": format_bytes(memory.available),
            "used": format_bytes(memory.used),
            "percent": f"{memory.percent}%",
        }
    except Exception as e:
        logger.error(f"Error getting memory usage: {e}")
        return {
            "total": "Unknown",
            "available": "Unknown",
            "used": "Unknown",
            "percent": "Unknown",
        }


def get_cpu_usage():
    """Get CPU usage information"""
    try:
        # Get CPU usage as a percentage (across all cores)
        cpu_percent = psutil.cpu_percent(interval=0.5)

        # Get per-CPU percentages
        per_cpu = psutil.cpu_percent(interval=0.5, percpu=True)

        # Get CPU count
        cpu_count = psutil.cpu_count(logical=True)
        physical_cores = psutil.cpu_count(logical=False) or 1

        return {
            "total_percent": f"{cpu_percent}%",
            "per_cpu": [f"{p}%" for p in per_cpu],
            "logical_cores": cpu_count,
            "physical_cores": physical_cores,
        }
    except Exception as e:
        logger.error(f"Error getting CPU usage: {e}")
        return {
            "total_percent": "Unknown",
            "per_cpu": [],
            "logical_cores": 0,
            "physical_cores": 0,
        }


def get_disk_usage():
    """Get disk usage information"""
    try:
        # Get disk usage for the root directory
        disk = psutil.disk_usage("/")

        return {
            "total": format_bytes(disk.total),
            "used": format_bytes(disk.used),
            "free": format_bytes(disk.free),
            "percent": f"{disk.percent}%",
        }
    except Exception as e:
        logger.error(f"Error getting disk usage: {e}")
        return {
            "total": "Unknown",
            "used": "Unknown",
            "free": "Unknown",
            "percent": "Unknown",
        }


def get_gpu_usage():
    """Get GPU usage information from Redis (updated by celery worker)"""
    try:
        import json

        from app.core.celery import celery_app

        # Try to get GPU stats from Redis (set by celery worker task)
        redis_client = celery_app.backend.client
        gpu_stats_json = redis_client.get("gpu_stats")

        if gpu_stats_json:
            gpu_stats = json.loads(gpu_stats_json)
            return gpu_stats
        else:
            # No stats available yet - worker hasn't reported
            return {
                "available": False,
                "name": "GPU stats not yet available",
                "memory_total": "N/A",
                "memory_used": "N/A",
                "memory_free": "N/A",
                "memory_percent": "N/A",
            }
    except Exception as e:
        logger.error(f"Error getting GPU usage from Redis: {e}")
        return {
            "available": False,
            "name": "Error",
            "memory_total": "Unknown",
            "memory_used": "Unknown",
            "memory_free": "Unknown",
            "memory_percent": "Unknown",
        }


def format_bytes(byte_count):
    """Format bytes to a human-readable string"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if byte_count < 1024 or unit == "TB":
            return f"{byte_count:.2f} {unit}"
        byte_count /= 1024


def _delete_user_speakers(db: Session, user_id: int) -> None:
    """Delete all speakers for a user.

    Args:
        db: Database session
        user_id: ID of the user whose speakers to delete
    """
    speakers_count = db.query(Speaker).filter(Speaker.user_id == user_id).count()
    if speakers_count > 0:
        logger.info(f"Deleting {speakers_count} speakers for user {user_id}")
        db.query(Speaker).filter(Speaker.user_id == user_id).delete(synchronize_session=False)
        logger.info("Speakers deleted successfully")


def _delete_user_media_files(db: Session, user_id: int) -> None:
    """Delete all media files and related records for a user.

    Args:
        db: Database session
        user_id: ID of the user whose media files to delete
    """
    media_files = db.query(MediaFile).filter(MediaFile.user_id == user_id).all()
    media_count = len(media_files)

    if media_count > 0:
        logger.info(f"Found {media_count} media files for user {user_id}")
        media_ids = [m.id for m in media_files]

        # Delete transcript segments for these media files
        segments_count = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.media_file_id.in_(media_ids))
            .count()
        )

        if segments_count > 0:
            logger.info(f"Deleting {segments_count} transcript segments for user's media files")
            db.query(TranscriptSegment).filter(
                TranscriptSegment.media_file_id.in_(media_ids)
            ).delete(synchronize_session=False)
            logger.info("Transcript segments deleted successfully")

        # Delete other related records using SQLAlchemy ORM for safety
        if media_ids:
            # Delete file_tag records safely using SQLAlchemy
            file_tags_deleted = (
                db.query(FileTag)
                .filter(FileTag.media_file_id.in_(media_ids))
                .delete(synchronize_session=False)
            )
            logger.info(f"Deleted {file_tags_deleted} file tags successfully")

            # Delete analytics records safely using SQLAlchemy
            analytics_deleted = (
                db.query(Analytics)
                .filter(Analytics.media_file_id.in_(media_ids))
                .delete(synchronize_session=False)
            )
            logger.info(f"Deleted {analytics_deleted} analytics records successfully")

        # Now delete the media files
        db.query(MediaFile).filter(MediaFile.user_id == user_id).delete(synchronize_session=False)
        logger.info(f"Deleted {media_count} media files for user {user_id}")


def _validate_user_deletion(user: User, current_user: User) -> None:
    """Validate that a user can be deleted.

    Args:
        user: User to be deleted
        current_user: User performing the deletion

    Raises:
        HTTPException: If user cannot be deleted
    """
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    if user.is_superuser and current_user.id != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete a superuser account",
        )


@router.get("/stats", response_model=dict[str, Any])
async def get_admin_stats(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)
):
    """
    Get admin statistics about the application and system
    """
    logger.info(f"Admin stats requested by user {current_user.email}")

    logger.info("Admin stats requested")

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

        # Get user statistics
        from datetime import datetime
        from datetime import timedelta
        from datetime import timezone

        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.is_active).count()
        inactive_users = total_users - active_users
        superusers = db.query(User).filter(User.is_superuser).count()

        # Calculate new users in last 7 days
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        new_users = db.query(User).filter(User.created_at >= seven_days_ago).count()

        # Get file statistics
        from sqlalchemy.sql import func

        total_files = db.query(MediaFile).count()

        # Calculate new files in last 7 days
        new_files = db.query(MediaFile).filter(MediaFile.upload_time >= seven_days_ago).count()

        # Count files by status
        pending_files = db.query(MediaFile).filter(MediaFile.status == "pending").count()
        processing_files = db.query(MediaFile).filter(MediaFile.status == "processing").count()
        completed_files = db.query(MediaFile).filter(MediaFile.status == "completed").count()
        error_files = db.query(MediaFile).filter(MediaFile.status == "error").count()

        # Get total file size
        total_size_result = db.query(func.sum(MediaFile.file_size)).scalar()
        total_size = total_size_result if total_size_result else 0

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
                "active": active_users,
                "inactive": inactive_users,
                "superusers": superusers,
                "new": new_users,
            },
            "files": {
                "total": total_files,
                "new": new_files,
                "total_duration": round(total_duration, 2) if total_duration else 0,
                "segments": total_segments,
                "by_status": {
                    "pending": pending_files,
                    "processing": processing_files,
                    "completed": completed_files,
                    "error": error_files,
                },
                "total_size": total_size,
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
        logger.error(f"Error getting admin stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving admin statistics: {str(e)}",
        ) from e


@router.get("/users", response_model=list[UserSchema])
def get_admin_users(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)
):
    """
    Get all users for admin
    """
    logger.info("Admin users list requested")

    try:
        users = db.query(User).all()
        return users
    except Exception as e:
        logger.error(f"Error getting admin users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving users: {str(e)}",
        ) from e


@router.post("/users", response_model=UserSchema)
def create_admin_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Create a new user (admin only)
    """
    logger.info(f"Admin creating new user with email: {user_data.email}")

    try:
        from app.api.endpoints.users import create_user as create_user_func

        # Call the user creation function from the users endpoint
        return create_user_func(user_data=user_data, db=db)
    except HTTPException as he:
        logger.error(f"HTTP error creating user: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating user: {str(e)}",
        ) from e


@router.delete("/users/{user_id}", response_model=dict[str, str])
def delete_admin_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Delete a user and all their data (admin only).

    Args:
        user_id: ID of the user to delete
        db: Database session
        current_user: Current admin user

    Returns:
        Success message

    Raises:
        HTTPException: If user not found or deletion not allowed
    """
    logger.info(f"Admin deleting user with ID: {user_id}")

    try:
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Validate deletion is allowed
        _validate_user_deletion(user, current_user)

        # Delete related data in order
        try:
            _delete_user_speakers(db, user_id)
        except Exception as speaker_error:
            logger.error(f"Error deleting speakers: {speaker_error}")
            raise

        try:
            _delete_user_media_files(db, user_id)
        except Exception as media_error:
            logger.error(f"Error deleting media files: {media_error}")
            raise

        # Delete the user
        try:
            logger.info(f"Final step: Deleting user with ID {user_id} and email {user.email}")
            db.delete(user)
            db.commit()
            logger.info("User deleted from database")
        except Exception as user_error:
            logger.error(f"Error deleting user object: {user_error}")
            db.rollback()
            raise

        logger.info(f"===== USER DELETION COMPLETED SUCCESSFULLY: {user_id} =====")
        return {"message": "User deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"===== ERROR IN DELETE_USER: {e} =====")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error details: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting user: {str(e)}",
        ) from e
