import logging
import os
import tempfile
from dataclasses import dataclass

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
from .whisperx_service import WhisperXService

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionContext:
    """Context holder for transcription task state."""

    task_id: str
    file_id: int
    file_uuid: str
    user_id: int
    file_path: str
    file_name: str
    content_type: str


def _get_media_file_context(file_uuid: str, task_id: str) -> TranscriptionContext | None:
    """Get media file and create transcription context."""
    from app.utils.uuid_helpers import get_file_by_uuid

    with session_scope() as db:
        media_file = get_file_by_uuid(db, file_uuid)
        if not media_file:
            logger.error(f"Media file with UUID {file_uuid} not found")
            return None

        ctx = TranscriptionContext(
            task_id=task_id,
            file_id=media_file.id,
            file_uuid=file_uuid,
            user_id=media_file.user_id,
            file_path=media_file.storage_path,
            file_name=media_file.filename,
            content_type=media_file.content_type,
        )
        update_media_file_status(db, ctx.file_id, FileStatus.PROCESSING)
        return ctx


def _handle_transcription_failure(
    ctx: TranscriptionContext, task_id: str, error_msg: str, error_type: str
) -> dict:
    """Handle transcription failure by updating status and sending notification."""
    with session_scope() as db:
        update_task_status(db, task_id, "failed", error_message=error_msg, completed=True)
        update_media_file_status(db, ctx.file_id, FileStatus.ERROR)
        media_file = get_refreshed_object(db, MediaFile, ctx.file_id)
        if media_file:
            media_file.last_error_message = error_msg
            db.commit()

    send_error_notification(ctx.user_id, ctx.file_id, error_msg)
    return {"status": "error", "message": error_msg, "error_type": error_type}


def _validate_transcription_result(
    result: dict, ctx: TranscriptionContext, task_id: str
) -> dict | None:
    """Validate transcription result has valid content. Returns error dict if invalid, None if valid."""
    if not result or not result.get("segments") or len(result["segments"]) == 0:
        error_msg = (
            "No audio content could be detected in this file. "
            "The file may be corrupted, contain only silence, or be in an unsupported format. "
            "Please check the file and try uploading again."
        )
        logger.warning(f"No valid audio content found in file {ctx.file_id}: {ctx.file_name}")
        return _handle_transcription_failure(ctx, task_id, error_msg, "no_valid_audio")

    # Check if segments contain actual transcribable content
    has_content = any(segment.get("text", "").strip() for segment in result["segments"])
    if not has_content:
        error_msg = (
            "No speech could be detected in this file. "
            "The file may contain only music, background noise, or silence. "
            "Please verify the file contains clear speech and try again."
        )
        logger.warning(f"No speech content found in file {ctx.file_id}: {ctx.file_name}")
        return _handle_transcription_failure(ctx, task_id, error_msg, "no_speech_content")

    return None


def _get_user_friendly_error_message(error_message: str) -> str:
    """Convert technical error to user-friendly message."""
    error_lower = error_message.lower()

    if "libcudnn" in error_lower:
        return (
            "Audio processing failed due to a system library compatibility issue. "
            "The transcription service requires updated dependencies. "
            "Please contact support for assistance."
        )
    if "cuda" in error_lower and "out of memory" in error_lower:
        return (
            "GPU out of memory error. The audio file may be too large for available GPU resources. "
            "Please try with a shorter audio file or contact support."
        )
    if "cuda" in error_lower or "gpu" in error_lower:
        return (
            "GPU processing error occurred during transcription. "
            "The system may need reconfiguration. "
            "Please try again or contact support if the issue persists."
        )
    if "model" in error_lower and ("download" in error_lower or "load" in error_lower):
        return (
            "Failed to download or load AI models. "
            "Please check your internet connection and try again. "
            "If the problem persists, contact support."
        )
    return error_message


def _process_speaker_embeddings(
    ctx: TranscriptionContext, audio_file_path: str, processed_segments: list, speaker_mapping: dict
) -> None:
    """Extract speaker embeddings and match profiles."""
    from app.utils.hardware_detection import detect_hardware

    # Force GPU synchronization before loading embedding model
    hardware_config = detect_hardware()
    hardware_config.optimize_memory_usage()
    logger.info("GPU memory synchronized before speaker embedding extraction")

    send_progress_notification(ctx.user_id, ctx.file_id, 0.78, "Processing speaker identification")

    embedding_service = SpeakerEmbeddingService()
    try:
        with session_scope() as db:
            matching_service = SpeakerMatchingService(db, embedding_service)
            logger.info(
                f"TRANSCRIPTION DEBUG: Starting speaker matching for {len(speaker_mapping)} speakers"
            )
            speaker_results = matching_service.process_speaker_segments(
                audio_file_path, ctx.file_id, ctx.user_id, processed_segments, speaker_mapping
            )
            logger.info(
                f"TRANSCRIPTION DEBUG: Speaker matching completed, got {len(speaker_results) if speaker_results else 0} results"
            )
            update_task_status(db, ctx.task_id, "in_progress", progress=0.82)

        logger.info(f"Speaker identification completed: {len(speaker_results)} speakers processed")
    finally:
        # Clean up embedding service to free VRAM
        embedding_service.cleanup()


def _index_transcript_in_search(ctx: TranscriptionContext, processed_segments: list) -> None:
    """Index transcript in OpenSearch."""
    full_transcript = generate_full_transcript(processed_segments)
    speaker_names = get_unique_speaker_names(processed_segments)

    with session_scope() as db:
        media_file = get_refreshed_object(db, MediaFile, ctx.file_id)
        file_title = (
            (media_file.title or media_file.filename) if media_file else f"File {ctx.file_id}"
        )
        file_uuid = media_file.uuid if media_file else None

    if file_uuid:
        index_transcript(
            ctx.file_id, file_uuid, ctx.user_id, full_transcript, speaker_names, file_title
        )
    else:
        logger.warning(f"Could not index transcript: file_uuid not found for file_id {ctx.file_id}")


def _run_whisperx_pipeline(
    ctx: TranscriptionContext,
    audio_file_path: str,
    min_speakers: int | None,
    max_speakers: int | None,
    num_speakers: int | None,
) -> dict:
    """Run the WhisperX transcription pipeline."""
    whisperx_service = WhisperXService(
        model_name=os.getenv("WHISPER_MODEL", "large-v2"),
        models_dir=settings.MODEL_BASE_DIR,
    )

    with session_scope() as db:
        update_task_status(db, ctx.task_id, "in_progress", progress=0.4)

    send_progress_notification(ctx.user_id, ctx.file_id, 0.4, "Running AI transcription")

    def whisperx_progress_callback(progress, message):
        with session_scope() as db:
            update_task_status(db, ctx.task_id, "in_progress", progress=progress)
        send_progress_notification(ctx.user_id, ctx.file_id, progress, message)

    return whisperx_service.process_full_pipeline(
        audio_file_path,
        settings.HUGGINGFACE_TOKEN,
        progress_callback=whisperx_progress_callback,
        min_speakers=min_speakers if min_speakers is not None else settings.MIN_SPEAKERS,
        max_speakers=max_speakers if max_speakers is not None else settings.MAX_SPEAKERS,
        num_speakers=num_speakers if num_speakers is not None else settings.NUM_SPEAKERS,
    )


def _process_transcription_result(
    ctx: TranscriptionContext, result: dict, audio_file_path: str
) -> dict:
    """Process successful transcription result including speakers, indexing, and finalization."""
    from app.utils.hardware_detection import detect_hardware

    # Process speakers and segments
    send_progress_notification(ctx.user_id, ctx.file_id, 0.68, "Processing speaker segments")
    unique_speakers = extract_unique_speakers(result["segments"])

    with session_scope() as db:
        speaker_mapping = create_speaker_mapping(db, ctx.user_id, ctx.file_id, unique_speakers)
        update_task_status(db, ctx.task_id, "in_progress", progress=0.72)

    send_progress_notification(ctx.user_id, ctx.file_id, 0.72, "Organizing transcript segments")
    processed_segments = process_segments_with_speakers(result["segments"], speaker_mapping)

    # Clean garbage words
    with session_scope() as db:
        from app.services import system_settings_service

        garbage_config = system_settings_service.get_garbage_cleanup_config(db)

    if garbage_config["garbage_cleanup_enabled"]:
        processed_segments, garbage_count = clean_garbage_words(
            processed_segments, garbage_config["max_word_length"]
        )
        if garbage_count > 0:
            logger.info(
                f"Cleaned {garbage_count} garbage word(s) from file {ctx.file_id} "
                f"(threshold: {garbage_config['max_word_length']} chars)"
            )

    with session_scope() as db:
        update_task_status(db, ctx.task_id, "in_progress", progress=0.75)

    # Save to database
    send_progress_notification(ctx.user_id, ctx.file_id, 0.75, "Saving transcript to database")
    with session_scope() as db:
        save_transcript_segments(db, ctx.file_id, processed_segments)
        update_media_file_transcription_status(
            db, ctx.file_id, processed_segments, result.get("language", "en")
        )
        update_task_status(db, ctx.task_id, "in_progress", progress=0.78)

    # Speaker embeddings
    try:
        _process_speaker_embeddings(ctx, audio_file_path, processed_segments, speaker_mapping)
    except Exception as e:
        logger.warning(f"Error in speaker identification: {e}")

    # Force GPU memory cleanup before OpenSearch indexing
    hardware_config = detect_hardware()
    hardware_config.optimize_memory_usage()
    logger.info("GPU memory cleanup checkpoint completed")

    with session_scope() as db:
        update_task_status(db, ctx.task_id, "in_progress", progress=0.85)

    # Index in search
    send_progress_notification(ctx.user_id, ctx.file_id, 0.85, "Indexing for search")
    try:
        _index_transcript_in_search(ctx, processed_segments)
    except Exception as e:
        logger.warning(f"Error indexing transcript: {e}")

    # Finalize
    send_progress_notification(ctx.user_id, ctx.file_id, 0.95, "Finalizing transcription")
    with session_scope() as db:
        update_task_status(db, ctx.task_id, "completed", progress=1.0, completed=True)

    send_completion_notification(ctx.user_id, ctx.file_id)

    logger.info(
        f"Transcription completed successfully for file {ctx.file_id}, triggering automatic summarization"
    )
    trigger_automatic_summarization(ctx.file_id, ctx.file_uuid)

    return {"status": "success", "file_id": ctx.file_id, "segments": len(processed_segments)}


def clean_garbage_words(segments: list, max_word_length: int = 50) -> tuple[list, int]:
    """
    Clean garbage words from transcript segments.

    Garbage words are very long continuous strings (no spaces) that typically result from
    WhisperX misinterpreting background noise (fans, static, rumbling) as speech.

    Args:
        segments: List of transcript segments with 'text' field
        max_word_length: Maximum word length threshold (words longer are replaced)

    Returns:
        Tuple of (cleaned segments, count of garbage words replaced)
    """
    garbage_count = 0
    cleaned_segments = []

    for segment in segments:
        text = segment.get("text", "")
        words = text.split()
        cleaned_words = []

        for word in words:
            # Check if word exceeds max length and has no spaces
            # (spaces would indicate it's not a single garbage word)
            if len(word) > max_word_length and " " not in word:
                cleaned_words.append("[background noise]")
                garbage_count += 1
                logger.debug(f"Replaced garbage word ({len(word)} chars): {word[:30]}...")
            else:
                cleaned_words.append(word)

        # Create a copy of the segment with cleaned text
        cleaned_segment = segment.copy()
        cleaned_segment["text"] = " ".join(cleaned_words)
        cleaned_segments.append(cleaned_segment)

    return cleaned_segments, garbage_count


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


def _extract_metadata_if_available(temp_file_path: str, ctx: TranscriptionContext) -> None:
    """Extract and save media metadata from file."""
    extracted_metadata = extract_media_metadata(temp_file_path)
    if not extracted_metadata:
        return

    with session_scope() as db:
        media_file = get_refreshed_object(db, MediaFile, ctx.file_id)
        if media_file:
            update_media_file_metadata(
                media_file, extracted_metadata, ctx.content_type, temp_file_path
            )
            db.commit()


def _process_file_in_temp_dir(
    ctx: TranscriptionContext,
    temp_dir: str,
    file_data,
    file_ext: str,
    min_speakers: int | None,
    max_speakers: int | None,
    num_speakers: int | None,
) -> dict:
    """Process the transcription pipeline within a temporary directory."""
    # Save downloaded file
    temp_file_path = os.path.join(temp_dir, f"input{file_ext}")
    with open(temp_file_path, "wb") as f:
        f.write(file_data.read())

    # Extract metadata (non-critical)
    try:
        _extract_metadata_if_available(temp_file_path, ctx)
    except Exception as e:
        logger.warning(f"Error extracting media metadata: {e}")

    # Prepare audio for transcription
    with session_scope() as db:
        update_task_status(db, ctx.task_id, "in_progress", progress=0.25)

    send_progress_notification(ctx.user_id, ctx.file_id, 0.25, "Preparing audio for transcription")
    audio_file_path = prepare_audio_for_transcription(temp_file_path, ctx.content_type, temp_dir)

    # Run WhisperX pipeline
    result = _run_whisperx_pipeline(ctx, audio_file_path, min_speakers, max_speakers, num_speakers)

    # Validate transcription result
    validation_error = _validate_transcription_result(result, ctx, ctx.task_id)
    if validation_error:
        return validation_error

    # Process successful result
    return _process_transcription_result(ctx, result, audio_file_path)


def _handle_outer_exception(
    ctx: TranscriptionContext | None, task_id: str, error: Exception
) -> dict:
    """Handle top-level exception in transcription task."""
    file_id = ctx.file_id if ctx else None
    user_id = ctx.user_id if ctx else None

    logger.error(f"Error processing file {file_id}: {str(error)}")

    try:
        with session_scope() as db:
            if file_id:
                update_media_file_status(db, file_id, FileStatus.ERROR)
            update_task_status(db, task_id, "failed", error_message=str(error), completed=True)

        if user_id:
            send_error_notification(user_id, file_id, str(error))
    except Exception as update_err:
        logger.error(f"Error updating task status: {update_err}")

    return {"status": "error", "message": str(error)}


@celery_app.task(bind=True, name="transcribe_audio")
def transcribe_audio_task(
    self,
    file_uuid: str,
    min_speakers: int = None,
    max_speakers: int = None,
    num_speakers: int = None,
):
    """
    Process an audio/video file with WhisperX for transcription and Pyannote for diarization.

    Args:
        file_uuid: UUID of the MediaFile to transcribe
        min_speakers: Optional minimum number of speakers for diarization (falls back to settings.MIN_SPEAKERS)
        max_speakers: Optional maximum number of speakers for diarization (falls back to settings.MAX_SPEAKERS)
        num_speakers: Optional fixed number of speakers for diarization (falls back to settings.NUM_SPEAKERS)
    """
    task_id = self.request.id
    ctx = None

    try:
        # Get file information and create context
        ctx = _get_media_file_context(file_uuid, task_id)
        if not ctx:
            return {"status": "error", "message": f"Media file with UUID {file_uuid} not found"}

        # Send processing notification
        send_processing_notification(ctx.user_id, ctx.file_id)

        # Create and initialize task record
        with session_scope() as db:
            create_task_record(db, task_id, ctx.user_id, ctx.file_id, "transcription")
            update_task_status(db, task_id, "in_progress", progress=0.1)

        # Download file from MinIO
        logger.info(f"Downloading file {ctx.file_path}")
        file_data, _, _ = download_file(ctx.file_path)
        file_ext = get_audio_file_extension(ctx.content_type, ctx.file_name)

        # Process in temporary directory
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                return _process_file_in_temp_dir(
                    ctx, temp_dir, file_data, file_ext, min_speakers, max_speakers, num_speakers
                )
        except PermissionError as e:
            logger.error(f"PyAnnote model access error: {str(e)}")
            return _handle_transcription_failure(ctx, task_id, str(e), "gated_model_access")
        except Exception as e:
            logger.error(f"Error in WhisperX processing: {str(e)}")
            error_message = _get_user_friendly_error_message(str(e))
            return _handle_transcription_failure(ctx, task_id, error_message, "processing_error")

    except Exception as e:
        return _handle_outer_exception(ctx, task_id, e)
