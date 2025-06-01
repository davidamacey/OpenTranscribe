from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
from typing import List, Dict, Any
import psutil
import datetime
import os
import platform

from app.db.base import get_db
from app.models.user import User
from app.models.media import MediaFile, Speaker, TranscriptSegment
from app.schemas.user import User as UserSchema, UserCreate
from app.api.endpoints.auth import get_current_active_superuser, get_current_admin_user

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
            "percent": f"{memory.percent}%"
        }
    except Exception as e:
        logger.error(f"Error getting memory usage: {e}")
        return {"total": "Unknown", "available": "Unknown", "used": "Unknown", "percent": "Unknown"}

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
            "physical_cores": physical_cores
        }
    except Exception as e:
        logger.error(f"Error getting CPU usage: {e}")
        return {"total_percent": "Unknown", "per_cpu": [], "logical_cores": 0, "physical_cores": 0}

def get_disk_usage():
    """Get disk usage information"""
    try:
        # Get disk usage for the root directory
        disk = psutil.disk_usage('/')
        
        return {
            "total": format_bytes(disk.total),
            "used": format_bytes(disk.used),
            "free": format_bytes(disk.free),
            "percent": f"{disk.percent}%"
        }
    except Exception as e:
        logger.error(f"Error getting disk usage: {e}")
        return {"total": "Unknown", "used": "Unknown", "free": "Unknown", "percent": "Unknown"}

def format_bytes(bytes):
    """Format bytes to a human-readable string"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes < 1024 or unit == 'TB':
            return f"{bytes:.2f} {unit}"
        bytes /= 1024


@router.get("/stats", response_model=Dict[str, Any])
async def get_admin_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
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
                "uptime": get_system_uptime()
            }
        except Exception as e:
            logger.error(f"Error getting system stats: {e}")
            system_stats = {
                "cpu": {"total_percent": "Unknown", "per_cpu": [], "logical_cores": 0, "physical_cores": 0},
                "memory": {"total": "Unknown", "available": "Unknown", "used": "Unknown", "percent": "Unknown"},
                "disk": {"total": "Unknown", "used": "Unknown", "free": "Unknown", "percent": "Unknown"},
                "uptime": "Unknown"
            }

        # Get user statistics
        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.is_active == True).count()
        inactive_users = total_users - active_users
        superusers = db.query(User).filter(User.is_superuser == True).count()
        
        # Get file statistics
        total_files = db.query(MediaFile).count()
        
        # Count files by status
        pending_files = db.query(MediaFile).filter(
            MediaFile.status == "pending"
        ).count()
        
        processing_files = db.query(MediaFile).filter(
            MediaFile.status == "processing"
        ).count()
        
        completed_files = db.query(MediaFile).filter(
            MediaFile.status == "completed"
        ).count()
        
        error_files = db.query(MediaFile).filter(
            MediaFile.status == "error"
        ).count()
        
        # Get total file size
        from sqlalchemy.sql import func
        total_size_result = db.query(
            func.sum(MediaFile.file_size)
        ).scalar()
        total_size = total_size_result if total_size_result else 0
        
        # Get transcript statistics
        total_segments = db.query(TranscriptSegment).count()
        
        # Get speaker statistics
        total_speakers = db.query(Speaker).count()
        
        # Get recent tasks (last 10)
        from app.models.media import Task
        recent_tasks = db.query(Task).order_by(Task.created_at.desc()).limit(10).all()
        recent = []
        for task in recent_tasks:
            elapsed = 0
            if task.completed_at and task.created_at:
                elapsed = (task.completed_at - task.created_at).total_seconds()
            elif task.created_at:
                from datetime import datetime
                elapsed = (datetime.utcnow() - task.created_at).total_seconds()
            recent.append({
                "id": task.id,
                "type": getattr(task, 'task_type', ''),
                "status": task.status,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "elapsed": int(elapsed) if elapsed else 0
            })

        # Construct the response
        stats = {
            "users": {
                "total": total_users,
                "active": active_users,
                "inactive": inactive_users,
                "superusers": superusers
            },
            "files": {
                "total": total_files,
                "by_status": {
                    "pending": pending_files,
                    "processing": processing_files,
                    "completed": completed_files,
                    "error": error_files
                },
                "total_size": total_size
            },
            "transcripts": {
                "total_segments": total_segments
            },
            "speakers": {
                "total": total_speakers
            },
            "system": {
                "version": "1.0.0",
                "uptime": system_stats["uptime"],
                "memory": system_stats["memory"],
                "cpu": system_stats["cpu"],
                "disk": system_stats["disk"],
                "platform": platform.platform(),
                "python_version": platform.python_version()
            },
            "tasks": {
                "recent": recent
            }
        }
        
        return stats
    except Exception as e:
        logger.error(f"Error getting admin stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving admin statistics: {str(e)}"
        )


@router.get("/users", response_model=List[UserSchema])
def get_admin_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
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
            detail=f"Error retrieving users: {str(e)}"
        )


@router.post("/users", response_model=UserSchema)
def create_admin_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
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
            detail=f"Error creating user: {str(e)}"
        )


@router.delete("/users/{user_id}", response_model=Dict[str, str])
def delete_admin_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Delete a user and all their data (admin only)
    """
    logger.info(f"Admin deleting user with ID: {user_id}")
    
    try:
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if user.id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account"
            )
        
        # Check if user is a superuser
        if user.is_superuser and current_user.id != 1:  # Only main admin can delete other superusers
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete a superuser account"
            )
        
        # Delete speakers
        try:
            speakers_count = db.query(Speaker).filter(Speaker.user_id == user_id).count()
            if speakers_count > 0:
                logger.info(f"Deleting {speakers_count} speakers for user {user_id}")
                db.query(Speaker).filter(Speaker.user_id == user_id).delete(synchronize_session=False)
                logger.info("Speakers deleted successfully")
        except Exception as speaker_error:
            logger.error(f"Error deleting speakers: {speaker_error}")
            raise
        
        # Find and delete all media file related entities
        try:
            media_files = db.query(MediaFile).filter(MediaFile.user_id == user_id).all()
            media_count = len(media_files)
            
            if media_count > 0:
                logger.info(f"Found {media_count} media files for user {user_id}")
                media_ids = [m.id for m in media_files]
                
                # Delete transcript segments for these media files
                segments_count = db.query(TranscriptSegment).filter(
                    TranscriptSegment.media_file_id.in_(media_ids)
                ).count()
                
                if segments_count > 0:
                    logger.info(f"Deleting {segments_count} transcript segments for user's media files")
                    db.query(TranscriptSegment).filter(
                        TranscriptSegment.media_file_id.in_(media_ids)
                    ).delete(synchronize_session=False)
                    logger.info("Transcript segments deleted successfully")
                
                # Delete other related records
                try:
                    if media_ids:
                        file_tag_sql = f"DELETE FROM file_tag WHERE media_file_id IN ({','.join(map(str, media_ids))})"
                        db.execute(text(file_tag_sql))
                        logger.info("File tags deleted successfully")
                        
                        analytics_sql = f"DELETE FROM analytics WHERE media_file_id IN ({','.join(map(str, media_ids))})"
                        db.execute(text(analytics_sql))
                        logger.info("Analytics deleted successfully")
                except Exception as related_error:
                    logger.error(f"Error deleting file_tag or analytics: {related_error}")
                    raise
                
                # Now delete the media files
                db.query(MediaFile).filter(MediaFile.user_id == user_id).delete(synchronize_session=False)
                logger.info(f"Deleted {media_count} media files for user {user_id}")
        except Exception as media_error:
            logger.error(f"Error deleting media files: {media_error}")
            raise
        
        # Now delete the user
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
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"===== ERROR IN DELETE_USER: {e} =====")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error details: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
