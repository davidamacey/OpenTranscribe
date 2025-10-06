import logging
from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_user
from app.api.endpoints.files.upload import create_media_file_record
from app.db.base import get_db
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

    def __init__(self, filename, content_type, extracted_from_video=None):
        self.filename = filename
        self.content_type = content_type
        self.file_hash = None
        self.extracted_from_video = extracted_from_video


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
        duplicate_id: Optional[int] = None
        if request.file_hash:
            # First clean up any failed files with the same hash to allow re-upload
            await cleanup_failed_duplicates(db, request.file_hash, current_user.id)

            duplicate_id = await check_duplicate_by_hash(db, request.file_hash, current_user.id)

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
        db_file = create_media_file_record(db, file_metadata, current_user, request.file_size)

        # If this is extracted audio, store the video metadata in metadata_important
        if request.extracted_from_video:
            db_file.metadata_important = request.extracted_from_video
            db.commit()
            logger.info(f"Stored extracted video metadata for {request.filename}")

        logger.info(f"Prepared upload for file {request.filename} (ID: {db_file.id})")

        # Return the file UUID for frontend
        return {"file_id": str(db_file.uuid), "is_duplicate": 0}

    except Exception as e:
        logger.error(f"Error preparing upload: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error preparing upload: {str(e)}",
        ) from e
