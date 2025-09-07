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

    Args:
        db_session: SQLAlchemy database session
        file_hash: Hash of the file to check (with or without 0x prefix)
        user_id: Optional user ID to restrict the search to a specific user

    Returns:
        The ID of the duplicate file if found, None otherwise
    """
    from app.models.media import MediaFile

    # Strip 0x prefix if present to maintain compatibility with database
    if file_hash and file_hash.startswith("0x"):
        file_hash = file_hash[2:]

    query = db_session.query(MediaFile).filter(MediaFile.file_hash == file_hash)

    if user_id is not None:
        query = query.filter(MediaFile.user_id == user_id)

    duplicate = query.first()

    if duplicate:
        return duplicate.id

    return None
