"""
Waveform generation service for media files.

This module provides Celery tasks for generating waveform visualization data
for media files, including both individual files and bulk operations.
"""

import logging
import os
import tempfile

from app.core.celery import celery_app
from app.db.session_utils import session_scope
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.services.minio_service import download_file
from app.tasks.transcription.waveform_generator import WaveformGenerator

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="generate_waveform_data")
def generate_waveform_data_task(self, file_id: int = None, skip_existing: bool = True):
    """
    Generate waveform data for media files.

    Args:
        file_id: Specific file ID to process, or None to process all eligible files
        skip_existing: Skip files that already have waveform data
    """

    try:
        with session_scope() as db:
            # Get files to process
            query = (
                db.query(MediaFile)
                .filter(MediaFile.status == FileStatus.COMPLETED)
                .filter(
                    MediaFile.content_type.like("audio/%") | MediaFile.content_type.like("video/%")
                )
            )

            if file_id:
                query = query.filter(MediaFile.id == file_id)

            if skip_existing:
                query = query.filter(MediaFile.waveform_data.is_(None))

            files_to_process = query.all()

            logger.info(f"Found {len(files_to_process)} files to process for waveform generation")

            if not files_to_process:
                return {
                    "status": "success",
                    "message": "No files need waveform generation",
                    "processed": 0,
                }

        processed_count = 0
        error_count = 0

        for media_file in files_to_process:
            try:
                result = _generate_waveform_for_file(
                    media_file.id, media_file.storage_path, media_file.filename
                )
                if result:
                    processed_count += 1
                    logger.info(
                        f"Generated waveform for file {media_file.id}: {media_file.filename}"
                    )
                else:
                    error_count += 1
                    logger.warning(
                        f"Failed to generate waveform for file {media_file.id}: {media_file.filename}"
                    )

            except Exception as e:
                error_count += 1
                logger.error(f"Error processing file {media_file.id}: {e}")

        logger.info(
            f"Waveform generation completed: {processed_count} processed, {error_count} errors"
        )
        return {
            "status": "success",
            "processed": processed_count,
            "errors": error_count,
            "total": len(files_to_process),
        }

    except Exception as e:
        logger.error(f"Error in waveform generation task: {e}")
        return {"status": "error", "message": str(e)}


def _generate_waveform_for_file(file_id: int, storage_path: str, filename: str) -> bool:
    """
    Generate waveform data for a single file.

    Args:
        file_id: Database ID of the file
        storage_path: MinIO storage path
        filename: Original filename for logging

    Returns:
        True if successful, False otherwise
    """
    try:
        # Download file from MinIO
        file_data, _, _ = download_file(storage_path)

        # Extract file extension for temporary file
        file_ext = os.path.splitext(filename)[1] or ".tmp"

        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            try:
                # Write file data to temporary file
                temp_file.write(file_data.read())
                temp_file_path = temp_file.name

                # Generate waveform data
                waveform_generator = WaveformGenerator()
                waveform_data = waveform_generator.generate_waveform_data(temp_file_path)

                if waveform_data:
                    # Save to database
                    with session_scope() as db:
                        media_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
                        if media_file:
                            media_file.waveform_data = waveform_data
                            db.commit()
                            return True

                return False

            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_file_path)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temp file {temp_file_path}: {cleanup_error}")

    except Exception as e:
        logger.error(f"Error generating waveform for file {file_id}: {e}")
        return False


def trigger_waveform_generation(file_id: int = None, skip_existing: bool = True):
    """
    Trigger waveform generation task.

    Args:
        file_id: Specific file ID to process, or None for all files
        skip_existing: Skip files that already have waveform data
    """
    task = generate_waveform_data_task.delay(file_id=file_id, skip_existing=skip_existing)
    logger.info(f"Triggered waveform generation task: {task.id}")
    return task.id
