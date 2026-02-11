import datetime
import logging
import uuid as uuid_module
from typing import Any

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.db.session_utils import get_refreshed_object
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.models.media import TranscriptSegment

logger = logging.getLogger(__name__)


def save_transcript_segments(db: Session, file_id: int, segments: list[dict[str, Any]]) -> None:
    """
    Save transcript segments to the database using bulk insert for efficiency.

    Uses SQLAlchemy's bulk insert to insert all segments in a single database
    roundtrip instead of individual INSERT statements per segment.

    Args:
        db: Database session
        file_id: Media file ID
        segments: List of processed segments with speaker information
    """
    import time

    start_time = time.perf_counter()

    if not segments:
        logger.info("No segments to save")
        return

    # Delete any existing segments for this file to prevent duplicates.
    # Recovery/retry code paths may re-run transcription without cleanup,
    # so this is the defensive single point of truth.
    existing_count = (
        db.query(TranscriptSegment).filter(TranscriptSegment.media_file_id == file_id).count()
    )
    if existing_count > 0:
        logger.warning(
            f"Found {existing_count} existing segments for file {file_id}, "
            f"deleting before re-saving {len(segments)} new segments"
        )
        db.query(TranscriptSegment).filter(TranscriptSegment.media_file_id == file_id).delete(
            synchronize_session=False
        )

    logger.info(f"Saving {len(segments)} transcript segments to database (bulk insert)")

    # Prepare all records for bulk insert
    overlap_count = 0
    records = []

    for segment in segments:
        is_overlap = segment.get("is_overlap", False)
        if is_overlap:
            overlap_count += 1

        # Get overlap_group_id and convert string UUID to proper UUID object if present
        overlap_group_id = segment.get("overlap_group_id")
        if overlap_group_id and isinstance(overlap_group_id, str):
            overlap_group_id = uuid_module.UUID(overlap_group_id)

        records.append(
            {
                "uuid": uuid_module.uuid4(),  # Generate UUID for each segment
                "media_file_id": file_id,
                "start_time": segment["start"],
                "end_time": segment["end"],
                "text": segment["text"],
                "speaker_id": segment.get("speaker_id"),
                "is_overlap": is_overlap,
                "overlap_group_id": overlap_group_id,
                "overlap_confidence": segment.get("overlap_confidence"),
            }
        )

    # Execute bulk insert - single database roundtrip for all segments
    db.execute(insert(TranscriptSegment), records)
    db.commit()

    elapsed = time.perf_counter() - start_time
    if overlap_count > 0:
        logger.info(
            f"TIMING: save_transcript_segments completed in {elapsed:.3f}s - "
            f"Saved {len(segments)} segments ({overlap_count} overlapping)"
        )
    else:
        logger.info(
            f"TIMING: save_transcript_segments completed in {elapsed:.3f}s - "
            f"Saved {len(segments)} segments"
        )


def update_media_file_transcription_status(
    db: Session,
    file_id: int,
    segments: list[dict[str, Any]],
    language: str = "en",
    whisper_model: str | None = None,
    diarization_model: str | None = None,
    embedding_mode: str | None = None,
) -> None:
    """
    Update media file with transcription completion metadata.

    Args:
        db: Database session
        file_id: Media file ID
        segments: List of transcript segments
        language: Detected language
        whisper_model: Whisper model used for transcription
        diarization_model: Diarization model used
        embedding_mode: Speaker embedding mode ("v3" or "v4")
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

    # Store processing model info
    if whisper_model:
        media_file.whisper_model = whisper_model
    if diarization_model:
        media_file.diarization_model = diarization_model
    if embedding_mode:
        media_file.embedding_mode = embedding_mode

    db.commit()
    logger.info(f"Updated media file {file_id} transcription status")


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
