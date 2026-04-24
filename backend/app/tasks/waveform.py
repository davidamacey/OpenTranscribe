"""
Waveform generation Celery task.

This module provides a standalone Celery task for generating waveform visualization
data that runs on the CPU queue in parallel with GPU transcription tasks.
"""

import logging
import os

from app.core.celery import celery_app
from app.core.constants import CPUPriority
from app.db.session_utils import get_refreshed_object
from app.db.session_utils import session_scope
from app.models.media import MediaFile
from app.services.minio_service import download_file
from app.tasks.transcription.waveform_generator import WaveformGenerator
from app.utils import benchmark_timing
from app.utils.temp_file_utils import cleanup_temp_file
from app.utils.temp_file_utils import download_to_temp_file

logger = logging.getLogger(__name__)


def _get_storage_path(file_id: int) -> str | None:
    """Get storage path for a media file from database."""
    with session_scope() as db:
        media_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
        if not media_file:
            logger.error(f"Media file {file_id} not found")
            return None
        if not media_file.storage_path:
            logger.error(f"No storage path for file {file_id}")
            return None
        return str(media_file.storage_path)  # type: ignore[no-any-return]


def _download_to_temp_file(storage_path: str) -> str | None:
    """Download file from storage to a temporary file. Returns temp file path or None."""
    logger.info(f"Downloading file from storage: {storage_path}")
    _, file_extension = os.path.splitext(storage_path)

    try:
        file_data, _, _ = download_file(storage_path)
        temp_file_path = download_to_temp_file(file_data, suffix=file_extension)
        logger.info(f"Downloaded file to {temp_file_path}")
        return temp_file_path
    except Exception as e:
        logger.error(f"Error downloading file from storage: {e}")
        return None


def _save_waveform_data(file_id: int, waveform_data: dict) -> None:
    """Save waveform data to database."""
    with session_scope() as db:
        media_file = get_refreshed_object(db, MediaFile, file_id)
        if media_file:
            media_file.waveform_data = waveform_data
            db.commit()
            logger.info(f"Waveform data saved for file {file_id} - generation complete")


def _cleanup_temp_file(temp_file_path: str | None) -> None:
    """Clean up temporary file if it exists."""
    cleanup_temp_file(temp_file_path)


@celery_app.task(
    name="media.generate_waveform",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    priority=CPUPriority.PIPELINE_CRITICAL,
)
def generate_waveform_task(self, file_id: int, file_uuid: str, task_id: str | None = None):
    """
    Generate waveform visualization data for a media file.

    This task runs on the CPU queue in parallel with GPU transcription tasks
    to avoid blocking GPU workers with I/O-bound operations.

    Args:
        file_id: Database ID of the media file
        file_uuid: UUID of the media file
        task_id: Optional upstream pipeline task_id. When provided, waveform
            start/end benchmark markers land in the same Redis hash as the
            rest of the pipeline so the CSV stages reconcile cleanly.

    Returns:
        dict: Success status and waveform data info
    """
    temp_file_path = None
    benchmark_timing.mark(task_id, "waveform_start")

    try:
        logger.info(f"Starting waveform generation for file {file_id} ({file_uuid})")

        storage_path = _get_storage_path(file_id)
        if not storage_path:
            return {"success": False, "error": "Media file not found or no storage path"}

        temp_file_path = _download_to_temp_file(storage_path)
        if not temp_file_path:
            return {"success": False, "error": "Download failed"}

        logger.info(f"Generating waveform visualization for file {file_id}")
        waveform_generator = WaveformGenerator()
        waveform_data = waveform_generator.generate_waveform_data(temp_file_path)

        if not waveform_data:
            logger.warning(f"Failed to generate waveform data for file {file_id}")
            return {"success": False, "error": "Waveform generation returned no data"}

        _save_waveform_data(file_id, waveform_data)
        return {"success": True, "file_id": file_id, "resolutions": len(waveform_data)}

    except Exception as e:
        logger.error(f"Unexpected error in waveform generation: {e}", exc_info=True)
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for waveform generation: {file_id}")
            return {"success": False, "error": "Max retries exceeded"}

    finally:
        _cleanup_temp_file(temp_file_path)
        benchmark_timing.mark(task_id, "waveform_end")
