import logging
from datetime import datetime
from datetime import timezone
from typing import Any

from fastapi import APIRouter
from fastapi import BackgroundTasks
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.api.endpoints.auth import get_current_admin_user
from app.db.base import get_db
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.models.media import Task as TaskModel
from app.models.user import User
from app.schemas.media import Task
from app.services.task_detection_service import task_detection_service
from app.services.task_filtering_service import TaskFilteringService
from app.services.task_recovery_service import task_recovery_service

logger = logging.getLogger(__name__)

router = APIRouter()


# Helper function to calculate age in seconds
def calculate_age_seconds(timestamp):
    """Calculate seconds between now and a timestamp, handling timezone differences safely"""
    if not timestamp:
        return None

    # Get current time with timezone
    now = datetime.now(timezone.utc)

    # Make timestamp timezone-aware if it's not
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    # Calculate the difference
    return (now - timestamp).total_seconds()


# Define task status constants to match those in the utils module
TASK_STATUS_PENDING = "pending"
TASK_STATUS_IN_PROGRESS = "in_progress"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"


def _get_user_media_files(db: Session, current_user: User) -> list[MediaFile]:
    """Get media files based on user permissions."""
    if current_user.role == "admin":
        return db.query(MediaFile).all()
    else:
        return db.query(MediaFile).filter(MediaFile.user_id == current_user.id).all()


def _map_file_status_to_task_status(file_status: FileStatus) -> str:
    """Map media file status to task status."""
    status_mapping = {
        FileStatus.PENDING: "pending",
        FileStatus.PROCESSING: "in_progress",
        FileStatus.COMPLETED: "completed",
        FileStatus.ERROR: "failed",
    }
    return status_mapping.get(file_status, "pending")


def _extract_file_format(content_type: str, filename: str) -> str:
    """Extract file format from content type or filename."""
    if content_type and "/" in content_type:
        return content_type.split("/")[1]
    elif filename and "." in filename:
        return filename.split(".")[-1]
    return None


def _create_task_dict_from_media_file(file: MediaFile, current_user: User) -> dict:
    """Convert a media file to a task dictionary."""
    task_status = _map_file_status_to_task_status(file.status)

    # Handle completed_at time
    completed_at = getattr(file, "completed_at", None)

    # Extract file format
    file_format = _extract_file_format(file.content_type, file.filename)

    # Calculate progress
    if file.status == FileStatus.COMPLETED:
        progress = 1.0
    elif file.status == FileStatus.PROCESSING:
        progress = 0.5
    else:
        progress = 0.0

    # Determine error message
    error_message = "Transcription failed" if file.status == FileStatus.ERROR else None

    return {
        "id": f"task_{file.id}",
        "user_id": current_user.id,
        "task_type": "transcription",
        "status": task_status,
        "media_file_id": file.id,
        "progress": progress,
        "created_at": file.upload_time,
        "updated_at": file.upload_time,
        "completed_at": completed_at,
        "error_message": error_message,
        "media_file": {
            "id": file.id,
            "filename": file.filename,
            "file_size": file.file_size,
            "content_type": file.content_type,
            "duration": file.duration,
            "language": file.language,
            "format": file_format,
            "media_format": getattr(file, "media_format", None),
            "codec": getattr(file, "codec", None),
            "upload_time": file.upload_time,
        },
    }


@router.get("/", response_model=list[Task])
def list_tasks(
    status: str = None,  # Filter by task status
    task_type: str = None,  # Filter by task type
    age_filter: str = None,  # Filter by age: "today", "week", "month", "older"
    date_from: str = None,  # Filter from date (YYYY-MM-DD)
    date_to: str = None,  # Filter to date (YYYY-MM-DD)
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    List all tasks for the current user with server-side filtering and computed fields
    """
    try:
        # Get media files based on user permissions
        media_files = _get_user_media_files(db, current_user)

        # Convert media files to task dictionaries
        tasks = [_create_task_dict_from_media_file(file, current_user) for file in media_files]

        # Apply server-side filtering
        filtered_tasks = TaskFilteringService.filter_tasks_by_criteria(
            tasks=tasks,
            status=status,
            task_type=task_type,
            age_filter=age_filter,
            date_from=date_from,
            date_to=date_to,
        )

        # Convert to Task schema objects
        return [Task(**task_dict) for task_dict in filtered_tasks]

    except Exception as e:
        logger.error(f"Error in list_tasks: {e}")
        return []


def _parse_task_id(task_id: str) -> int:
    """Parse task ID to extract media file ID."""
    if not task_id.startswith("task_"):
        raise ValueError("Invalid task ID format")
    try:
        return int(task_id.split("_")[1])
    except (ValueError, IndexError) as e:
        raise ValueError("Invalid task ID format") from e


def _get_media_file_by_id(db: Session, file_id: int, current_user: User) -> MediaFile:
    """Get media file by ID with proper permission checking."""
    if current_user.role == "admin":
        media_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
    else:
        media_file = (
            db.query(MediaFile)
            .filter(MediaFile.id == file_id, MediaFile.user_id == current_user.id)
            .first()
        )

    if not media_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return media_file


@router.get("/{task_id}", response_model=Task)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get a specific task by its ID
    """
    try:
        # Parse task ID and get file ID
        try:
            file_id = _parse_task_id(task_id)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid task ID format"
            ) from e

        # Get media file with permission checking
        media_file = _get_media_file_by_id(db, file_id, current_user)

        # Create task dictionary and convert to Task object
        task_dict = _create_task_dict_from_media_file(media_file, current_user)
        task_dict["id"] = task_id  # Ensure we use the original task_id

        return Task(**task_dict)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        ) from e


@router.get("/system/health", response_model=dict[str, Any])
async def task_system_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),  # Only admins can access this endpoint
):
    """
    Get health information about the task system

    Returns information about stuck tasks and inconsistent media files
    """
    try:
        # Identify stuck tasks
        stuck_tasks = task_detection_service.identify_stuck_tasks(db)

        # Identify inconsistent media files
        inconsistent_files = task_detection_service.identify_inconsistent_media_files(db)

        # Count actual tasks by status
        task_counts = {
            TASK_STATUS_PENDING: db.query(TaskModel)
            .filter(TaskModel.status == TASK_STATUS_PENDING)
            .count(),
            TASK_STATUS_IN_PROGRESS: db.query(TaskModel)
            .filter(TaskModel.status == TASK_STATUS_IN_PROGRESS)
            .count(),
            TASK_STATUS_COMPLETED: db.query(TaskModel)
            .filter(TaskModel.status == TASK_STATUS_COMPLETED)
            .count(),
            TASK_STATUS_FAILED: db.query(TaskModel)
            .filter(TaskModel.status == TASK_STATUS_FAILED)
            .count(),
            "total": db.query(TaskModel).count(),
        }

        # Count media files by status
        file_counts = {
            "pending": db.query(MediaFile).filter(MediaFile.status == FileStatus.PENDING).count(),
            "processing": db.query(MediaFile)
            .filter(MediaFile.status == FileStatus.PROCESSING)
            .count(),
            "completed": db.query(MediaFile)
            .filter(MediaFile.status == FileStatus.COMPLETED)
            .count(),
            "error": db.query(MediaFile).filter(MediaFile.status == FileStatus.ERROR).count(),
            "total": db.query(MediaFile).count(),
        }

        # Format stuck tasks for response
        stuck_task_data = []
        for task in stuck_tasks:
            stuck_task_data.append(
                {
                    "id": task.id,
                    "task_type": task.task_type,
                    "status": task.status,
                    "media_file_id": task.media_file_id,
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                    "age_seconds": calculate_age_seconds(task.created_at),
                }
            )

        # Format inconsistent files for response
        inconsistent_file_data = []
        for file in inconsistent_files:
            inconsistent_file_data.append(
                {
                    "id": file.id,
                    "filename": file.filename,
                    "status": file.status.value,
                    "user_id": file.user_id,
                    "upload_time": file.upload_time,
                    "age_seconds": calculate_age_seconds(file.upload_time),
                }
            )

        return {
            "task_counts": task_counts,
            "file_counts": file_counts,
            "stuck_tasks": {"count": len(stuck_tasks), "items": stuck_task_data},
            "inconsistent_files": {
                "count": len(inconsistent_files),
                "items": inconsistent_file_data,
            },
            "timestamp": datetime.now(timezone.utc),
        }
    except Exception as e:
        logger.error(f"Error in task_system_health: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        ) from e


@router.post("/recover-stuck-tasks", response_model=dict[str, Any])
async def recover_all_stuck_tasks(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),  # Only admins can recover tasks
):
    """
    Attempt to recover all stuck tasks

    This endpoint will identify and recover all stuck tasks in the system.
    """
    try:
        # Identify stuck tasks
        stuck_tasks = task_detection_service.identify_stuck_tasks(db)
        if not stuck_tasks:
            return {"success": True, "count": 0, "message": "No stuck tasks found"}

        # Try to recover each task
        recovered_count = 0
        for task in stuck_tasks:
            success = task_recovery_service.recover_stuck_task(db, task)
            if success:
                recovered_count += 1

                # If it's a transcription task, retry it
                if task.task_type == "transcription" and task.media_file_id:
                    # Schedule a retry in the background for each recovered task
                    async def retry_transcription(file_id):
                        try:
                            # Import here to avoid circular imports
                            from app.tasks.transcription import transcribe_audio_task

                            result = transcribe_audio_task.delay(file_id)
                            logger.info(
                                f"Retrying transcription for file {file_id}, "
                                f"new task ID: {result.id}"
                            )
                        except Exception as e:
                            logger.error(f"Error retrying transcription: {e}")

                    background_tasks.add_task(retry_transcription, task.media_file_id)

        return {
            "success": True,
            "count": recovered_count,
            "total": len(stuck_tasks),
            "message": f"Successfully recovered {recovered_count} of {len(stuck_tasks)} tasks",
        }
    except Exception as e:
        logger.error(f"Error in recover_all_stuck_tasks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        ) from e


@router.post("/system/recover-task/{task_id}", response_model=dict[str, Any])
async def recover_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),  # Only admins can recover tasks
):
    """
    Attempt to recover a stuck task

    This endpoint will mark a stuck task as failed and retry it if appropriate.
    """
    try:
        # Find the task
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        # Attempt recovery
        success = task_recovery_service.recover_stuck_task(db, task)

        # If successful and appropriate, retry the task
        if success and task.task_type == "transcription" and task.media_file_id:
            # Schedule a retry in the background
            # This avoids blocking the API call
            async def retry_transcription():
                try:
                    # Import here to avoid circular imports
                    from app.tasks.transcription import transcribe_audio_task

                    result = transcribe_audio_task.delay(task.media_file_id)
                    logger.info(
                        f"Retrying transcription for file {task.media_file_id}, "
                        f"new task ID: {result.id}"
                    )
                except Exception as e:
                    logger.error(f"Error retrying transcription: {e}")

            background_tasks.add_task(retry_transcription)

        return {
            "success": success,
            "task_id": task_id,
            "message": "Task recovery successful" if success else "Task recovery failed",
            "retry_scheduled": success and task.task_type == "transcription",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in recover_task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        ) from e


@router.post("/system/fix-file/{file_id}", response_model=dict[str, Any])
async def fix_inconsistent_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),  # Only admins can fix files
):
    """
    Attempt to fix a media file with inconsistent state
    """
    try:
        # Find the media file
        media_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
        if not media_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found"
            )

        # Attempt to fix the file
        success = task_recovery_service.fix_inconsistent_media_file(db, media_file)

        return {
            "success": success,
            "file_id": file_id,
            "message": "File fixed successfully" if success else "Failed to fix file",
            "new_status": media_file.status.value,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in fix_inconsistent_file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        ) from e


@router.post("/retry/{file_id}", response_model=dict[str, Any])
async def retry_file_processing(
    file_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),  # Any user can retry their own files
):
    """
    Retry processing for a file that failed or got stuck
    """
    try:
        # Find the media file
        if current_user.role == "admin":
            media_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
        else:
            media_file = (
                db.query(MediaFile)
                .filter(MediaFile.id == file_id, MediaFile.user_id == current_user.id)
                .first()
            )

        if not media_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found"
            )

        # Check if the file is in a state where retry makes sense
        if media_file.status not in [FileStatus.ERROR, FileStatus.PROCESSING]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot retry file in {media_file.status.value} status",
            )

        # Reset the file status to PENDING
        from app.utils.task_utils import update_media_file_status

        update_media_file_status(db, file_id, FileStatus.PENDING)

        # Clear old tasks or mark them as failed
        old_tasks = (
            db.query(TaskModel)
            .filter(
                TaskModel.media_file_id == file_id,
                TaskModel.status.in_([TASK_STATUS_PENDING, TASK_STATUS_IN_PROGRESS]),
            )
            .all()
        )

        for task in old_tasks:
            task.status = TASK_STATUS_FAILED
            task.error_message = "Task marked as failed for retry"
            task.completed_at = datetime.now()

        db.commit()

        # Schedule a new transcription in the background
        async def start_new_transcription():
            try:
                # Import here to avoid circular imports
                from app.tasks.transcription import transcribe_audio_task

                result = transcribe_audio_task.delay(file_id)
                logger.info(f"Started new transcription for file {file_id}, task ID: {result.id}")
            except Exception as e:
                logger.error(f"Error starting new transcription: {e}")

        background_tasks.add_task(start_new_transcription)

        return {
            "success": True,
            "file_id": file_id,
            "message": "File processing restarted",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in retry_file_processing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        ) from e


@router.post("/system/startup-recovery", response_model=dict[str, Any])
async def trigger_startup_recovery(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Manually trigger startup recovery for files interrupted by system crashes.

    This endpoint allows admins to manually run the startup recovery process
    that would normally run automatically when the system starts.
    """
    try:
        # Schedule startup recovery in background
        async def run_recovery():
            try:
                from app.tasks.recovery import startup_recovery_task

                result = startup_recovery_task.delay()
                logger.info(f"Manual startup recovery triggered: {result.id}")
            except Exception as e:
                logger.error(f"Error in manual startup recovery: {e}")

        background_tasks.add_task(run_recovery)

        return {
            "success": True,
            "message": "Startup recovery task scheduled successfully",
        }
    except Exception as e:
        logger.error(f"Error triggering startup recovery: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        ) from e


@router.post("/system/recover-user-files/{user_id}", response_model=dict[str, Any])
async def trigger_user_file_recovery(
    user_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Manually trigger file recovery for a specific user.

    This is useful when a user reports stuck or missing files.
    """
    try:
        # Verify the user exists
        target_user = db.query(User).filter(User.id == user_id).first()
        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Schedule user file recovery in background
        async def run_user_recovery():
            try:
                from app.tasks.recovery import recover_user_files_task

                result = recover_user_files_task.delay(user_id)
                logger.info(f"User file recovery triggered for user {user_id}: {result.id}")
            except Exception as e:
                logger.error(f"Error in user file recovery: {e}")

        background_tasks.add_task(run_user_recovery)

        return {
            "success": True,
            "message": f"File recovery scheduled for user {target_user.email}",
            "user_id": user_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering user file recovery: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        ) from e


@router.post("/system/recover-all-user-files", response_model=dict[str, Any])
async def trigger_all_user_file_recovery(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Manually trigger file recovery for all users.

    This is useful for system-wide recovery after major issues.
    """
    try:
        # Schedule recovery for all users in background
        async def run_all_user_recovery():
            try:
                from app.tasks.recovery import recover_user_files_task

                result = recover_user_files_task.delay()  # No user_id means all users
                logger.info(f"All user file recovery triggered: {result.id}")
            except Exception as e:
                logger.error(f"Error in all user file recovery: {e}")

        background_tasks.add_task(run_all_user_recovery)

        return {"success": True, "message": "File recovery scheduled for all users"}
    except Exception as e:
        logger.error(f"Error triggering all user file recovery: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        ) from e
