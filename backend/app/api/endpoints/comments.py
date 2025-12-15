from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.models.media import Comment
from app.models.media import MediaFile
from app.models.user import User
from app.schemas.media import Comment as CommentSchema
from app.schemas.media import CommentCreate
from app.schemas.media import CommentUpdate
from app.utils.uuid_helpers import get_comment_by_uuid
from app.utils.uuid_helpers import get_file_by_uuid_with_permission

router = APIRouter()


@router.get("/files/{file_uuid}/comments", response_model=list[CommentSchema])
def get_comments_for_file_nested(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get all comments for a specific media file (nested route)"""
    from sqlalchemy.orm import joinedload

    # Verify file exists and belongs to user
    media_file = get_file_by_uuid_with_permission(db, file_uuid, current_user.id)
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
    """Create a comment for a specific media file (nested route)"""
    # Verify file exists and belongs to user
    media_file = get_file_by_uuid_with_permission(db, file_uuid, current_user.id)
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
    from sqlalchemy.orm import joinedload

    db_comment = (
        db.query(Comment)
        .options(joinedload(Comment.user), joinedload(Comment.media_file))
        .filter(Comment.id == db_comment.id)
        .first()
    )

    return CommentSchema.model_validate(db_comment)


@router.get("/", response_model=list[CommentSchema])
def get_comments_for_file(
    media_file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    List all comments for a media file using query parameter
    This is an alternative to the /files/{file_uuid}/comments endpoint
    """
    # Verify file exists and belongs to user
    media_file = get_file_by_uuid_with_permission(db, media_file_uuid, current_user.id)
    media_file_id = media_file.id

    # Get comments for this file
    comments = (
        db.query(Comment)
        .filter(Comment.media_file_id == media_file_id)
        .order_by(Comment.timestamp)
        .all()
    )

    return comments


@router.post("/", response_model=CommentSchema)
def create_comment_query_param(
    comment: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Add a comment to a media file using query parameter
    This is an alternative to the /files/{file_uuid}/comments endpoint
    """
    # Assume media_file_id in CommentCreate is now a UUID
    media_file = get_file_by_uuid_with_permission(db, comment.media_file_id, current_user.id)
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
    from sqlalchemy.orm import joinedload

    db_comment = (
        db.query(Comment)
        .options(joinedload(Comment.user), joinedload(Comment.media_file))
        .filter(Comment.id == db_comment.id)
        .first()
    )

    return CommentSchema.model_validate(db_comment)


@router.get("/{comment_uuid}", response_model=CommentSchema)
def get_comment(
    comment_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get a single comment by UUID
    """
    # Get comment and verify ownership through media file
    comment = get_comment_by_uuid(db, comment_uuid)

    # Verify the comment's media file belongs to the user
    media_file = db.query(MediaFile).filter(MediaFile.id == comment.media_file_id).first()
    if not media_file or media_file.user_id != current_user.id:
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
    """
    Update a comment
    """
    from sqlalchemy.orm import joinedload

    # Get comment with eager-loaded relationships and verify ownership
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
    comment = (
        db.query(Comment)
        .options(joinedload(Comment.user), joinedload(Comment.media_file))
        .filter(Comment.id == comment.id)
        .first()
    )

    # Use model_validate to handle UUID conversion automatically
    return CommentSchema.model_validate(comment)


@router.delete("/{comment_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Delete a comment
    """
    # Get comment and verify ownership
    comment = get_comment_by_uuid(db, comment_uuid)

    if comment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this comment",
        )

    # Delete the comment
    db.delete(comment)
    db.commit()

    return None
