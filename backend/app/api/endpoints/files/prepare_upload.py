import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_user
from app.api.endpoints.files.upload import create_media_file_record
from app.db.base import get_db
from app.models.media import Collection
from app.models.media import CollectionMember
from app.models.media import FileTag
from app.models.media import Tag
from app.models.user import User
from app.schemas.media import PrepareUploadRequest
from app.utils.file_hash import check_duplicate_by_hash
from app.utils.file_hash import cleanup_failed_duplicates

logger = logging.getLogger(__name__)

router = APIRouter()


class FileMetadata:
    """Lightweight class containing essential file information without the actual file content.
    Used for creating database records before the actual file upload starts.

    Attributes:
        filename: Name of the file to be uploaded
        content_type: MIME type of the file
        file_hash: Hash of the file for duplicate detection
        extracted_from_video: Optional metadata from original video if audio was extracted client-side
    """

    def __init__(
        self,
        filename: str,
        content_type: str,
        extracted_from_video: dict[str, Any] | None = None,
    ):
        self.filename = filename
        self.content_type = content_type
        self.file_hash: str | None = None
        self.extracted_from_video = extracted_from_video


def add_file_to_collections(
    db: Session, file_id: int, user_id: int, collection_ids: list[UUID]
) -> None:
    """Add a media file to the specified collections owned by the user.

    Silently skips collections that don't exist or aren't owned by the user.
    """
    for coll_uuid in collection_ids:
        collection = (
            db.query(Collection)
            .filter(Collection.uuid == str(coll_uuid), Collection.user_id == user_id)
            .first()
        )
        if not collection:
            logger.warning(f"Collection {coll_uuid} not found for user {user_id}, skipping")
            continue

        existing = (
            db.query(CollectionMember)
            .filter(
                CollectionMember.collection_id == collection.id,
                CollectionMember.media_file_id == file_id,
            )
            .first()
        )
        if not existing:
            db.add(CollectionMember(collection_id=collection.id, media_file_id=file_id))

    db.flush()


def add_tags_to_file(db: Session, file_id: int, tag_names: list[str]) -> None:
    """Add tags to a media file, creating tags if they don't exist.

    Uses atomic get-or-create pattern for race-condition safety.
    """
    for name in tag_names:
        name = name.strip()[:50]
        if not name:
            continue

        tag = db.query(Tag).filter(Tag.name == name).first()
        if not tag:
            try:
                tag = Tag(name=name)
                db.add(tag)
                db.flush()
            except IntegrityError:
                db.rollback()
                tag = db.query(Tag).filter(Tag.name == name).first()
                if not tag:
                    continue

        existing = (
            db.query(FileTag)
            .filter(FileTag.media_file_id == file_id, FileTag.tag_id == tag.id)
            .first()
        )
        if not existing:
            db.add(FileTag(media_file_id=file_id, tag_id=tag.id))

    db.flush()


@router.post("/prepare", response_model=dict[str, str | int])
async def prepare_upload(
    request: PrepareUploadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Prepare for a file upload by creating a MediaFile record and returning the file ID.
    This allows the frontend to track the file ID before the actual upload begins.

    If a file hash is provided, check if a duplicate file already exists.
    """
    try:
        # If file hash is provided, check for duplicates
        duplicate_id: str | None = None
        if request.file_hash:
            # First clean up any failed files with the same hash to allow re-upload
            await cleanup_failed_duplicates(db, request.file_hash, int(current_user.id))

            duplicate_id = await check_duplicate_by_hash(
                db, request.file_hash, int(current_user.id)
            )

            if duplicate_id:
                logger.info(
                    f"Duplicate file found for {request.filename} (Duplicate ID: {duplicate_id})"
                )
                return {"file_id": duplicate_id, "is_duplicate": 1}

        # Create file metadata object with information needed for the record
        file_metadata = FileMetadata(
            request.filename,
            request.content_type,
            extracted_from_video=request.extracted_from_video,
        )
        file_metadata.file_hash = request.file_hash

        # Create the database record
        db_file = create_media_file_record(db, file_metadata, current_user, request.file_size)  # type: ignore[arg-type]

        # If this is extracted audio, store the video metadata in metadata_important
        if request.extracted_from_video:
            db_file.metadata_important = request.extracted_from_video  # type: ignore[assignment]
            db.commit()
            logger.info(f"Stored extracted video metadata for {request.filename}")

        # Assign to collections if specified
        if request.collection_ids:
            add_file_to_collections(
                db, int(db_file.id), int(current_user.id), request.collection_ids
            )

        # Apply tags if specified
        if request.tag_names:
            add_tags_to_file(db, int(db_file.id), request.tag_names)

        # Commit collection and tag assignments
        if request.collection_ids or request.tag_names:
            db.commit()

        logger.info(f"Prepared upload for file {request.filename} (ID: {db_file.id})")

        # Return the file UUID for frontend
        return {"file_id": str(db_file.uuid), "is_duplicate": 0}

    except Exception as e:
        logger.error(f"Error preparing upload: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error preparing upload: {str(e)}",
        ) from e
