import os
import logging
from typing import List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import inspect

from app.models.user import User
from app.models.media import MediaFile, TranscriptSegment, FileTag, Tag, Collection, CollectionMember
from app.schemas.media import MediaFileDetail, MediaFileUpdate, TranscriptSegmentUpdate
from app.services.minio_service import delete_file

logger = logging.getLogger(__name__)


def get_media_file_by_id(db: Session, file_id: int, user_id: int, is_admin: bool = False) -> MediaFile:
    """
    Get a media file by ID and user ID.
    
    Args:
        db: Database session
        file_id: File ID
        user_id: User ID
        is_admin: Whether the current user is an admin (can access any file)
        
    Returns:
        MediaFile object
        
    Raises:
        HTTPException: If file not found
    """
    # Admin users can access any file, regular users only their own
    query = db.query(MediaFile).filter(MediaFile.id == file_id)
    if not is_admin:
        query = query.filter(MediaFile.user_id == user_id)
    
    db_file = query.first()
    
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found"
        )
    
    return db_file


def get_file_tags(db: Session, file_id: int) -> List[str]:
    """
    Get tags for a media file.
    
    Args:
        db: Database session
        file_id: File ID
        
    Returns:
        List of tag names
    """
    tags = []
    try:
        # Check if tag table exists first
        inspector = inspect(db.bind)
        if 'tag' in inspector.get_table_names() and 'file_tag' in inspector.get_table_names():
            tags = db.query(Tag.name).join(FileTag).filter(
                FileTag.media_file_id == file_id
            ).all()
        else:
            logger.warning("Tag tables don't exist yet, skipping tag retrieval")
    except Exception as tag_error:
        logger.error(f"Error getting tags: {tag_error}")
        db.rollback()  # Important to roll back the failed transaction
    
    return [tag[0] for tag in tags]


def get_file_collections(db: Session, file_id: int, user_id: int) -> List[dict]:
    """
    Get collections that contain a media file.
    
    Args:
        db: Database session
        file_id: File ID
        user_id: User ID
        
    Returns:
        List of collection dictionaries
    """
    collections = []
    try:
        # Check if collection tables exist first
        inspector = inspect(db.bind)
        if 'collection' in inspector.get_table_names() and 'collection_member' in inspector.get_table_names():
            collection_objs = db.query(Collection).join(CollectionMember).filter(
                CollectionMember.media_file_id == file_id,
                Collection.user_id == user_id
            ).all()
            
            # Convert to dictionaries
            collections = [
                {
                    "id": col.id,
                    "name": col.name,
                    "description": col.description,
                    "is_public": col.is_public,
                    "created_at": col.created_at.isoformat() if col.created_at else None,
                    "updated_at": col.updated_at.isoformat() if col.updated_at else None
                }
                for col in collection_objs
            ]
        else:
            logger.warning("Collection tables don't exist yet, skipping collection retrieval")
    except Exception as collection_error:
        logger.error(f"Error getting collections: {collection_error}")
        db.rollback()  # Important to roll back the failed transaction
    
    return collections


def set_file_urls(db_file: MediaFile) -> None:
    """
    Set download and preview URLs for a media file.
    
    Args:
        db_file: MediaFile object to update
    """
    if db_file.storage_path:
        logger.info(f"Setting up direct video URL for file {db_file.id}")
        
        # Simple video URL that doesn't require authentication
        video_url = f"/api/files/{db_file.id}/video"
        
        # Set both download_url and preview_url to our video URL
        db_file.download_url = video_url
        db_file.preview_url = video_url
        
        logger.info(f"Direct video URL set: {video_url}")
    else:
        logger.warning(f"Cannot generate video URL: no storage path available")
        db_file.download_url = None
        db_file.preview_url = None


def get_media_file_detail(db: Session, file_id: int, current_user: User) -> MediaFileDetail:
    """
    Get detailed media file information including tags.
    
    Args:
        db: Database session
        file_id: File ID
        current_user: Current user
        
    Returns:
        MediaFileDetail object
    """
    try:
        # Get the file by id and user id (admin can access any file)
        is_admin = current_user.role == "admin"
        db_file = get_media_file_by_id(db, file_id, current_user.id, is_admin=is_admin)
        
        # Get tags for this file
        tags = get_file_tags(db, file_id)
        
        # Get collections for this file
        collections = get_file_collections(db, file_id, current_user.id)
        
        # Set URLs
        set_file_urls(db_file)
        
        # Ensure changes are committed
        db.commit()
        
        # Prepare the response
        response = MediaFileDetail.model_validate(db_file)
        response.tags = tags
        response.collections = collections
        
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error in get_media_file_detail: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving media file: {str(e)}"
        )


def update_media_file(db: Session, file_id: int, media_file_update: MediaFileUpdate, 
                     current_user: User) -> MediaFile:
    """
    Update a media file's metadata.
    
    Args:
        db: Database session
        file_id: File ID
        media_file_update: Update data
        current_user: Current user
        
    Returns:
        Updated MediaFile object
    """
    is_admin = current_user.role == "admin"
    db_file = get_media_file_by_id(db, file_id, current_user.id, is_admin=is_admin)
    
    # Update fields
    for field, value in media_file_update.model_dump(exclude_unset=True).items():
        setattr(db_file, field, value)
    
    db.commit()
    db.refresh(db_file)
    
    return db_file


def delete_media_file(db: Session, file_id: int, current_user: User) -> None:
    """
    Delete a media file and all associated data.
    
    Args:
        db: Database session
        file_id: File ID
        current_user: Current user
    """
    is_admin = current_user.role == "admin"
    db_file = get_media_file_by_id(db, file_id, current_user.id, is_admin=is_admin)
    
    # Delete from MinIO (if exists)
    try:
        delete_file(db_file.storage_path)
    except Exception as e:
        logger.warning(f"Error deleting file from storage: {e}")
        # Continue with DB deletion even if storage deletion fails
    
    # Delete from database (cascade will handle related records)
    db.delete(db_file)
    db.commit()


def update_single_transcript_segment(db: Session, file_id: int, segment_id: int, 
                                   segment_update: TranscriptSegmentUpdate, current_user: User) -> TranscriptSegment:
    """
    Update a single transcript segment for a media file.
    
    Args:
        db: Database session
        file_id: File ID
        segment_id: Segment ID
        segment_update: Segment update data
        current_user: Current user
        
    Returns:
        Updated TranscriptSegment object
    """
    # Verify user owns the file or is admin
    is_admin = current_user.role == "admin"
    db_file = get_media_file_by_id(db, file_id, current_user.id, is_admin=is_admin)
    
    # Find the specific segment
    segment = db.query(TranscriptSegment).filter(
        TranscriptSegment.id == segment_id,
        TranscriptSegment.media_file_id == file_id
    ).first()
    
    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcript segment not found"
        )
    
    # Update fields
    for field, value in segment_update.model_dump(exclude_unset=True).items():
        setattr(segment, field, value)
    
    db.commit()
    db.refresh(segment)
    
    return segment


def get_stream_url_info(db: Session, file_id: int, current_user: User) -> dict:
    """
    Get streaming URL information for a media file.
    
    Args:
        db: Database session
        file_id: File ID
        current_user: Current user
        
    Returns:
        Dictionary with URL and content type information
    """
    is_admin = current_user.role == "admin"
    db_file = get_media_file_by_id(db, file_id, current_user.id, is_admin=is_admin)
    
    # Skip S3 operations in test environment
    if os.environ.get('SKIP_S3', 'False').lower() == 'true':
        logger.info("Returning mock URL in test environment")
        return {"url": f"/api/files/{file_id}/content", "content_type": db_file.content_type}
    
    # Return the URL to our video endpoint
    return {
        "url": f"/api/files/{file_id}/video",  # Video endpoint
        "content_type": db_file.content_type,
        "requires_auth": False  # No auth required for video endpoint
    }