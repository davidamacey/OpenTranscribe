"""
Summary retry utilities for OpenTranscribe

This module provides functionality to retry failed AI summaries,
similar to the transcription retry mechanism in task_utils.py
"""

import logging
import asyncio
from typing import Optional

from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.models.media import MediaFile
from app.services.llm_service import is_llm_available
from app.tasks.summarization import summarize_transcript_task
from app.db.session_utils import get_refreshed_object

logger = logging.getLogger(__name__)


def reset_summary_for_retry(db: Session, file_id: int) -> bool:
    """
    Reset a file's summary for retry processing, similar to reset_file_for_retry for transcription.
    
    Args:
        db: Database session
        file_id: ID of the file to reset summary for
        
    Returns:
        True if reset was successful, False otherwise
    """
    media_file = get_refreshed_object(db, MediaFile, file_id)
    if not media_file:
        logger.error(f"File {file_id} not found")
        return False
    
    # Only retry if transcription is completed
    if media_file.status != 'completed':
        logger.error(f"Cannot retry summary for file {file_id} - transcription not completed (status: {media_file.status})")
        return False
        
    try:
        # Reset summary fields
        media_file.summary = None
        media_file.summary_opensearch_id = None
        media_file.summary_status = 'pending'
        
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


def retry_summary_if_available(db: Session, file_id: int) -> bool:
    """
    Retry summary generation for a specific file if LLM is available
    
    Args:
        db: Database session
        file_id: ID of the file to retry
        
    Returns:
        True if retry was queued successfully, False otherwise
    """
    # Check if LLM is available
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        llm_available = loop.run_until_complete(check_llm_availability())
    finally:
        try:
            loop.close()
        except:
            pass
            
    if not llm_available:
        logger.debug(f"LLM not available for retry of file {file_id}")
        return False
        
    # Reset summary status and clear existing data
    if not reset_summary_for_retry(db, file_id):
        return False
        
    try:
        # Queue summarization task
        summarize_transcript_task.delay(file_id)
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
    db = SessionLocal()
    try:
        return db.query(MediaFile).filter(
            MediaFile.summary_status == 'failed',
            MediaFile.status == 'completed'
        ).count()
    except Exception as e:
        logger.error(f"Error getting failed summary count: {e}")
        return 0
    finally:
        db.close()