"""
Summary retry utilities for OpenTranscribe

This module provides functionality to retry failed AI summaries,
similar to the transcription retry mechanism in task_utils.py
"""

import asyncio
import logging

from sqlalchemy.orm import Session

from app.db.session_utils import session_scope
from app.models.media import MediaFile
from app.services.llm_service import is_llm_available
from app.tasks.summarization import summarize_transcript_task

logger = logging.getLogger(__name__)


def reset_summary_for_retry(db: Session, file_uuid: str) -> bool:
    """
    Reset a file's summary for retry processing, similar to reset_file_for_retry for transcription.

    Args:
        db: Database session
        file_uuid: UUID of the file to reset summary for

    Returns:
        True if reset was successful, False otherwise
    """
    from app.utils.uuid_helpers import get_file_by_uuid

    media_file = get_file_by_uuid(db, file_uuid)
    if not media_file:
        logger.error(f"File {file_uuid} not found")
        return False

    file_id = media_file.id  # Get internal ID for logging

    # Only retry if transcription is completed
    if media_file.status != "completed":
        logger.error(
            f"Cannot retry summary for file {file_id} - transcription not completed (status: {media_file.status})"
        )
        return False

    try:
        # Reset summary fields
        media_file.summary_data = None  # type: ignore[assignment]
        media_file.summary_opensearch_id = None  # type: ignore[assignment]
        media_file.summary_status = "pending"  # type: ignore[assignment]

        db.commit()
        logger.info(f"Reset summary status for file {file_id}")
        return True

    except Exception as e:
        logger.error(f"Error resetting summary for file {file_id}: {e}")
        db.rollback()
        return False


async def check_llm_availability() -> bool:
    """
    Check if LLM service is available for summary generation

    Returns:
        True if LLM is available, False otherwise
    """
    try:
        return await is_llm_available()
    except Exception as e:
        logger.debug(f"Error checking LLM availability: {e}")
        return False


def retry_summary_if_available(db: Session, file_uuid: str) -> bool:
    """
    Retry summary generation for a specific file if LLM is available

    Args:
        db: Database session
        file_uuid: UUID of the file to retry

    Returns:
        True if retry was queued successfully, False otherwise
    """
    from app.utils.uuid_helpers import get_file_by_uuid

    # Check if LLM is available
    llm_available = asyncio.run(check_llm_availability())

    # Get internal ID for logging
    media_file = get_file_by_uuid(db, file_uuid)
    if not media_file:
        logger.debug(f"File {file_uuid} not found for retry")
        return False
    file_id = media_file.id

    if not llm_available:
        logger.debug(f"LLM not available for retry of file {file_id}")
        return False

    # Reset summary status and clear existing data
    if not reset_summary_for_retry(db, file_uuid):
        return False

    try:
        # Queue summarization task
        summarize_transcript_task.delay(file_uuid)
        logger.info(f"Queued summary retry for file {file_id}")
        return True

    except Exception as e:
        logger.error(f"Error queuing summary retry for file {file_id}: {e}")
        return False


def get_failed_summary_count() -> int:
    """
    Get count of files with failed summary status

    Returns:
        Number of files with failed summaries
    """
    with session_scope() as db:
        try:
            return (  # type: ignore[no-any-return]
                db.query(MediaFile)
                .filter(MediaFile.summary_status == "failed", MediaFile.status == "completed")
                .count()
            )
        except Exception as e:
            logger.error(f"Error getting failed summary count: {e}")
            return 0
