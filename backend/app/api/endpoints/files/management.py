"""
Enhanced file management endpoints for error handling and recovery.
"""

import logging
from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Query
from fastapi import status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_user
from app.api.endpoints.files.crud import delete_media_file
from app.api.endpoints.files.crud import get_media_file_by_uuid
from app.db.base import get_db
from app.models.media import FileStatus
from app.models.user import User
from app.tasks.transcription import transcribe_audio_task
from app.utils.task_utils import cancel_active_task
from app.utils.task_utils import check_for_stuck_files
from app.utils.task_utils import is_file_safe_to_delete
from app.utils.task_utils import recover_stuck_file
from app.utils.task_utils import reset_file_for_retry

router = APIRouter()
logger = logging.getLogger(__name__)


class FileStatusDetail(BaseModel):
    """Detailed file status information."""

    file_id: int
    filename: str
    status: str
    can_delete: bool
    can_retry: bool
    can_cancel: bool
    is_stuck: bool
    retry_count: int
    max_retries: int
    active_task_id: Optional[str] = None
    task_started_at: Optional[str] = None
    task_last_update: Optional[str] = None
    last_error_message: Optional[str] = None
    recovery_attempts: int = 0
    force_delete_eligible: bool = False
    actions_available: list[str] = []
    recommendations: list[str] = []


class BulkActionRequest(BaseModel):
    """Request for bulk file operations."""

    file_uuids: list[str]
    action: str  # "delete", "retry", "cancel", "recover"
    force: bool = False
    reset_retry_count: bool = False


class BulkActionResult(BaseModel):
    """Result of bulk file operations."""

    file_uuid: str
    success: bool
    message: str
    error: Optional[str] = None


@router.get("/{file_uuid}/status-detail", response_model=FileStatusDetail)
async def get_file_status_detail(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed status information for a file."""
    try:
        is_admin = current_user.role == "admin"
        db_file = get_media_file_by_uuid(db, file_uuid, current_user.id, is_admin=is_admin)
        file_id = db_file.id  # Get internal ID for task operations

        # Check if file is safe to delete
        is_safe, delete_reason = is_file_safe_to_delete(db, file_id)

        # Determine if file is stuck
        stuck_files = check_for_stuck_files(db, stuck_threshold_hours=1)
        is_stuck = file_id in stuck_files

        # Determine available actions
        actions = []
        recommendations = []

        if db_file.status == FileStatus.PROCESSING and db_file.active_task_id:
            actions.append("cancel")
            if is_stuck:
                recommendations.append("This file appears stuck. Consider cancelling and retrying.")

        if db_file.status in [
            FileStatus.ERROR,
            FileStatus.CANCELLED,
            FileStatus.ORPHANED,
        ]:
            actions.append("retry")
            if db_file.retry_count < db_file.max_retries:
                recommendations.append("This file can be retried for processing.")
            else:
                recommendations.append(
                    "This file has reached maximum retry attempts. Consider force deletion or admin intervention."
                )

        if is_safe or db_file.force_delete_eligible:
            actions.append("delete")
        elif is_admin:
            actions.append("force_delete")

        if is_stuck:
            actions.append("recover")
            recommendations.append("Auto-recovery may help resolve stuck processing.")

        return FileStatusDetail(
            file_id=db_file.id,
            filename=db_file.filename,
            status=db_file.status,
            can_delete=is_safe,
            can_retry=db_file.status
            in [FileStatus.ERROR, FileStatus.CANCELLED, FileStatus.ORPHANED],
            can_cancel=db_file.status == FileStatus.PROCESSING
            and db_file.active_task_id is not None,
            is_stuck=is_stuck,
            retry_count=db_file.retry_count,
            max_retries=db_file.max_retries,
            active_task_id=db_file.active_task_id,
            task_started_at=db_file.task_started_at.isoformat()
            if db_file.task_started_at
            else None,
            task_last_update=db_file.task_last_update.isoformat()
            if db_file.task_last_update
            else None,
            last_error_message=db_file.last_error_message,
            recovery_attempts=db_file.recovery_attempts,
            force_delete_eligible=db_file.force_delete_eligible,
            actions_available=actions,
            recommendations=recommendations,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting file status detail for {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving file status details",
        ) from e


@router.post("/{file_uuid}/cancel")
async def cancel_file_processing(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel active processing for a file."""
    try:
        is_admin = current_user.role == "admin"
        db_file = get_media_file_by_uuid(db, file_uuid, current_user.id, is_admin=is_admin)
        file_id = db_file.id  # Get internal ID for task operations

        if db_file.status != FileStatus.PROCESSING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is not currently processing",
            )

        if not db_file.active_task_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active task found for this file",
            )

        success = cancel_active_task(db, file_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to cancel file processing",
            )

        return {"message": "File processing cancelled successfully", "file_id": str(db_file.uuid)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling file {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error cancelling file processing",
        ) from e


@router.post("/{file_uuid}/retry")
async def retry_file_processing(
    file_uuid: str,
    reset_retry_count: bool = Query(False, description="Reset retry count to 0"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retry processing for a failed file."""
    try:
        is_admin = current_user.role == "admin"
        db_file = get_media_file_by_uuid(db, file_uuid, current_user.id, is_admin=is_admin)
        file_id = db_file.id  # Get internal ID for task operations

        # Check if file can be retried
        if db_file.status not in [
            FileStatus.ERROR,
            FileStatus.CANCELLED,
            FileStatus.ORPHANED,
        ]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File cannot be retried in current status: {db_file.status}",
            )

        # Check retry limits
        if db_file.retry_count >= db_file.max_retries and not reset_retry_count and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File has reached maximum retry attempts ({db_file.max_retries}). Contact admin for help.",
            )

        # Reset file for retry
        success = reset_file_for_retry(db, file_id, reset_retry_count)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reset file for retry",
            )

        # Start new transcription task
        import os

        if os.environ.get("SKIP_CELERY", "False").lower() != "true":
            task = transcribe_audio_task.delay(file_uuid)
            logger.info(f"Started retry task {task.id} for file {file_id}")
            return {
                "message": "File retry initiated successfully",
                "file_id": str(db_file.uuid),  # Use UUID for frontend
                "task_id": task.id,
                "retry_attempt": db_file.retry_count,
            }
        else:
            logger.info("Skipping Celery task in test environment")
            return {
                "message": "File retry prepared (test mode)",
                "file_id": str(db_file.uuid),  # Use UUID for frontend
                "retry_attempt": db_file.retry_count,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying file {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrying file processing",
        ) from e


@router.post("/{file_uuid}/recover")
async def recover_file(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attempt to recover a stuck file."""
    try:
        is_admin = current_user.role == "admin"
        db_file = get_media_file_by_uuid(db, file_uuid, current_user.id, is_admin=is_admin)
        file_id = db_file.id  # Get internal ID for task operations

        success = recover_stuck_file(db, file_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to recover file",
            )

        # Refresh file to get updated status
        db.refresh(db_file)

        return {
            "message": "File recovery completed",
            "file_id": str(db_file.uuid),  # Use UUID for frontend
            "new_status": db_file.status,
            "recovery_attempts": db_file.recovery_attempts,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recovering file {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error recovering file",
        ) from e


@router.delete("/{file_uuid}/force")
async def force_delete_file(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Force delete a file (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can force delete files",
        )

    try:
        delete_media_file(db, file_uuid, current_user, force=True)
        return {"message": "File force deleted successfully", "file_uuid": file_uuid}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error force deleting file {file_uuid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error force deleting file",
        ) from e


@router.get("/management/stuck")
async def get_stuck_files(
    threshold_hours: float = Query(2.0, description="Hours threshold for stuck detection"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get list of files that appear to be stuck in processing."""
    try:
        stuck_file_ids = check_for_stuck_files(db, threshold_hours)

        # Get file details for user's files only (unless admin)
        is_admin = current_user.role == "admin"
        stuck_files = []

        for file_id in stuck_file_ids:
            try:
                # Use internal ID lookup for stuck files (file_id is int from check_for_stuck_files)
                from app.api.endpoints.files.crud import get_media_file_by_id
                db_file = get_media_file_by_id(db, file_id, current_user.id, is_admin=is_admin)
                stuck_files.append(
                    {
                        "id": str(db_file.uuid),  # Use UUID for frontend
                        "filename": db_file.filename,
                        "status": db_file.status,
                        "active_task_id": db_file.active_task_id,
                        "task_started_at": db_file.task_started_at.isoformat()
                        if db_file.task_started_at
                        else None,
                        "task_last_update": db_file.task_last_update.isoformat()
                        if db_file.task_last_update
                        else None,
                        "recovery_attempts": db_file.recovery_attempts,
                    }
                )
            except HTTPException:
                # User doesn't have access to this file, skip it
                continue

        return {
            "stuck_files": stuck_files,
            "total_count": len(stuck_files),
            "threshold_hours": threshold_hours,
        }

    except Exception as e:
        logger.error(f"Error getting stuck files: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving stuck files",
        ) from e


@router.post("/management/bulk-action", response_model=list[BulkActionResult])
async def bulk_file_action(
    request: BulkActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Perform bulk actions on multiple files."""
    try:
        results = []
        is_admin = current_user.role == "admin"

        for file_uuid in request.file_uuids:
            try:
                # Verify user has access to this file
                db_file = get_media_file_by_uuid(db, file_uuid, current_user.id, is_admin=is_admin)
                file_id = db_file.id  # Get internal ID for task operations

                if request.action == "delete":
                    delete_media_file(db, file_uuid, current_user, force=request.force)
                    results.append(
                        BulkActionResult(
                            file_uuid=file_uuid,
                            success=True,
                            message="File deleted successfully",
                        )
                    )

                elif request.action == "retry":
                    success = reset_file_for_retry(db, file_id, request.reset_retry_count)
                    if success:
                        # Start transcription task
                        import os

                        if os.environ.get("SKIP_CELERY", "False").lower() != "true":
                            task = transcribe_audio_task.delay(file_uuid)
                            message = f"Retry started (task: {task.id})"
                        else:
                            message = "Retry prepared (test mode)"

                        results.append(
                            BulkActionResult(file_uuid=file_uuid, success=True, message=message)
                        )
                    else:
                        results.append(
                            BulkActionResult(
                                file_uuid=file_uuid,
                                success=False,
                                message="Failed to reset file for retry",
                                error="RESET_FAILED",
                            )
                        )

                elif request.action == "cancel":
                    success = cancel_active_task(db, file_id)
                    results.append(
                        BulkActionResult(
                            file_uuid=file_uuid,
                            success=success,
                            message="Task cancelled successfully"
                            if success
                            else "Failed to cancel task",
                            error=None if success else "CANCEL_FAILED",
                        )
                    )

                elif request.action == "recover":
                    success = recover_stuck_file(db, file_id)
                    results.append(
                        BulkActionResult(
                            file_uuid=file_uuid,
                            success=success,
                            message="File recovered successfully"
                            if success
                            else "Failed to recover file",
                            error=None if success else "RECOVERY_FAILED",
                        )
                    )

                else:
                    results.append(
                        BulkActionResult(
                            file_uuid=file_uuid,
                            success=False,
                            message=f"Unknown action: {request.action}",
                            error="UNKNOWN_ACTION",
                        )
                    )

            except HTTPException as e:
                results.append(
                    BulkActionResult(
                        file_uuid=file_uuid,
                        success=False,
                        message=str(e.detail),
                        error="HTTP_ERROR",
                    )
                )
            except Exception as e:
                logger.error(f"Error processing bulk action for file {file_uuid}: {e}")
                results.append(
                    BulkActionResult(
                        file_uuid=file_uuid,
                        success=False,
                        message=f"Unexpected error: {str(e)}",
                        error="UNEXPECTED_ERROR",
                    )
                )

        return results

    except Exception as e:
        logger.error(f"Error in bulk file action: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error performing bulk file action",
        ) from e


@router.post("/management/cleanup-orphaned")
async def cleanup_orphaned_files(
    dry_run: bool = Query(False, description="Preview changes without applying them"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clean up orphaned files (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can cleanup orphaned files",
        )

    try:
        # Find stuck files
        stuck_file_ids = check_for_stuck_files(db, stuck_threshold_hours=6)

        cleanup_results = {
            "stuck_files_found": len(stuck_file_ids),
            "recovered": 0,
            "marked_orphaned": 0,
            "errors": [],
            "dry_run": dry_run,
        }

        if not dry_run:
            for file_id in stuck_file_ids:
                try:
                    success = recover_stuck_file(db, file_id)
                    if success:
                        cleanup_results["recovered"] += 1
                    else:
                        cleanup_results["errors"].append(f"Failed to recover file {file_id}")
                except Exception as e:
                    cleanup_results["errors"].append(f"Error processing file {file_id}: {str(e)}")

        return cleanup_results

    except Exception as e:
        logger.error(f"Error in cleanup orphaned files: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error cleaning up orphaned files",
        ) from e
