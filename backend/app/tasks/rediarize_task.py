"""Celery task for re-diarization without re-transcription.

Re-runs PyAnnote speaker diarization on existing audio and reassigns
speakers to existing transcript segments using word-level timestamps.
Preserves the original transcript text and word timings.

Runs on the GPU queue (requires PyAnnote diarization model).
"""

import logging
import os
import tempfile
import time

from app.core.celery import celery_app
from app.core.config import settings
from app.db.session_utils import session_scope
from app.models.media import FileStatus
from app.models.media import TranscriptSegment
from app.services.minio_service import download_file
from app.utils.task_utils import create_task_record
from app.utils.task_utils import update_media_file_status
from app.utils.task_utils import update_task_status

logger = logging.getLogger(__name__)


def _load_segments_as_transcript(file_id: int) -> dict:
    """Load existing transcript segments from DB in the pipeline result format.

    Reconstructs the dict format expected by assign_speakers:
    {"segments": [{"text": ..., "start": ..., "end": ..., "words": [...]}]}

    Args:
        file_id: Internal media file ID.

    Returns:
        Dict with "segments" key matching the transcription pipeline output format.

    Raises:
        ValueError: If no segments found or segments lack word timestamps.
    """
    with session_scope() as db:
        segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.media_file_id == file_id)
            .order_by(TranscriptSegment.start_time)
            .all()
        )

        if not segments:
            raise ValueError(f"No transcript segments found for file {file_id}")

        # Check that at least some segments have word-level timestamps
        has_words = any(seg.words for seg in segments)
        if not has_words:
            logger.warning(
                f"File {file_id} has no word-level timestamps; "
                "speaker assignment will use segment-level overlap only"
            )

        result_segments = []
        for seg in segments:
            segment_dict: dict = {
                "text": seg.text,
                "start": seg.start_time,
                "end": seg.end_time,
            }

            # Preserve word-level timestamps for fine-grained speaker assignment
            if seg.words:
                segment_dict["words"] = [
                    {
                        "word": w.get("word", ""),
                        "start": w["start"],
                        "end": w["end"],
                        "score": w.get("score", 1.0),
                    }
                    for w in seg.words
                    if "start" in w and "end" in w
                ]

            result_segments.append(segment_dict)

    return {"segments": result_segments}


def _prepare_audio(storage_path: str, content_type: str, filename: str) -> str:
    """Download file from MinIO and convert to WAV for diarization.

    Args:
        storage_path: MinIO object path.
        content_type: MIME type of the file.
        filename: Original filename (for extension detection).

    Returns:
        Path to the prepared WAV audio file in a temp directory.
        Caller is responsible for cleanup via the returned temp_dir.
    """
    from app.tasks.transcription.audio_processor import get_audio_file_extension
    from app.tasks.transcription.audio_processor import prepare_audio_for_transcription

    file_data, _, _ = download_file(storage_path)
    file_ext = get_audio_file_extension(content_type, filename)

    temp_dir = tempfile.mkdtemp(prefix="rediarize_")
    temp_file_path = os.path.join(temp_dir, f"input{file_ext}")
    with open(temp_file_path, "wb") as f:
        f.write(file_data.read())

    audio_file_path = prepare_audio_for_transcription(temp_file_path, content_type, temp_dir)
    return audio_file_path


def _run_diarization(
    audio_file_path: str,
    min_speakers: int | None,
    max_speakers: int | None,
    num_speakers: int | None,
):
    """Run PyAnnote diarization on audio.

    Returns:
        Tuple of (diarize_df, overlap_info, native_embeddings).
    """
    from app.transcription.audio import load_audio
    from app.transcription.config import TranscriptionConfig
    from app.transcription.model_manager import ModelManager

    config = TranscriptionConfig.from_environment(
        min_speakers=min_speakers if min_speakers is not None else settings.MIN_SPEAKERS,
        max_speakers=max_speakers if max_speakers is not None else settings.MAX_SPEAKERS,
        num_speakers=num_speakers if num_speakers is not None else settings.NUM_SPEAKERS,
        hf_token=settings.HUGGINGFACE_TOKEN,
    )

    audio = load_audio(audio_file_path)
    manager = ModelManager.get_instance()
    diarizer = manager.get_diarizer(config)
    diarize_df, overlap_info, native_embeddings = diarizer.diarize(audio)

    return diarize_df, overlap_info, native_embeddings


def _dispatch_downstream(
    downstream_tasks: list[str],
    file_uuid: str,
    file_id: int | None = None,
    user_id: int | None = None,
) -> None:
    """Dispatch downstream tasks by stage name after rediarization completes."""
    from app.api.endpoints.files.reprocess import dispatch_task_by_name

    for stage in downstream_tasks:
        try:
            dispatch_task_by_name(stage, file_uuid, file_id=file_id, user_id=user_id)
            logger.info(f"Dispatched downstream task '{stage}' for file {file_uuid}")
        except Exception as e:
            logger.warning(f"Failed to dispatch downstream task '{stage}' for {file_uuid}: {e}")


@celery_app.task(bind=True, name="rediarize", queue="gpu")
def rediarize_task(  # noqa: C901
    self,
    file_uuid: str,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    num_speakers: int | None = None,
    downstream_tasks: list[str] | None = None,
):
    """Re-run speaker diarization on an existing transcript without re-transcribing.

    Loads the original audio from MinIO and existing transcript segments from the
    database, runs PyAnnote diarization, and reassigns speakers using word-level
    timestamp overlap. Preserves all transcript text and word timings.

    Args:
        file_uuid: UUID of the MediaFile to rediarize.
        min_speakers: Minimum speakers for diarization (falls back to settings).
        max_speakers: Maximum speakers for diarization (falls back to settings).
        num_speakers: Fixed speaker count for diarization (falls back to settings).
        downstream_tasks: Optional list of downstream stage names to dispatch.
            Valid values: 'analytics', 'speaker_llm', 'summarization',
            'topic_extraction', 'search_indexing'.
    """
    import shutil

    from app.utils.uuid_helpers import get_file_by_uuid

    task_id = self.request.id
    temp_dir = None

    try:
        # Resolve file metadata
        with session_scope() as db:
            media_file = get_file_by_uuid(db, file_uuid)
            file_id = int(media_file.id)
            user_id = int(media_file.user_id)
            storage_path = str(media_file.storage_path)
            content_type = str(media_file.content_type)
            filename = str(media_file.filename)

        logger.info(f"Starting rediarization for file {file_uuid} (id={file_id})")

        # Create task record and set processing status
        with session_scope() as db:
            create_task_record(db, task_id, user_id, file_id, "rediarize")
            update_task_status(db, task_id, "in_progress", progress=0.05)
            update_media_file_status(db, file_id, FileStatus.PROCESSING)

        # Send processing notification
        from app.tasks.transcription.notifications import send_progress_notification

        send_progress_notification(user_id, file_id, 0.05, "Starting re-diarization")

        # Step 1: Load existing transcript segments
        with session_scope() as db:
            update_task_status(db, task_id, "in_progress", progress=0.10)

        transcript = _load_segments_as_transcript(file_id)
        logger.info(f"Loaded {len(transcript['segments'])} existing segments for file {file_id}")

        # Step 2: Download and prepare audio
        send_progress_notification(user_id, file_id, 0.15, "Downloading audio")
        audio_file_path = _prepare_audio(storage_path, content_type, filename)
        temp_dir = os.path.dirname(audio_file_path)

        with session_scope() as db:
            update_task_status(db, task_id, "in_progress", progress=0.25)

        # Step 3: Run diarization
        send_progress_notification(user_id, file_id, 0.30, "Running speaker diarization")
        step_start = time.perf_counter()

        diarize_df, overlap_info, native_embeddings = _run_diarization(
            audio_file_path, min_speakers, max_speakers, num_speakers
        )

        logger.info(
            f"TIMING: diarization completed in {time.perf_counter() - step_start:.3f}s - "
            f"{diarize_df['speaker'].nunique()} speakers, {len(diarize_df)} rows"
        )

        with session_scope() as db:
            update_task_status(db, task_id, "in_progress", progress=0.60)

        # Step 4: Reassign speakers using WhisperX speaker assignment
        send_progress_notification(user_id, file_id, 0.60, "Reassigning speakers")
        from app.transcription.speaker_assigner import assign_speakers

        result = assign_speakers(diarize_df, transcript)

        # Step 5: Process speakers and update DB
        send_progress_notification(user_id, file_id, 0.70, "Updating speaker database")
        from app.tasks.transcription.speaker_processor import create_speaker_mapping
        from app.tasks.transcription.speaker_processor import extract_unique_speakers
        from app.tasks.transcription.speaker_processor import process_segments_with_speakers

        unique_speakers = extract_unique_speakers(result["segments"])

        with session_scope() as db:
            speaker_mapping = create_speaker_mapping(db, user_id, file_id, unique_speakers)
            update_task_status(db, task_id, "in_progress", progress=0.75)

        processed_segments = process_segments_with_speakers(result["segments"], speaker_mapping)

        # Mark overlapping segments if overlap info available
        enable_overlap = os.getenv("ENABLE_OVERLAP_DETECTION", "true").lower() == "true"
        overlap_regions = overlap_info.get("regions", [])
        if enable_overlap and overlap_regions:
            from app.tasks.transcription.speaker_processor import mark_overlapping_segments

            processed_segments = mark_overlapping_segments(processed_segments, overlap_regions)

        # Step 6: Save updated segments to database
        send_progress_notification(user_id, file_id, 0.80, "Saving updated transcript")
        from app.tasks.transcription.storage import save_transcript_segments

        with session_scope() as db:
            save_transcript_segments(db, file_id, processed_segments)
            update_task_status(db, task_id, "in_progress", progress=0.85)

        # Step 7: Process speaker embeddings (native centroids or traditional)
        send_progress_notification(user_id, file_id, 0.85, "Processing speaker embeddings")
        from app.tasks.transcription.core import TranscriptionContext
        from app.tasks.transcription.core import _should_use_native_embeddings
        from app.tasks.transcription.core import _store_native_centroids_in_v4_staging

        # Build a lightweight context for embedding functions
        ctx = TranscriptionContext(
            task_id=task_id,
            file_id=file_id,
            file_uuid=file_uuid,
            user_id=user_id,
            file_path=storage_path,
            file_name=filename,
            content_type=content_type,
        )

        # Build a pseudo-result for _should_use_native_embeddings
        embedding_result = {}
        if native_embeddings:
            embedding_result["native_speaker_embeddings"] = native_embeddings

        use_native = _should_use_native_embeddings(embedding_result)
        try:
            if use_native and native_embeddings:
                from app.tasks.transcription.core import _process_speaker_embeddings_native

                _process_speaker_embeddings_native(
                    ctx, native_embeddings, processed_segments, speaker_mapping
                )
            elif not use_native:
                from app.tasks.transcription.core import _process_speaker_embeddings

                _process_speaker_embeddings(
                    ctx, audio_file_path, processed_segments, speaker_mapping
                )
        except Exception as e:
            logger.warning(f"Error processing speaker embeddings during rediarize: {e}")

        # Store v4 centroids if available
        if native_embeddings and not use_native:
            try:
                _store_native_centroids_in_v4_staging(ctx, native_embeddings, speaker_mapping)
            except Exception as e:
                logger.warning(f"v4 staging error during rediarize (non-fatal): {e}")

        # Step 8: Finalize
        send_progress_notification(user_id, file_id, 0.95, "Finalizing re-diarization")
        with session_scope() as db:
            update_task_status(db, task_id, "completed", progress=1.0, completed=True)
            update_media_file_status(db, file_id, FileStatus.COMPLETED)

        # Send completion notification
        from app.tasks.transcription.notifications import send_completion_notification

        send_completion_notification(user_id, file_id)

        logger.info(
            f"Rediarization completed for file {file_uuid} - "
            f"{len(processed_segments)} segments, "
            f"{len(unique_speakers)} speakers"
        )

        # Step 9: Dispatch speaker attribute detection (gender/age) → chains to LLM speaker ID.
        # This mirrors the transcription pipeline flow: attributes are detected first,
        # then identify_speakers_llm_task is chained automatically by the attribute task.
        try:
            from app.tasks.speaker_attribute_task import _is_speaker_attribute_detection_enabled

            if _is_speaker_attribute_detection_enabled(user_id):
                from app.tasks.speaker_attribute_task import detect_speaker_attributes_task

                detect_speaker_attributes_task.delay(str(file_uuid), user_id)
                logger.info(f"Dispatched speaker attribute detection for {file_uuid}")
        except Exception as e:
            logger.warning(f"Failed to dispatch speaker attribute detection: {e}")

        # Step 10: Dispatch remaining downstream tasks.
        # Remove speaker_llm — it's chained from detect_speaker_attributes_task
        # to ensure gender/age context is available for LLM identification.
        if downstream_tasks:
            filtered = [s for s in downstream_tasks if s != "speaker_llm"]
            if filtered:
                _dispatch_downstream(filtered, file_uuid, file_id=file_id, user_id=user_id)

        return {
            "status": "success",
            "file_id": file_id,
            "segments": len(processed_segments),
            "speakers": len(unique_speakers),
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Rediarization failed for file {file_uuid}: {error_msg}")

        try:
            with session_scope() as db:
                update_task_status(db, task_id, "failed", error_message=error_msg, completed=True)
                # Resolve file_id if we have it
                try:
                    from app.utils.uuid_helpers import get_file_by_uuid

                    media_file = get_file_by_uuid(db, file_uuid)
                    update_media_file_status(db, int(media_file.id), FileStatus.ERROR)
                    media_file.last_error_message = error_msg
                    from app.utils.error_classification import categorize_error

                    media_file.error_category = categorize_error(error_msg).value
                    db.commit()
                except Exception as file_err:
                    logger.warning(f"Could not update file error status: {file_err}")
        except Exception as update_err:
            logger.error(f"Error updating task status after rediarize failure: {update_err}")

        return {"status": "error", "message": error_msg}

    finally:
        # Clean up temp directory
        if temp_dir and os.path.isdir(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as cleanup_err:
                logger.warning(f"Failed to clean up temp dir {temp_dir}: {cleanup_err}")
