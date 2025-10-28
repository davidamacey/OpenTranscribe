"""
Waveform generation Celery task.

This module provides a standalone Celery task for generating waveform visualization
data that runs on the CPU queue in parallel with GPU transcription tasks.
"""

import logging
import os
import tempfile

from app.core.celery import celery_app
from app.db.session_utils import get_refreshed_object
from app.db.session_utils import session_scope
from app.models.media import MediaFile
from app.services.minio_service import download_file
from app.tasks.transcription.waveform_generator import WaveformGenerator

logger = logging.getLogger(__name__)


@celery_app.task(
    name="generate_waveform_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_waveform_task(self, file_id: int, file_uuid: str):
    """
    Generate waveform visualization data for a media file.

    This task runs on the CPU queue in parallel with GPU transcription tasks
    to avoid blocking GPU workers with I/O-bound operations.

    Args:
        file_id: Database ID of the media file
        file_uuid: UUID of the media file

    Returns:
        dict: Success status and waveform data info
    """
    temp_file_path = None

    try:
        logger.info(f"Starting waveform generation for file {file_id} ({file_uuid})")

        # Get file information from database
        with session_scope() as db:
            media_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
            if not media_file:
                logger.error(f"Media file {file_id} not found")
                return {"success": False, "error": "Media file not found"}

            storage_path = media_file.storage_path

            if not storage_path:
                logger.error(f"No storage path for file {file_id}")
                return {"success": False, "error": "No storage path"}

        # Download file from storage to temporary location
        # Note: Progress notifications suppressed to avoid conflicting with transcription progress
        logger.info(f"Downloading file from storage: {storage_path}")
        _, file_extension = os.path.splitext(storage_path)

        try:
            # Download file from MinIO (returns BytesIO buffer)
            file_data, _, content_type = download_file(storage_path)

            # Create temporary file with original extension
            temp_fd, temp_file_path = tempfile.mkstemp(suffix=file_extension)
            os.close(temp_fd)

            # Write buffer to temporary file
            with open(temp_file_path, "wb") as f:
                f.write(file_data.read())

            logger.info(f"Downloaded file to {temp_file_path}")
        except Exception as e:
            logger.error(f"Error downloading file from storage: {e}")
            return {"success": False, "error": f"Download failed: {str(e)}"}

        # Generate waveform data (silently in background)
        logger.info(f"Generating waveform visualization for file {file_id}")

        try:
            waveform_generator = WaveformGenerator()
            waveform_data = waveform_generator.generate_waveform_data(temp_file_path)

            if waveform_data:
                # Save waveform data to database
                with session_scope() as db:
                    media_file = get_refreshed_object(db, MediaFile, file_id)
                    if media_file:
                        media_file.waveform_data = waveform_data
                        db.commit()
                        logger.info(f"Waveform data saved for file {file_id} - generation complete")

                return {
                    "success": True,
                    "file_id": file_id,
                    "resolutions": len(waveform_data),
                }
            else:
                logger.warning(f"Failed to generate waveform data for file {file_id}")
                return {"success": False, "error": "Waveform generation returned no data"}

        except Exception as e:
            logger.error(f"Error generating waveform data: {e}")
            # Don't fail the task - waveform is optional
            return {"success": False, "error": f"Waveform generation error: {str(e)}"}

    except Exception as e:
        logger.error(f"Unexpected error in waveform generation: {e}", exc_info=True)
        # Retry on unexpected errors
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for waveform generation: {file_id}")
            return {"success": False, "error": "Max retries exceeded"}

    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                logger.debug(f"Cleaned up temporary file: {temp_file_path}")
            except Exception as e:
                logger.warning(f"Error cleaning up temporary file: {e}")
