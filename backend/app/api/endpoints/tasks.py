from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.base import get_db
from app.models.user import User
from app.models.media import MediaFile
from app.schemas.media import Task, TaskStatus, FileStatus
from app.api.endpoints.auth import get_current_active_user

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
        print("Fetching tasks for user", current_user.id)
        # Query tasks from the database
        # In a real implementation, we would have a Task model
        # Here we're simulating tasks based on MediaFile statuses
        
        # Get all media files for this user
        media_files = db.query(MediaFile).filter(
            MediaFile.user_id == current_user.id
        ).all()
        
        print(f"Found {len(media_files)} media files")
        
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
                
            # Create a task for each file based on its status
            task = Task(
                id=f"task_{file.id}",
                user_id=current_user.id,  # Explicitly include user_id to match schema
                task_type="transcription",
                status=task_status,
                media_file_id=file.id,
                progress=1.0 if file.status == FileStatus.COMPLETED else 0.5 if file.status == FileStatus.PROCESSING else 0.0,
                created_at=file.upload_time,
                updated_at=file.upload_time,
                completed_at=file.upload_time if file.status == FileStatus.COMPLETED else None,
                error_message=None if file.status != FileStatus.ERROR else "Transcription failed",
                media_file={
                    "id": file.id,
                    "filename": file.filename
                }
            )
            tasks.append(task)
        
        print(f"Returning {len(tasks)} tasks")
        return tasks
    except Exception as e:
        print(f"Error in list_tasks: {e}")
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
        
        # Get the media file
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
        
        # Convert to task
        task = Task(
            id=task_id,
            user_id=current_user.id,  # Include user_id to match schema requirement
            media_file_id=media_file.id,
            task_type="transcription",
            status=task_status,
            progress=1.0 if media_file.status == FileStatus.COMPLETED else 0.5 if media_file.status == FileStatus.PROCESSING else 0.0,
            created_at=media_file.upload_time,
            updated_at=media_file.upload_time,
            completed_at=media_file.upload_time if media_file.status == FileStatus.COMPLETED else None,
            error_message=None if media_file.status != FileStatus.ERROR else "Transcription failed",
            media_file={
                "id": media_file.id,
                "filename": media_file.filename
            }
        )
        
        return task
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        print(f"Error in get_task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )
