import logging
import os
import tempfile

from app.core.celery import celery_app
from app.core.config import settings
from app.db.session_utils import get_refreshed_object
from app.db.session_utils import session_scope
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.services.minio_service import download_file
from app.services.opensearch_service import index_transcript
from app.services.speaker_embedding_service import SpeakerEmbeddingService
from app.services.speaker_matching_service import SpeakerMatchingService
from app.utils.task_utils import create_task_record
from app.utils.task_utils import update_media_file_status
from app.utils.task_utils import update_task_status

from .audio_processor import get_audio_file_extension
from .audio_processor import prepare_audio_for_transcription
from .metadata_extractor import extract_media_metadata
from .metadata_extractor import update_media_file_metadata
from .notifications import send_completion_notification
from .notifications import send_error_notification
from .notifications import send_processing_notification
from .notifications import send_progress_notification
from .speaker_processor import create_speaker_mapping
from .speaker_processor import extract_unique_speakers
from .speaker_processor import process_segments_with_speakers
from .storage import generate_full_transcript
from .storage import get_unique_speaker_names
from .storage import save_transcript_segments
from .storage import update_media_file_transcription_status
from .waveform_generator import WaveformGenerator
from .whisperx_service import WhisperXService

logger = logging.getLogger(__name__)


# Import for automatic summarization, speaker identification, and analytics
def trigger_automatic_summarization(file_id: int, file_uuid: str):
    """Trigger automatic summarization, speaker identification, and analytics after transcription completes"""
    try:
        # First trigger analytics computation
        from app.tasks.analytics import analyze_transcript_task

        analytics_task = analyze_transcript_task.delay(file_uuid=file_uuid)
        logger.info(
            f"Automatic analytics computation task {analytics_task.id} started for file {file_id}"
        )

        # Then trigger speaker identification
        from app.tasks.speaker_tasks import identify_speakers_llm_task

        speaker_task = identify_speakers_llm_task.delay(file_uuid=file_uuid)
        logger.info(
            f"Automatic speaker identification task {speaker_task.id} started for file {file_id}"
        )

        # Trigger summarization (this will use the speaker suggestions when available)
        from app.tasks.summarization import summarize_transcript_task

        summary_task = summarize_transcript_task.delay(file_uuid=file_uuid)
        logger.info(f"Automatic summarization task {summary_task.id} started for file {file_id}")

        # Trigger topic extraction (after transcription completes, independent of summarization)
        from app.tasks.topic_extraction import extract_topics_task

        topic_task = extract_topics_task.delay(file_uuid=file_uuid, force_regenerate=False)
        logger.info(f"Automatic topic extraction task {topic_task.id} started for file {file_id}")
    except Exception as e:
        logger.warning(f"Failed to start automatic tasks for file {file_id}: {e}")


@celery_app.task(bind=True, name="transcribe_audio")
def transcribe_audio_task(self, file_uuid: str):
    """
    Process an audio/video file with WhisperX for transcription and Pyannote for diarization.

    Args:
        file_uuid: UUID of the MediaFile to transcribe
    """
    from app.utils.uuid_helpers import get_file_by_uuid

    task_id = self.request.id
    user_id = None
    file_id = None

    try:
        # Step 1: Get file information and update status
        with session_scope() as db:
            media_file = get_file_by_uuid(db, file_uuid)
            if not media_file:
                logger.error(f"Media file with UUID {file_uuid} not found")
                return {
                    "status": "error",
                    "message": f"Media file with UUID {file_uuid} not found",
                }

            file_id = media_file.id  # Get internal ID for database operations
            user_id = media_file.user_id
            file_path = media_file.storage_path
            file_name = media_file.filename
            content_type = media_file.content_type

            # Update to processing status
            update_media_file_status(db, file_id, FileStatus.PROCESSING)

        # Send processing notification
        send_processing_notification(user_id, file_id)

        # Step 2: Create and initialize task record
        with session_scope() as db:
            create_task_record(db, task_id, user_id, file_id, "transcription")
            update_task_status(db, task_id, "in_progress", progress=0.1)

        # Step 3: Download file from MinIO
        logger.info(f"Downloading file {file_path}")
        file_data, _, content_type = download_file(file_path)

        # Step 4: Process file
        file_ext = get_audio_file_extension(content_type, file_name)

        with tempfile.TemporaryDirectory() as temp_dir:
            # Save downloaded file
            temp_file_path = os.path.join(temp_dir, f"input{file_ext}")
            with open(temp_file_path, "wb") as f:
                f.write(file_data.read())

            # Step 5: Extract metadata
            try:
                extracted_metadata = extract_media_metadata(temp_file_path)
                if extracted_metadata:
                    with session_scope() as db:
                        media_file = get_refreshed_object(db, MediaFile, file_id)
                        if media_file:
                            update_media_file_metadata(
                                media_file,
                                extracted_metadata,
                                content_type,
                                temp_file_path,
                            )
                            db.commit()
            except Exception as e:
                logger.warning(f"Error extracting media metadata: {e}")

            # Step 5.5: Generate waveform data
            with session_scope() as db:
                update_task_status(db, task_id, "in_progress", progress=0.25)

            send_progress_notification(user_id, file_id, 0.25, "Generating waveform visualization")
            try:
                waveform_generator = WaveformGenerator()
                waveform_data = waveform_generator.generate_waveform_data(temp_file_path)

                if waveform_data:
                    with session_scope() as db:
                        media_file = get_refreshed_object(db, MediaFile, file_id)
                        if media_file:
                            media_file.waveform_data = waveform_data
                            db.commit()
                            logger.info(f"Waveform data cached for file {file_id}")
            except Exception as e:
                logger.warning(f"Error generating waveform data: {e}")
                # Continue processing even if waveform generation fails

            # Step 6: Prepare audio for transcription
            with session_scope() as db:
                update_task_status(db, task_id, "in_progress", progress=0.3)

            send_progress_notification(user_id, file_id, 0.3, "Preparing audio for transcription")
            audio_file_path = prepare_audio_for_transcription(
                temp_file_path, content_type, temp_dir
            )

            # Step 7: Run WhisperX pipeline
            try:
                whisperx_service = WhisperXService(
                    model_name="medium.en", models_dir=settings.MODEL_BASE_DIR
                )

                with session_scope() as db:
                    update_task_status(db, task_id, "in_progress", progress=0.4)

                send_progress_notification(user_id, file_id, 0.4, "Running AI transcription")

                # Create progress callback for detailed WhisperX updates
                def whisperx_progress_callback(progress, message):
                    with session_scope() as db:
                        update_task_status(db, task_id, "in_progress", progress=progress)
                    send_progress_notification(user_id, file_id, progress, message)

                # Run full WhisperX pipeline with progress updates
                result = whisperx_service.process_full_pipeline(
                    audio_file_path,
                    settings.HUGGINGFACE_TOKEN,
                    progress_callback=whisperx_progress_callback,
                )

                # Check if transcription produced any valid content
                if not result or not result.get("segments") or len(result["segments"]) == 0:
                    error_msg = (
                        "No audio content could be detected in this file. "
                        "The file may be corrupted, contain only silence, or be in an unsupported format. "
                        "Please check the file and try uploading again."
                    )
                    logger.warning(f"No valid audio content found in file {file_id}: {file_name}")

                    with session_scope() as db:
                        update_task_status(
                            db,
                            task_id,
                            "failed",
                            error_message=error_msg,
                            completed=True,
                        )
                        update_media_file_status(db, file_id, FileStatus.ERROR)
                        # Store the specific error for user guidance
                        media_file = get_refreshed_object(db, MediaFile, file_id)
                        if media_file:
                            media_file.last_error_message = error_msg
                            db.commit()

                    send_error_notification(user_id, file_id, error_msg)
                    return {
                        "status": "error",
                        "message": error_msg,
                        "error_type": "no_valid_audio",
                    }

                # Check if segments contain actual transcribable content
                has_content = False
                for segment in result["segments"]:
                    if segment.get("text", "").strip():
                        has_content = True
                        break

                if not has_content:
                    error_msg = (
                        "No speech could be detected in this file. "
                        "The file may contain only music, background noise, or silence. "
                        "Please verify the file contains clear speech and try again."
                    )
                    logger.warning(f"No speech content found in file {file_id}: {file_name}")

                    with session_scope() as db:
                        update_task_status(
                            db,
                            task_id,
                            "failed",
                            error_message=error_msg,
                            completed=True,
                        )
                        update_media_file_status(db, file_id, FileStatus.ERROR)
                        # Store the specific error for user guidance
                        media_file = get_refreshed_object(db, MediaFile, file_id)
                        if media_file:
                            media_file.last_error_message = error_msg
                            db.commit()

                    send_error_notification(user_id, file_id, error_msg)
                    return {
                        "status": "error",
                        "message": error_msg,
                        "error_type": "no_speech_content",
                    }

                # Step 8: Process speakers and segments (WhisperX callback handles 0.4->0.65)
                send_progress_notification(user_id, file_id, 0.68, "Processing speaker segments")
                unique_speakers = extract_unique_speakers(result["segments"])

                with session_scope() as db:
                    speaker_mapping = create_speaker_mapping(db, user_id, file_id, unique_speakers)
                    update_task_status(db, task_id, "in_progress", progress=0.72)

                send_progress_notification(user_id, file_id, 0.72, "Organizing transcript segments")
                processed_segments = process_segments_with_speakers(
                    result["segments"], speaker_mapping
                )

                with session_scope() as db:
                    update_task_status(db, task_id, "in_progress", progress=0.75)

                send_progress_notification(user_id, file_id, 0.75, "Saving transcript to database")
                # Step 9: Save to database
                with session_scope() as db:
                    save_transcript_segments(db, file_id, processed_segments)
                    update_media_file_transcription_status(
                        db, file_id, processed_segments, result.get("language", "en")
                    )
                    update_task_status(db, task_id, "in_progress", progress=0.78)

                # Step 9.5: Extract speaker embeddings and match profiles
                # CRITICAL: Force GPU synchronization before loading embedding model
                # Ensure all WhisperX operations are complete and memory is freed
                from app.utils.hardware_detection import detect_hardware

                hardware_config = detect_hardware()
                hardware_config.optimize_memory_usage()
                logger.info("GPU memory synchronized before speaker embedding extraction")

                send_progress_notification(
                    user_id, file_id, 0.78, "Processing speaker identification"
                )
                try:
                    embedding_service = SpeakerEmbeddingService()

                    with session_scope() as db:
                        matching_service = SpeakerMatchingService(db, embedding_service)

                        # Process speaker embeddings and matching
                        logger.info(
                            f"TRANSCRIPTION DEBUG: Starting speaker matching for {len(speaker_mapping)} speakers"
                        )
                        speaker_results = matching_service.process_speaker_segments(
                            audio_file_path,
                            file_id,
                            user_id,
                            processed_segments,
                            speaker_mapping,
                        )
                        logger.info(
                            f"TRANSCRIPTION DEBUG: Speaker matching completed, got {len(speaker_results) if speaker_results else 0} results"
                        )

                        update_task_status(db, task_id, "in_progress", progress=0.82)

                    logger.info(
                        f"Speaker identification completed: {len(speaker_results)} speakers processed"
                    )

                    # CRITICAL: Clean up embedding service and matching service to free VRAM
                    # PyAnnote embedding model uses ~500 MB and must be deleted before OpenSearch indexing
                    embedding_service.cleanup()
                    del embedding_service
                    del matching_service

                except Exception as e:
                    logger.warning(f"Error in speaker identification: {e}")
                    # Continue with transcription even if speaker matching fails

                # Force GPU memory cleanup checkpoint before OpenSearch indexing
                # This ensures all models are fully cleared from VRAM
                from app.utils.hardware_detection import detect_hardware

                hardware_config = detect_hardware()
                hardware_config.optimize_memory_usage()
                logger.info("GPU memory cleanup checkpoint completed")

                with session_scope() as db:
                    update_task_status(db, task_id, "in_progress", progress=0.85)

                send_progress_notification(user_id, file_id, 0.85, "Indexing for search")
                # Step 10: Index in search
                try:
                    full_transcript = generate_full_transcript(processed_segments)
                    speaker_names = get_unique_speaker_names(processed_segments)

                    with session_scope() as db:
                        media_file = get_refreshed_object(db, MediaFile, file_id)
                        file_title = (
                            (media_file.title or media_file.filename)
                            if media_file
                            else f"File {file_id}"
                        )
                        file_uuid = media_file.uuid if media_file else None

                    if file_uuid:
                        index_transcript(
                            file_id, file_uuid, user_id, full_transcript, speaker_names, file_title
                        )
                    else:
                        logger.warning(
                            f"Could not index transcript: file_uuid not found for file_id {file_id}"
                        )
                except Exception as e:
                    logger.warning(f"Error indexing transcript: {e}")

                # Step 11: Finalize
                send_progress_notification(user_id, file_id, 0.95, "Finalizing transcription")
                with session_scope() as db:
                    update_task_status(db, task_id, "completed", progress=1.0, completed=True)

                # Send completion notification
                send_completion_notification(user_id, file_id)

                # Trigger automatic summarization
                logger.info(
                    f"Transcription completed successfully for file {file_id}, triggering automatic summarization"
                )
                trigger_automatic_summarization(file_id, file_uuid)

                return {
                    "status": "success",
                    "file_id": file_id,
                    "segments": len(processed_segments),
                }

            except Exception as e:
                logger.error(f"Error in WhisperX processing: {str(e)}")

                # Provide user-friendly error messages for common issues
                error_message = str(e)
                if "libcudnn" in error_message.lower():
                    error_message = (
                        "Audio processing failed due to a system library compatibility issue. "
                        "The transcription service requires updated dependencies. "
                        "Please contact support for assistance."
                    )
                elif "cuda" in error_message.lower() and "out of memory" in error_message.lower():
                    error_message = (
                        "GPU out of memory error. The audio file may be too large for available GPU resources. "
                        "Please try with a shorter audio file or contact support."
                    )
                elif "cuda" in error_message.lower() or "gpu" in error_message.lower():
                    error_message = (
                        "GPU processing error occurred during transcription. "
                        "The system may need reconfiguration. "
                        "Please try again or contact support if the issue persists."
                    )
                elif "model" in error_message.lower() and (
                    "download" in error_message.lower() or "load" in error_message.lower()
                ):
                    error_message = (
                        "Failed to download or load AI models. "
                        "Please check your internet connection and try again. "
                        "If the problem persists, contact support."
                    )

                with session_scope() as db:
                    update_task_status(
                        db,
                        task_id,
                        "failed",
                        error_message=error_message,
                        completed=True,
                    )
                    update_media_file_status(db, file_id, FileStatus.ERROR)

                send_error_notification(user_id, file_id, error_message)
                return {"status": "error", "message": error_message}

    except Exception as e:
        logger.error(f"Error processing file {file_id}: {str(e)}")

        try:
            with session_scope() as db:
                update_media_file_status(db, file_id, FileStatus.ERROR)
                update_task_status(db, task_id, "failed", error_message=str(e), completed=True)

            if user_id:
                send_error_notification(user_id, file_id, str(e))
        except Exception as update_err:
            logger.error(f"Error updating task status: {update_err}")

        return {"status": "error", "message": str(e)}
