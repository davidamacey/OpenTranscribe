import logging
import os
import tempfile
import time
from dataclasses import dataclass

from app.core.celery import celery_app
from app.core.config import settings
from app.core.constants import GPUPriority
from app.core.constants import get_speaker_index_v4
from app.db.session_utils import get_refreshed_object
from app.db.session_utils import session_scope
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.services.minio_service import download_file
from app.services.opensearch_service import index_transcript
from app.services.speaker_matching_service import SpeakerMatchingService
from app.utils.error_classification import categorize_error
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
from .speaker_processor import mark_overlapping_segments
from .speaker_processor import process_segments_with_speakers
from .storage import generate_full_transcript
from .storage import get_unique_speaker_names
from .storage import save_transcript_segments
from .storage import update_media_file_transcription_status

logger = logging.getLogger(__name__)


# Deprecation warning for legacy TRANSCRIPTION_ENGINE env var
_engine = os.getenv("TRANSCRIPTION_ENGINE", "")
if _engine and _engine.lower() != "native":
    logger.warning(
        f"TRANSCRIPTION_ENGINE={_engine} is deprecated and ignored. "
        "The unified pipeline is now used for all transcription."
    )

# Deprecation warning for legacy ENABLE_ALIGNMENT env var
_align = os.getenv("ENABLE_ALIGNMENT", "")
if _align:
    logger.warning(
        "ENABLE_ALIGNMENT is deprecated and ignored. "
        "Word-level timestamps are now provided natively by faster-whisper "
        "for all 100+ languages without a separate alignment model."
    )


def _get_user_language_settings(db, user_id: int) -> dict:
    """
    Retrieve user's language settings from the database.

    Args:
        db: Database session
        user_id: ID of the user

    Returns:
        Dict with source_language and translate_to_english keys
    """
    from app import models
    from app.core.constants import DEFAULT_SOURCE_LANGUAGE

    user_settings = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == user_id,
            models.UserSetting.setting_key.in_(
                [
                    "transcription_source_language",
                    "transcription_translate_to_english",
                ]
            ),
        )
        .all()
    )

    settings_map = {s.setting_key: s.setting_value for s in user_settings}

    return {
        "source_language": settings_map.get(
            "transcription_source_language", DEFAULT_SOURCE_LANGUAGE
        ),
        "translate_to_english": settings_map.get(
            "transcription_translate_to_english", "false"
        ).lower()
        == "true",
    }


def _get_user_transcription_settings(db, user_id: int) -> dict:
    """Retrieve user's transcription tuning settings from the database."""
    from app import models
    from app.core.constants import DEFAULT_HALLUCINATION_SILENCE_THRESHOLD
    from app.core.constants import DEFAULT_REPETITION_PENALTY
    from app.core.constants import DEFAULT_VAD_MIN_SILENCE_MS
    from app.core.constants import DEFAULT_VAD_MIN_SPEECH_MS
    from app.core.constants import DEFAULT_VAD_SPEECH_PAD_MS
    from app.core.constants import DEFAULT_VAD_THRESHOLD

    setting_keys = [
        "transcription_vad_threshold",
        "transcription_vad_min_silence_ms",
        "transcription_vad_min_speech_ms",
        "transcription_vad_speech_pad_ms",
        "transcription_hallucination_silence_threshold",
        "transcription_repetition_penalty",
    ]
    user_settings = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == user_id,
            models.UserSetting.setting_key.in_(setting_keys),
        )
        .all()
    )
    settings_map = {s.setting_key: s.setting_value for s in user_settings}

    hal_raw = settings_map.get("transcription_hallucination_silence_threshold", "")
    hal_value = float(hal_raw) if hal_raw else DEFAULT_HALLUCINATION_SILENCE_THRESHOLD

    return {
        "vad_threshold": float(
            settings_map.get("transcription_vad_threshold", str(DEFAULT_VAD_THRESHOLD))
        ),
        "vad_min_silence_ms": int(
            settings_map.get("transcription_vad_min_silence_ms", str(DEFAULT_VAD_MIN_SILENCE_MS))
        ),
        "vad_min_speech_ms": int(
            settings_map.get("transcription_vad_min_speech_ms", str(DEFAULT_VAD_MIN_SPEECH_MS))
        ),
        "vad_speech_pad_ms": int(
            settings_map.get("transcription_vad_speech_pad_ms", str(DEFAULT_VAD_SPEECH_PAD_MS))
        ),
        "hallucination_silence_threshold": hal_value,
        "repetition_penalty": float(
            settings_map.get("transcription_repetition_penalty", str(DEFAULT_REPETITION_PENALTY))
        ),
    }


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
            file_id=int(media_file.id),
            file_uuid=file_uuid,
            user_id=int(media_file.user_id),
            file_path=str(media_file.storage_path),
            file_name=str(media_file.filename),
            content_type=str(media_file.content_type),
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
            media_file.error_category = categorize_error(error_msg).value
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
    """Extract speaker embeddings and match profiles using warm cached model."""
    import time

    from app.services.speaker_embedding_service import get_cached_embedding_service
    from app.utils.hardware_detection import detect_hardware

    total_start = time.perf_counter()

    # Force GPU synchronization before embedding extraction
    sync_start = time.perf_counter()
    hardware_config = detect_hardware()
    hardware_config.optimize_memory_usage()
    logger.info(f"TIMING: GPU sync completed in {time.perf_counter() - sync_start:.3f}s")

    # Use cached embedding service (warm model, avoids 40-60s cold start)
    cache_start = time.perf_counter()
    embedding_service = get_cached_embedding_service()
    cache_elapsed = time.perf_counter() - cache_start
    logger.info(
        f"TIMING: get_cached_embedding_service completed in {cache_elapsed:.3f}s - "
        f"mode: {embedding_service.mode} ({embedding_service.model_name})"
    )

    matching_start = time.perf_counter()
    with session_scope() as db:
        # Compute accessible profiles for cross-user matching via shared collections
        from app.services.permission_service import PermissionService

        accessible_ids = PermissionService.get_accessible_profile_ids(db, ctx.user_id)

        matching_service = SpeakerMatchingService(db, embedding_service)
        logger.info(f"Starting speaker matching for {len(speaker_mapping)} speakers")
        speaker_results = matching_service.process_speaker_segments(
            audio_file_path,
            ctx.file_id,
            ctx.user_id,
            processed_segments,
            speaker_mapping,
            accessible_profile_ids=accessible_ids,
        )
        matching_elapsed = time.perf_counter() - matching_start
        logger.info(
            f"TIMING: process_speaker_segments completed in {matching_elapsed:.3f}s - "
            f"got {len(speaker_results) if speaker_results else 0} results"
        )
        update_task_status(db, ctx.task_id, "in_progress", progress=0.82)

    total_elapsed = time.perf_counter() - total_start
    logger.info(
        f"TIMING: _process_speaker_embeddings TOTAL completed in {total_elapsed:.3f}s - "
        f"{len(speaker_results) if speaker_results else 0} speakers processed"
    )
    # Note: We do NOT cleanup the embedding service here - keep it warm for next transcription


def _process_speaker_embeddings_native(
    ctx: TranscriptionContext,
    native_embeddings: dict,
    processed_segments: list,
    speaker_mapping: dict,
) -> None:
    """Process speaker embeddings using pre-computed PyAnnote centroids (native path).

    Uses 256-dim WeSpeaker centroids from diarization instead of loading a separate
    embedding model. Saves 5-80s GPU time and ~500MB VRAM per file.

    Args:
        ctx: Transcription context.
        native_embeddings: Dict mapping speaker labels (e.g. "SPEAKER_00") to
            L2-normalized centroid vectors from PyAnnote.
        processed_segments: Processed transcript segments.
        speaker_mapping: Mapping of speaker labels to database IDs.
    """
    import time

    import numpy as np

    total_start = time.perf_counter()

    # Map speaker labels -> DB IDs using speaker_mapping
    db_embeddings: dict[int, np.ndarray] = {}
    for label, embedding in native_embeddings.items():
        db_id = speaker_mapping.get(label)
        if db_id is not None:
            db_embeddings[db_id] = embedding
        else:
            logger.debug(f"No DB mapping for speaker label '{label}', skipping embedding")

    if not db_embeddings:
        logger.warning("No speaker embeddings could be mapped to DB IDs")
        return

    matching_start = time.perf_counter()
    with session_scope() as db:
        # Compute accessible profiles for cross-user matching via shared collections
        from app.services.permission_service import PermissionService

        accessible_ids = PermissionService.get_accessible_profile_ids(db, ctx.user_id)

        matching_service = SpeakerMatchingService(db, embedding_service=None)
        logger.info(
            f"Starting native speaker matching for {len(db_embeddings)} speakers "
            f"(dim={next(iter(db_embeddings.values())).shape[0]})"
        )
        speaker_results = matching_service.process_speaker_embeddings_native(
            media_file_id=ctx.file_id,
            user_id=ctx.user_id,
            native_embeddings=db_embeddings,
            accessible_profile_ids=accessible_ids,
        )
        matching_elapsed = time.perf_counter() - matching_start
        logger.info(
            f"TIMING: process_speaker_embeddings_native completed in {matching_elapsed:.3f}s - "
            f"got {len(speaker_results) if speaker_results else 0} results"
        )
        update_task_status(db, ctx.task_id, "in_progress", progress=0.82)

    total_elapsed = time.perf_counter() - total_start
    logger.info(
        f"TIMING: _process_speaker_embeddings_native TOTAL completed in {total_elapsed:.3f}s - "
        f"{len(speaker_results) if speaker_results else 0} speakers processed"
    )


def _collect_v4_profile_embeddings(
    profile_id: int,
    native_embeddings: dict,
    speaker_mapping: dict[str, int],
    current_file_speaker_uuids: set[str],
    db,
) -> list:
    """Collect 256-dim embeddings for a profile from current file and existing v4 docs.

    Args:
        profile_id: Profile to collect embeddings for.
        native_embeddings: Current file's native centroid dict.
        speaker_mapping: Speaker label -> DB ID mapping.
        current_file_speaker_uuids: UUIDs of speakers from the current file (to avoid double-counting).
        db: Active database session.

    Returns:
        List of numpy arrays (256-dim embeddings).
    """
    import numpy as np

    from app.models.media import Speaker

    v4_embeddings = []

    # Embeddings from current file's speakers assigned to this profile
    profile_speakers = db.query(Speaker).filter(Speaker.profile_id == profile_id).all()
    for ps in profile_speakers:
        for label, db_id in speaker_mapping.items():
            if db_id == ps.id and label in native_embeddings:
                emb = native_embeddings[label]
                v4_embeddings.append(np.array(emb) if not isinstance(emb, np.ndarray) else emb)
                break

    # Existing v4 speaker docs for this profile from other files
    try:
        from app.services.opensearch_service import get_opensearch_client

        client = get_opensearch_client()
        if not client:
            raise RuntimeError("OpenSearch client unavailable")
        v4_index = get_speaker_index_v4()
        resp = client.search(
            index=v4_index,
            body={
                "query": {
                    "bool": {
                        "must": [{"term": {"profile_id": profile_id}}],
                        "must_not": [{"term": {"document_type": "profile"}}],
                    }
                },
                "size": 500,
                "_source": ["embedding"],
            },
        )
        for hit in resp.get("hits", {}).get("hits", []):
            existing_emb = hit["_source"].get("embedding")
            if existing_emb and hit["_id"] not in current_file_speaker_uuids:
                v4_embeddings.append(np.array(existing_emb))
    except Exception as e:
        logger.debug(f"v4 staging: Could not fetch existing v4 docs for profile {profile_id}: {e}")

    return v4_embeddings


def _update_v4_profile_embeddings(
    touched_profile_ids: set[int],
    native_embeddings: dict,
    speaker_mapping: dict[str, int],
    current_file_speaker_uuids: set[str],
) -> int:
    """Update consolidated profile embeddings in v4 for touched profiles.

    Returns:
        Number of profiles successfully updated.
    """
    import numpy as np

    from app.models.media import SpeakerProfile
    from app.services.opensearch_service import store_profile_embedding_v4

    update_count = 0
    with session_scope() as db:
        for profile_id in touched_profile_ids:
            try:
                profile = db.query(SpeakerProfile).filter(SpeakerProfile.id == profile_id).first()
                if not profile:
                    logger.warning(f"v4 staging: Profile {profile_id} not found")
                    continue

                v4_embeddings = _collect_v4_profile_embeddings(
                    profile_id,
                    native_embeddings,
                    speaker_mapping,
                    current_file_speaker_uuids,
                    db,
                )
                if not v4_embeddings:
                    logger.debug(f"v4 staging: No v4 embeddings for profile {profile_id}")
                    continue

                # Average and L2-normalize for consistent cosine similarity
                avg_vec = np.mean(v4_embeddings, axis=0)
                norm = np.linalg.norm(avg_vec)
                if norm < 1e-8:
                    logger.warning(f"v4 staging: Zero-norm profile embedding for {profile_id}")
                    continue
                avg_embedding = (avg_vec / norm).tolist()
                store_profile_embedding_v4(
                    profile_id=profile_id,
                    profile_uuid=str(profile.uuid),
                    profile_name=str(profile.name),
                    embedding=avg_embedding,
                    speaker_count=len(v4_embeddings),
                    user_id=int(profile.user_id),
                )
                update_count += 1

            except Exception as e:
                logger.warning(f"v4 staging: Error updating profile {profile_id}: {e}")

    return update_count


def _store_native_centroids_in_v4_staging(
    ctx: TranscriptionContext,
    native_embeddings: dict,
    speaker_mapping: dict[str, int],
) -> None:
    """Store 256-dim native centroids in speakers_v4 staging index.

    Phase 1: Store per-speaker centroids (inheriting labels from DB).
    Phase 2: Update consolidated profile embeddings in v4 for any
             profiles touched by this file's speakers.

    Fire-and-forget: failures logged but don't affect main pipeline.
    """
    from app.models.media import Speaker
    from app.services.opensearch_service import add_speaker_embedding_v4
    from app.services.opensearch_service import ensure_v4_index_exists

    if not ensure_v4_index_exists():
        logger.warning("v4 staging: Could not create/verify speakers_v4 index, skipping")
        return

    stored_count = 0
    touched_profile_ids: set[int] = set()
    current_file_speaker_uuids: set[str] = set()

    # Phase 1: Store per-speaker centroids
    with session_scope() as db:
        for label, embedding in native_embeddings.items():
            db_id = speaker_mapping.get(label)
            if db_id is None:
                continue

            try:
                speaker = db.query(Speaker).filter(Speaker.id == db_id).first()
                if not speaker:
                    logger.warning(f"v4 staging: Speaker ID {db_id} not found in DB")
                    continue

                emb_list = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
                speaker_uuid = str(speaker.uuid)
                current_file_speaker_uuids.add(speaker_uuid)

                profile_uuid = None
                if speaker.profile_id and speaker.profile:
                    profile_uuid = str(speaker.profile.uuid)
                    touched_profile_ids.add(speaker.profile_id)

                add_speaker_embedding_v4(
                    speaker_id=int(speaker.id),
                    speaker_uuid=speaker_uuid,
                    user_id=ctx.user_id,
                    name=speaker.display_name or speaker.name,
                    embedding=emb_list,
                    profile_id=speaker.profile_id,
                    profile_uuid=profile_uuid,
                    media_file_id=ctx.file_id,
                    segment_count=1,
                    display_name=speaker.display_name,
                )
                stored_count += 1

            except Exception as e:
                logger.warning(f"v4 staging: Error storing speaker {db_id}: {e}")

    # Phase 2: Update consolidated profile embeddings in v4
    profile_update_count = 0
    if touched_profile_ids:
        profile_update_count = _update_v4_profile_embeddings(
            touched_profile_ids,
            native_embeddings,
            speaker_mapping,
            current_file_speaker_uuids,
        )

    logger.info(
        f"v4 staging: stored {stored_count} speakers + "
        f"{profile_update_count} profile updates (256-dim) "
        f"for file {ctx.file_id}"
    )


def _should_use_native_embeddings(result: dict) -> bool:
    """Determine whether to use native PyAnnote centroids or traditional embedding model.

    Decision logic:
    1. Check USE_NATIVE_SPEAKER_EMBEDDINGS env var (default true)
    2. Check native_speaker_embeddings exist in result
    3. Auto-detect index dimension compatibility:
       - Fresh install (no index): use native (creates 256-dim index)
       - v4 index (256-dim): compatible with native centroids
       - v3 index (512-dim): incompatible, fall back to traditional

    Returns:
        True if native embeddings should be used.
    """
    use_native = os.getenv("USE_NATIVE_SPEAKER_EMBEDDINGS", "true").lower() == "true"
    if not use_native:
        logger.info("Native speaker embeddings disabled by USE_NATIVE_SPEAKER_EMBEDDINGS=false")
        return False

    native_embeddings = result.get("native_speaker_embeddings", {})
    if not native_embeddings:
        logger.info("No native speaker embeddings in result, falling back to traditional path")
        return False

    # Auto-detect index dimension compatibility
    try:
        from app.services.embedding_mode_service import EmbeddingModeService

        index_dim = EmbeddingModeService.get_embedding_dimension()

        # Get centroid dimension from first embedding
        first_emb = next(iter(native_embeddings.values()))
        centroid_dim = first_emb.shape[-1] if hasattr(first_emb, "shape") else len(first_emb)

        if index_dim == centroid_dim:
            logger.info(
                f"Using native speaker embeddings: index dim ({index_dim}) matches "
                f"centroid dim ({centroid_dim})"
            )
            return True

        # Check if this is a fresh install (v4 mode = 256-dim, matching centroids)
        mode = EmbeddingModeService.detect_mode()
        if mode == "v4" and centroid_dim == 256:
            logger.info(
                "Using native speaker embeddings: v4 mode detected, "
                f"centroid dim={centroid_dim} compatible"
            )
            return True

        logger.warning(
            f"Index dimension ({index_dim}) does not match centroid dimension "
            f"({centroid_dim}). Falling back to traditional SpeakerEmbeddingService "
            f"for backward compatibility with existing v3 embeddings."
        )
        return False

    except Exception as e:
        logger.warning(
            f"Error checking embedding dimension compatibility: {e}. "
            "Falling back to traditional path."
        )
        return False


def _index_transcript_in_search(ctx: TranscriptionContext, processed_segments: list) -> None:
    """Index transcript in OpenSearch with chunk-level embeddings and legacy whole-doc."""
    full_transcript = generate_full_transcript(processed_segments)
    speaker_names = get_unique_speaker_names(processed_segments)

    with session_scope() as db:
        media_file = get_refreshed_object(db, MediaFile, ctx.file_id)
        file_title = (
            (media_file.title or media_file.filename) if media_file else f"File {ctx.file_id}"
        )
        file_uuid = media_file.uuid if media_file else None

    if not file_uuid:
        logger.warning(f"Could not index transcript: file_uuid not found for file_id {ctx.file_id}")
        return

    # Legacy whole-doc index (backward compatibility)
    index_transcript(
        ctx.file_id, file_uuid, ctx.user_id, full_transcript, speaker_names, file_title
    )

    # Dispatch chunk-level search indexing as a separate tracked Celery task
    try:
        from app.tasks.search_indexing_task import index_transcript_search_task

        index_transcript_search_task.delay(
            file_id=ctx.file_id,
            file_uuid=str(file_uuid),
            user_id=ctx.user_id,
        )
        logger.info(f"Dispatched search indexing task for file {file_uuid}")
    except Exception as e:
        logger.warning(f"Failed to dispatch search indexing task for file {file_uuid}: {e}")


def _resolve_language_settings(
    ctx: TranscriptionContext,
    source_language: str | None,
    translate_to_english: bool | None,
) -> tuple[str, bool]:
    """Resolve language settings from explicit args or user DB settings."""
    if source_language is not None and translate_to_english is not None:
        return source_language, translate_to_english

    with session_scope() as db:
        user_lang_settings = _get_user_language_settings(db, ctx.user_id)
        resolved_lang = source_language or user_lang_settings["source_language"]
        resolved_translate = (
            translate_to_english
            if translate_to_english is not None
            else user_lang_settings["translate_to_english"]
        )

    return resolved_lang, resolved_translate


def _run_transcription_pipeline(
    ctx: TranscriptionContext,
    audio_file_path: str,
    min_speakers: int | None,
    max_speakers: int | None,
    num_speakers: int | None,
    source_language: str | None = None,
    translate_to_english: bool | None = None,
) -> dict:
    """Run the unified transcription pipeline."""
    from app.transcription import TranscriptionConfig
    from app.transcription import TranscriptionPipeline

    source_language, translate_to_english = _resolve_language_settings(
        ctx, source_language, translate_to_english
    )

    logger.info(
        f"Language settings for file {ctx.file_id}: "
        f"source_language={source_language}, translate_to_english={translate_to_english}"
    )

    # Get user's transcription tuning settings from DB
    with session_scope() as db:
        user_settings = _get_user_transcription_settings(db, ctx.user_id)

    config = TranscriptionConfig.from_environment(
        source_language=source_language,
        translate_to_english=translate_to_english,
        min_speakers=min_speakers if min_speakers is not None else settings.MIN_SPEAKERS,
        max_speakers=max_speakers if max_speakers is not None else settings.MAX_SPEAKERS,
        num_speakers=num_speakers if num_speakers is not None else settings.NUM_SPEAKERS,
        hf_token=settings.HUGGINGFACE_TOKEN,
        vad_threshold=user_settings["vad_threshold"],
        vad_min_silence_ms=user_settings["vad_min_silence_ms"],
        vad_min_speech_ms=user_settings["vad_min_speech_ms"],
        vad_speech_pad_ms=user_settings["vad_speech_pad_ms"],
        hallucination_silence_threshold=user_settings["hallucination_silence_threshold"],
        repetition_penalty=user_settings["repetition_penalty"],
    )

    with session_scope() as db:
        update_task_status(db, ctx.task_id, "in_progress", progress=0.4)

    send_progress_notification(ctx.user_id, ctx.file_id, 0.4, "Running AI transcription")

    def progress_callback(progress, message):
        with session_scope() as db:
            update_task_status(db, ctx.task_id, "in_progress", progress=progress)
        send_progress_notification(ctx.user_id, ctx.file_id, progress, message)

    pipeline = TranscriptionPipeline(config)
    raw_result = pipeline.process(audio_file_path, progress_callback=progress_callback)
    # Annotate the raw WhisperX result with provider/model metadata so that
    # _process_transcription_result can persist it to media_file.asr_provider /
    # media_file.asr_model.  Without this the local pipeline leaves those columns NULL.
    if isinstance(raw_result, dict):
        raw_result.setdefault("asr_provider", "local")
        raw_result.setdefault(
            "asr_model",
            config.model_name if hasattr(config, "model_name") else settings.WHISPER_MODEL,
        )
    return raw_result


def _run_speaker_embeddings_with_retry(
    ctx: TranscriptionContext,
    result: dict,
    audio_file_path: str,
    processed_segments: list,
    speaker_mapping: dict,
) -> None:
    """Run speaker embedding processing with up to 2 retries on failure."""
    use_native = _should_use_native_embeddings(result)
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            if use_native:
                logger.info(
                    "Using native speaker embeddings (PyAnnote centroids, no separate model)"
                )
                _process_speaker_embeddings_native(
                    ctx,
                    result["native_speaker_embeddings"],
                    processed_segments,
                    speaker_mapping,
                )
            else:
                logger.info("Using traditional SpeakerEmbeddingService for speaker embeddings")
                _process_speaker_embeddings(
                    ctx, audio_file_path, processed_segments, speaker_mapping
                )
            break  # Success
        except Exception as e:
            if attempt < max_retries:
                logger.warning(f"Speaker embedding attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(1)
            else:
                logger.error(f"Speaker embedding failed after {max_retries + 1} attempts: {e}")


def _process_transcription_result(
    ctx: TranscriptionContext,
    result: dict,
    audio_file_path: str,
    downstream_tasks: list[str] | None = None,
) -> dict:
    """Process successful transcription result including speakers, indexing, and finalization."""
    import time

    from app.utils.hardware_detection import detect_hardware

    # Process speakers and segments
    send_progress_notification(ctx.user_id, ctx.file_id, 0.68, "Processing speaker segments")
    step_start = time.perf_counter()
    unique_speakers = extract_unique_speakers(result["segments"])
    logger.info(
        f"TIMING: extract_unique_speakers completed in {time.perf_counter() - step_start:.3f}s"
    )

    step_start = time.perf_counter()
    with session_scope() as db:
        speaker_mapping = create_speaker_mapping(db, ctx.user_id, ctx.file_id, unique_speakers)
        update_task_status(db, ctx.task_id, "in_progress", progress=0.72)
    logger.info(
        f"TIMING: create_speaker_mapping completed in {time.perf_counter() - step_start:.3f}s"
    )

    send_progress_notification(ctx.user_id, ctx.file_id, 0.72, "Organizing transcript segments")
    step_start = time.perf_counter()
    processed_segments = process_segments_with_speakers(result["segments"], speaker_mapping)
    logger.info(
        f"TIMING: process_segments_with_speakers completed in {time.perf_counter() - step_start:.3f}s - {len(processed_segments)} segments"
    )

    # Mark overlapping segments if overlap info is available and detection is enabled
    enable_overlap = os.getenv("ENABLE_OVERLAP_DETECTION", "true").lower() == "true"
    overlap_info = result.get("overlap_info", {})
    overlap_regions = overlap_info.get("regions", [])
    if enable_overlap and overlap_regions:
        step_start = time.perf_counter()
        logger.info(f"Marking {len(overlap_regions)} overlap regions for file {ctx.file_id}")
        processed_segments = mark_overlapping_segments(processed_segments, overlap_regions)
        # Note: mark_overlapping_segments has its own internal timing log
    elif not enable_overlap and overlap_regions:
        logger.info("Overlap marking disabled by ENABLE_OVERLAP_DETECTION=false")

    # Clean garbage words
    step_start = time.perf_counter()
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
    logger.info(f"TIMING: garbage cleanup completed in {time.perf_counter() - step_start:.3f}s")

    with session_scope() as db:
        update_task_status(db, ctx.task_id, "in_progress", progress=0.75)

    # Save to database
    send_progress_notification(ctx.user_id, ctx.file_id, 0.75, "Saving transcript to database")
    step_start = time.perf_counter()
    # Determine model info for tracking
    whisper_model = os.getenv("WHISPER_MODEL", "large-v3-turbo")
    diarization_model = "pyannote/speaker-diarization-3.1"
    try:
        from app.services.embedding_mode_service import EmbeddingModeService

        embedding_mode = EmbeddingModeService.get_current_mode()
    except Exception:
        embedding_mode = None

    with session_scope() as db:
        save_transcript_segments(db, ctx.file_id, processed_segments)
        update_media_file_transcription_status(
            db,
            ctx.file_id,
            processed_segments,
            result.get("language", "en"),
            whisper_model=whisper_model,
            diarization_model=diarization_model,
            embedding_mode=embedding_mode,
            asr_provider=result.get("asr_provider"),
            asr_model=result.get("asr_model"),
        )
        update_task_status(db, ctx.task_id, "in_progress", progress=0.78)
    # Note: save_transcript_segments has its own internal timing log

    # Speaker embeddings - choose native (PyAnnote centroids) or traditional path
    # Retry up to 2 times with short backoff to handle transient OpenSearch failures
    send_progress_notification(ctx.user_id, ctx.file_id, 0.78, "Processing speaker identification")
    step_start = time.perf_counter()
    _run_speaker_embeddings_with_retry(
        ctx, result, audio_file_path, processed_segments, speaker_mapping
    )
    # Note: embedding processing functions have their own internal timing logs

    # Store native centroids in v4 staging index (fire-and-forget).
    # Only when the traditional v3 path was used but native centroids exist —
    # this pre-populates the v4 index for future migration.
    native_embeddings_for_v4 = result.get("native_speaker_embeddings")
    if native_embeddings_for_v4 and not _should_use_native_embeddings(result):
        try:
            _store_native_centroids_in_v4_staging(ctx, native_embeddings_for_v4, speaker_mapping)
        except Exception as e:
            logger.warning(f"v4 staging: Error (non-fatal): {e}")

    # Force GPU memory cleanup before OpenSearch indexing
    hardware_config = detect_hardware()
    hardware_config.optimize_memory_usage()
    logger.info("GPU memory cleanup checkpoint completed")

    with session_scope() as db:
        update_task_status(db, ctx.task_id, "in_progress", progress=0.85)

    # Index in search (dispatched as separate Celery task)
    send_progress_notification(ctx.user_id, ctx.file_id, 0.85, "Dispatching search indexing")
    try:
        _index_transcript_in_search(ctx, processed_segments)
    except Exception as e:
        logger.warning(f"Error dispatching search indexing: {e}")

    # Finalize
    send_progress_notification(ctx.user_id, ctx.file_id, 0.95, "Finalizing transcription")
    with session_scope() as db:
        update_task_status(db, ctx.task_id, "completed", progress=1.0, completed=True)

    send_completion_notification(ctx.user_id, ctx.file_id)

    logger.info(
        f"Transcription completed successfully for file {ctx.file_id}, triggering automatic summarization"
    )
    trigger_automatic_summarization(ctx.file_id, ctx.file_uuid, tasks_to_run=downstream_tasks)

    # Dispatch speaker attribute detection (fire-and-forget, CPU queue).
    # When speaker_llm is explicitly in downstream_tasks, it's dispatched directly
    # by trigger_automatic_summarization — skip attribute detection chain to avoid
    # double dispatch of speaker_llm.
    speaker_llm_explicit = downstream_tasks is not None and "speaker_llm" in downstream_tasks
    if not speaker_llm_explicit:
        try:
            from app.tasks.speaker_attribute_task import _is_speaker_attribute_detection_enabled

            if _is_speaker_attribute_detection_enabled(ctx.user_id):
                from app.tasks.speaker_attribute_task import detect_speaker_attributes_task

                detect_speaker_attributes_task.delay(str(ctx.file_uuid), ctx.user_id)
                logger.info(f"Dispatched speaker attribute detection for {ctx.file_uuid}")
        except Exception as e:
            logger.warning(f"Failed to dispatch speaker attribute detection: {e}")

    # --- Speaker clustering ---
    # Only dispatch if this is the normal pipeline (not selective reprocessing,
    # which dispatches these from trigger_automatic_summarization)
    if not downstream_tasks or "speaker_clustering" not in downstream_tasks:
        try:
            from app.tasks.speaker_clustering import cluster_speakers_for_file

            cluster_speakers_for_file.delay(str(ctx.file_uuid), ctx.user_id)
            logger.info(f"Dispatched speaker clustering for {ctx.file_uuid}")
        except Exception as e:
            logger.warning(f"Failed to dispatch speaker clustering: {e}")

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


def _get_collection_prompt_uuid(file_id: int) -> str | None:
    """Look up the default summary prompt UUID from the file's first collection (by added_at)."""
    try:
        from app.db.session_utils import session_scope
        from app.models.media import Collection
        from app.models.media import CollectionMember
        from app.models.prompt import SummaryPrompt

        with session_scope() as db:
            result = (
                db.query(SummaryPrompt.uuid)
                .join(Collection, Collection.default_summary_prompt_id == SummaryPrompt.id)
                .join(CollectionMember, CollectionMember.collection_id == Collection.id)
                .filter(
                    CollectionMember.media_file_id == file_id,
                    SummaryPrompt.is_active,
                )
                .order_by(CollectionMember.added_at.asc())
                .first()
            )

            if result:
                logger.info(f"File {file_id} using collection default prompt: {result[0]}")
                return str(result[0])

        return None
    except Exception as e:
        logger.warning(f"Failed to get collection prompt for file {file_id}: {e}")
        return None


# Import for automatic summarization, speaker identification, and analytics
def trigger_automatic_summarization(
    file_id: int, file_uuid: str, tasks_to_run: list[str] | None = None
):
    """Trigger automatic summarization, speaker identification, and analytics after transcription completes.

    Note: In the default (full) flow, LLM speaker identification is dispatched by
    detect_speaker_attributes_task after gender detection completes, ensuring gender
    data is available to the LLM. When tasks_to_run explicitly includes 'speaker_llm',
    it is dispatched directly for selective reprocessing.

    Args:
        file_id: Internal file ID
        file_uuid: File UUID string
        tasks_to_run: Optional list of specific stages to run. None = run all tasks.
            Valid values: 'analytics', 'speaker_llm', 'summarization',
            'topic_extraction', 'search_indexing', 'speaker_clustering'
    """
    try:
        # Analytics computation
        if tasks_to_run is None or "analytics" in tasks_to_run:
            from app.tasks.analytics import analyze_transcript_task

            analytics_task = analyze_transcript_task.delay(file_uuid=file_uuid)
            logger.info(
                f"Automatic analytics computation task {analytics_task.id} started for file {file_id}"
            )

        # Speaker LLM identification: In the default full pipeline (tasks_to_run=None),
        # this is chained from detect_speaker_attributes_task (dispatched after
        # transcription completes) to ensure gender/age context is available.
        # When explicitly requested via selective reprocessing, dispatch directly.
        if tasks_to_run is not None and "speaker_llm" in tasks_to_run:
            from app.tasks.speaker_tasks import identify_speakers_llm_task

            speaker_task = identify_speakers_llm_task.delay(file_uuid=file_uuid)
            logger.info(
                f"Selective speaker LLM identification task {speaker_task.id} started for file {file_id}"
            )

        # Note: search_indexing is dispatched in _process_transcription_result (always
        # runs during transcription). No need to dispatch it here to avoid double dispatch.

        # Look up collection default prompt for this file
        collection_prompt_uuid = _get_collection_prompt_uuid(file_id)

        # Summarization
        if tasks_to_run is None or "summarization" in tasks_to_run:
            from app.tasks.summarization import summarize_transcript_task

            summary_task = summarize_transcript_task.delay(
                file_uuid=file_uuid,
                prompt_uuid=collection_prompt_uuid,
            )
            logger.info(
                f"Automatic summarization task {summary_task.id} started for file {file_id}"
            )

        # Topic extraction
        if tasks_to_run is None or "topic_extraction" in tasks_to_run:
            from app.tasks.topic_extraction import extract_topics_task

            topic_task = extract_topics_task.delay(file_uuid=file_uuid, force_regenerate=False)
            logger.info(
                f"Automatic topic extraction task {topic_task.id} started for file {file_id}"
            )

        # Speaker clustering (selective reprocessing only)
        _clustering_stages = {"speaker_clustering"}
        if tasks_to_run is not None and _clustering_stages & set(tasks_to_run):
            try:
                from app.db.session_utils import session_scope
                from app.models.media import MediaFile

                with session_scope() as _db:
                    _mf = _db.query(MediaFile).filter(MediaFile.uuid == file_uuid).first()
                    if not _mf:
                        logger.warning(f"File {file_uuid} not found for clustering dispatch")
                    else:
                        _uid = int(_mf.user_id)

                        if "speaker_clustering" in tasks_to_run:
                            try:
                                from app.tasks.speaker_clustering import cluster_speakers_for_file

                                cluster_speakers_for_file.delay(file_uuid, _uid)
                                logger.info(
                                    f"Selective speaker clustering dispatched for file {file_id}"
                                )
                            except Exception as sc_err:
                                logger.warning(f"Failed to dispatch speaker clustering: {sc_err}")

            except Exception as e:
                logger.warning(f"Failed to look up file for clustering dispatch: {e}")
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


def _convert_asr_result_to_segments(result, media_file_id: int) -> list[dict]:
    """
    Convert an ASRResult from a cloud provider to the segment dict format used by storage.

    Args:
        result: ASRResult instance from a cloud ASR provider
        media_file_id: ID of the media file (unused here, kept for signature clarity)

    Returns:
        List of segment dicts matching the format expected by save_transcript_segments
        and process_segments_with_speakers.

    Notes:
        - Handles ``segment.words`` being None or an empty list (returns ``words: []``).
        - Handles ``segment.speaker`` being None (non-diarized providers).
        - Handles ``segment.confidence`` being None (mapped to None in output dict,
          which ``save_transcript_segments`` accepts via ``.get("confidence")``).
        - Each word dict uses the key ``"score"`` (not ``"confidence"``) to match
          the WhisperX output convention expected by ``process_segments_with_speakers``.
        - An empty ``result.segments`` list produces an empty return value, which is
          then caught by ``_validate_transcription_result`` in the calling pipeline.
    """
    segments = []
    for seg in result.segments:
        words = []
        for w in seg.words or []:
            words.append(
                {
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                    "score": w.confidence if w.confidence is not None else 1.0,
                }
            )
        segments.append(
            {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "speaker": seg.speaker,  # already SPEAKER_XX format or None
                "confidence": seg.confidence,  # may be None — safe for .get("confidence")
                "words": words,
            }
        )
    return segments


def _run_cloud_asr_pipeline(
    ctx: TranscriptionContext,
    audio_file_path: str,
    min_speakers: int | None,
    max_speakers: int | None,
    num_speakers: int | None,
    provider=None,
) -> dict:
    """
    Run the cloud ASR transcription pipeline for a non-local provider.

    Args:
        ctx: Transcription context
        audio_file_path: Path to the prepared audio file
        min_speakers: Optional minimum speakers hint
        max_speakers: Optional maximum speakers hint
        num_speakers: Optional fixed speaker count
        provider: Already-instantiated ASR provider (avoids a redundant DB lookup).
            If None, a new provider is created from DB config (fallback path).

    Returns:
        Result dict with 'segments' and 'language' keys matching the WhisperX format
    """
    from app.services.asr.factory import ASRProviderFactory
    from app.services.asr.types import ASRConfig

    with session_scope() as db:
        # Re-use the already-created provider if supplied; otherwise create a fresh one.
        # This prevents a redundant DB round-trip when called from _process_file_in_temp_dir.
        if provider is None:
            provider = ASRProviderFactory.create_for_user(ctx.user_id, db)
        user_lang_settings = _get_user_language_settings(db, ctx.user_id)

        # Load active custom vocabulary terms for this user
        from app.models.custom_vocabulary import CustomVocabulary

        vocab_terms: list[str] = [
            row.term
            for row in db.query(CustomVocabulary.term)
            .filter(
                (CustomVocabulary.user_id == ctx.user_id) | CustomVocabulary.user_id.is_(None),
                CustomVocabulary.is_active.is_(True),
            )
            .all()
        ]

    logger.info(
        f"Running cloud ASR pipeline with provider '{provider.provider_name}' "
        f"for file {ctx.file_id}"
        + (f" ({len(vocab_terms)} vocabulary terms)" if vocab_terms else "")
    )

    send_progress_notification(ctx.user_id, ctx.file_id, 0.4, "Running cloud ASR transcription")

    # Only request diarization when the provider actually supports it; passing
    # enable_diarization=True to a provider that doesn't support it (e.g. OpenAI
    # whisper-1) wastes the parameter and can confuse the response parser.
    config = ASRConfig(
        language=user_lang_settings["source_language"],
        min_speakers=min_speakers if min_speakers is not None else settings.MIN_SPEAKERS,
        max_speakers=max_speakers if max_speakers is not None else settings.MAX_SPEAKERS,
        num_speakers=num_speakers if num_speakers is not None else settings.NUM_SPEAKERS,
        enable_diarization=provider.supports_diarization(),
        translate_to_english=user_lang_settings["translate_to_english"],
        vocabulary=vocab_terms if vocab_terms else None,
    )

    def cloud_progress_callback(progress: float, message: str) -> None:
        with session_scope() as db:
            update_task_status(db, ctx.task_id, "in_progress", progress=progress)
        send_progress_notification(ctx.user_id, ctx.file_id, progress, message)

    with session_scope() as db:
        update_task_status(db, ctx.task_id, "in_progress", progress=0.4)

    asr_result = provider.transcribe(audio_file_path, config, cloud_progress_callback)

    # Convert ASRResult to the dict format the rest of the pipeline expects
    raw_segments = _convert_asr_result_to_segments(asr_result, ctx.file_id)

    return {
        "segments": raw_segments,
        "language": asr_result.language,
        "asr_provider": asr_result.provider_name,
        "asr_model": asr_result.model_name,
    }


def _process_file_in_temp_dir(
    ctx: TranscriptionContext,
    temp_dir: str,
    file_data,
    file_ext: str,
    min_speakers: int | None,
    max_speakers: int | None,
    num_speakers: int | None,
    downstream_tasks: list[str] | None = None,
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

    # Create progress callback for audio extraction phase (25% to 38% of overall progress)
    def audio_extraction_progress_callback(stage_progress: float, message: str) -> None:
        # Map 0-1 stage progress to 0.25-0.38 overall progress
        overall_progress = 0.25 + (stage_progress * 0.13)
        send_progress_notification(ctx.user_id, ctx.file_id, overall_progress, message)

    send_progress_notification(ctx.user_id, ctx.file_id, 0.25, "Starting audio preparation")
    audio_file_path = prepare_audio_for_transcription(
        temp_file_path,
        ctx.content_type,
        temp_dir,
        progress_callback=audio_extraction_progress_callback,
    )

    # Check whether the user has a cloud ASR provider configured.
    # If so, route to the cloud pipeline; otherwise fall through to the local WhisperX pipeline.
    # The provider instance is passed directly into _run_cloud_asr_pipeline to avoid a
    # redundant DB round-trip (factory.create_for_user hits the DB every call).
    #
    # Only fall back to local for factory/config-loading errors (e.g. DB connectivity or
    # missing env vars at startup).  Errors from the provider's transcribe() call itself
    # (network failures, quota exceeded, bad API key) are re-raised so the outer handler
    # marks the file as FAILED with a clear error message rather than silently re-running
    # on local GPU (which can be very confusing in production).
    try:
        from app.services.asr.factory import ASRProviderFactory

        with session_scope() as db:
            provider = ASRProviderFactory.create_for_user(ctx.user_id, db)
    except Exception as factory_exc:
        logger.warning(
            "Failed to instantiate ASR provider for file %d (user %d), "
            "falling back to local pipeline: %s",
            ctx.file_id,
            ctx.user_id,
            factory_exc,
        )
        provider = None  # type: ignore[assignment]

    if provider is not None and provider.provider_name != "local":
        # Cloud pipeline — errors propagate so the task is marked FAILED, not silently
        # re-attempted on local GPU.
        result = _run_cloud_asr_pipeline(
            ctx,
            audio_file_path,
            min_speakers,
            max_speakers,
            num_speakers,
            provider=provider,
        )
        # Validate transcription result
        validation_error = _validate_transcription_result(result, ctx, ctx.task_id)
        if validation_error:
            return validation_error
        return _process_transcription_result(ctx, result, audio_file_path, downstream_tasks)

    # Local pipeline
    result = _run_transcription_pipeline(
        ctx, audio_file_path, min_speakers, max_speakers, num_speakers
    )

    # Validate transcription result
    validation_error = _validate_transcription_result(result, ctx, ctx.task_id)
    if validation_error:
        return validation_error

    # Process successful result
    return _process_transcription_result(ctx, result, audio_file_path, downstream_tasks)


def _handle_outer_exception(
    ctx: TranscriptionContext | None, task_id: str, error: Exception
) -> dict:
    """Handle top-level exception in transcription task."""
    file_id = ctx.file_id if ctx else None
    user_id = ctx.user_id if ctx else None
    error_msg = str(error)

    logger.error(f"Error processing file {file_id}: {error_msg}")

    try:
        with session_scope() as db:
            if file_id:
                update_media_file_status(db, file_id, FileStatus.ERROR)
                media_file = get_refreshed_object(db, MediaFile, file_id)
                if media_file:
                    media_file.error_category = categorize_error(error_msg).value
                    db.commit()
            update_task_status(db, task_id, "failed", error_message=error_msg, completed=True)

        if user_id and file_id:
            send_error_notification(user_id, file_id, error_msg)
    except Exception as update_err:
        logger.error(f"Error updating task status: {update_err}")

    return {"status": "error", "message": error_msg}


@celery_app.task(bind=True, name="transcription.process_file", priority=GPUPriority.USER_IMPORT)
def transcribe_audio_task(
    self,
    file_uuid: str,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    num_speakers: int | None = None,
    downstream_tasks: list[str] | None = None,
):
    """Process an audio/video file for transcription and speaker diarization.

    Uses the unified faster-whisper + PyAnnote v4 pipeline with
    user-configurable VAD and accuracy settings.

    Args:
        file_uuid: UUID of the MediaFile to transcribe.
        min_speakers: Minimum speakers for diarization (falls back to settings).
        max_speakers: Maximum speakers for diarization (falls back to settings).
        num_speakers: Fixed speaker count for diarization (falls back to settings).
        downstream_tasks: Optional list of specific post-transcription stages to run.
            None = run all tasks. Valid values: 'analytics', 'speaker_llm',
            'summarization', 'topic_extraction', 'search_indexing'.
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
                    ctx,
                    temp_dir,
                    file_data,
                    file_ext,
                    min_speakers,
                    max_speakers,
                    num_speakers,
                    downstream_tasks,
                )
        except PermissionError as e:
            logger.error(f"PyAnnote model access error: {str(e)}")
            return _handle_transcription_failure(ctx, task_id, str(e), "gated_model_access")
        except Exception as e:
            logger.error(f"Error in transcription processing: {str(e)}")
            error_message = _get_user_friendly_error_message(str(e))
            return _handle_transcription_failure(ctx, task_id, error_message, "processing_error")

    except Exception as e:
        return _handle_outer_exception(ctx, task_id, e)
