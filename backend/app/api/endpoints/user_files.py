"""
User-level file management endpoints.

This module provides endpoints for regular users to manage their files,
check status, and request retries without requiring admin privileges.
"""

import logging
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any

from fastapi import APIRouter
from fastapi import BackgroundTasks
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.models.media import Task as TaskModel
from app.models.user import User
from app.services.formatting_service import FormattingService
from app.services.task_recovery_service import task_recovery_service
from app.utils.task_utils import get_task_summary_for_media_file
from app.utils.uuid_helpers import get_file_by_uuid_with_permission

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status", response_model=dict[str, Any])
def get_user_file_status(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)
):
    """
    Get status summary of current user's files including any problems.

    Returns counts of files by status and identifies files that may need attention.
    """
    try:
        # Get user's files
        user_files = db.query(MediaFile).filter(MediaFile.user_id == current_user.id).all()

        # Count files by status
        status_counts = {
            "total": len(user_files),
            "pending": 0,
            "processing": 0,
            "completed": 0,
            "error": 0,
        }

        problem_files = []
        recent_files = []

        for file in user_files:
            # Count by status
            if file.status == FileStatus.PENDING:
                status_counts["pending"] += 1
            elif file.status == FileStatus.PROCESSING:
                status_counts["processing"] += 1
            elif file.status == FileStatus.COMPLETED:
                status_counts["completed"] += 1
            elif file.status == FileStatus.ERROR:
                status_counts["error"] += 1

            # Check for potential problems
            file_age = datetime.now(timezone.utc) - file.upload_time

            # Files that might need attention
            if (
                (file.status == FileStatus.PROCESSING and file_age > timedelta(hours=1))
                or (file.status == FileStatus.PENDING and file_age > timedelta(hours=2))
                or (file.status == FileStatus.ERROR)
            ):
                problem_files.append(
                    {
                        "id": str(file.uuid),  # Use UUID for frontend
                        "filename": file.filename,
                        "status": file.status.value,
                        "upload_time": file.upload_time,
                        "age_hours": file_age.total_seconds() / 3600,
                        "can_retry": file.status in [FileStatus.ERROR, FileStatus.PROCESSING],
                        # Add formatted fields for frontend display
                        "formatted_duration": FormattingService.format_duration(file.duration),
                        "formatted_file_age": FormattingService.format_file_age(file.upload_time),
                        "formatted_file_size": FormattingService.format_bytes_detailed(
                            file.file_size
                        ),
                        "display_status": FormattingService.format_status(file.status),
                        "status_badge_class": FormattingService.get_status_badge_class(
                            file.status.value
                        ),
                    }
                )

            # Recent files (last 24 hours)
            if file_age < timedelta(hours=24):
                recent_files.append(
                    {
                        "id": str(file.uuid),  # Use UUID for frontend
                        "filename": file.filename,
                        "status": file.status.value,
                        "upload_time": file.upload_time,
                        "duration": file.duration,
                        "age_hours": file_age.total_seconds() / 3600,
                        # Add formatted fields for frontend display
                        "formatted_duration": FormattingService.format_duration(file.duration),
                        "formatted_file_age": FormattingService.format_file_age(file.upload_time),
                        "formatted_file_size": FormattingService.format_bytes_detailed(
                            file.file_size
                        ),
                        "display_status": FormattingService.format_status(file.status),
                        "status_badge_class": FormattingService.get_status_badge_class(
                            file.status.value
                        ),
                    }
                )

        # Sort recent files by upload time (newest first)
        recent_files.sort(key=lambda x: x["upload_time"], reverse=True)

        return {
            "status_counts": status_counts,
            "problem_files": {"count": len(problem_files), "files": problem_files},
            "recent_files": {
                "count": len(recent_files),
                "files": recent_files[:10],  # Limit to 10 most recent
            },
            "has_problems": len(problem_files) > 0,
            "timestamp": datetime.now(timezone.utc),
        }

    except Exception as e:
        logger.error(f"Error getting user file status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving file status: {str(e)}",
        ) from e


@router.get("/{file_uuid}/status", response_model=dict[str, Any])
def get_file_detailed_status(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get detailed status for a specific file including task information.
    """
    try:
        # Get the file (ensure user owns it)
        media_file = get_file_by_uuid_with_permission(db, file_uuid, current_user.id)
        file_id = media_file.id

        # Get task summary
        task_summary = get_task_summary_for_media_file(db, file_id)

        # Get all tasks for this file
        tasks = db.query(TaskModel).filter(TaskModel.media_file_id == file_id).all()

        task_details = []
        for task in tasks:
            task_details.append(
                {
                    "id": task.id,
                    "task_type": task.task_type,
                    "status": task.status,
                    "progress": task.progress,
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                    "completed_at": task.completed_at,
                    "error_message": task.error_message,
                    # Add formatted processing time
                    "formatted_processing_time": FormattingService.format_processing_time(
                        task.created_at, task.completed_at
                    ),
                    "status_display": task.status.title(),
                }
            )

        # Calculate file age and determine if retry is available
        file_age = datetime.now(timezone.utc) - media_file.upload_time
        can_retry = media_file.status in [FileStatus.ERROR, FileStatus.PROCESSING]

        # Check if file might be stuck
        is_stuck = False
        if media_file.status == FileStatus.PROCESSING:
            active_tasks = [t for t in tasks if t.status in ["pending", "in_progress"]]
            if not active_tasks and file_age > timedelta(hours=1):
                is_stuck = True

        return {
            "file": {
                "id": str(media_file.uuid),  # Use UUID for frontend
                "filename": media_file.filename,
                "status": media_file.status.value,
                "upload_time": media_file.upload_time,
                "completed_at": media_file.completed_at,
                "file_size": media_file.file_size,
                "duration": media_file.duration,
                "language": media_file.language,
                # Add formatted fields for frontend display
                "formatted_file_size": FormattingService.format_bytes_detailed(
                    media_file.file_size
                ),
                "formatted_duration": FormattingService.format_duration(media_file.duration),
                "formatted_file_age": FormattingService.format_file_age(media_file.upload_time),
                "display_status": FormattingService.format_status(media_file.status),
                "status_badge_class": FormattingService.get_status_badge_class(
                    media_file.status.value
                ),
            },
            "task_summary": task_summary,
            "task_details": task_details,
            "file_age_hours": file_age.total_seconds() / 3600,
            "can_retry": can_retry,
            "is_stuck": is_stuck,
            "suggestions": _get_file_suggestions(media_file, task_summary, file_age),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting file detailed status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving file details: {str(e)}",
        ) from e


@router.post("/{file_uuid}/retry", response_model=dict[str, Any])
async def retry_file_processing(
    file_uuid: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Retry processing for a file that failed or is stuck.
    Available to all users for their own files.
    """
    try:
        # Get the file (ensure user owns it)
        media_file = get_file_by_uuid_with_permission(db, file_uuid, current_user.id)
        file_id = media_file.id

        # Check if retry is appropriate
        if media_file.status not in [FileStatus.ERROR, FileStatus.PROCESSING]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot retry file in {media_file.status.value} status. Only error or stuck processing files can be retried.",
            )

        # Check rate limiting (prevent spam retries)
        recent_tasks = (
            db.query(TaskModel)
            .filter(
                TaskModel.media_file_id == file_id,
                TaskModel.created_at > datetime.now(timezone.utc) - timedelta(minutes=5),
            )
            .count()
        )

        if recent_tasks > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Please wait at least 5 minutes between retry attempts",
            )

        # Use recovery service to handle the retry
        success = task_recovery_service.schedule_file_retry(file_id)

        if success:
            # Update file status to pending
            from app.utils.task_utils import update_media_file_status

            update_media_file_status(db, file_id, FileStatus.PENDING)

            # Mark old tasks as failed
            old_tasks = (
                db.query(TaskModel)
                .filter(
                    TaskModel.media_file_id == file_id,
                    TaskModel.status.in_(["pending", "in_progress"]),
                )
                .all()
            )

            for task in old_tasks:
                task.status = "failed"
                task.error_message = "Task marked as failed for user retry"
                task.completed_at = datetime.now(timezone.utc)

            db.commit()

            logger.info(f"User {current_user.id} successfully retried file {file_id}")

            return {
                "success": True,
                "message": "File processing restarted successfully",
                "file_id": str(media_file.uuid),  # Use UUID for frontend
                "new_status": "pending",
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to schedule file retry",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying file processing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrying file: {str(e)}",
        ) from e


@router.post("/request-recovery", response_model=dict[str, Any])
async def request_user_recovery(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Request recovery for all of the current user's problem files.
    This triggers the same recovery process that admins can run.
    """
    try:
        # Check rate limiting (prevent spam requests)
        # This could be implemented with Redis or database tracking

        # Schedule user-specific recovery
        async def run_user_recovery():
            try:
                from app.tasks.recovery import recover_user_files_task

                result = recover_user_files_task.delay(current_user.id)
                logger.info(f"User {current_user.id} requested file recovery, task ID: {result.id}")
            except Exception as e:
                logger.error(f"Error in user recovery request: {e}")

        background_tasks.add_task(run_user_recovery)

        return {
            "success": True,
            "message": "Recovery process started for your files",
            "user_id": str(current_user.uuid),
        }

    except Exception as e:
        logger.error(f"Error requesting user recovery: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error requesting recovery: {str(e)}",
        ) from e


def _get_file_suggestions(
    media_file: MediaFile, task_summary: dict[str, Any], file_age: timedelta
) -> list[str]:
    """Generate helpful suggestions for the user based on file status."""
    suggestions = []

    if media_file.status == FileStatus.ERROR:
        suggestions.append(
            "This file failed to process. You can retry processing by clicking the retry button."
        )
        if task_summary.get("failed", 0) > 0:
            suggestions.append(
                "Check if the file format is supported or if the audio quality is sufficient."
            )

    elif media_file.status == FileStatus.PROCESSING:
        if file_age > timedelta(hours=2):
            suggestions.append(
                "This file has been processing for a long time. It may be stuck and could benefit from a retry."
            )
        elif file_age > timedelta(minutes=30):
            suggestions.append(
                "Large files or files with poor audio quality may take longer to process."
            )
        else:
            suggestions.append("File is currently being processed. Please wait for completion.")

    elif media_file.status == FileStatus.PENDING:
        if file_age > timedelta(hours=1):
            suggestions.append(
                "This file has been waiting to be processed for a while. You can retry to move it to the front of the queue."
            )
        else:
            suggestions.append("File is waiting to be processed. Processing will begin shortly.")

    elif media_file.status == FileStatus.COMPLETED:
        suggestions.append("File has been successfully processed and is ready for use.")

    return suggestions
