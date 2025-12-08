"""
UUID Helper Utilities for Hybrid ID System

This module provides utilities for the hybrid ID approach:
- Internal: Fast integer IDs for database operations
- External: Secure UUIDs for API exposure

Performance Notes:
- UUID lookups use indexed columns for fast resolution
- Integer IDs used for all internal joins and foreign keys
- UUIDs only exposed in API layer (Pydantic schemas)
"""

from typing import Optional
from typing import TypeVar
from uuid import UUID

from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session

from app.models.media import Collection
from app.models.media import Comment
from app.models.media import MediaFile
from app.models.media import Speaker
from app.models.media import SpeakerProfile
from app.models.prompt import SummaryPrompt
from app.models.user import User
from app.models.user_llm_settings import UserLLMSettings

T = TypeVar("T")


def get_by_uuid(
    db: Session,
    model: type[T],
    uuid: UUID | str,
    error_message: Optional[str] = None,
) -> T:
    """
    Get a database record by UUID.

    Args:
        db: Database session
        model: SQLAlchemy model class
        uuid: UUID to look up (UUID object or string)
        error_message: Custom error message for 404

    Returns:
        Model instance

    Raises:
        HTTPException: 404 if not found
    """
    # Convert string to UUID if needed
    if isinstance(uuid, str):
        try:
            uuid = UUID(uuid)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid UUID format: {uuid}",
            ) from None

    # Query by UUID
    instance = db.query(model).filter(model.uuid == uuid).first()

    if not instance:
        model_name = model.__name__
        message = error_message or f"{model_name} not found"
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=message,
        )

    return instance


def get_by_uuid_optional(
    db: Session,
    model: type[T],
    uuid: UUID | str | None,
) -> Optional[T]:
    """
    Get a database record by UUID, returning None if not found.

    Args:
        db: Database session
        model: SQLAlchemy model class
        uuid: UUID to look up (UUID object, string, or None)

    Returns:
        Model instance or None
    """
    if uuid is None:
        return None

    # Convert string to UUID if needed
    if isinstance(uuid, str):
        try:
            uuid = UUID(uuid)
        except ValueError:
            return None

    return db.query(model).filter(model.uuid == uuid).first()


def uuid_to_id(db: Session, model: type[T], uuid: UUID | str) -> int:
    """
    Convert UUID to internal integer ID.

    Useful for constructing queries with foreign keys.

    Args:
        db: Database session
        model: SQLAlchemy model class
        uuid: UUID to look up

    Returns:
        Integer ID

    Raises:
        HTTPException: 404 if not found
    """
    instance = get_by_uuid(db, model, uuid)
    return instance.id


def validate_uuids(uuids: list[str]) -> list[UUID]:
    """
    Validate and convert list of UUID strings.

    Args:
        uuids: List of UUID strings

    Returns:
        List of UUID objects

    Raises:
        HTTPException: 400 if any UUID is invalid
    """
    result = []
    for uuid_item in uuids:
        try:
            # Handle both UUID objects and strings
            if isinstance(uuid_item, UUID):
                result.append(uuid_item)
            else:
                result.append(UUID(uuid_item))
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid UUID format: {uuid_item}",
            ) from None
    return result


# Convenience functions for common models
def get_user_by_uuid(db: Session, uuid: UUID | str) -> User:
    """Get user by UUID"""
    return get_by_uuid(db, User, uuid, error_message="User not found")


def get_file_by_uuid(db: Session, uuid: UUID | str) -> MediaFile:
    """Get media file by UUID"""
    return get_by_uuid(db, MediaFile, uuid, error_message="File not found")


def get_speaker_by_uuid(db: Session, uuid: UUID | str) -> Speaker:
    """Get speaker by UUID"""
    return get_by_uuid(db, Speaker, uuid, error_message="Speaker not found")


def get_speaker_profile_by_uuid(db: Session, uuid: UUID | str) -> SpeakerProfile:
    """Get speaker profile by UUID"""
    return get_by_uuid(db, SpeakerProfile, uuid, error_message="Speaker profile not found")


def get_collection_by_uuid(db: Session, uuid: UUID | str) -> Collection:
    """Get collection by UUID"""
    return get_by_uuid(db, Collection, uuid, error_message="Collection not found")


def get_comment_by_uuid(db: Session, uuid: UUID | str) -> Comment:
    """Get comment by UUID"""
    return get_by_uuid(db, Comment, uuid, error_message="Comment not found")


def get_prompt_by_uuid(db: Session, uuid: UUID | str) -> SummaryPrompt:
    """Get summary prompt by UUID"""
    return get_by_uuid(db, SummaryPrompt, uuid, error_message="Prompt not found")


def get_llm_config_by_uuid(db: Session, uuid: UUID | str) -> UserLLMSettings:
    """Get LLM configuration by UUID"""
    return get_by_uuid(db, UserLLMSettings, uuid, error_message="LLM configuration not found")


# Permission checking helpers
def get_file_by_uuid_with_permission(
    db: Session, uuid: UUID | str, user_id: int, allow_public: bool = False
) -> MediaFile:
    """
    Get media file by UUID with permission check.

    Args:
        db: Database session
        uuid: File UUID
        user_id: Current user ID
        allow_public: Whether to allow public files

    Returns:
        MediaFile instance

    Raises:
        HTTPException: 404 if not found, 403 if no permission
    """
    file = get_file_by_uuid(db, uuid)

    # Check permissions
    if file.user_id != user_id and not (allow_public and file.is_public):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this file",
        )

    return file


def get_collection_by_uuid_with_permission(
    db: Session, uuid: UUID | str, user_id: int
) -> Collection:
    """
    Get collection by UUID with permission check.

    Args:
        db: Database session
        uuid: Collection UUID
        user_id: Current user ID

    Returns:
        Collection instance

    Raises:
        HTTPException: 404 if not found, 403 if no permission
    """
    collection = get_collection_by_uuid(db, uuid)

    if collection.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this collection",
        )

    return collection
