import asyncio
import json
import logging
import time

import redis

from app.core.celery import celery_app
from app.core.config import settings
from app.db.base import SessionLocal
from app.models.media import MediaFile
from app.models.media import TranscriptSegment
from app.services.llm_service import LLMService
from app.services.opensearch_summary_service import OpenSearchSummaryService

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

        start_time = time.time()

        try:
            # Run LLM summarization
            logger.info(
                f"Starting LLM summarization for transcript of {len(full_transcript)} characters"
            )

            # Log transcript details for debugging
            transcript_length = len(full_transcript)
            speaker_count = len(speaker_stats) if speaker_stats else 0
            logger.info(
                f"Starting LLM summary generation: {transcript_length} chars, {speaker_count} speakers"
            )

            # Estimate token count
            estimated_tokens = transcript_length // 3
            logger.info(f"Estimated input tokens: {estimated_tokens}")

            # Create LLM service using user settings or system settings
            if media_file.user_id:
                llm_service = LLMService.create_from_user_settings(media_file.user_id)
                logger.info(f"Attempted to load user LLM settings for user {media_file.user_id}")
            else:
                llm_service = LLMService.create_from_system_settings()
                logger.info("Attempted to load system LLM settings")

            if not llm_service:
                logger.info("No LLM provider configured - skipping AI summary generation")

                # Set summary status to skipped (indicating no LLM configured)
                media_file.summary_status = "not_configured"
                media_file.summary = None
                db.commit()

                # Send notification that LLM is not configured
                send_summary_notification(
                    media_file.user_id,
                    file_id,
                    "not_configured",
                    "AI summary not available - no LLM provider configured in settings",
                    0,
                )

                # Update task status
                update_task_status(db, task_id, "completed", progress=1.0, completed=True)

                logger.info(
                    f"Transcription completed for file {media_file.filename} (no LLM summary generated)"
                )
                return {
                    "status": "success",
                    "file_id": file_id,
                    "message": "Transcription completed successfully. AI summary not available - no LLM provider configured.",
                }

            logger.info(f"Using LLM: {llm_service.config.provider}/{llm_service.config.model}")
            logger.info(f"User context window: {llm_service.user_context_window} tokens")

            try:
                # Generate summary using user's configured context window
                summary_data = llm_service.generate_summary(
                    transcript=full_transcript,
                    speaker_data=speaker_stats,
                    user_id=media_file.user_id,
                )
            finally:
                # Clean up the service
                llm_service.close()

            processing_time = int((time.time() - start_time) * 1000)
            if "metadata" not in summary_data:
                summary_data["metadata"] = {}
            summary_data["metadata"]["processing_time_ms"] = processing_time

            logger.info(f"LLM summarization completed in {processing_time}ms")

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(f"LLM summarization failed with {error_type}: {error_msg}")
            logger.error(f"Full error details: {repr(e)}")

            # Log additional context
            logger.error(f"Transcript length: {len(full_transcript)} chars")
            logger.error(f"Provider: {llm_provider or 'unknown'}, Model: {llm_model or 'unknown'}")
            logger.error(f"User ID: {media_file.user_id}")

            # Set summary status to failed for graceful handling
            media_file.summary_status = "failed"
            db.commit()

            # Send failed notification with more detail
            detailed_error = f"{error_type}: {error_msg}"
            if "timeout" in error_msg.lower():
                detailed_error = "Request timed out. Try reducing video length or contact support."
            elif "context" in error_msg.lower() or "token" in error_msg.lower():
                detailed_error = (
                    "Content too long for model. Try shorter videos or contact support."
                )

            send_summary_notification(
                media_file.user_id,
                file_id,
                "failed",
                f"AI summary generation failed: {detailed_error}",
                0,
            )

            # Don't use fallback - let the task fail if LLM is unavailable
            raise Exception(
                f"LLM summarization failed: {detailed_error}. No fallback summary will be generated."
            ) from e

        # Update task progress
        update_task_status(db, task_id, "in_progress", progress=0.7)

        # Store summary in PostgreSQL
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
            logger.info("Summary generated successfully but OpenSearch indexing failed")

            # Summary generation succeeded, only OpenSearch failed - task is still successful
            media_file.summary_status = "completed"
            db.commit()

            # Send completion notification with summary data (OpenSearch failed but summary exists)
            send_summary_notification(
                media_file.user_id,
                file_id,
                "completed",
                "AI summary generation completed (search indexing failed)",
                100,
                summary_data=media_file.summary,  # Send the brief summary text for frontend
                summary_opensearch_id=None,  # No OpenSearch ID since indexing failed
            )

        # Send completion notification with summary text for frontend
        try:
            send_summary_notification(
                media_file.user_id,
                file_id,
                "completed",
                "AI summary generation completed successfully",
                100,
                summary_data=summary_data.get("brief_summary", ""),
            )
            logger.info(f"Sent completion notification to user {media_file.user_id}")
        except Exception as notif_error:
            logger.error(f"Failed to send completion notification: {notif_error}")
            # Don't fail the task if notification fails

        logger.info("=== Summarization Task Completed Successfully ===")
        logger.info(f"Total processing time: {int((time.time() - start_time) * 1000)}ms")
        logger.info(f"Final summary length: {len(media_file.summary)} characters")
        logger.info(f"Summary status: {media_file.summary_status}")

        # OpenSearch indexing error handling removed since we're skipping it

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
        # Handle errors with comprehensive logging
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(f"Error summarizing file {file_id}: {error_type}: {error_msg}")
        logger.error("Full error traceback:", exc_info=True)

        # Log additional context for debugging
        try:
            if "media_file" in locals() and media_file:
                logger.error(
                    f"Media file details: ID={media_file.id}, filename={media_file.filename}, user_id={media_file.user_id}"
                )
                if hasattr(media_file, "duration"):
                    logger.error(
                        f"Media duration: {getattr(media_file, 'duration', 'unknown')} seconds"
                    )
        except Exception as ctx_e:
            logger.error(f"Error logging context: {ctx_e}")

        # Set summary status to failed if not already set
        try:
            if "media_file" in locals() and media_file and media_file.summary_status != "failed":
                # Create user-friendly error message
                user_error_msg = error_msg
                if "timeout" in error_msg.lower():
                    user_error_msg = (
                        "Request timed out. The video may be too long. Try with shorter content."
                    )
                elif "context" in error_msg.lower() or "token" in error_msg.lower():
                    user_error_msg = (
                        "Content is too long for the AI model. Try with shorter videos."
                    )
                elif "connection" in error_msg.lower() or "network" in error_msg.lower():
                    user_error_msg = "Network connection failed. Please try again."
                elif not error_msg.strip():
                    user_error_msg = "Unknown error occurred during summary generation"

                # Send failed notification
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

    finally:
        db.close()
