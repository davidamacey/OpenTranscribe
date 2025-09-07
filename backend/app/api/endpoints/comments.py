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

router = APIRouter()


@router.get("/files/{file_id}/comments", response_model=list[CommentSchema])
def get_comments_for_file_nested(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get all comments for a specific media file (nested route)"""
    # Verify file exists and belongs to user
    media_file = (
        db.query(MediaFile)
        .filter(MediaFile.id == file_id, MediaFile.user_id == current_user.id)
        .first()
    )

    if not media_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found"
        )

    # Get comments for this file
    comments = db.query(Comment).filter(Comment.media_file_id == file_id).all()
    return comments


@router.post("/files/{file_id}/comments", response_model=CommentSchema)
def create_comment_for_file_nested(
    file_id: int,
    comment: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a comment for a specific media file (nested route)"""
    # Verify file exists and belongs to user
    media_file = (
        db.query(MediaFile)
        .filter(MediaFile.id == file_id, MediaFile.user_id == current_user.id)
        .first()
    )

    if not media_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found"
        )

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

    return db_comment


@router.get("/", response_model=list[CommentSchema])
def get_comments_for_file(
    media_file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    List all comments for a media file using query parameter
    This is an alternative to the /files/{file_id}/comments endpoint
    """
    # Verify file exists and belongs to user
    media_file = (
        db.query(MediaFile)
        .filter(MediaFile.id == media_file_id, MediaFile.user_id == current_user.id)
        .first()
    )

    if not media_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found"
        )

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
    This is an alternative to the /files/{file_id}/comments endpoint
    """
    file_id = comment.media_file_id

    # Verify file exists and belongs to user
    media_file = (
        db.query(MediaFile)
        .filter(MediaFile.id == file_id, MediaFile.user_id == current_user.id)
        .first()
    )

    if not media_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found"
        )

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

    return db_comment


@router.get("/{comment_id}", response_model=CommentSchema)
def get_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get a single comment by ID
    """
    # Get comment and verify ownership
    comment = (
        db.query(Comment)
        .join(MediaFile)
        .filter(Comment.id == comment_id, MediaFile.user_id == current_user.id)
        .first()
    )

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found or you do not have permission to view it",
        )

    return comment


@router.put("/{comment_id}", response_model=CommentSchema)
def update_comment(
    comment_id: int,
    comment_update: CommentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Update a comment
    """
    # Get comment and verify ownership
    comment = (
        db.query(Comment)
        .filter(Comment.id == comment_id, Comment.user_id == current_user.id)
        .first()
    )

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found or you do not have permission to edit it",
        )

    # Update fields
    for field, value in comment_update.model_dump(exclude_unset=True).items():
        setattr(comment, field, value)

    db.commit()
    db.refresh(comment)

    # Create a comment schema with user information properly formatted as a dictionary
    # This fixes the ResponseValidationError about user not being a valid dictionary
    result = CommentSchema(
        id=comment.id,
        media_file_id=comment.media_file_id,
        user_id=comment.user_id,
        text=comment.text,
        timestamp=comment.timestamp,
        created_at=comment.created_at,
        user={
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
        },
    )

    return result


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Delete a comment
    """
    # Get comment and verify ownership
    comment = (
        db.query(Comment)
        .filter(Comment.id == comment_id, Comment.user_id == current_user.id)
        .first()
    )

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found or you do not have permission to delete it",
        )

    # Delete the comment
    db.delete(comment)
    db.commit()

    return None
