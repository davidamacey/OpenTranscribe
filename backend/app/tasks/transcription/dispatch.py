"""Transcription pipeline dispatch — Celery chain orchestration.

Builds a 3-stage chain for maximum GPU utilization:
  CPU preprocess → GPU transcribe+diarize → CPU postprocess

For batch processing (1000+ files), dispatch individual chains per file.
The CPU queue (concurrency=8) preprocesses multiple files ahead, ensuring
the GPU always has work ready. The GPU processes one file at a time while
the next file's audio is already prepared.

    File 1:  [CPU preprocess] → [GPU transcribe+diarize] → [CPU postprocess]
    File 2:       [CPU preprocess] → [GPU transcribe+diarize] → ...
    File 3:            [CPU preprocess] → ...
"""

import contextlib
import logging
import uuid

from celery import chain

from app.core.celery import celery_app
from app.core.constants import CPUPriority
from app.core.constants import GPUPriority
from app.db.session_utils import session_scope
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.utils.task_utils import create_task_record
from app.utils.task_utils import update_media_file_status
from app.utils.task_utils import update_task_status

logger = logging.getLogger(__name__)


def _resolve_gpu_queue(user_id: int, db) -> str:
    """Resolve the correct queue based on the user's active ASR provider.

    Returns 'cloud-asr' for cloud providers, 'gpu' for local.
    """
    try:
        from app.services.asr.factory import ASRProviderFactory

        provider = ASRProviderFactory.create_for_user(user_id, db)
        if provider.provider_name != "local":
            logger.info(
                f"Resolved ASR queue 'cloud-asr' for user {user_id} "
                f"(provider: {provider.provider_name})"
            )
            return "cloud-asr"
    except Exception as e:
        logger.debug(f"ASR provider resolution failed, defaulting to 'gpu': {e}")
    return "gpu"


def dispatch_transcription_pipeline(
    file_uuid: str,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    num_speakers: int | None = None,
    downstream_tasks: list[str] | None = None,
    source_language: str | None = None,
    translate_to_english: bool | None = None,
    gpu_queue: str | None = None,
) -> str:
    """Build and dispatch a 3-stage transcription chain.

    Returns the application-level task_id used for frontend progress tracking.
    The chain pipelines CPU and GPU work: while the GPU processes file N,
    the CPU queue preprocesses file N+1.

    Args:
        file_uuid: UUID of the MediaFile to transcribe.
        min_speakers: Min speakers for diarization (falls back to settings).
        max_speakers: Max speakers for diarization (falls back to settings).
        num_speakers: Fixed speaker count (falls back to settings).
        downstream_tasks: Optional list of post-transcription stages to run.
        source_language: Override source language (None = auto-detect).
        translate_to_english: Override translation setting.
        gpu_queue: Queue for GPU task. None = auto-resolve from user's ASR
            provider ('gpu' for local, 'cloud-asr' for cloud providers).
    """
    from .core import transcribe_gpu_task
    from .postprocess import finalize_transcription
    from .preprocess import preprocess_for_transcription

    task_id = str(uuid.uuid4())

    # Create task record and set file to PROCESSING
    with session_scope() as db:
        media_file = db.query(MediaFile).filter(MediaFile.uuid == file_uuid).first()
        if not media_file:
            raise ValueError(f"Media file {file_uuid} not found")

        file_id = int(media_file.id)
        user_id = int(media_file.user_id)

        # Auto-resolve queue from user's ASR provider if not specified
        if gpu_queue is None:
            gpu_queue = _resolve_gpu_queue(user_id, db)

        create_task_record(db, task_id, user_id, file_id, "transcription")
        update_media_file_status(db, file_id, FileStatus.PROCESSING)
        update_task_status(db, task_id, "in_progress", progress=0.0)

    # Build the 3-stage chain
    pipeline = chain(
        preprocess_for_transcription.s(
            file_uuid=file_uuid,
            task_id=task_id,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            num_speakers=num_speakers,
            downstream_tasks=downstream_tasks,
            source_language=source_language,
            translate_to_english=translate_to_english,
        ).set(queue="cpu", priority=CPUPriority.PIPELINE_CRITICAL),
        transcribe_gpu_task.s().set(queue=gpu_queue, priority=GPUPriority.USER_IMPORT),
        finalize_transcription.s().set(queue="cpu", priority=CPUPriority.PIPELINE_CRITICAL),
    )

    # Dispatch with error callback for cleanup
    pipeline.apply_async(
        link_error=[on_pipeline_error.si(file_uuid, task_id).set(queue="utility")],
    )

    logger.info(
        f"Dispatched transcription pipeline for file {file_uuid} "
        f"(task_id={task_id}, gpu_queue={gpu_queue})"
    )

    return task_id


def dispatch_batch_transcription(
    file_uuids: list[str],
    gpu_queue: str = "gpu",
    **kwargs,
) -> list[str]:
    """Dispatch transcription chains for a batch of files.

    Each file gets its own chain. The CPU queue (concurrency=8) preprocesses
    multiple files in parallel, keeping audio ready for the GPU. The GPU
    processes files one at a time (concurrency=1) with zero idle time.

    Returns list of task_ids for tracking.
    """
    task_ids = []
    for file_uuid in file_uuids:
        try:
            task_id = dispatch_transcription_pipeline(file_uuid, gpu_queue=gpu_queue, **kwargs)
            task_ids.append(task_id)
        except Exception as e:
            logger.error(f"Failed to dispatch pipeline for {file_uuid}: {e}")
    return task_ids


@celery_app.task(name="transcription.pipeline_error", ignore_result=True)
def on_pipeline_error(file_uuid: str, task_id: str) -> None:
    """Safety-net error handler for pipeline chain failures.

    Ensures temp audio is cleaned up and file/task status is marked ERROR
    even if the failing task's internal error handler didn't complete.
    Called via link_error when any task in the chain raises an exception.
    """
    from app.services.minio_service import cleanup_temp_audio
    from app.utils.uuid_helpers import get_file_by_uuid

    from .notifications import send_error_notification

    logger.warning(f"Pipeline error handler triggered for file {file_uuid}")

    # Clean up temp audio
    with contextlib.suppress(Exception):
        cleanup_temp_audio(file_uuid)

    # Ensure file is marked as errored
    try:
        with session_scope() as db:
            media_file = get_file_by_uuid(db, file_uuid)
            if media_file and media_file.status not in (
                FileStatus.ERROR,
                FileStatus.COMPLETED,
            ):
                update_media_file_status(db, int(media_file.id), FileStatus.ERROR)

            # Only update task if not already finalized
            from app.models.media import Task

            task = db.query(Task).filter(Task.id == task_id).first()
            if task and task.status not in ("completed", "failed"):
                update_task_status(
                    db,
                    task_id,
                    "failed",
                    error_message="Transcription pipeline failed",
                    completed=True,
                )

                if media_file:
                    send_error_notification(
                        int(media_file.user_id),
                        int(media_file.id),
                        "Transcription pipeline failed unexpectedly",
                    )
    except Exception as e:
        logger.error(f"Error in pipeline error handler: {e}")
