import asyncio
import json
import logging
import time
from typing import Optional

import redis

from app.core.celery import celery_app
from app.core.config import settings
from app.db.base import SessionLocal
from app.models.media import TranscriptSegment
from app.services.llm_service import LLMService
from app.services.opensearch_summary_service import OpenSearchSummaryService

# Setup logging
logger = logging.getLogger(__name__)


def _get_speaker_name(segment) -> str:
    """Get the best available speaker name from a segment."""
    if not segment.speaker:
        return "Unknown Speaker"

    speaker = segment.speaker
    # Use display_name if verified, otherwise use suggested_name or fallback to original name
    if speaker.display_name and speaker.verified:
        return speaker.display_name
    if speaker.suggested_name and speaker.confidence and speaker.confidence >= 0.75:
        return f"{speaker.suggested_name} (suggested)"
    return speaker.name  # Original diarization label


def _build_transcript_and_stats(transcript_segments) -> tuple[str, dict]:
    """Build full transcript text and speaker statistics from segments."""
    full_transcript = ""
    current_speaker = None
    speaker_stats = {}

    for segment in transcript_segments:
        speaker_name = _get_speaker_name(segment)

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
            full_transcript += " "

        # Add segment text with timestamp for reference
        timestamp = f"[{int(segment.start_time // 60):02d}:{int(segment.start_time % 60):02d}]"
        full_transcript += f"{timestamp} {segment.text}"

    # Calculate speaker percentages
    total_time = sum(stats["total_time"] for stats in speaker_stats.values())
    for stats in speaker_stats.values():
        stats["percentage"] = (stats["total_time"] / total_time * 100) if total_time > 0 else 0

    return full_transcript, speaker_stats


def _handle_force_regeneration(media_file, db) -> None:
    """Handle force regeneration by clearing existing summaries."""
    logger.info(
        f"Force regenerate requested - clearing existing summaries for file {media_file.id}"
    )

    # Clear OpenSearch summary if it exists
    if media_file.summary_opensearch_id:
        try:
            OpenSearchSummaryService()
            logger.info(f"Clearing OpenSearch document {media_file.summary_opensearch_id}")
        except Exception as e:
            logger.warning(f"Could not clear OpenSearch summary: {e}")

    # Clear PostgreSQL summary fields
    media_file.summary_data = None
    media_file.summary_opensearch_id = None


def _handle_no_llm_configured(media_file, file_id: int, task_id: str, db) -> dict:
    """Handle case when no LLM provider is configured."""
    from app.utils.task_utils import update_task_status

    logger.info("No LLM provider configured - skipping AI summary generation")

    media_file.summary_status = "not_configured"
    media_file.summary_data = None
    db.commit()

    send_summary_notification(
        media_file.user_id,
        file_id,
        "not_configured",
        "AI summary not available - no LLM provider configured in settings",
        0,
    )

    update_task_status(db, task_id, "completed", progress=1.0, completed=True)

    logger.info(
        f"Transcription completed for file {media_file.filename} (no LLM summary generated)"
    )
    return {
        "status": "success",
        "file_id": file_id,
        "message": "Transcription completed successfully. AI summary not available - no LLM provider configured.",
    }


def _create_user_friendly_error(error_msg: str) -> str:
    """Create a user-friendly error message from an exception message."""
    if "timeout" in error_msg.lower():
        return "Request timed out. Try reducing video length or contact support."
    if "context" in error_msg.lower() or "token" in error_msg.lower():
        return "Content too long for model. Try shorter videos or contact support."
    if "connection" in error_msg.lower() or "network" in error_msg.lower():
        return "Network connection failed. Please try again."
    if not error_msg.strip():
        return "Unknown error occurred during summary generation"
    return error_msg


def _handle_llm_error(
    e: Exception,
    media_file,
    file_id: int,
    full_transcript: str,
    llm_provider: Optional[str],
    llm_model: Optional[str],
    db,
) -> None:
    """Handle LLM summarization errors."""
    error_type = type(e).__name__
    error_msg = str(e)
    logger.error(f"LLM summarization failed with {error_type}: {error_msg}")
    logger.error(f"Full error details: {repr(e)}")
    logger.error(f"Transcript length: {len(full_transcript)} chars")
    logger.error(f"Provider: {llm_provider or 'unknown'}, Model: {llm_model or 'unknown'}")
    logger.error(f"User ID: {media_file.user_id}")

    media_file.summary_status = "failed"
    db.commit()

    detailed_error = _create_user_friendly_error(error_msg)
    send_summary_notification(
        media_file.user_id,
        file_id,
        "failed",
        f"AI summary generation failed: {detailed_error}",
        0,
    )

    raise Exception(
        f"LLM summarization failed: {detailed_error}. No fallback summary will be generated."
    ) from e


def _store_summary_to_opensearch(summary_data: dict, media_file, file_id: int) -> Optional[str]:
    """Store summary to OpenSearch and return document ID."""
    summary_service = OpenSearchSummaryService()

    # Get the latest version number for proper versioning
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    max_version = loop.run_until_complete(
        summary_service.get_max_version(file_id, media_file.user_id)
    )
    loop.close()

    # Make a copy for OpenSearch indexing with tracking fields
    opensearch_data = summary_data.copy()
    opensearch_data.update(
        {
            "file_id": file_id,
            "user_id": media_file.user_id,
            "summary_version": max_version + 1,
            "provider": summary_data["metadata"].get("provider", "unknown"),
            "model": summary_data["metadata"].get("model", "unknown"),
        }
    )

    # Index in OpenSearch
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    document_id = loop.run_until_complete(summary_service.index_summary(opensearch_data))
    loop.close()

    return document_id


def _send_completion_notification(
    media_file, file_id: int, summary_data: dict, document_id: Optional[str], message: str
) -> None:
    """Send completion notification with summary preview."""
    summary_preview = (
        summary_data.get("brief_summary")
        or summary_data.get("bluf")
        or "Summary generated successfully"
    )
    send_summary_notification(
        media_file.user_id,
        file_id,
        "completed",
        message,
        100,
        summary_data=summary_preview,
        summary_opensearch_id=document_id,
    )


def _finalize_summary_storage(summary_data: dict, media_file, file_id: int, db) -> Optional[str]:
    """Store summary to OpenSearch and handle all completion scenarios."""
    try:
        document_id = _store_summary_to_opensearch(summary_data, media_file, file_id)

        if document_id:
            media_file.summary_opensearch_id = document_id
            logger.info(f"Summary indexed in OpenSearch: {document_id}")
            media_file.summary_status = "completed"
            db.commit()
            _send_completion_notification(
                media_file,
                file_id,
                summary_data,
                document_id,
                "AI summary generation completed successfully",
            )
        else:
            logger.warning("OpenSearch client not available, summary saved to PostgreSQL only")
            media_file.summary_status = "completed"
            db.commit()
            _send_completion_notification(
                media_file,
                file_id,
                summary_data,
                None,
                "AI summary generation completed (search not available)",
            )
        return document_id

    except Exception as e:
        logger.error(f"Failed to store summary in OpenSearch: {e}")
        logger.info("Summary generated successfully but OpenSearch indexing failed")
        media_file.summary_status = "completed"
        db.commit()
        _send_completion_notification(
            media_file,
            file_id,
            summary_data,
            None,
            "AI summary generation completed (search indexing failed)",
        )
        return None


def _log_error_context(media_file) -> None:
    """Log additional context for debugging errors."""
    try:
        if media_file:
            logger.error(
                f"Media file details: ID={media_file.id}, filename={media_file.filename}, "
                f"user_id={media_file.user_id}"
            )
            if hasattr(media_file, "duration"):
                logger.error(
                    f"Media duration: {getattr(media_file, 'duration', 'unknown')} seconds"
                )
    except Exception as ctx_e:
        logger.error(f"Error logging context: {ctx_e}")


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
            "file_id": file_metadata.get("file_uuid"),  # Use UUID from metadata
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


def _generate_llm_summary(
    media_file, file_id: int, full_transcript: str, speaker_stats: dict, task_id: str, db
) -> dict:
    """Generate LLM summary and return summary data."""
    start_time = time.time()
    llm_provider = None
    llm_model = None

    # Log transcript details for debugging
    transcript_length = len(full_transcript)
    speaker_count = len(speaker_stats) if speaker_stats else 0
    logger.info(
        f"Starting LLM summary generation: {transcript_length} chars, {speaker_count} speakers"
    )
    logger.info(f"Estimated input tokens: {transcript_length // 3}")

    # Create LLM service using user settings or system settings
    if media_file.user_id:
        llm_service = LLMService.create_from_user_settings(media_file.user_id)
        logger.info(f"Attempted to load user LLM settings for user {media_file.user_id}")
    else:
        llm_service = LLMService.create_from_system_settings()
        logger.info("Attempted to load system LLM settings")

    if not llm_service:
        return None  # Signal that no LLM is configured

    llm_provider = llm_service.config.provider
    llm_model = llm_service.config.model
    logger.info(f"Using LLM: {llm_provider}/{llm_model}")
    logger.info(f"User context window: {llm_service.user_context_window} tokens")

    try:
        summary_data = llm_service.generate_summary(
            transcript=full_transcript,
            speaker_data=speaker_stats,
            user_id=media_file.user_id,
        )
    except Exception as e:
        _handle_llm_error(e, media_file, file_id, full_transcript, llm_provider, llm_model, db)
    finally:
        llm_service.close()

    processing_time = int((time.time() - start_time) * 1000)
    if "metadata" not in summary_data:
        summary_data["metadata"] = {}
    summary_data["metadata"]["processing_time_ms"] = processing_time
    logger.info(f"LLM summarization completed in {processing_time}ms")

    return summary_data


def _handle_task_error(e: Exception, media_file, file_id: int, task_id: str, db) -> dict:
    """Handle task-level errors and return error result."""
    from app.utils.task_utils import update_task_status

    error_type = type(e).__name__
    error_msg = str(e)
    logger.error(f"Error summarizing file {file_id}: {error_type}: {error_msg}")
    logger.error("Full error traceback:", exc_info=True)

    _log_error_context(media_file)

    # Set summary status to failed if not already set
    try:
        if media_file and media_file.summary_status != "failed":
            user_error_msg = _create_user_friendly_error(error_msg)
            send_summary_notification(
                media_file.user_id,
                file_id,
                "failed",
                f"AI summary generation failed: {user_error_msg}",
                0,
            )
            media_file.summary_status = "failed"
            db.commit()
    except Exception as cleanup_e:
        logger.error(
            f"Error during cleanup: {type(cleanup_e).__name__}: {cleanup_e}", exc_info=True
        )

    update_task_status(db, task_id, "failed", error_message=error_msg, completed=True)
    return {"status": "error", "message": error_msg}


@celery_app.task(bind=True, name="summarize_transcript")
def summarize_transcript_task(
    self,
    file_uuid: str,
    force_regenerate: bool = False,
):
    """
    Generate a comprehensive summary of a transcript using LLM with structured BLUF format

    This task runs AFTER speaker embedding matching has been completed to ensure
    accurate speaker information is available for summarization.

    Args:
        file_uuid: UUID of the MediaFile to summarize
        force_regenerate: If True, clear existing summaries before regenerating
    """
    from app.utils.task_utils import create_task_record
    from app.utils.task_utils import update_task_status
    from app.utils.uuid_helpers import get_file_by_uuid

    task_id = self.request.id
    db = SessionLocal()
    media_file = None
    file_id = None

    try:
        media_file = get_file_by_uuid(db, file_uuid)
        if not media_file:
            raise ValueError(f"Media file with UUID {file_uuid} not found")

        file_id = media_file.id
        create_task_record(db, task_id, media_file.user_id, file_id, "summarization")
        update_task_status(db, task_id, "in_progress", progress=0.1)

        if force_regenerate:
            _handle_force_regeneration(media_file, db)

        media_file.summary_status = "processing"
        db.commit()

        action = "regeneration" if force_regenerate else "generation"
        send_summary_notification(
            media_file.user_id, file_id, "processing", f"AI summary {action} started", 10
        )

        # Get and validate transcript segments
        transcript_segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.media_file_id == file_id)
            .order_by(TranscriptSegment.start_time)
            .all()
        )
        if not transcript_segments:
            raise ValueError(f"No transcript segments found for file {file_id}")

        full_transcript, speaker_stats = _build_transcript_and_stats(transcript_segments)

        update_task_status(db, task_id, "in_progress", progress=0.3)
        send_summary_notification(
            media_file.user_id, file_id, "processing", "Analyzing speakers and content", 30
        )

        logger.info(
            f"Generating LLM summary for file {media_file.filename} "
            f"(length: {len(full_transcript)} chars)"
        )
        send_summary_notification(
            media_file.user_id, file_id, "processing", "Generating AI summary with LLM", 50
        )

        start_time = time.time()
        summary_data = _generate_llm_summary(
            media_file, file_id, full_transcript, speaker_stats, task_id, db
        )

        if summary_data is None:
            return _handle_no_llm_configured(media_file, file_id, task_id, db)

        update_task_status(db, task_id, "in_progress", progress=0.7)
        media_file.summary_data = summary_data
        media_file.summary_schema_version = 1

        _finalize_summary_storage(summary_data, media_file, file_id, db)

        logger.info("=== Summarization Task Completed Successfully ===")
        logger.info(f"Total processing time: {int((time.time() - start_time) * 1000)}ms")
        logger.info(
            f"Final summary data keys: "
            f"{list(media_file.summary_data.keys()) if media_file.summary_data else 'None'}"
        )
        logger.info(f"Summary status: {media_file.summary_status}")

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
        return _handle_task_error(e, media_file, file_id, task_id, db)

    finally:
        db.close()
