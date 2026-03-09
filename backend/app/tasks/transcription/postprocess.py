"""CPU postprocessing task for the transcription pipeline.

Handles speaker embeddings, search indexing, downstream task dispatch,
and MinIO temp cleanup after GPU processing completes.

Part of the 3-stage chain: preprocess (CPU) → transcribe (GPU) → postprocess (CPU)
"""

import logging
import time

import numpy as np

from app.core.celery import celery_app
from app.core.constants import CPUPriority
from app.db.session_utils import session_scope
from app.services.opensearch_service import index_transcript
from app.utils.task_utils import update_task_status

from .notifications import send_completion_notification
from .notifications import send_progress_notification
from .storage import generate_full_transcript
from .storage import get_unique_speaker_names

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="transcription.postprocess",
    priority=CPUPriority.PIPELINE_CRITICAL,
    acks_late=True,
)
def finalize_transcription(self, gpu_result: dict) -> dict:
    """CPU postprocessing: speaker embeddings, indexing, downstream dispatch.

    Stage 3 of the 3-stage pipeline chain. Receives result from GPU task.
    All work here is CPU-bound or network I/O — no GPU needed.
    Segments are already saved to DB by the GPU task, so failures here
    are non-fatal (logged but do not lose transcription data).
    """
    if gpu_result.get("status") == "error":
        logger.warning(
            f"Skipping postprocess — GPU task failed for file {gpu_result.get('file_id')}"
        )
        _cleanup_temp(gpu_result.get("file_uuid"))
        return gpu_result

    file_uuid = gpu_result["file_uuid"]
    file_id = gpu_result["file_id"]
    user_id = gpu_result["user_id"]
    task_id = gpu_result["task_id"]
    speaker_mapping = gpu_result.get("speaker_mapping", {})
    native_embeddings = gpu_result.get("native_embeddings")
    use_native = gpu_result.get("use_native_embeddings", False)
    downstream_tasks = gpu_result.get("downstream_tasks")

    post_start = time.perf_counter()

    try:
        # --- Speaker embedding processing ---
        send_progress_notification(user_id, file_id, 0.80, "Processing speaker identification")

        if use_native and native_embeddings:
            _process_native_embeddings(
                file_id, user_id, task_id, native_embeddings, speaker_mapping
            )

        # Store v4 centroids if applicable (native available but not used for matching)
        if native_embeddings and not use_native:
            _store_v4_centroids(file_id, file_uuid, user_id, native_embeddings, speaker_mapping)

        with session_scope() as db:
            update_task_status(db, task_id, "in_progress", progress=0.88)

        # --- Search indexing ---
        send_progress_notification(user_id, file_id, 0.88, "Indexing for search")
        _index_transcript(file_id, file_uuid, user_id)

        # --- Finalize ---
        send_progress_notification(user_id, file_id, 0.95, "Finalizing transcription")
        with session_scope() as db:
            update_task_status(db, task_id, "completed", progress=1.0, completed=True)

        send_completion_notification(user_id, file_id)

        # --- Dispatch downstream tasks ---
        from .core import trigger_automatic_summarization

        logger.info(f"Transcription pipeline completed for file {file_id}, triggering downstream")
        trigger_automatic_summarization(file_id, file_uuid, tasks_to_run=downstream_tasks)

        _dispatch_speaker_attributes(file_uuid, user_id, downstream_tasks)
        _dispatch_speaker_clustering(file_uuid, user_id, downstream_tasks)

    except Exception as e:
        logger.error(f"Postprocess failed for file {file_id}: {e}")
        try:
            with session_scope() as db:
                update_task_status(
                    db,
                    task_id,
                    "failed",
                    error_message=f"Post-processing error: {e}",
                    completed=True,
                )
        except Exception as task_err:
            logger.debug(f"Failed to mark task as failed: {task_err}")
        # Don't re-raise — segments are already saved by GPU task

        return {
            "status": "error",
            "file_id": file_id,
            "error": str(e),
            "segment_count": gpu_result.get("segment_count", 0),
        }

    finally:
        _cleanup_temp(file_uuid)

    elapsed = time.perf_counter() - post_start
    logger.info(f"TIMING: postprocess completed in {elapsed:.3f}s for file {file_id}")

    return {
        "status": "success",
        "file_id": file_id,
        "segment_count": gpu_result.get("segment_count", 0),
    }


def _process_native_embeddings(
    file_id: int,
    user_id: int,
    task_id: str,
    native_embeddings_serialized: dict,
    speaker_mapping: dict,
) -> None:
    """Process speaker embeddings using native PyAnnote centroids (no GPU)."""
    from app.services.permission_service import PermissionService
    from app.services.speaker_matching_service import SpeakerMatchingService

    step_start = time.perf_counter()

    db_embeddings: dict[int, np.ndarray] = {}
    for label, emb_list in native_embeddings_serialized.items():
        db_id = speaker_mapping.get(label)
        if db_id is not None:
            db_embeddings[db_id] = np.array(emb_list)

    if not db_embeddings:
        return

    with session_scope() as db:
        accessible_ids = PermissionService.get_accessible_profile_ids(db, user_id)
        matching_service = SpeakerMatchingService(db, embedding_service=None)
        logger.info(
            f"Starting native speaker matching for {len(db_embeddings)} speakers "
            f"(dim={next(iter(db_embeddings.values())).shape[0]})"
        )
        matching_service.process_speaker_embeddings_native(
            media_file_id=file_id,
            user_id=user_id,
            native_embeddings=db_embeddings,
            accessible_profile_ids=accessible_ids,
        )
        update_task_status(db, task_id, "in_progress", progress=0.85)

    logger.info(
        f"TIMING: native speaker matching completed in {time.perf_counter() - step_start:.3f}s"
    )


def _store_v4_centroids(
    file_id: int,
    file_uuid: str,
    user_id: int,
    native_embeddings_serialized: dict,
    speaker_mapping: dict,
) -> None:
    """Store native centroids in v4 staging index (fire-and-forget)."""
    from .core import TranscriptionContext
    from .core import _store_native_centroids_in_v4_staging

    native_embs = {
        label: np.array(emb_list) for label, emb_list in native_embeddings_serialized.items()
    }

    ctx = TranscriptionContext(
        task_id="",
        file_id=file_id,
        file_uuid=file_uuid,
        user_id=user_id,
        file_path="",
        file_name="",
        content_type="",
    )

    try:
        _store_native_centroids_in_v4_staging(ctx, native_embs, speaker_mapping)
    except Exception as e:
        logger.warning(f"v4 staging error (non-fatal): {e}")


def _index_transcript(file_id: int, file_uuid: str, user_id: int) -> None:
    """Index transcript in OpenSearch (whole-doc + dispatch chunk-level)."""
    from sqlalchemy.orm import joinedload

    from app.db.session_utils import get_refreshed_object
    from app.models.media import MediaFile
    from app.models.media import TranscriptSegment

    with session_scope() as db:
        segments = (
            db.query(TranscriptSegment)
            .options(joinedload(TranscriptSegment.speaker))
            .filter(TranscriptSegment.media_file_id == file_id)
            .order_by(TranscriptSegment.start_time)
            .all()
        )
        seg_dicts = [
            {"text": s.text, "speaker": s.speaker.name if s.speaker else None} for s in segments
        ]

        media_file = get_refreshed_object(db, MediaFile, file_id)
        file_title = (media_file.title or media_file.filename) if media_file else f"File {file_id}"

    full_transcript = generate_full_transcript(seg_dicts)
    speaker_names = get_unique_speaker_names(seg_dicts)

    index_transcript(file_id, file_uuid, user_id, full_transcript, speaker_names, file_title)

    # Dispatch chunk-level search indexing
    try:
        from app.tasks.search_indexing_task import index_transcript_search_task

        index_transcript_search_task.delay(
            file_id=file_id,
            file_uuid=str(file_uuid),
            user_id=user_id,
        )
        logger.info(f"Dispatched search indexing task for file {file_uuid}")
    except Exception as e:
        logger.warning(f"Failed to dispatch search indexing: {e}")


def _dispatch_speaker_attributes(
    file_uuid: str, user_id: int, downstream_tasks: list[str] | None
) -> None:
    """Dispatch speaker attribute detection (fire-and-forget)."""
    if downstream_tasks is not None and "speaker_llm" in downstream_tasks:
        return
    try:
        from app.tasks.speaker_attribute_task import _is_speaker_attribute_detection_enabled
        from app.tasks.speaker_attribute_task import detect_speaker_attributes_task

        if _is_speaker_attribute_detection_enabled(user_id):
            detect_speaker_attributes_task.delay(str(file_uuid), user_id)
            logger.info(f"Dispatched speaker attribute detection for {file_uuid}")
    except Exception as e:
        logger.warning(f"Failed to dispatch speaker attribute detection: {e}")


def _dispatch_speaker_clustering(
    file_uuid: str, user_id: int, downstream_tasks: list[str] | None
) -> None:
    """Dispatch speaker clustering (fire-and-forget)."""
    if downstream_tasks and "speaker_clustering" in downstream_tasks:
        return
    try:
        from app.tasks.speaker_clustering import cluster_speakers_for_file

        cluster_speakers_for_file.delay(str(file_uuid), user_id)
        logger.info(f"Dispatched speaker clustering for {file_uuid}")
    except Exception as e:
        logger.warning(f"Failed to dispatch speaker clustering: {e}")


def _cleanup_temp(file_uuid: str | None) -> None:
    """Clean up MinIO temp audio (best-effort)."""
    if not file_uuid:
        return
    try:
        from app.services.minio_service import cleanup_temp_audio

        cleanup_temp_audio(file_uuid)
    except Exception as e:
        logger.debug(f"Temp cleanup failed (non-fatal): {e}")
