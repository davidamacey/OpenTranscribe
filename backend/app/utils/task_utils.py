import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.media import Task, MediaFile, FileStatus
from app.db.session_utils import get_refreshed_object

logger = logging.getLogger(__name__)

# Task status constants
TASK_STATUS_PENDING = "pending"
TASK_STATUS_IN_PROGRESS = "in_progress"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"


def create_task_record(db: Session, celery_task_id: str, user_id: int, 
                      media_file_id: int, task_type: str) -> Task:
    """Create a new task record in the database."""
    task = Task(
        id=celery_task_id,
        user_id=user_id,
        media_file_id=media_file_id,
        task_type=task_type,
        status=TASK_STATUS_PENDING,
        progress=0.0
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    
    # Update the media file status to processing if it's pending
    media_file = get_refreshed_object(db, MediaFile, media_file_id)
    if media_file and media_file.status == FileStatus.PENDING:
        update_media_file_status(db, media_file_id, FileStatus.PROCESSING)
        
    return task


def update_task_status(db: Session, task_id: str, status: str, progress: float = None, 
                      error_message: str = None, completed: bool = False) -> Optional[Task]:
    """Update task status in the database."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        logger.warning(f"Task {task_id} not found")
        return None
    
    # Log state transition for debugging
    logger.debug(f"Task {task_id} state change: {task.status} -> {status}")
    
    # Update task fields
    task.status = status
    if progress is not None:
        task.progress = progress
    if error_message:
        task.error_message = error_message
    if completed:
        task.completed_at = datetime.now(timezone.utc)
    
    # Always update the timestamp for task state changes
    task.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(task)
    
    # If task is completed or failed, check if we need to update the media file status
    if status in [TASK_STATUS_COMPLETED, TASK_STATUS_FAILED] and task.media_file_id:
        update_media_file_from_task_status(db, task.media_file_id)
    
    return task


def update_media_file_status(db: Session, file_id: int, status: FileStatus) -> Optional[MediaFile]:
    """Update media file status."""
    media_file = get_refreshed_object(db, MediaFile, file_id)
    if not media_file:
        logger.warning(f"Media file {file_id} not found")
        return None
    
    # Log state transition for debugging
    logger.debug(f"Media file {file_id} state change: {media_file.status} -> {status}")
    
    # Update status and timestamps
    media_file.status = status
    
    # Set completed_at timestamp if status is COMPLETED or ERROR
    if status in [FileStatus.COMPLETED, FileStatus.ERROR] and not media_file.completed_at:
        media_file.completed_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(media_file)
    return media_file


def update_media_file_from_task_status(db: Session, file_id: int) -> Optional[MediaFile]:
    """Check task statuses and update media file status accordingly.
    
    This function checks all tasks associated with a media file and updates
    the media file status based on task statuses:
    - If all tasks are completed, mark the file as COMPLETED
    - If any task is failed and no tasks are pending/in_progress, mark as ERROR
    - If any tasks are still pending/in_progress, leave as PROCESSING
    
    Args:
        db: Database session
        file_id: ID of the media file to check
        
    Returns:
        Updated MediaFile object or None if not found
    """
    media_file = get_refreshed_object(db, MediaFile, file_id)
    if not media_file:
        logger.warning(f"Media file {file_id} not found")
        return None
    
    # Skip if the file is already in a terminal state
    if media_file.status in [FileStatus.COMPLETED, FileStatus.ERROR]:
        return media_file
    
    # Get all tasks for this media file
    tasks = db.query(Task).filter(Task.media_file_id == file_id).all()
    if not tasks:
        logger.warning(f"No tasks found for media file {file_id}")
        return media_file
    
    # Count task statuses
    counts = {
        TASK_STATUS_PENDING: 0,
        TASK_STATUS_IN_PROGRESS: 0,
        TASK_STATUS_COMPLETED: 0,
        TASK_STATUS_FAILED: 0
    }
    
    for task in tasks:
        counts[task.status] = counts.get(task.status, 0) + 1
    
    # Determine the appropriate media file status
    if counts[TASK_STATUS_PENDING] > 0 or counts[TASK_STATUS_IN_PROGRESS] > 0:
        # Still has active tasks
        new_status = FileStatus.PROCESSING
    elif counts[TASK_STATUS_FAILED] > 0 and counts[TASK_STATUS_COMPLETED] == 0:
        # All finished tasks failed
        new_status = FileStatus.ERROR
    else:
        # All tasks completed successfully
        new_status = FileStatus.COMPLETED
    
    # Only update if status is changing
    if media_file.status != new_status:
        return update_media_file_status(db, file_id, new_status)
    
    return media_file


def get_task_summary_for_media_file(db: Session, file_id: int) -> Dict[str, Any]:
    """Get a summary of task statuses for a media file.
    
    Args:
        db: Database session
        file_id: ID of the media file to check
        
    Returns:
        Dictionary with task status counts and overall progress
    """
    tasks = db.query(Task).filter(Task.media_file_id == file_id).all()
    
    summary = {
        "total": len(tasks),
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
        "overall_progress": 0.0
    }
    
    if not tasks:
        return summary
    
    # Count tasks by status and calculate overall progress
    total_progress = 0.0
    for task in tasks:
        summary[task.status] = summary.get(task.status, 0) + 1
        total_progress += task.progress
    
    summary["overall_progress"] = total_progress / len(tasks)
    
    return summary