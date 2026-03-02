"""API endpoints for media file comments with sharing-aware permissions."""

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.models.media import Comment
from app.models.media import MediaFile
from app.models.user import User
from app.schemas.media import Comment as CommentSchema
from app.schemas.media import CommentCreate
from app.schemas.media import CommentUpdate
from app.services.permission_service import PermissionService
from app.utils.uuid_helpers import get_comment_by_uuid
from app.utils.uuid_helpers import get_file_by_uuid_with_permission

router = APIRouter()


def _check_file_access(db: Session, file_uuid: str, user_id: int) -> MediaFile:
    """Get a media file after verifying the user has at least viewer permission.

    Uses PermissionService to check ownership, direct shares, and group shares.
    """
    media_file = get_file_by_uuid_with_permission(db, file_uuid, user_id)
    return media_file


@router.get("/files/{file_uuid}/comments", response_model=list[CommentSchema])
def get_comments_for_file_nested(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get all comments for a specific media file (nested route).

    Requires viewer+ permission on the file (via ownership or sharing).
    """
    media_file = _check_file_access(db, file_uuid, int(current_user.id))
    file_id = media_file.id

    # Get comments for this file with user relationship loaded
    comments = (
        db.query(Comment)
        .options(joinedload(Comment.user), joinedload(Comment.media_file))
        .filter(Comment.media_file_id == file_id)
        .all()
    )
    return comments


@router.post("/files/{file_uuid}/comments", response_model=CommentSchema)
def create_comment_for_file_nested(
    file_uuid: str,
    comment: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a comment for a specific media file (nested route).

    Requires viewer+ permission on the file (commenting is collaborative).
    """
    media_file = _check_file_access(db, file_uuid, int(current_user.id))
    file_id = media_file.id

    # Create comment with file_id from URL
    db_comment = Comment(
        text=comment.text,
        timestamp=comment.timestamp,
        media_file_id=file_id,
        user_id=current_user.id,
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)

    # Reload with relationships for UUID mapping
    db_comment_reloaded = (
        db.query(Comment)
        .options(joinedload(Comment.user), joinedload(Comment.media_file))
        .filter(Comment.id == db_comment.id)
        .first()
    )

    return CommentSchema.model_validate(db_comment_reloaded)


@router.get("", response_model=list[CommentSchema])
def get_comments_for_file(
    media_file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all comments for a media file using query parameter.

    Requires viewer+ permission on the file.
    """
    media_file = _check_file_access(db, media_file_uuid, int(current_user.id))
    media_file_id = media_file.id

    # Get comments for this file (eager-load relationships to avoid N+1)
    comments = (
        db.query(Comment)
        .options(joinedload(Comment.user), joinedload(Comment.media_file))
        .filter(Comment.media_file_id == media_file_id)
        .order_by(Comment.timestamp)
        .all()
    )

    return comments


@router.post("", response_model=CommentSchema)
def create_comment_query_param(
    comment: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Add a comment to a media file using query parameter.

    Requires viewer+ permission on the file.
    """
    media_file = _check_file_access(db, comment.media_file_id, int(current_user.id))  # type: ignore[attr-defined]
    file_id = media_file.id

    # Create new comment
    db_comment = Comment(
        media_file_id=file_id,
        user_id=current_user.id,  # Always use the authenticated user's ID
        text=comment.text,
        timestamp=comment.timestamp,
    )

    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)

    # Reload with relationships for UUID mapping
    db_comment_reloaded = (
        db.query(Comment)
        .options(joinedload(Comment.user), joinedload(Comment.media_file))
        .filter(Comment.id == db_comment.id)
        .first()
    )

    return CommentSchema.model_validate(db_comment_reloaded)


@router.get("/{comment_uuid}", response_model=CommentSchema)
def get_comment(
    comment_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a single comment by UUID.

    Requires viewer+ permission on the comment's file.
    """
    comment = get_comment_by_uuid(db, comment_uuid)

    # Verify the user has access to the comment's file via PermissionService
    permission = PermissionService.get_file_permission(
        db, int(comment.media_file_id), int(current_user.id)
    )
    if permission is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this comment",
        )

    return comment


@router.put("/{comment_uuid}", response_model=CommentSchema)
def update_comment(
    comment_uuid: str,
    comment_update: CommentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a comment. Only the comment author can edit."""
    comment = get_comment_by_uuid(db, comment_uuid)

    if comment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to edit this comment",
        )

    # Update fields
    for field, value in comment_update.model_dump(exclude_unset=True).items():
        setattr(comment, field, value)

    db.commit()

    # Reload with relationships for UUID mapping
    db.refresh(comment)
    comment_reloaded = (
        db.query(Comment)
        .options(joinedload(Comment.user), joinedload(Comment.media_file))
        .filter(Comment.id == comment.id)
        .first()
    )

    # Use model_validate to handle UUID conversion automatically
    return CommentSchema.model_validate(comment_reloaded)


@router.delete("/{comment_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Delete a comment. Comment author or file owner can delete."""
    comment = get_comment_by_uuid(db, comment_uuid)

    # Allow deletion by comment author
    if comment.user_id == current_user.id:
        db.delete(comment)
        db.commit()
        return None

    # Allow deletion by file owner
    media_file = db.query(MediaFile).filter(MediaFile.id == comment.media_file_id).first()
    if media_file and media_file.user_id == current_user.id:
        db.delete(comment)
        db.commit()
        return None

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to delete this comment",
    )
