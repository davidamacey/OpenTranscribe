import logging
import os

from fastapi import HTTPException
from fastapi import status
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models.media import Collection
from app.models.media import CollectionMember
from app.models.media import FileTag
from app.models.media import MediaFile
from app.models.media import Tag
from app.models.media import TranscriptSegment
from app.models.user import User
from app.schemas.media import MediaFileDetail
from app.schemas.media import MediaFileUpdate
from app.schemas.media import TranscriptSegmentUpdate
from app.services.minio_service import delete_file

logger = logging.getLogger(__name__)


def get_media_file_by_id(
    db: Session, file_id: int, user_id: int, is_admin: bool = False
) -> MediaFile:
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
            status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found"
        )

    return db_file


def get_file_tags(db: Session, file_id: int) -> list[str]:
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
        if (
            "tag" in inspector.get_table_names()
            and "file_tag" in inspector.get_table_names()
        ):
            tags = (
                db.query(Tag.name)
                .join(FileTag)
                .filter(FileTag.media_file_id == file_id)
                .all()
            )
        else:
            logger.warning("Tag tables don't exist yet, skipping tag retrieval")
    except Exception as tag_error:
        logger.error(f"Error getting tags: {tag_error}")
        db.rollback()  # Important to roll back the failed transaction

    return [tag[0] for tag in tags]


def get_file_collections(db: Session, file_id: int, user_id: int) -> list[dict]:
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
        if (
            "collection" in inspector.get_table_names()
            and "collection_member" in inspector.get_table_names()
        ):
            collection_objs = (
                db.query(Collection)
                .join(CollectionMember)
                .filter(
                    CollectionMember.media_file_id == file_id,
                    Collection.user_id == user_id,
                )
                .all()
            )

            # Convert to dictionaries
            collections = [
                {
                    "id": col.id,
                    "name": col.name,
                    "description": col.description,
                    "is_public": col.is_public,
                    "created_at": col.created_at.isoformat()
                    if col.created_at
                    else None,
                    "updated_at": col.updated_at.isoformat()
                    if col.updated_at
                    else None,
                }
                for col in collection_objs
            ]
        else:
            logger.warning(
                "Collection tables don't exist yet, skipping collection retrieval"
            )
    except Exception as collection_error:
        logger.error(f"Error getting collections: {collection_error}")
        db.rollback()  # Important to roll back the failed transaction

    return collections


def set_file_urls(db_file: MediaFile) -> None:
    """
    Set download, preview, and thumbnail URLs for a media file.

    Args:
        db_file: MediaFile object to update
    """
    if db_file.storage_path:
        # Skip S3 operations in test environment
        if os.environ.get("SKIP_S3", "False").lower() == "true":
            db_file.download_url = f"/api/files/{db_file.id}/download"
            db_file.preview_url = f"/api/files/{db_file.id}/video"
            if db_file.thumbnail_path:
                db_file.thumbnail_url = f"/api/files/{db_file.id}/thumbnail"
            return

        # Set URLs for frontend to use
        db_file.download_url = f"/api/files/{db_file.id}/download"  # Download endpoint

        # Video files use our video endpoint for optimized streaming
        if db_file.content_type.startswith("video/"):
            db_file.preview_url = f"/api/files/{db_file.id}/video"
        else:
            # Audio files can use the download endpoint
            db_file.preview_url = f"/api/files/{db_file.id}/download"

        # Set thumbnail URL if thumbnail exists
        if db_file.thumbnail_path:
            db_file.thumbnail_url = f"/api/files/{db_file.id}/thumbnail"


def get_media_file_detail(
    db: Session, file_id: int, current_user: User
) -> MediaFileDetail:
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
            detail=f"Error retrieving media file: {str(e)}",
        )


def update_media_file(
    db: Session, file_id: int, media_file_update: MediaFileUpdate, current_user: User
) -> MediaFile:
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


def delete_media_file(
    db: Session, file_id: int, current_user: User, force: bool = False
) -> None:
    """
    Delete a media file and all associated data with safety checks.

    Args:
        db: Database session
        file_id: File ID
        current_user: Current user
        force: Force deletion even if processing is active (admin only)
    """
    from app.utils.task_utils import cancel_active_task
    from app.utils.task_utils import is_file_safe_to_delete

    is_admin = current_user.role == "admin"
    db_file = get_media_file_by_id(db, file_id, current_user.id, is_admin=is_admin)

    # Check if file is safe to delete
    is_safe, reason = is_file_safe_to_delete(db, file_id)

    if not is_safe and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "FILE_NOT_SAFE_TO_DELETE",
                "message": f"Cannot delete file: {reason}",
                "file_id": file_id,
                "active_task_id": db_file.active_task_id,
                "status": db_file.status,
                "options": {
                    "cancel_and_delete": is_admin,
                    "wait_for_completion": True,
                    "force_delete": is_admin and db_file.force_delete_eligible,
                },
            },
        )

    # If force deletion and file has active task, cancel it first
    if force and db_file.active_task_id:
        logger.info(
            f"Force deleting file {file_id}, cancelling active task {db_file.active_task_id}"
        )
        cancel_active_task(db, file_id)
        # Refresh the file object
        db.refresh(db_file)

    # Delete from MinIO (if exists)
    storage_deleted = False
    try:
        delete_file(db_file.storage_path)
        storage_deleted = True
        logger.info(f"Successfully deleted file from storage: {db_file.storage_path}")
    except Exception as e:
        logger.warning(f"Error deleting file from storage: {e}")
        # Don't fail the entire operation if storage deletion fails

    try:
        # Delete from database (cascade will handle related records)
        db.delete(db_file)
        db.commit()
        logger.info(f"Successfully deleted file {file_id} from database")
    except Exception as e:
        logger.error(f"Failed to delete file {file_id} from database: {e}")
        db.rollback()

        # If we deleted from storage but DB deletion failed, that's a problem
        if storage_deleted:
            logger.error(
                f"File {file_id} deleted from storage but not from database - orphaned!"
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file from database: {str(e)}",
        )


def update_single_transcript_segment(
    db: Session,
    file_id: int,
    segment_id: int,
    segment_update: TranscriptSegmentUpdate,
    current_user: User,
) -> TranscriptSegment:
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
    get_media_file_by_id(db, file_id, current_user.id, is_admin=is_admin)

    # Find the specific segment
    segment = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.id == segment_id,
            TranscriptSegment.media_file_id == file_id,
        )
        .first()
    )

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transcript segment not found"
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
    if os.environ.get("SKIP_S3", "False").lower() == "true":
        logger.info("Returning mock URL in test environment")
        return {
            "url": f"/api/files/{file_id}/content",
            "content_type": db_file.content_type,
        }

    # Return the URL to our video endpoint
    return {
        "url": f"/api/files/{file_id}/video",  # Video endpoint
        "content_type": db_file.content_type,
        "requires_auth": False,  # No auth required for video endpoint
    }
