"""
Helper functions for AI summarization tasks

Contains the LLM summary generation and speaker identification functions.
"""

import asyncio
import logging
from typing import Any
from typing import Optional

from app.core.celery import celery_app
from app.db.base import SessionLocal
from app.models.media import MediaFile
from app.models.media import Speaker
from app.models.media import SpeakerProfile
from app.models.media import TranscriptSegment
from app.services.llm_service import LLMServiceContext

logger = logging.getLogger(__name__)


async def generate_llm_summary(transcript: str, speaker_stats: dict[str, Any],
                              provider: Optional[str] = None, model: Optional[str] = None, user_id: Optional[int] = None) -> dict[str, Any]:
    """
    Generate structured summary using LLM service

    Args:
        transcript: Full transcript text
        speaker_stats: Speaker statistics
        provider: Optional LLM provider override
        model: Optional model override
        user_id: Optional user ID for custom prompt selection

    Returns:
        Structured summary data
    """
    try:
        async with LLMServiceContext() as llm_service:
            # Override provider/model if specified
            if provider:
                llm_service.config.provider = provider
            if model:
                llm_service.config.model = model

            # Generate summary
            summary_data = await llm_service.generate_summary(
                transcript=transcript,
                speaker_data=speaker_stats,
                user_id=user_id
            )

            return summary_data

    except Exception as e:
        logger.error(f"LLM summary generation failed: {e}")
        raise




@celery_app.task(bind=True, name="identify_speakers_llm")
def identify_speakers_llm_task(self, file_id: int):
    """
    Use LLM to provide speaker identification suggestions

    This task provides suggestions to help users identify speakers manually.
    The predictions are NOT automatically applied to the transcript.

    Args:
        file_id: Database ID of the MediaFile
    """
    task_id = self.request.id
    db = SessionLocal()

    try:
        # Get media file and check if it exists
        media_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
        if not media_file:
            raise ValueError(f"Media file with ID {file_id} not found")

        # Create task record
        from app.utils.task_utils import create_task_record
        from app.utils.task_utils import update_task_status
        create_task_record(db, task_id, media_file.user_id, file_id, "speaker_identification")

        # Update task status
        update_task_status(db, task_id, "in_progress", progress=0.1)

        # Get transcript segments and speakers
        transcript_segments = db.query(TranscriptSegment).filter(
            TranscriptSegment.media_file_id == file_id
        ).order_by(TranscriptSegment.start_time).all()

        if not transcript_segments:
            raise ValueError(f"No transcript segments found for file {file_id}")

        # Get current speakers
        speakers = db.query(Speaker).filter(
            Speaker.media_file_id == file_id
        ).all()

        if not speakers:
            logger.info(f"No speakers found for file {file_id}, skipping LLM identification")
            update_task_status(db, task_id, "completed", progress=1.0, completed=True)
            return {"status": "skipped", "message": "No speakers to identify"}

        # Build transcript text
        full_transcript = ""
        for segment in transcript_segments:
            speaker_name = segment.speaker.name if segment.speaker else "Unknown"
            timestamp = f"[{int(segment.start_time//60):02d}:{int(segment.start_time%60):02d}]"
            full_transcript += f"\n{speaker_name}: {timestamp} {segment.text}"

        # Build speaker segments data
        speaker_segments = []
        for segment in transcript_segments[:50]:  # Limit for analysis
            speaker_segments.append({
                "speaker_label": segment.speaker.name if segment.speaker else "Unknown",
                "start_time": segment.start_time,
                "end_time": segment.end_time,
                "text": segment.text[:200]  # Limit text length
            })

        # Get known speakers (verified speakers from other files)
        known_speakers = []
        profiles = db.query(SpeakerProfile).filter(
            SpeakerProfile.user_id == media_file.user_id
        ).all()

        for profile in profiles:
            known_speakers.append({
                "name": profile.name,
                "description": profile.description or "No description available",
                "uuid": profile.uuid
            })

        update_task_status(db, task_id, "in_progress", progress=0.5)

        # Generate LLM speaker predictions
        async def _run_speaker_identification():
            async with LLMServiceContext() as llm_service:
                return await llm_service.identify_speakers(
                    transcript=full_transcript,
                    speaker_segments=speaker_segments,
                    known_speakers=known_speakers
                )

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            predictions = loop.run_until_complete(_run_speaker_identification())

            loop.close()

            # Store predictions as suggestions in speaker records
            for prediction in predictions.get("speaker_predictions", []):
                speaker_label = prediction.get("speaker_label")
                predicted_name = prediction.get("predicted_name")
                confidence = prediction.get("confidence", 0.0)

                # Find the speaker in the database
                speaker = db.query(Speaker).filter(
                    Speaker.media_file_id == file_id,
                    Speaker.name == speaker_label
                ).first()

                if speaker and confidence >= 0.5:  # Only store medium+ confidence predictions
                    # Store as suggestion, not automatic assignment
                    speaker.suggested_name = predicted_name
                    speaker.confidence = confidence

            db.commit()

            logger.info(f"Generated {len(predictions.get('speaker_predictions', []))} speaker predictions")

        except Exception as e:
            logger.error(f"LLM speaker identification failed: {e}")
            # Don't fail the task, just log the error
            predictions = {"speaker_predictions": [], "error": str(e)}

        # Update task as completed
        update_task_status(db, task_id, "completed", progress=1.0, completed=True)

        return {
            "status": "success",
            "file_id": file_id,
            "predictions_count": len(predictions.get("speaker_predictions", [])),
            "overall_confidence": predictions.get("overall_confidence", "unknown")
        }

    except Exception as e:
        logger.error(f"Error in speaker identification task for file {file_id}: {str(e)}")
        update_task_status(db, task_id, "failed", error_message=str(e), completed=True)
        return {"status": "error", "message": str(e)}

    finally:
        db.close()
