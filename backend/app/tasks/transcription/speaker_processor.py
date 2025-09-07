import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.media import Speaker

logger = logging.getLogger(__name__)


def normalize_speaker_label(speaker_id: str) -> str:
    """
    Normalize speaker labels to ensure consistent format (SPEAKER_XX).

    Args:
        speaker_id: Original speaker ID

    Returns:
        Normalized speaker ID
    """
    if speaker_id is None:
        return "SPEAKER_00"

    if not speaker_id.startswith("SPEAKER_"):
        return f"SPEAKER_{speaker_id}"

    return speaker_id


def extract_unique_speakers(segments: list[dict[str, Any]]) -> set[str]:
    """
    Extract unique speaker IDs from transcription segments.

    Args:
        segments: List of transcription segments

    Returns:
        Set of unique speaker IDs
    """
    unique_speakers = set()

    for segment in segments:
        if "speaker" in segment and segment["speaker"] is not None:
            normalized_speaker = normalize_speaker_label(segment["speaker"])
            segment["speaker"] = normalized_speaker  # Update in place
            unique_speakers.add(normalized_speaker)

    return unique_speakers


def create_or_get_speaker(
    db: Session, user_id: int, media_file_id: int, speaker_label: str
) -> Speaker:
    """
    Create a new speaker or get existing one from database for a specific file.

    Args:
        db: Database session
        user_id: User ID
        media_file_id: Media file ID to associate speaker with
        speaker_label: Speaker label (e.g., "SPEAKER_01")

    Returns:
        Speaker object
    """
    # Check if speaker already exists for this user and file
    speaker = (
        db.query(Speaker)
        .filter(
            Speaker.user_id == user_id,
            Speaker.media_file_id == media_file_id,
            Speaker.name == speaker_label,
        )
        .first()
    )

    if not speaker:
        try:
            speaker_uuid = str(uuid.uuid4())

            speaker = Speaker(
                name=speaker_label,
                display_name=None,
                uuid=speaker_uuid,
                user_id=user_id,
                media_file_id=media_file_id,
                verified=False,
            )
            db.add(speaker)
            db.flush()  # Get the ID without committing
            logger.info(
                f"Created new speaker: {speaker_label} with UUID: {speaker_uuid} for file: {media_file_id}"
            )

        except Exception as e:
            logger.error(
                f"Error creating speaker {speaker_label} for file {media_file_id}: {str(e)}"
            )
            # Create a fallback speaker with guaranteed UUID
            speaker_uuid = str(uuid.uuid4())
            speaker = Speaker(
                name=speaker_label,
                display_name=None,
                uuid=speaker_uuid,
                user_id=user_id,
                media_file_id=media_file_id,
                verified=False,
            )
            db.add(speaker)
            db.flush()

    return speaker


def create_speaker_mapping(
    db: Session, user_id: int, media_file_id: int, unique_speakers: set[str]
) -> dict[str, int]:
    """
    Create a mapping of speaker labels to database IDs for a specific file.

    Args:
        db: Database session
        user_id: User ID
        media_file_id: Media file ID
        unique_speakers: Set of unique speaker labels

    Returns:
        Dictionary mapping speaker labels to database IDs
    """
    speaker_mapping = {}

    for speaker_id in unique_speakers:
        speaker = create_or_get_speaker(db, user_id, media_file_id, speaker_id)
        speaker_mapping[speaker_id] = speaker.id

    return speaker_mapping


def process_segments_with_speakers(
    segments: list[dict[str, Any]], speaker_mapping: dict[str, int]
) -> list[dict[str, Any]]:
    """
    Process transcription segments and add speaker database IDs.

    Args:
        segments: List of transcription segments from WhisperX
        speaker_mapping: Mapping of speaker labels to database IDs

    Returns:
        Processed segments with speaker information
    """
    processed_segments = []

    for i, segment in enumerate(segments):
        # Get basic segment info
        segment_start = segment.get("start", 0.0)
        segment_end = segment.get("end", 0.0)
        segment_text = segment.get("text", "")

        # Get speaker ID with fallback
        speaker_id = segment.get("speaker")
        if speaker_id is None:
            speaker_id = f"SPEAKER_{i % 2}"  # Fallback assignment

        speaker_id = normalize_speaker_label(speaker_id)
        speaker_db_id = speaker_mapping.get(speaker_id)

        # Process word-level timestamps
        words_data = []
        if "words" in segment:
            for word in segment["words"]:
                if "start" in word and "end" in word:
                    words_data.append(
                        {
                            "word": word.get("word", ""),
                            "start": word.get("start", 0.0),
                            "end": word.get("end", 0.0),
                            "score": word.get("score", 1.0),
                        }
                    )

        # Create processed segment
        processed_segment = {
            "start": segment_start,
            "end": segment_end,
            "text": segment_text,
            "speaker": speaker_id,
            "speaker_id": speaker_db_id,
            "words": words_data,
            "confidence": segment.get("confidence", 1.0),
        }

        processed_segments.append(processed_segment)

    return processed_segments
