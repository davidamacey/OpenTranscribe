"""
Speaker identification and management tasks
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.celery import celery_app
from app.core.constants import DEFAULT_LLM_OUTPUT_LANGUAGE
from app.db.base import SessionLocal
from app.models.media import Speaker
from app.models.media import SpeakerProfile
from app.models.media import TranscriptSegment
from app.models.prompt import UserSetting
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


def _build_full_transcript(transcript_segments: list[TranscriptSegment]) -> str:
    """Build formatted transcript text from segments."""
    lines = []
    for segment in transcript_segments:
        speaker_name = segment.speaker.name if segment.speaker else "Unknown"
        timestamp = f"[{int(segment.start_time // 60):02d}:{int(segment.start_time % 60):02d}]"
        lines.append(f"{speaker_name}: {timestamp} {segment.text}")
    return "\n" + "\n".join(lines)


def _build_speaker_segments(transcript_segments: list[TranscriptSegment]) -> list[dict[str, Any]]:
    """Build speaker segments data for LLM analysis (limited to first 50)."""
    return [
        {
            "speaker_label": segment.speaker.name if segment.speaker else "Unknown",
            "start_time": segment.start_time,
            "end_time": segment.end_time,
            "text": segment.text[:200],
        }
        for segment in transcript_segments[:50]
    ]


def _get_known_speakers(db: Session, user_id: int) -> list[dict[str, Any]]:
    """Get known speaker profiles for the user."""
    profiles = db.query(SpeakerProfile).filter(SpeakerProfile.user_id == user_id).all()
    return [
        {
            "name": profile.name,
            "description": profile.description or "No description available",
            "uuid": profile.uuid,
        }
        for profile in profiles
    ]


def _get_user_llm_output_language(db: Session, user_id: int) -> str:
    """
    Retrieve user's LLM output language setting from the database.

    Args:
        db: Database session
        user_id: ID of the user

    Returns:
        LLM output language code (default: "en")
    """
    setting = (
        db.query(UserSetting)
        .filter(
            UserSetting.user_id == user_id,
            UserSetting.setting_key == "transcription_llm_output_language",
        )
        .first()
    )

    if setting:
        return setting.setting_value
    return DEFAULT_LLM_OUTPUT_LANGUAGE


def _create_llm_service(user_id: int | None) -> LLMService:
    """Create LLM service based on user settings or system defaults."""
    if user_id:
        llm_service = LLMService.create_from_user_settings(user_id)
    else:
        llm_service = LLMService.create_from_system_settings()

    if not llm_service:
        raise Exception("Could not create LLM service for speaker identification")
    return llm_service


def _run_llm_identification(
    llm_service: LLMService,
    full_transcript: str,
    speaker_segments: list[dict[str, Any]],
    known_speakers: list[dict[str, Any]],
    output_language: str = "en",
) -> dict[str, Any]:
    """Run LLM speaker identification and return predictions."""
    try:
        if hasattr(llm_service, "identify_speakers"):
            return llm_service.identify_speakers(
                transcript=full_transcript,
                speaker_segments=speaker_segments,
                known_speakers=known_speakers,
                output_language=output_language,
            )
        logger.warning("Speaker identification not implemented - skipping")
        return {"speaker_predictions": [], "error": "Feature not implemented"}
    finally:
        llm_service.close()


def _store_speaker_predictions(db: Session, file_id: int, predictions: dict[str, Any]) -> None:
    """Store speaker predictions as suggestions in speaker records."""
    for prediction in predictions.get("speaker_predictions", []):
        speaker_label = prediction.get("speaker_label")
        predicted_name = prediction.get("predicted_name")
        confidence = prediction.get("confidence", 0.0)

        if confidence < 0.5:
            continue

        speaker = (
            db.query(Speaker)
            .filter(Speaker.media_file_id == file_id, Speaker.name == speaker_label)
            .first()
        )

        if speaker:
            speaker.suggested_name = predicted_name
            speaker.confidence = confidence

    db.commit()


@celery_app.task(bind=True, name="identify_speakers_llm")
def identify_speakers_llm_task(self, file_uuid: str):
    """
    Use LLM to provide speaker identification suggestions

    This task provides suggestions to help users identify speakers manually.
    The predictions are NOT automatically applied to the transcript.

    Args:
        file_uuid: UUID of the MediaFile
    """
    from app.utils.task_utils import create_task_record
    from app.utils.task_utils import update_task_status
    from app.utils.uuid_helpers import get_file_by_uuid

    task_id = self.request.id
    db = SessionLocal()
    file_id = None

    try:
        media_file = get_file_by_uuid(db, file_uuid)
        if not media_file:
            raise ValueError(f"Media file with UUID {file_uuid} not found")

        file_id = media_file.id

        create_task_record(db, task_id, media_file.user_id, file_id, "speaker_identification")
        update_task_status(db, task_id, "in_progress", progress=0.1)

        transcript_segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.media_file_id == file_id)
            .order_by(TranscriptSegment.start_time)
            .all()
        )

        if not transcript_segments:
            raise ValueError(f"No transcript segments found for file {file_id}")

        speakers = db.query(Speaker).filter(Speaker.media_file_id == file_id).all()

        if not speakers:
            logger.info(f"No speakers found for file {file_id}, skipping LLM identification")
            update_task_status(db, task_id, "completed", progress=1.0, completed=True)
            return {"status": "skipped", "message": "No speakers to identify"}

        full_transcript = _build_full_transcript(transcript_segments)
        speaker_segments = _build_speaker_segments(transcript_segments)
        known_speakers = _get_known_speakers(db, media_file.user_id)

        update_task_status(db, task_id, "in_progress", progress=0.5)

        predictions = _generate_predictions(
            file_id, media_file.user_id, db, full_transcript, speaker_segments, known_speakers
        )

        update_task_status(db, task_id, "completed", progress=1.0, completed=True)

        return {
            "status": "success",
            "file_id": file_id,
            "predictions_count": len(predictions.get("speaker_predictions", [])),
            "overall_confidence": predictions.get("overall_confidence", "unknown"),
        }

    except Exception as e:
        logger.error(f"Error in speaker identification task for file {file_id}: {str(e)}")
        update_task_status(db, task_id, "failed", error_message=str(e), completed=True)
        return {"status": "error", "message": str(e)}

    finally:
        db.close()


def _generate_predictions(
    file_id: int,
    user_id: int | None,
    db: Session,
    full_transcript: str,
    speaker_segments: list[dict[str, Any]],
    known_speakers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate LLM speaker predictions and store them."""
    try:
        logger.info(f"Starting LLM speaker identification for file {file_id}")

        # Get user's language preference for LLM output
        output_language = (
            _get_user_llm_output_language(db, user_id) if user_id else DEFAULT_LLM_OUTPUT_LANGUAGE
        )
        logger.info(f"Using LLM output language: {output_language}")

        llm_service = _create_llm_service(user_id)
        predictions = _run_llm_identification(
            llm_service, full_transcript, speaker_segments, known_speakers, output_language
        )

        _store_speaker_predictions(db, file_id, predictions)

        logger.info(
            f"Generated {len(predictions.get('speaker_predictions', []))} speaker predictions"
        )
        return predictions

    except Exception as e:
        logger.error(f"LLM speaker identification failed: {type(e).__name__}: {e}")
        logger.error("Full traceback:", exc_info=True)
        return {"speaker_predictions": [], "error": str(e)}
