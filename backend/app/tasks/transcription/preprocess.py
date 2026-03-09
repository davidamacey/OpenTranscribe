"""CPU preprocessing task for the transcription pipeline.

Downloads media from MinIO, extracts audio via FFmpeg, and stages
the normalized audio.wav in MinIO temp storage for the GPU worker.

Part of the 3-stage chain: preprocess (CPU) → transcribe (GPU) → postprocess (CPU)
"""

import logging
import os
import tempfile
import time

from app.core.celery import celery_app
from app.core.constants import CPUPriority
from app.db.session_utils import get_refreshed_object
from app.db.session_utils import session_scope
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.utils.error_classification import categorize_error
from app.utils.task_utils import update_media_file_status
from app.utils.task_utils import update_task_status

from .audio_processor import extract_audio_from_video
from .audio_processor import get_audio_file_extension
from .audio_processor import prepare_audio_for_transcription
from .metadata_extractor import extract_media_metadata
from .metadata_extractor import update_media_file_metadata
from .notifications import send_error_notification
from .notifications import send_progress_notification

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="transcription.preprocess",
    priority=CPUPriority.PIPELINE_CRITICAL,
    acks_late=True,
)
def preprocess_for_transcription(
    self,
    file_uuid: str,
    task_id: str,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    num_speakers: int | None = None,
    downstream_tasks: list[str] | None = None,
    source_language: str | None = None,
    translate_to_english: bool | None = None,
) -> dict:
    """Download media, extract audio, upload to MinIO temp for GPU worker.

    Returns context dict consumed by the GPU transcription task via Celery chain.
    """
    from app.services.minio_service import upload_temp_audio
    from app.utils.uuid_helpers import get_file_by_uuid

    step_start = time.perf_counter()

    try:
        # Resolve file from DB
        with session_scope() as db:
            media_file = get_file_by_uuid(db, file_uuid)
            if not media_file:
                raise ValueError(f"Media file {file_uuid} not found")

            file_id = int(media_file.id)
            user_id = int(media_file.user_id)
            storage_path = str(media_file.storage_path)
            file_name = str(media_file.filename)
            content_type = str(media_file.content_type)

            update_task_status(db, task_id, "in_progress", progress=0.05)

        send_progress_notification(user_id, file_id, 0.05, "Preparing media file")

        file_ext = get_audio_file_extension(content_type, file_name)
        is_video = content_type.startswith("video/")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_audio_path = os.path.join(temp_dir, "audio.wav")

            if is_video:
                _preprocess_video(
                    storage_path,
                    file_ext,
                    temp_dir,
                    temp_audio_path,
                    file_id,
                    user_id,
                    content_type,
                )
            else:
                _preprocess_audio(
                    storage_path,
                    file_ext,
                    temp_dir,
                    temp_audio_path,
                    file_id,
                    user_id,
                    content_type,
                )

            # Upload preprocessed audio to MinIO temp for GPU worker
            send_progress_notification(user_id, file_id, 0.18, "Staging audio for transcription")
            audio_size_mb = os.path.getsize(temp_audio_path) / (1024 * 1024)
            audio_temp_path = upload_temp_audio(file_uuid, temp_audio_path)

        with session_scope() as db:
            update_task_status(db, task_id, "in_progress", progress=0.20)

        elapsed = time.perf_counter() - step_start
        logger.info(
            f"TIMING: preprocess completed in {elapsed:.3f}s for file {file_id} "
            f"(audio: {audio_size_mb:.1f}MB)"
        )

        send_progress_notification(user_id, file_id, 0.20, "Audio ready for transcription")

        return {
            "file_uuid": file_uuid,
            "file_id": file_id,
            "user_id": user_id,
            "task_id": task_id,
            "audio_temp_path": audio_temp_path,
            "content_type": content_type,
            "file_name": file_name,
            "storage_path": storage_path,
            "min_speakers": min_speakers,
            "max_speakers": max_speakers,
            "num_speakers": num_speakers,
            "downstream_tasks": downstream_tasks,
            "source_language": source_language,
            "translate_to_english": translate_to_english,
        }

    except Exception as e:
        logger.error(f"Preprocess failed for file {file_uuid}: {e}")
        _mark_pipeline_error(file_uuid, task_id, f"Audio preprocessing failed: {e}")
        raise


def _preprocess_video(
    storage_path: str,
    file_ext: str,
    temp_dir: str,
    temp_audio_path: str,
    file_id: int,
    user_id: int,
    content_type: str,
) -> None:
    """Extract audio from video via FFmpeg with presigned URL fallback."""
    from app.services.minio_service import download_file_to_path
    from app.services.minio_service import get_internal_presigned_url

    send_progress_notification(user_id, file_id, 0.08, "Extracting audio from video")

    # Try presigned URL first (FFmpeg reads directly from MinIO, no full download)
    try:
        minio_url = get_internal_presigned_url(storage_path, expires=3600)
        extract_audio_from_video(minio_url, temp_audio_path)
    except Exception as url_err:
        logger.warning(f"Presigned URL FFmpeg failed, falling back to download: {url_err}")
        temp_video_path = os.path.join(temp_dir, f"input{file_ext}")
        download_file_to_path(storage_path, temp_video_path)
        extract_audio_from_video(temp_video_path, temp_audio_path)

    # Metadata extraction (best-effort, downloads video if needed)
    _extract_metadata_best_effort(storage_path, file_ext, temp_dir, file_id, content_type)


def _preprocess_audio(
    storage_path: str,
    file_ext: str,
    temp_dir: str,
    temp_audio_path: str,
    file_id: int,
    user_id: int,
    content_type: str,
) -> None:
    """Download audio file and convert to WAV."""
    from app.services.minio_service import download_file_to_path

    send_progress_notification(user_id, file_id, 0.08, "Processing audio file")
    temp_input_path = os.path.join(temp_dir, f"input{file_ext}")
    download_file_to_path(storage_path, temp_input_path)

    # Metadata extraction
    _extract_metadata_best_effort(
        storage_path,
        file_ext,
        temp_dir,
        file_id,
        content_type,
        existing_local_path=temp_input_path,
    )

    # Convert to WAV (modifies temp_audio_path in-place via prepare_audio_for_transcription)
    result_path = prepare_audio_for_transcription(temp_input_path, content_type, temp_dir)

    # If prepare returned a different path (e.g., input was already .wav), copy it
    if result_path != temp_audio_path:
        import shutil

        shutil.copy2(result_path, temp_audio_path)


def _extract_metadata_best_effort(
    storage_path: str,
    file_ext: str,
    temp_dir: str,
    file_id: int,
    content_type: str,
    existing_local_path: str | None = None,
) -> None:
    """Extract media metadata. Best-effort — failures are logged but don't stop pipeline."""
    from app.services.minio_service import download_file_to_path

    try:
        local_path = existing_local_path
        if not local_path or not os.path.exists(local_path):
            local_path = os.path.join(temp_dir, f"meta_input{file_ext}")
            download_file_to_path(storage_path, local_path)

        metadata = extract_media_metadata(local_path)
        if metadata:
            with session_scope() as db:
                mf = get_refreshed_object(db, MediaFile, file_id)
                if mf:
                    update_media_file_metadata(mf, metadata, content_type, local_path)
                    db.commit()
    except Exception as e:
        logger.warning(f"Metadata extraction failed for file {file_id} (non-fatal): {e}")


def _mark_pipeline_error(file_uuid: str, task_id: str, error_msg: str) -> None:
    """Mark file and task as failed."""
    from app.utils.uuid_helpers import get_file_by_uuid

    try:
        with session_scope() as db:
            media_file = get_file_by_uuid(db, file_uuid)
            if media_file:
                update_media_file_status(db, int(media_file.id), FileStatus.ERROR)
                media_file.last_error_message = error_msg
                media_file.error_category = categorize_error(error_msg).value
                db.commit()
                send_error_notification(int(media_file.user_id), int(media_file.id), error_msg)
            update_task_status(db, task_id, "failed", error_message=error_msg, completed=True)
    except Exception as status_err:
        logger.error(f"Failed to update error status: {status_err}")
