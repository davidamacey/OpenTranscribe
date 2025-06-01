from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from app.db.base import get_db
from app.models.user import User
from app.models.media import MediaFile
from app.schemas.media import Task, TaskStatus, FileStatus
from app.api.endpoints.auth import get_current_active_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=List[Task])
def list_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    List all tasks for the current user
    """
    try:
        # Query tasks from the database
        # In a real implementation, we would have a Task model
        # Here we're simulating tasks based on MediaFile statuses
        
        # Admin users can see all files/tasks, regular users only see their own
        if current_user.role == "admin":
            media_files = db.query(MediaFile).all()
        else:
            media_files = db.query(MediaFile).filter(
                MediaFile.user_id == current_user.id
            ).all()
        
        # Convert them to tasks
        tasks = []
        for file in media_files:
            # Map file status to task status
            task_status = "pending"
            if file.status == FileStatus.PENDING:
                task_status = "pending"
            elif file.status == FileStatus.PROCESSING:
                task_status = "in_progress"
            elif file.status == FileStatus.COMPLETED:
                task_status = "completed"
            elif file.status == FileStatus.ERROR:
                task_status = "failed"
                
            # Use the actual completed_at time stored in the database
            completed_at = getattr(file, "completed_at", None)
            if file.status == FileStatus.COMPLETED and not completed_at:
                # Fall back to upload_time for older records without completed_at
                completed_at = file.upload_time
            
            # Extract file format from content_type or use extension
            file_format = None
            if file.content_type:
                # Extract format from content_type (e.g., audio/mp3 -> mp3)
                if "/" in file.content_type:
                    file_format = file.content_type.split("/")[1]
            if not file_format and file.filename and "." in file.filename:
                # Fall back to filename extension
                file_format = file.filename.split(".")[-1]
            
            # Create a task for each file based on its status
            task = Task(
                id=f"task_{file.id}",
                user_id=current_user.id,
                task_type="transcription",
                status=task_status,
                media_file_id=file.id,
                progress=1.0 if file.status == FileStatus.COMPLETED else 0.5 if file.status == FileStatus.PROCESSING else 0.0,
                created_at=file.upload_time,
                updated_at=file.upload_time,
                completed_at=completed_at,
                error_message=None if file.status != FileStatus.ERROR else "Transcription failed",
                media_file={
                    "id": file.id,
                    "filename": file.filename,
                    "file_size": file.file_size,
                    "content_type": file.content_type,
                    "duration": file.duration,
                    "language": file.language,
                    "format": file_format,
                    "media_format": getattr(file, "media_format", None),
                    "codec": getattr(file, "codec", None),
                    "upload_time": file.upload_time
                }
            )
            tasks.append(task)
        
        return tasks
    except Exception as e:
        logger.error(f"Error in list_tasks: {e}")
        # Return an empty list if there's an error
        return []


@router.get("/{task_id}", response_model=Task)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get a specific task by its ID
    """
    try:
        # Extract the media file ID from the task ID
        try:
            # Parse task_id format "task_{file_id}"
            if not task_id.startswith("task_"):
                raise ValueError("Invalid task ID format")
            file_id = int(task_id.split("_")[1])
        except (ValueError, IndexError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid task ID format"
            )
        
        # Admin users can access any file/task, regular users only their own
        if current_user.role == "admin":
            media_file = db.query(MediaFile).filter(
                MediaFile.id == file_id
            ).first()
        else:
            media_file = db.query(MediaFile).filter(
                MediaFile.id == file_id,
                MediaFile.user_id == current_user.id
            ).first()
        
        if not media_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        # Map file status to task status
        task_status = "pending"
        if media_file.status == FileStatus.PENDING:
            task_status = "pending"
        elif media_file.status == FileStatus.PROCESSING:
            task_status = "in_progress"
        elif media_file.status == FileStatus.COMPLETED:
            task_status = "completed"
        elif media_file.status == FileStatus.ERROR:
            task_status = "failed"
        
        # Use the actual completed_at time stored in the database
        completed_at = getattr(media_file, "completed_at", None)
        if media_file.status == FileStatus.COMPLETED and not completed_at:
            # Fall back to upload_time for older records without completed_at
            completed_at = media_file.upload_time
        
        # Extract file format from content_type or use extension
        file_format = None
        if media_file.content_type:
            # Extract format from content_type (e.g., audio/mp3 -> mp3)
            if "/" in media_file.content_type:
                file_format = media_file.content_type.split("/")[1]
        if not file_format and media_file.filename and "." in media_file.filename:
            # Fall back to filename extension
            file_format = media_file.filename.split(".")[-1]
        
        # Convert to task
        task = Task(
            id=task_id,
            user_id=current_user.id,
            media_file_id=media_file.id,
            task_type="transcription",
            status=task_status,
            progress=1.0 if media_file.status == FileStatus.COMPLETED else 0.5 if media_file.status == FileStatus.PROCESSING else 0.0,
            created_at=media_file.upload_time,
            updated_at=media_file.upload_time,
            completed_at=completed_at,
            error_message=None if media_file.status != FileStatus.ERROR else "Transcription failed",
            media_file={
                "id": media_file.id,
                "filename": media_file.filename,
                "file_size": media_file.file_size,
                "content_type": media_file.content_type,
                "duration": media_file.duration,
                "language": media_file.language,
                "format": file_format,
                "media_format": getattr(media_file, "media_format", None),
                "codec": getattr(media_file, "codec", None)
            }
        )
        
        return task
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error in get_task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )
