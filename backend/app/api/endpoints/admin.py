import asyncio
import logging
import platform
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any
from typing import Optional

import psutil
from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Query
from fastapi import status
from sqlalchemy import and_
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from app.api.endpoints.auth import get_current_admin_user
from app.auth.audit import AuditEventType
from app.auth.audit import AuditOutcome
from app.auth.audit import audit_logger
from app.auth.lockout import unlock_account as lockout_unlock_account
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.base import get_db
from app.models.media import Analytics
from app.models.media import Collection
from app.models.media import CollectionMember
from app.models.media import Comment
from app.models.media import FileStatus
from app.models.media import FileTag
from app.models.media import MediaFile
from app.models.media import Speaker
from app.models.media import SpeakerCollection
from app.models.media import SpeakerCollectionMember
from app.models.media import SpeakerProfile
from app.models.media import Task as TaskModel
from app.models.media import TranscriptSegment
from app.models.prompt import SummaryPrompt
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.user_mfa import UserMFA
from app.schemas.admin import GarbageCleanupConfig
from app.schemas.admin import GarbageCleanupConfigUpdate
from app.schemas.admin import RetentionConfig
from app.schemas.admin import RetentionConfigUpdate
from app.schemas.admin import RetentionPreviewFile
from app.schemas.admin import RetentionPreviewResponse
from app.schemas.admin import RetentionRunResponse
from app.schemas.admin import RetryConfig
from app.schemas.admin import RetryConfigUpdate
from app.schemas.user import AdminPasswordResetRequest
from app.schemas.user import User as UserSchema
from app.schemas.user import UserCreate
from app.services import system_settings_service

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()


# System statistics utility functions
def get_system_uptime():
    """Get system uptime in a readable format"""
    try:
        # Get boot time and calculate uptime
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time

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
    """Get CPU usage information.

    Uses interval=None (non-blocking) which returns CPU usage since the last call.
    The first call after import returns 0.0; subsequent calls return meaningful values.
    This avoids blocking the async event loop for 1+ second.
    """
    try:
        per_cpu = psutil.cpu_percent(interval=None, percpu=True)
        cpu_percent = sum(per_cpu) / len(per_cpu) if per_cpu else 0.0
        cpu_count = psutil.cpu_count(logical=True)
        physical_cores = psutil.cpu_count(logical=False) or 1

        return {
            "total_percent": f"{cpu_percent:.1f}%",
            "per_cpu": [f"{p:.1f}%" for p in per_cpu],
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


# Prime the CPU percent counter on module load so the first API call returns real data.
# This call is instant (interval=None) and runs once at import time.
psutil.cpu_percent(interval=None)


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


def _query_gpu_via_smi() -> dict | None:
    """Run nvidia-smi directly to get GPU stats. Returns None if unavailable."""
    import os
    import subprocess

    try:
        device_id = int(os.environ.get("GPU_DEVICE_ID", "0"))
        result = subprocess.run(  # noqa: S603  # nosec B603
            [  # noqa: S607  # nosec B607
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,memory.free,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
                f"--id={device_id}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        parts = result.stdout.strip().split(", ")
        used_mib, total_mib, free_mib = float(parts[1]), float(parts[2]), float(parts[3])
        used_bytes = used_mib * 1024 * 1024
        total_bytes = total_mib * 1024 * 1024
        free_bytes = free_mib * 1024 * 1024
        pct = (used_bytes / total_bytes * 100) if total_bytes > 0 else 0
        util = int(parts[4]) if len(parts) > 4 else None
        temp = int(parts[5]) if len(parts) > 5 else None
        return {
            "available": True,
            "name": parts[0],
            "memory_total": format_bytes(total_bytes),
            "memory_used": format_bytes(used_bytes),
            "memory_free": format_bytes(free_bytes),
            "memory_percent": f"{pct:.1f}%",
            "utilization_percent": f"{util}%" if util is not None else "N/A",
            "temperature_celsius": temp,
        }
    except (FileNotFoundError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def get_gpu_usage():
    """Get GPU usage array from Redis cache, falling back to direct nvidia-smi query.

    Returns a list of GPU stat dicts — one per active GPU device.  In normal
    mode this is a single-element list; in --gpu-scale dual-worker mode it
    contains one entry per active GPU worker.
    """
    try:
        import json

        from app.core.celery import celery_app

        redis_client = celery_app.backend.client
        gpu_stats_json = redis_client.get("gpu_stats")

        if gpu_stats_json:
            data = json.loads(gpu_stats_json)
            # Migrate legacy single-dict format to list
            return data if isinstance(data, list) else [data]

        # Redis empty — try nvidia-smi directly (works if backend host has NVIDIA drivers)
        direct_stats = _query_gpu_via_smi()
        if direct_stats:
            result = [direct_stats]
            redis_client.setex("gpu_stats", 600, json.dumps(result))
            return result

        # nvidia-smi not available — dispatch to cpu worker (debounced)
        lock_acquired = redis_client.set("gpu_stats_pending", "1", nx=True, ex=30)
        if lock_acquired:
            celery_app.send_task("system.update_gpu_stats", queue="cpu")
            logger.info("Dispatched on-demand GPU stats collection")

        return [
            {
                "available": False,
                "loading": True,
                "name": "Loading GPU stats...",
                "memory_total": "N/A",
                "memory_used": "N/A",
                "memory_free": "N/A",
                "memory_percent": "N/A",
            }
        ]
    except Exception as e:
        logger.error(f"Error getting GPU usage from Redis: {e}")
        return [
            {
                "available": False,
                "name": "Error",
                "memory_total": "Unknown",
                "memory_used": "Unknown",
                "memory_free": "Unknown",
                "memory_percent": "Unknown",
            }
        ]


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


def _delete_user_owned_records(db: Session, user_id: int) -> None:
    """Delete all user-owned records that are not covered by DB-level CASCADE.

    Cleans up: SpeakerProfile, SpeakerCollection (+ members), Collection (+ members),
    Comment, and Task records. Must be called BEFORE deleting MediaFile rows since
    some of these tables have FK references to media_file.
    """
    # Speaker collections and their members
    sc_ids = [
        sc.id
        for sc in db.query(SpeakerCollection.id).filter(SpeakerCollection.user_id == user_id).all()
    ]
    if sc_ids:
        db.query(SpeakerCollectionMember).filter(
            SpeakerCollectionMember.speaker_collection_id.in_(sc_ids)
        ).delete(synchronize_session=False)
        db.query(SpeakerCollection).filter(SpeakerCollection.user_id == user_id).delete(
            synchronize_session=False
        )
        logger.info(f"Deleted {len(sc_ids)} speaker collections for user {user_id}")

    # Collections and their members
    col_ids = [c.id for c in db.query(Collection.id).filter(Collection.user_id == user_id).all()]
    if col_ids:
        db.query(CollectionMember).filter(CollectionMember.collection_id.in_(col_ids)).delete(
            synchronize_session=False
        )
        db.query(Collection).filter(Collection.user_id == user_id).delete(synchronize_session=False)
        logger.info(f"Deleted {len(col_ids)} collections for user {user_id}")

    # Speaker profiles
    profiles_deleted = (
        db.query(SpeakerProfile)
        .filter(SpeakerProfile.user_id == user_id)
        .delete(synchronize_session=False)
    )
    if profiles_deleted:
        logger.info(f"Deleted {profiles_deleted} speaker profiles for user {user_id}")

    # Comments
    comments_deleted = (
        db.query(Comment).filter(Comment.user_id == user_id).delete(synchronize_session=False)
    )
    if comments_deleted:
        logger.info(f"Deleted {comments_deleted} comments for user {user_id}")

    # Background tasks
    tasks_deleted = (
        db.query(TaskModel).filter(TaskModel.user_id == user_id).delete(synchronize_session=False)
    )
    if tasks_deleted:
        logger.info(f"Deleted {tasks_deleted} task records for user {user_id}")

    # Summary prompts
    prompts_deleted = (
        db.query(SummaryPrompt)
        .filter(SummaryPrompt.user_id == user_id)
        .delete(synchronize_session=False)
    )
    if prompts_deleted:
        logger.info(f"Deleted {prompts_deleted} summary prompts for user {user_id}")


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
        segments_deleted = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.media_file_id.in_(media_ids))
            .delete(synchronize_session=False)
        )
        if segments_deleted:
            logger.info(f"Deleted {segments_deleted} transcript segments")

        # Delete file_tag records
        file_tags_deleted = (
            db.query(FileTag)
            .filter(FileTag.media_file_id.in_(media_ids))
            .delete(synchronize_session=False)
        )
        if file_tags_deleted:
            logger.info(f"Deleted {file_tags_deleted} file tags")

        # Delete analytics records
        analytics_deleted = (
            db.query(Analytics)
            .filter(Analytics.media_file_id.in_(media_ids))
            .delete(synchronize_session=False)
        )
        if analytics_deleted:
            logger.info(f"Deleted {analytics_deleted} analytics records")

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

    if user.is_superuser and not current_user.is_superuser:
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
        # System statistics — offload sync psutil calls to a thread to avoid
        # blocking the async event loop.
        def _collect_system_stats():
            return {
                "cpu": get_cpu_usage(),
                "memory": get_memory_usage(),
                "disk": get_disk_usage(),
                "gpu": get_gpu_usage(),
                "uptime": get_system_uptime(),
            }

        try:
            system_stats = await asyncio.to_thread(_collect_system_stats)
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

        # Consolidated database statistics (3 aggregate queries instead of 15+)
        from app.utils.stats_helpers import get_file_stats
        from app.utils.stats_helpers import get_recent_tasks
        from app.utils.stats_helpers import get_task_stats
        from app.utils.stats_helpers import get_user_stats

        user_stats = get_user_stats(db, include_breakdown=True)
        file_stats = get_file_stats(db, include_status_breakdown=True)
        task_stats = get_task_stats(db)
        recent = get_recent_tasks(db, limit=10)

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
        }

        total_files = file_stats["total"]
        total_speakers = file_stats["speakers"]
        total_segments = file_stats["segments"]

        # Construct the response
        stats = {
            "users": user_stats,
            "files": {
                "total": total_files,
                "new": file_stats["new"],
                "total_duration": file_stats["total_duration"],
                "segments": total_segments,
                "by_status": file_stats.get("by_status", {}),
                "total_size": file_stats["total_size"],
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
            "tasks": {**task_stats, "recent": recent},
        }

        return stats
    except Exception as e:
        logger.error("Error getting admin stats: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred. Please try again.",
        ) from e


@router.get("/users", response_model=list[UserSchema])
def get_admin_users(
    limit: int = Query(200, ge=1, le=1000, description="Max users to return"),
    offset: int = Query(0, ge=0, description="Number of users to skip"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Get users for admin panel with pagination.

    Defaults to 200 users which covers most deployments without breaking
    existing frontend code. Use limit/offset for larger user bases.
    """
    try:
        users = (
            db.query(User).order_by(func.lower(User.full_name)).offset(offset).limit(limit).all()
        )
        return users
    except Exception as e:
        logger.error("Error getting admin users: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred. Please try again.",
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
        logger.error("Error creating user: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred. Please try again.",
        ) from e


@router.delete("/users/{user_uuid}", response_model=dict[str, str])
def delete_admin_user(
    user_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Delete a user and all their data (admin only).

    Args:
        user_uuid: UUID of the user to delete
        db: Database session
        current_user: Current admin user

    Returns:
        Success message

    Raises:
        HTTPException: If user not found or deletion not allowed
    """
    from app.utils.uuid_helpers import get_user_by_uuid

    logger.info(f"Admin deleting user with UUID: {user_uuid}")

    try:
        user = get_user_by_uuid(db, user_uuid)
        user_id = user.id  # Get internal ID for cascade operations

        # Validate deletion is allowed
        _validate_user_deletion(user, current_user)

        # Delete all user data atomically using a savepoint
        savepoint = db.begin_nested()
        try:
            _delete_user_owned_records(db, int(user_id))
            _delete_user_speakers(db, int(user_id))
            _delete_user_media_files(db, int(user_id))
            logger.info(f"Deleting user with ID {user_id} and email {user.email}")
            db.delete(user)
            savepoint.commit()
        except Exception:
            savepoint.rollback()
            raise
        db.commit()

        logger.info(f"User deletion completed successfully: {user_id}")
        return {"message": "User deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User deletion failed, all changes rolled back: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User deletion failed",
        ) from e


@router.get("/settings/retry-config", response_model=RetryConfig)
async def get_retry_configuration(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> RetryConfig:
    """
    Get retry configuration settings (admin only).

    Returns the current retry configuration including:
    - max_retries: Maximum retry attempts (0 = unlimited)
    - retry_limit_enabled: Whether limits are enforced
    """
    logger.info(f"Retry config requested by admin {current_user.email}")
    config = system_settings_service.get_retry_config(db)
    return RetryConfig(**config)


@router.put("/settings/retry-config", response_model=RetryConfig)
async def update_retry_configuration(
    config: RetryConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> RetryConfig:
    """
    Update retry configuration settings (admin only).

    Args:
        config: New configuration values (only provided values are updated)

    Returns:
        Updated retry configuration
    """
    logger.info(f"Retry config update by admin {current_user.email}: {config}")

    updated = system_settings_service.update_retry_config(
        db,
        max_retries=config.max_retries,
        retry_limit_enabled=config.retry_limit_enabled,
    )

    return RetryConfig(**updated)


@router.get("/settings/garbage-cleanup", response_model=GarbageCleanupConfig)
async def get_garbage_cleanup_configuration(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> GarbageCleanupConfig:
    """
    Get garbage cleanup configuration settings (admin only).

    Returns the current garbage cleanup configuration including:
    - garbage_cleanup_enabled: Whether garbage cleanup is active
    - max_word_length: Maximum word length threshold (words longer are replaced)
    """
    logger.info(f"Garbage cleanup config requested by admin {current_user.email}")
    config = system_settings_service.get_garbage_cleanup_config(db)
    return GarbageCleanupConfig(**config)


@router.put("/settings/garbage-cleanup", response_model=GarbageCleanupConfig)
async def update_garbage_cleanup_configuration(
    config: GarbageCleanupConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> GarbageCleanupConfig:
    """
    Update garbage cleanup configuration settings (admin only).

    Args:
        config: New configuration values (only provided values are updated)

    Returns:
        Updated garbage cleanup configuration
    """
    logger.info(f"Garbage cleanup config update by admin {current_user.email}: {config}")

    updated = system_settings_service.update_garbage_cleanup_config(
        db,
        garbage_cleanup_enabled=config.garbage_cleanup_enabled,
        max_word_length=config.max_word_length,
    )

    return GarbageCleanupConfig(**updated)


# ============== File Retention Settings ==============


def _get_retention_eligible_files(db: Session, retention_days: int, delete_error_files: bool):
    """Query files eligible for deletion under the given retention parameters."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    eligible_statuses = [FileStatus.COMPLETED]
    if delete_error_files:
        eligible_statuses.append(FileStatus.ERROR)

    return (
        db.query(MediaFile)
        .options(selectinload(MediaFile.speakers))
        .filter(
            or_(
                and_(MediaFile.completed_at.isnot(None), MediaFile.completed_at < cutoff),
                and_(MediaFile.completed_at.is_(None), MediaFile.upload_time < cutoff),
            ),
            MediaFile.status.in_([s.value for s in eligible_statuses]),
        )
        .all()
    )


@router.get("/settings/retention-config", response_model=RetentionConfig)
async def get_retention_configuration(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> RetentionConfig:
    """
    Get file retention configuration settings (admin only).

    Returns the current retention configuration including:
    - retention_enabled: Whether automatic deletion is active
    - retention_days: Files older than this are deleted
    - delete_error_files: Whether error-status files are also deleted
    - run_time: HH:MM daily schedule time
    - timezone: IANA timezone for the schedule
    - last_run: ISO timestamp of last run
    - last_run_deleted: Files deleted in last run
    """
    logger.info(f"Retention config requested by admin {current_user.email}")
    config = system_settings_service.get_retention_config(db)
    return RetentionConfig(**config)


@router.put("/settings/retention-config", response_model=RetentionConfig)
async def update_retention_configuration(
    config: RetentionConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> RetentionConfig:
    """
    Update file retention configuration settings (admin only).

    Args:
        config: New configuration values (only provided values are updated)

    Returns:
        Updated retention configuration
    """
    logger.info(f"Retention config update by admin {current_user.email}: {config}")

    updated = system_settings_service.update_retention_config(
        db,
        retention_enabled=config.retention_enabled,
        retention_days=config.retention_days,
        delete_error_files=config.delete_error_files,
        run_time=config.run_time,
        timezone=config.timezone,
    )

    return RetentionConfig(**updated)


@router.get("/settings/retention-config/preview", response_model=RetentionPreviewResponse)
async def preview_retention_deletion(
    retention_days: int = Query(..., ge=1, le=3650, description="Retention window in days"),
    delete_error_files: bool = Query(False, description="Include error-status files"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> RetentionPreviewResponse:
    """
    Dry-run preview of files that would be deleted (admin only).

    Returns count, total size, and a sample list of files that would be deleted
    with the given retention parameters. No files are modified.
    """
    logger.info(
        f"Retention preview requested by admin {current_user.email}: "
        f"{retention_days} days, delete_error_files={delete_error_files}"
    )

    files = _get_retention_eligible_files(db, retention_days, delete_error_files)

    # Build user lookup for owner names
    user_ids = list({f.user_id for f in files})
    users = db.query(User).filter(User.id.in_(user_ids)).all()
    user_map = {u.id: u.email for u in users}

    now_utc = datetime.now(timezone.utc)
    total_size = sum(f.file_size or 0 for f in files)

    # Build preview list (cap at 100 rows for response size)
    preview_files = []
    for f in files[:100]:
        if f.completed_at:
            ref_dt = (
                f.completed_at.replace(tzinfo=timezone.utc)
                if f.completed_at.tzinfo is None
                else f.completed_at
            )
        else:
            ref_dt = (
                f.upload_time.replace(tzinfo=timezone.utc)
                if f.upload_time.tzinfo is None
                else f.upload_time
            )
        age_days = (now_utc - ref_dt).days
        preview_files.append(
            RetentionPreviewFile(
                uuid=str(f.uuid),
                title=f.filename or str(f.uuid),
                owner_email=user_map.get(f.user_id, "unknown"),
                completed_at=f.completed_at.isoformat() if f.completed_at else None,
                age_days=age_days,
                size_bytes=f.file_size or 0,
                status=f.status if isinstance(f.status, str) else f.status.value,
            )
        )

    return RetentionPreviewResponse(
        file_count=len(files),
        total_size_bytes=total_size,
        files=preview_files,
    )


@router.post("/settings/retention-config/run", response_model=RetentionRunResponse)
async def trigger_retention_run(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> RetentionRunResponse:
    """
    Manually trigger a retention cleanup run (admin only).

    Dispatches the cleanup task immediately with force=True, bypassing
    the time-window check and the retention_enabled flag. Useful for
    on-demand cleanup without enabling the automatic schedule.
    """
    logger.info(f"Manual retention run triggered by admin {current_user.email}")

    from app.core.celery import celery_app

    task = celery_app.send_task(
        "cleanup_expired_files",
        kwargs={"force": True},
        queue="utility",
    )

    return RetentionRunResponse(
        task_id=str(task.id),
        status="queued",
        message="Retention cleanup task queued successfully.",
    )


@router.get("/settings/retention-config/status", response_model=RetentionConfig)
async def get_retention_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> RetentionConfig:
    """
    Get retention configuration with last-run status (admin only).

    Same as GET /retention-config but intended for status polling after
    a manual run to refresh last_run and last_run_deleted values.
    """
    config = system_settings_service.get_retention_config(db)
    return RetentionConfig(**config)


# ============== Super Admin Role Verification ==============


def get_current_super_admin_user(
    current_user: User = Depends(get_current_admin_user),
) -> User:
    """Verify user has super_admin role."""
    if current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin access required")
    return current_user


# ============== Account Management (FedRAMP AC-2) ==============


@router.post("/users/{user_uuid}/reset-password")
async def admin_reset_user_password(
    user_uuid: str,
    request_body: AdminPasswordResetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin_user),
):
    """Admin-initiated password reset. Requires super_admin role.

    Security: Password is passed in request body (not query parameter) to prevent
    exposure in server logs, browser history, and HTTP referrer headers.
    """
    user = db.query(User).filter(User.uuid == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = get_password_hash(request_body.new_password)  # type: ignore[assignment]
    user.must_change_password = request_body.force_change  # type: ignore[assignment]
    user.password_changed_at = datetime.now(timezone.utc)  # type: ignore[assignment]
    db.commit()

    audit_logger.log(
        event_type=AuditEventType.ADMIN_USER_UPDATE,
        user_id=int(current_user.id),
        username=str(current_user.email),
        outcome=AuditOutcome.SUCCESS,
        details={
            "action": "password_reset",
            "target_user": user_uuid,
            "force_change": request_body.force_change,
        },
    )

    return {"success": True}


@router.post("/users/{user_uuid}/unlock")
async def admin_unlock_account(
    user_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Admin unlock of locked account."""
    user = db.query(User).filter(User.uuid == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Use the lockout manager to unlock the account
    unlocked = lockout_unlock_account(str(user.email))

    audit_logger.log(
        event_type=AuditEventType.AUTH_ACCOUNT_UNLOCK,
        user_id=int(current_user.id),
        username=str(current_user.email),
        outcome=AuditOutcome.SUCCESS,
        details={
            "target_user": user_uuid,
            "unlocked_by": "admin",
            "was_locked": unlocked,
        },
    )

    return {"success": True, "was_locked": unlocked}


@router.post("/users/{user_uuid}/lock")
async def admin_lock_account(
    user_uuid: str,
    reason: str = Query("Admin action", description="Reason for locking the account"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Admin lock of user account."""
    user = db.query(User).filter(User.uuid == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False  # type: ignore[assignment]
    db.commit()

    audit_logger.log(
        event_type=AuditEventType.AUTH_ACCOUNT_DISABLED,
        user_id=int(current_user.id),
        username=str(current_user.email),
        outcome=AuditOutcome.SUCCESS,
        details={
            "target_user": user_uuid,
            "reason": reason,
            "locked_by": "admin",
        },
    )

    return {"success": True}


@router.delete("/users/{user_uuid}/sessions")
async def admin_terminate_user_sessions(
    user_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Force logout user by terminating all sessions."""
    user = db.query(User).filter(User.uuid == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Revoke all refresh tokens
    now = datetime.now(timezone.utc)
    tokens = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        )
        .all()
    )

    count = 0
    for token in tokens:
        token.revoked_at = now  # type: ignore[assignment]
        count += 1

    db.commit()

    audit_logger.log(
        event_type=AuditEventType.AUTH_LOGOUT_ALL,
        user_id=int(current_user.id),
        username=str(current_user.email),
        outcome=AuditOutcome.SUCCESS,
        details={
            "target_user": user_uuid,
            "sessions_terminated": count,
            "terminated_by": "admin",
        },
    )

    return {"success": True, "sessions_terminated": count}


@router.get("/users/{user_uuid}/sessions")
async def admin_get_user_sessions(
    user_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """View all active sessions for a user."""
    user = db.query(User).filter(User.uuid == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sessions = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
        .all()
    )

    return {
        "sessions": [
            {
                "id": str(s.jti),
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
                "ip_address": s.ip_address,
                "user_agent": s.user_agent,
            }
            for s in sessions
        ]
    }


@router.put("/users/{user_uuid}/role")
async def admin_change_user_role(
    user_uuid: str,
    new_role: str = Query(..., description="New role for the user (user, admin, super_admin)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin_user),
):
    """Change user role. Only super_admin can promote to super_admin."""
    if new_role not in ("user", "admin", "super_admin"):
        raise HTTPException(status_code=400, detail="Invalid role")

    user = db.query(User).filter(User.uuid == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if str(user.uuid) == str(current_user.uuid):
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    old_role = user.role
    user.role = new_role  # type: ignore[assignment]
    db.commit()

    audit_logger.log(
        event_type=AuditEventType.ADMIN_ROLE_CHANGE,
        user_id=int(current_user.id),
        username=str(current_user.email),
        outcome=AuditOutcome.SUCCESS,
        details={
            "target_user": user_uuid,
            "old_role": old_role,
            "new_role": new_role,
        },
    )

    return {"success": True, "old_role": old_role, "new_role": new_role}


# ============== MFA Management ==============


@router.post("/users/{user_uuid}/mfa/reset")
async def admin_reset_user_mfa(
    user_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin_user),
):
    """Admin reset of user MFA (if user loses device). Requires super_admin role."""
    user = db.query(User).filter(User.uuid == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    mfa_settings = db.query(UserMFA).filter(UserMFA.user_id == user.id).first()
    if mfa_settings:
        mfa_settings.totp_enabled = False  # type: ignore[assignment]
        mfa_settings.totp_secret = None  # type: ignore[assignment]
        mfa_settings.backup_codes = []  # type: ignore[assignment]
        db.commit()

    audit_logger.log(
        event_type=AuditEventType.AUTH_MFA_DISABLE,
        user_id=int(current_user.id),
        username=str(current_user.email),
        outcome=AuditOutcome.SUCCESS,
        details={
            "target_user": user_uuid,
            "reset_by": "admin",
        },
    )

    return {"success": True}


# ============== User Search ==============


@router.get("/users/search")
async def admin_search_users(
    query: Optional[str] = Query(None, description="Search query for email or name"),
    role: Optional[str] = Query(None, description="Filter by role"),
    auth_type: Optional[str] = Query(None, description="Filter by auth type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(default=50, le=200, description="Maximum results to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Advanced user search with filtering and pagination."""
    q = db.query(User)

    if query:
        q = q.filter(or_(User.email.ilike(f"%{query}%"), User.full_name.ilike(f"%{query}%")))

    if role:
        q = q.filter(User.role == role)

    if auth_type:
        q = q.filter(User.auth_type == auth_type)

    if is_active is not None:
        q = q.filter(User.is_active == is_active)

    total = q.count()
    users = q.offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "users": [
            {
                "uuid": str(u.uuid),
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role,
                "auth_type": u.auth_type,
                "is_active": u.is_active,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
    }


# ============== Reporting ==============


@router.get("/reports/account-status")
async def get_account_status_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Account status summary for compliance reporting."""
    # Consolidate 3 User COUNT queries into 1 using FILTER clauses
    expiry_threshold = datetime.now(timezone.utc) - timedelta(days=settings.PASSWORD_MAX_AGE_DAYS)
    user_row = db.query(
        func.count().label("total"),
        func.count().filter(User.is_active.is_(True)).label("active"),
        func.count().filter(User.password_changed_at < expiry_threshold).label("pwd_expired"),
    ).one()

    # MFA is a separate table, so one more query
    mfa_enabled = db.query(func.count(UserMFA.id)).filter(UserMFA.totp_enabled.is_(True)).scalar()

    total = user_row.total
    active = user_row.active

    return {
        "total_users": total,
        "active_users": active,
        "inactive_users": total - active,
        "mfa_enabled_users": mfa_enabled,
        "password_expired_users": user_row.pwd_expired,
    }


# ============== Audit Logs (FedRAMP AU-2/AU-3) ==============


@router.get("/audit-logs")
async def get_audit_logs(
    start_date: Optional[datetime] = Query(None, description="Start date for log query"),
    end_date: Optional[datetime] = Query(None, description="End date for log query"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    outcome: Optional[str] = Query(None, description="Filter by outcome"),
    limit: int = Query(default=100, le=1000, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin_user),
):
    """
    Query audit logs with filtering. Super admin only.

    Note: This endpoint queries OpenSearch if audit logging to OpenSearch is enabled.
    If OpenSearch is not available, returns an error message.
    """
    # Check if OpenSearch audit logging is enabled
    if not settings.AUDIT_LOG_TO_OPENSEARCH:
        return {
            "error": "Audit log querying requires AUDIT_LOG_TO_OPENSEARCH=true",
            "logs": [],
            "total": 0,
        }

    try:
        from opensearchpy import OpenSearch

        client = OpenSearch(
            hosts=[
                {
                    "host": settings.OPENSEARCH_HOST,
                    "port": int(settings.OPENSEARCH_PORT),
                }
            ],
            http_auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
            use_ssl=False,
            verify_certs=settings.OPENSEARCH_VERIFY_CERTS,
        )

        # Build OpenSearch query
        must_clauses: list[dict] = []

        if start_date:
            must_clauses.append({"range": {"timestamp": {"gte": start_date.isoformat()}}})
        if end_date:
            must_clauses.append({"range": {"timestamp": {"lte": end_date.isoformat()}}})
        if event_type:
            must_clauses.append({"term": {"event_type": event_type}})
        if user_id:
            must_clauses.append({"term": {"user_id": user_id}})
        if outcome:
            must_clauses.append({"term": {"outcome": outcome}})

        query = {
            "query": {"bool": {"must": must_clauses}} if must_clauses else {"match_all": {}},
            "sort": [{"timestamp": {"order": "desc"}}],
            "from": offset,
            "size": limit,
        }

        # Search across all audit log indices
        index_pattern = "audit-logs-*"
        response = client.search(index=index_pattern, body=query)

        logs = [hit["_source"] for hit in response["hits"]["hits"]]
        total = response["hits"]["total"]["value"]

        return {
            "logs": logs,
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    except Exception as e:
        logger.error(f"Error querying audit logs: {e}")
        return {
            "error": "An internal error occurred while querying audit logs.",
            "logs": [],
            "total": 0,
        }


@router.get("/audit-logs/export")
async def export_audit_logs(
    export_format: str = Query("csv", description="Export format (csv or json)"),
    start_date: Optional[datetime] = Query(None, description="Start date for export"),
    end_date: Optional[datetime] = Query(None, description="End date for export"),
    current_user: User = Depends(get_current_super_admin_user),
):
    """Export audit logs for compliance reporting. Super admin only."""
    import csv
    import io
    import json

    from fastapi.responses import StreamingResponse

    if export_format not in ("csv", "json"):
        raise HTTPException(status_code=400, detail="Format must be csv or json")

    # Check if OpenSearch audit logging is enabled
    if not settings.AUDIT_LOG_TO_OPENSEARCH:
        raise HTTPException(
            status_code=400,
            detail="Audit log export requires AUDIT_LOG_TO_OPENSEARCH=true",
        )

    try:
        from opensearchpy import OpenSearch

        client = OpenSearch(
            hosts=[
                {
                    "host": settings.OPENSEARCH_HOST,
                    "port": int(settings.OPENSEARCH_PORT),
                }
            ],
            http_auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
            use_ssl=False,
            verify_certs=settings.OPENSEARCH_VERIFY_CERTS,
        )

        # Build query
        must_clauses = []
        if start_date:
            must_clauses.append({"range": {"timestamp": {"gte": start_date.isoformat()}}})
        if end_date:
            must_clauses.append({"range": {"timestamp": {"lte": end_date.isoformat()}}})

        query = {
            "query": {"bool": {"must": must_clauses}} if must_clauses else {"match_all": {}},
            "sort": [{"timestamp": {"order": "desc"}}],
            "size": 10000,  # Maximum export size
        }

        index_pattern = "audit-logs-*"
        response = client.search(index=index_pattern, body=query)
        logs = [hit["_source"] for hit in response["hits"]["hits"]]

        if export_format == "json":
            content = json.dumps(logs, indent=2, default=str)
            media_type = "application/json"
        else:
            # CSV format
            output = io.StringIO()
            if logs:
                fieldnames = [
                    "timestamp",
                    "event_type",
                    "outcome",
                    "user_id",
                    "username",
                    "source_ip",
                    "user_agent",
                    "error_code",
                    "details",
                ]
                writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                for log in logs:
                    # Convert details dict to string for CSV
                    if "details" in log and isinstance(log["details"], dict):
                        log["details"] = json.dumps(log["details"])
                    writer.writerow(log)
            content = output.getvalue()
            media_type = "text/csv"

        filename = f"audit-logs-{datetime.now().strftime('%Y%m%d')}.{export_format}"

        return StreamingResponse(
            iter([content]),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        logger.error("Error exporting audit logs: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again.",
        ) from e
