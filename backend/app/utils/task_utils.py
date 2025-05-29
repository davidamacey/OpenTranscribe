import logging
import datetime
from sqlalchemy.orm import Session

from app.models.media import Task, MediaFile, FileStatus
from app.db.session_utils import get_refreshed_object

logger = logging.getLogger(__name__)


def create_task_record(db: Session, celery_task_id: str, user_id: int, 
                      media_file_id: int, task_type: str) -> Task:
    """Create a new task record in the database."""
    task = Task(
        id=celery_task_id,
        user_id=user_id,
        media_file_id=media_file_id,
        task_type=task_type,
        status="pending",
        progress=0.0
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_task_status(db: Session, task_id: str, status: str, progress: float = None, 
                      error_message: str = None, completed: bool = False) -> None:
    """Update task status in the database."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        logger.warning(f"Task {task_id} not found")
        return
    
    task.status = status
    if progress is not None:
        task.progress = progress
    if error_message:
        task.error_message = error_message
    if completed:
        task.completed_at = datetime.datetime.now()
    
    db.commit()


def update_media_file_status(db: Session, file_id: int, status: FileStatus) -> None:
    """Update media file status."""
    media_file = get_refreshed_object(db, MediaFile, file_id)
    if media_file:
        media_file.status = status
        db.commit()
    else:
        logger.warning(f"Media file {file_id} not found")