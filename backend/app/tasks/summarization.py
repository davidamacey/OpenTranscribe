import asyncio
import contextlib
import json
import logging
import time
from typing import Optional

import redis

from app.core.celery import celery_app
from app.core.config import settings
from app.db.base import SessionLocal
from app.models.media import MediaFile
from app.models.media import TranscriptSegment
from app.services.opensearch_summary_service import OpenSearchSummaryService
from app.tasks.summarization_helpers import generate_llm_summary

# Setup logging
logger = logging.getLogger(__name__)


def send_summary_notification(
    user_id: int,
    file_id: int,
    status: str,
    message: str,
    progress: int = 0,
    summary_data: dict = None,
    summary_opensearch_id: str = None,
) -> bool:
    """
    Send summary status notification via Redis pub/sub from synchronous context (like Celery worker).

    Args:
        user_id: User ID
        file_id: File ID
        status: Summary status ('processing', 'completed', 'failed')
        message: Status message
        progress: Progress percentage
        summary_data: Summary content (included when status is 'completed')
        summary_opensearch_id: OpenSearch document ID (included when status is 'completed')

    Returns:
        True if notification was sent successfully, False otherwise
    """
    try:
        # Create Redis client
        redis_client = redis.from_url(settings.REDIS_URL)

        # Get file metadata
        from app.tasks.transcription.notifications import get_file_metadata

        file_metadata = get_file_metadata(file_id)

        # Prepare notification data
        notification_data = {
            "file_id": str(file_id),
            "status": status,
            "message": message,
            "progress": progress,
            "filename": file_metadata["filename"],
            "content_type": file_metadata["content_type"],
            "file_size": file_metadata["file_size"],
        }

        # Include summary data when status is completed
        if status == "completed" and summary_data:
            notification_data["summary"] = summary_data
        if status == "completed" and summary_opensearch_id:
            notification_data["summary_opensearch_id"] = summary_opensearch_id

        notification = {
            "user_id": user_id,
            "type": "summarization_status",
            "data": notification_data,
        }

        # Publish to Redis
        redis_client.publish("websocket_notifications", json.dumps(notification))
        logger.info(
            f"Published summary notification via Redis for user {user_id}, file {file_id}: {status}"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to send summary notification via Redis for file {file_id}: {e}")
        return False


@celery_app.task(bind=True, name="summarize_transcript")
def summarize_transcript_task(
    self,
    file_id: int,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    force_regenerate: bool = False,
):
    """
    Generate a comprehensive summary of a transcript using LLM with structured BLUF format

    This task runs AFTER speaker embedding matching has been completed to ensure
    accurate speaker information is available for summarization.

    Args:
        file_id: Database ID of the MediaFile to summarize
        provider: Optional LLM provider override (openai, vllm, ollama, etc.)
        model: Optional model override
        force_regenerate: If True, clear existing summaries before regenerating
    """
    task_id = self.request.id
    db = SessionLocal()

    try:
        # Get media file from database
        media_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
        if not media_file:
            raise ValueError(f"Media file with ID {file_id} not found")

        # Create task record
        from app.utils.task_utils import create_task_record
        from app.utils.task_utils import update_task_status

        create_task_record(db, task_id, media_file.user_id, file_id, "summarization")

        # Update task status
        update_task_status(db, task_id, "in_progress", progress=0.1)

        # Handle force regeneration - clear existing summaries
        if force_regenerate:
            logger.info(
                f"Force regenerate requested - clearing existing summaries for file {file_id}"
            )

            # Clear OpenSearch summary if it exists
            if media_file.summary_opensearch_id:
                try:
                    summary_service = OpenSearchSummaryService()
                    # Note: This is a sync context, so we can't use await
                    # The service should handle sync operations or we'll handle errors gracefully
                    logger.info(f"Clearing OpenSearch document {media_file.summary_opensearch_id}")
                except Exception as e:
                    logger.warning(f"Could not clear OpenSearch summary: {e}")

            # Clear PostgreSQL summary fields
            media_file.summary = None
            media_file.summary_opensearch_id = None

        # Set summary status to processing
        media_file.summary_status = "processing"
        db.commit()

        # Send processing notification
        send_summary_notification(
            media_file.user_id,
            file_id,
            "processing",
            f"AI summary {'regeneration' if force_regenerate else 'generation'} started",
            10,
        )

        # Get transcript segments from database
        transcript_segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.media_file_id == file_id)
            .order_by(TranscriptSegment.start_time)
            .all()
        )

        if not transcript_segments:
            raise ValueError(f"No transcript segments found for file {file_id}")

        # Build full transcript text with proper speaker identification
        # Use display names from speaker embedding matching when available
        full_transcript = ""
        current_speaker = None
        speaker_stats = {}  # Track speaker statistics

        for segment in transcript_segments:
            # Get the best available speaker name
            if segment.speaker:
                speaker = segment.speaker
                # Use display_name if verified, otherwise use suggested_name or fallback to original name
                if speaker.display_name and speaker.verified:
                    speaker_name = speaker.display_name
                elif speaker.suggested_name and speaker.confidence and speaker.confidence >= 0.75:
                    speaker_name = f"{speaker.suggested_name} (suggested)"
                else:
                    speaker_name = speaker.name  # Original diarization label
            else:
                speaker_name = "Unknown Speaker"

            # Track speaker statistics
            segment_duration = segment.end_time - segment.start_time
            if speaker_name not in speaker_stats:
                speaker_stats[speaker_name] = {
                    "total_time": 0,
                    "segment_count": 0,
                    "word_count": 0,
                }
            speaker_stats[speaker_name]["total_time"] += segment_duration
            speaker_stats[speaker_name]["segment_count"] += 1
            speaker_stats[speaker_name]["word_count"] += len(segment.text.split())

            # Add speaker name if speaker changes
            if speaker_name != current_speaker:
                full_transcript += f"\n\n{speaker_name}: "
                current_speaker = speaker_name
            else:
                # Continue with same speaker
                full_transcript += " "

            # Add segment text with timestamp for reference
            timestamp = f"[{int(segment.start_time // 60):02d}:{int(segment.start_time % 60):02d}]"
            full_transcript += f"{timestamp} {segment.text}"

        # Calculate speaker percentages
        total_time = sum(stats["total_time"] for stats in speaker_stats.values())
        for speaker_name, stats in speaker_stats.items():
            stats["percentage"] = (stats["total_time"] / total_time * 100) if total_time > 0 else 0

        # Update task progress
        update_task_status(db, task_id, "in_progress", progress=0.3)
        send_summary_notification(
            media_file.user_id,
            file_id,
            "processing",
            "Analyzing speakers and content",
            30,
        )

        # Generate comprehensive structured summary using LLM
        logger.info(
            f"Generating LLM summary for file {media_file.filename} (length: {len(full_transcript)} chars)"
        )
        send_summary_notification(
            media_file.user_id,
            file_id,
            "processing",
            "Generating AI summary with LLM",
            50,
        )

        # Use asyncio to run the async LLM service
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        start_time = time.time()

        try:
            # Run LLM summarization - fail if LLM is not available
            summary_data = loop.run_until_complete(
                generate_llm_summary(
                    full_transcript, speaker_stats, provider, model, media_file.user_id
                )
            )

            processing_time = int((time.time() - start_time) * 1000)
            summary_data["metadata"]["processing_time_ms"] = processing_time

        except Exception as e:
            logger.error(f"LLM summarization failed: {e}")
            # Set summary status to failed for graceful handling
            media_file.summary_status = "failed"
            db.commit()
            # Send failed notification
            send_summary_notification(
                media_file.user_id,
                file_id,
                "failed",
                f"AI summary generation failed: {str(e)}",
                0,
            )
            # Don't use fallback - let the task fail if LLM is unavailable
            raise Exception(
                f"LLM summarization failed: {str(e)}. No fallback summary will be generated."
            ) from e

        finally:
            with contextlib.suppress(Exception):
                loop.close()

        # Update task progress
        update_task_status(db, task_id, "in_progress", progress=0.7)

        # Store summary in PostgreSQL (for backward compatibility)
        media_file.summary = summary_data.get("brief_summary", "Summary generation failed")

        # Store structured summary in OpenSearch
        try:
            summary_service = OpenSearchSummaryService()

            # Get the latest version number for proper versioning
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            max_version = loop.run_until_complete(
                summary_service.get_max_version(file_id, media_file.user_id)
            )
            loop.close()

            # Add file and user information to summary data
            summary_data.update(
                {
                    "file_id": file_id,
                    "user_id": media_file.user_id,
                    "summary_version": max_version + 1,  # Increment version
                    "provider": summary_data["metadata"].get("provider", "unknown"),
                    "model": summary_data["metadata"].get("model", "unknown"),
                }
            )

            # Index in OpenSearch
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            document_id = loop.run_until_complete(summary_service.index_summary(summary_data))
            loop.close()

            if document_id:
                # Store OpenSearch document ID reference
                media_file.summary_opensearch_id = document_id
                logger.info(f"Summary indexed in OpenSearch: {document_id}")

                # Set summary status to completed
                media_file.summary_status = "completed"
                db.commit()

                # Send completion notification with summary text for frontend
                send_summary_notification(
                    media_file.user_id,
                    file_id,
                    "completed",
                    "AI summary generation completed successfully",
                    100,
                    summary_data=media_file.summary,  # Send the brief summary text for frontend
                    summary_opensearch_id=document_id,
                )

        except Exception as e:
            logger.error(f"Failed to store summary in OpenSearch: {e}")

            # Set summary status to failed if OpenSearch indexing fails
            media_file.summary_status = "failed"
            db.commit()

            # Send failure notification
            send_summary_notification(
                media_file.user_id,
                file_id,
                "failed",
                f"Failed to index summary: {str(e)}",
                0,
            )

        # Update task as completed
        update_task_status(db, task_id, "completed", progress=1.0, completed=True)

        logger.info(f"Successfully generated comprehensive summary for file {media_file.filename}")
        return {
            "status": "success",
            "file_id": file_id,
            "summary_data": {
                "bluf": summary_data.get("bluf", ""),
                "speakers_analyzed": len(speaker_stats),
                "processing_time_ms": summary_data["metadata"].get("processing_time_ms"),
                "opensearch_document_id": getattr(media_file, "summary_opensearch_id", None),
            },
        }

    except Exception as e:
        # Handle errors
        logger.error(f"Error summarizing file {file_id}: {str(e)}")

        # Set summary status to failed if not already set
        try:
            if media_file and media_file.summary_status != "failed":
                # Send failed notification
                send_summary_notification(
                    media_file.user_id,
                    file_id,
                    "failed",
                    f"AI summary generation failed: {str(e)}",
                    0,
                )
                media_file.summary_status = "failed"
                db.commit()
        except Exception:
            logger.exception("Error during cleanup")  # Log the exception

        update_task_status(db, task_id, "failed", error_message=str(e), completed=True)
        return {"status": "error", "message": str(e)}

    finally:
        db.close()


@celery_app.task(bind=True, name="translate_transcript")
def translate_transcript_task(self, file_id: int, target_language: str = "en"):
    """
    Translate a transcript to the target language

    Args:
        file_id: Database ID of the MediaFile to translate
        target_language: Target language code (default: English)
    """
    task_id = self.request.id
    db = SessionLocal()

    try:
        # Get media file from database
        media_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
        if not media_file:
            raise ValueError(f"Media file with ID {file_id} not found")

        # Skip if the file is already in the target language
        if media_file.language == target_language:
            return {
                "status": "skipped",
                "message": f"File already in {target_language}",
            }

        # Create task record
        from app.utils.task_utils import create_task_record
        from app.utils.task_utils import update_task_status

        create_task_record(db, task_id, media_file.user_id, file_id, "translation")

        # Update task status
        update_task_status(db, task_id, "in_progress", progress=0.1)

        # Get transcript segments
        transcript_segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.media_file_id == file_id)
            .order_by(TranscriptSegment.start_time)
            .all()
        )

        if not transcript_segments:
            raise ValueError(f"No transcript segments found for file {file_id}")

        # Build full transcript text
        full_transcript = " ".join([segment.text for segment in transcript_segments])

        # Update task progress
        update_task_status(db, task_id, "in_progress", progress=0.3)

        # In a real implementation, we would:
        # 1. Use a translation model (e.g., M2M100, NLLB, or MarianMT)
        # 2. Translate the transcript

        # Simulate translation progress
        update_task_status(db, task_id, "in_progress", progress=0.7)

        # Simulated translation (placeholder)
        translated_text = (
            f"[This is a simulated {target_language} translation of: {full_transcript[:100]}...]"
        )

        # Save the translated text
        media_file.translated_text = translated_text
        db.commit()

        # Update task as completed
        update_task_status(db, task_id, "completed", progress=1.0, completed=True)

        logger.info(f"Successfully translated file {media_file.filename} to {target_language}")
        return {"status": "success", "file_id": file_id}

    except Exception as e:
        # Handle errors
        logger.error(f"Error translating file {file_id}: {str(e)}")
        update_task_status(db, task_id, "failed", error_message=str(e), completed=True)
        return {"status": "error", "message": str(e)}

    finally:
        db.close()
