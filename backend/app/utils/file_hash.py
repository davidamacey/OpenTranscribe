"""
Utility module for file duplicate detection

This module provides functions for checking if files with the same hash
already exist in the database.

The primary hash calculation happens client-side (frontend) for efficiency.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Hashing is now done client-side in the frontend


async def check_duplicate_by_hash(
    db_session, file_hash: str, user_id: Optional[int] = None
) -> Optional[int]:
    """
    Check if a file with the same hash exists in the database.
    Only considers files that are not in ERROR, CANCELLED, or ORPHANED status.

    Args:
        db_session: SQLAlchemy database session
        file_hash: Hash of the file to check (with or without 0x prefix)
        user_id: Optional user ID to restrict the search to a specific user

    Returns:
        The ID of the duplicate file if found, None otherwise
    """
    from app.models.media import FileStatus
    from app.models.media import MediaFile

    # Strip 0x prefix if present to maintain compatibility with database
    if file_hash and file_hash.startswith("0x"):
        file_hash = file_hash[2:]

    query = db_session.query(MediaFile).filter(MediaFile.file_hash == file_hash)

    if user_id is not None:
        query = query.filter(MediaFile.user_id == user_id)

    # Only consider files that are not in failed/error states
    # This prevents failed uploads from blocking re-uploads of the same file
    query = query.filter(
        MediaFile.status.notin_([FileStatus.ERROR, FileStatus.CANCELLED, FileStatus.ORPHANED])
    )

    duplicate = query.first()

    if duplicate:
        return duplicate.id

    return None


async def cleanup_failed_duplicates(db_session, file_hash: str, user_id: int) -> int:
    """
    Clean up any failed (ERROR, CANCELLED, ORPHANED) files with the same hash.
    This allows users to re-upload files that previously failed.

    Args:
        db_session: SQLAlchemy database session
        file_hash: Hash of the file to clean up
        user_id: User ID to restrict cleanup to specific user

    Returns:
        Number of files cleaned up
    """
    from app.models.media import FileStatus
    from app.models.media import MediaFile
    from app.services.minio_service import delete_file

    # Strip 0x prefix if present
    if file_hash and file_hash.startswith("0x"):
        file_hash = file_hash[2:]

    # Find failed files with the same hash for this user
    failed_files = (
        db_session.query(MediaFile)
        .filter(
            MediaFile.file_hash == file_hash,
            MediaFile.user_id == user_id,
            MediaFile.status.in_([FileStatus.ERROR, FileStatus.CANCELLED, FileStatus.ORPHANED]),
        )
        .all()
    )

    cleanup_count = 0
    for file in failed_files:
        try:
            # Delete from storage if exists
            if file.storage_path:
                try:
                    delete_file(file.storage_path)
                    logger.info(f"Cleaned up failed file storage: {file.storage_path}")
                except Exception as e:
                    logger.warning(f"Could not delete storage for failed file {file.id}: {e}")

            # Delete from database (cascade will handle related records)
            db_session.delete(file)
            cleanup_count += 1
            logger.info(f"Cleaned up failed duplicate file {file.id} ({file.filename})")

        except Exception as e:
            logger.error(f"Error cleaning up failed file {file.id}: {e}")
            # Continue with other files even if one fails

    if cleanup_count > 0:
        db_session.commit()
        logger.info(f"Cleaned up {cleanup_count} failed duplicate files with hash {file_hash}")

    return cleanup_count
