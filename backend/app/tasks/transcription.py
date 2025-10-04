"""
Transcription tasks module - refactored for modularity.

This file now serves as the main entry point for transcription tasks,
with the actual implementation moved to the transcription/ submodule.
"""

import logging
import tempfile
from pathlib import Path

from app.core.celery import celery_app
from app.db.session_utils import session_scope
from app.models.media import Analytics
from app.models.media import TranscriptSegment
from app.services.minio_service import download_file
from app.services.minio_service import upload_file

# Import the main transcription task from the modular implementation

logger = logging.getLogger(__name__)


@celery_app.task(name="extract_audio")
def extract_audio_task(file_uuid: str, output_format: str = "wav"):
    """
    Extract audio from a video file

    Args:
        file_uuid: UUID of the MediaFile
        output_format: Output audio format (default: wav)
    """
    from app.utils.uuid_helpers import get_file_by_uuid

    try:
        with session_scope() as db:
            media_file = get_file_by_uuid(db, file_uuid)
            if not media_file:
                logger.error(f"Media file with UUID {file_uuid} not found")
                return {
                    "status": "error",
                    "message": f"Media file with UUID {file_uuid} not found",
                }

            file_id = media_file.id  # Get internal ID for subsequent operations
            user_id = media_file.user_id
            storage_path = media_file.storage_path
            filename = media_file.filename

        file_data, file_size, content_type = download_file(storage_path)

        if not content_type.startswith("video/"):
            return {"status": "error", "message": "Not a video file"}

        video_suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(suffix=video_suffix, delete=False) as temp_video:
            temp_video.write(file_data.read())
            video_path = temp_video.name

        try:
            import io
            import os

            import ffmpeg

            audio_filename = f"{Path(filename).stem}.{output_format}"
            audio_storage_path = f"user_{user_id}/file_{file_id}/audio/{audio_filename}"

            with tempfile.NamedTemporaryFile(
                suffix=f".{output_format}", delete=False
            ) as temp_audio:
                audio_path = temp_audio.name

            ffmpeg.input(video_path).output(audio_path).run(quiet=True, overwrite_output=True)

            with open(audio_path, "rb") as audio_file:
                audio_data = audio_file.read()

            upload_file(
                file_content=io.BytesIO(audio_data),
                file_size=os.path.getsize(audio_path),
                object_name=audio_storage_path,
                content_type=f"audio/{output_format}",
            )

            logger.info(f"Audio extraction completed for file {file_id}")
            return {
                "status": "success",
                "file_id": file_id,
                "audio_path": audio_storage_path,
            }

        finally:
            try:
                if os.path.exists(video_path):
                    os.unlink(video_path)
                if "audio_path" in locals() and os.path.exists(audio_path):
                    os.unlink(audio_path)
            except Exception as e:
                logger.error(f"Error cleaning up temporary files: {e}")

    except Exception as e:
        logger.error(f"Error extracting audio from file {file_id}: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(name="analyze_transcript")
def analyze_transcript_task(file_uuid: str):
    """
    Analyze a transcript for additional metadata and insights

    Args:
        file_uuid: UUID of the MediaFile to analyze
    """
    from app.utils.uuid_helpers import get_file_by_uuid

    try:
        with session_scope() as db:
            media_file = get_file_by_uuid(db, file_uuid)
            if not media_file:
                logger.error(f"Media file with UUID {file_uuid} not found")
                return {
                    "status": "error",
                    "message": f"Media file with UUID {file_uuid} not found",
                }

            file_id = media_file.id  # Get internal ID for database queries
            segments = (
                db.query(TranscriptSegment)
                .filter(TranscriptSegment.media_file_id == file_id)
                .order_by(TranscriptSegment.segment_index)
                .all()
            )

            if not segments:
                logger.warning(f"No transcript segments found for file {file_id}")
                return {"status": "error", "message": "No transcript segments found"}

            full_text = " ".join([segment.text for segment in segments])

            analytics = db.query(Analytics).filter(Analytics.media_file_id == file_id).first()
            if not analytics:
                analytics = Analytics(media_file_id=file_id)
                db.add(analytics)

            word_count = len(full_text.split())
            unique_speakers = len(set([segment.speaker_id for segment in segments]))

            analytics.word_count = word_count
            analytics.speaker_count = unique_speakers
            analytics.segment_count = len(segments)

            db.commit()

            logger.info(f"Analytics completed for file {file_id}")
            return {"status": "success", "file_id": file_id}

    except Exception as e:
        logger.error(f"Error analyzing transcript for file {file_id}: {str(e)}")
        return {"status": "error", "message": str(e)}
