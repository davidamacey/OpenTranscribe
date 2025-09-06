import datetime
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.db.session_utils import get_refreshed_object
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.models.media import TranscriptSegment

logger = logging.getLogger(__name__)


def save_transcript_segments(db: Session, file_id: int, segments: list[dict[str, Any]]) -> None:
    """
    Save transcript segments to the database.

    Args:
        db: Database session
        file_id: Media file ID
        segments: List of processed segments with speaker information
    """
    logger.info(f"Saving {len(segments)} transcript segments to database")

    for segment in segments:
        db_segment = TranscriptSegment(
            media_file_id=file_id,
            start_time=segment["start"],
            end_time=segment["end"],
            text=segment["text"],
            speaker_id=segment["speaker_id"]
        )
        db.add(db_segment)

    db.commit()
    logger.info(f"Successfully saved {len(segments)} segments")


def update_media_file_transcription_status(db: Session, file_id: int, segments: list[dict[str, Any]],
                                         language: str = "en") -> None:
    """
    Update media file with transcription completion metadata.

    Args:
        db: Database session
        file_id: Media file ID
        segments: List of transcript segments
        language: Detected language
    """
    media_file = get_refreshed_object(db, MediaFile, file_id)
    if not media_file:
        logger.error(f"Media file with ID {file_id} not found when updating transcription status")
        return

    # Calculate duration from segments
    duration = segments[-1]["end"] if segments else 0.0

    # Update media file
    media_file.duration = duration
    media_file.language = language
    media_file.status = FileStatus.COMPLETED
    media_file.completed_at = datetime.datetime.now()

    db.commit()
    logger.info(f"Updated media file {file_id} transcription status")


def create_search_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Create cleaned segments for search indexing.

    Args:
        segments: Original transcript segments

    Returns:
        Cleaned segments for search indexing
    """
    index_segments = []
    for segment in segments:
        index_segments.append({
            "start": segment["start"],
            "end": segment["end"],
            "text": segment["text"],
            "speaker": segment["speaker"]
        })
    return index_segments


def generate_full_transcript(segments: list[dict[str, Any]]) -> str:
    """
    Generate full transcript text from segments.

    Args:
        segments: List of transcript segments

    Returns:
        Full transcript as a single string
    """
    return " ".join([segment["text"] for segment in segments])


def get_unique_speaker_names(segments: list[dict[str, Any]]) -> list[str]:
    """
    Extract unique speaker names from segments.

    Args:
        segments: List of transcript segments

    Returns:
        List of unique speaker names
    """
    return list(set([segment["speaker"] for segment in segments]))
