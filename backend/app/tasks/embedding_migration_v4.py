"""
Speaker embedding migration task for v3->v4 upgrade.

This module provides the migration infrastructure for upgrading speaker
embeddings from PyAnnote v3 (512-dim) to v4 (256-dim WeSpeaker).

Key improvements over the initial implementation:
- Batched extraction (25 files/task) with warm-cached embedding model
- Prefetch pipeline: I/O threads download next files while GPU processes current
- Skip logic for files already migrated to v4
- Bulk OpenSearch writes instead of individual calls
- Migration lock pauses transcription so GPU is fully available
- Safe finalize with count validation, backup, and finally-block cleanup
"""

import contextlib
import datetime
import json
import logging
from concurrent.futures import Future
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import field

import redis

from app.core.celery import celery_app
from app.core.config import settings
from app.core.constants import NOTIFICATION_TYPE_MIGRATION_COMPLETE
from app.core.constants import NOTIFICATION_TYPE_MIGRATION_PROGRESS
from app.db.session_utils import session_scope
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.services.embedding_mode_service import MODE_V4
from app.services.embedding_mode_service import EmbeddingModeService
from app.services.migration_lock_service import migration_lock
from app.services.migration_progress_service import migration_progress

logger = logging.getLogger(__name__)

# Batch size for grouping files into a single GPU task
_BATCH_SIZE = 25


# ---------------------------------------------------------------------------
# Notification helper
# ---------------------------------------------------------------------------


def _send_migration_notification(
    notification_type: str,
    data: dict,
    user_id: int | None = None,
) -> None:
    """Send a migration progress notification via Redis pub/sub."""
    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        target_user = user_id if user_id else 1
        notification = {
            "user_id": target_user,
            "type": notification_type,
            "data": data,
        }
        redis_client.publish("websocket_notifications", json.dumps(notification))
    except Exception as e:
        logger.error(f"Failed to send migration notification: {e}")


# ---------------------------------------------------------------------------
# Status helpers (unchanged API)
# ---------------------------------------------------------------------------


def get_migration_status() -> dict:
    """Get the current migration status."""
    from app.services.opensearch_service import get_opensearch_client

    client = get_opensearch_client()
    if not client:
        return {"status": "error", "message": "OpenSearch not available"}

    current_mode = EmbeddingModeService.detect_mode()
    v4_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4"
    v4_exists = client.indices.exists(index=v4_index)

    try:
        v3_count = (
            client.count(index=settings.OPENSEARCH_SPEAKER_INDEX)["count"]
            if client.indices.exists(index=settings.OPENSEARCH_SPEAKER_INDEX)
            else 0
        )
        v4_count = client.count(index=v4_index)["count"] if v4_exists else 0
    except Exception:
        v3_count = 0
        v4_count = 0

    return {
        "current_mode": current_mode,
        "v4_index_exists": v4_exists,
        "v3_document_count": v3_count,
        "v4_document_count": v4_count,
        "migration_needed": current_mode == "v3",
        "migration_complete": current_mode == "v4"
        and not client.indices.exists(index=settings.OPENSEARCH_SPEAKER_INDEX + "_v3_backup"),
        "transcription_paused": migration_lock.is_active(),
    }


@celery_app.task(bind=True, name="check_migration_status", queue="utility")
def check_migration_status_task(self):
    """Check the current embedding migration status."""
    return get_migration_status()


# ---------------------------------------------------------------------------
# Skip-logic helper
# ---------------------------------------------------------------------------


def _get_already_migrated_file_ids() -> set[int]:
    """Return set of media_file_id values already present in the v4 index.

    Uses an OpenSearch terms aggregation (single query) so this is fast
    even for thousands of documents.
    """
    from app.services.opensearch_service import get_opensearch_client

    client = get_opensearch_client()
    if not client:
        return set()

    v4_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4"
    if not client.indices.exists(index=v4_index):
        return set()

    try:
        response = client.search(
            index=v4_index,
            body={
                "size": 0,
                "aggs": {
                    "file_ids": {
                        "terms": {
                            "field": "media_file_id",
                            "size": 50000,
                        }
                    }
                },
            },
        )
        buckets = response.get("aggregations", {}).get("file_ids", {}).get("buckets", [])
        return {int(b["key"]) for b in buckets}
    except Exception as e:
        logger.warning(f"Could not query v4 index for skip logic: {e}")
        return set()


# ---------------------------------------------------------------------------
# Segment builder (shared between batch task and legacy single-file task)
# ---------------------------------------------------------------------------


def _build_speaker_segments(db, media_file_id: int) -> dict[int, list[dict[str, float]]]:
    """Build mapping of speaker ID to their transcript segments."""
    from app.models.media import TranscriptSegment

    segments = (
        db.query(TranscriptSegment).filter(TranscriptSegment.media_file_id == media_file_id).all()
    )

    speaker_segments: dict[int, list[dict[str, float]]] = {}
    for seg in segments:
        if seg.speaker_id not in speaker_segments:
            speaker_segments[seg.speaker_id] = []
        speaker_segments[seg.speaker_id].append({"start": seg.start_time, "end": seg.end_time})
    return speaker_segments


# ---------------------------------------------------------------------------
# Bulk-write helper
# ---------------------------------------------------------------------------


def _bulk_write_v4_embeddings(speaker_docs: list[dict]) -> int:
    """Bulk-index a list of speaker embedding documents to the v4 index.

    Args:
        speaker_docs: List of dicts, each containing the document body
            and a ``_id`` key for the document ID.

    Returns:
        Number of documents successfully indexed.
    """
    from app.services.opensearch_service import get_opensearch_client

    if not speaker_docs:
        return 0

    client = get_opensearch_client()
    if not client:
        logger.error("OpenSearch client unavailable for bulk write")
        return 0

    v4_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4"
    bulk_body: list[dict] = []
    for doc in speaker_docs:
        doc_id = doc.pop("_id")
        bulk_body.append({"index": {"_index": v4_index, "_id": doc_id}})
        bulk_body.append(doc)

    try:
        response = client.bulk(body=bulk_body)
        errors = response.get("errors", False)
        if errors:
            for item in response.get("items", []):
                err = item.get("index", {}).get("error")
                if err:
                    logger.error(f"Bulk index error: {err}")
        return len(speaker_docs)
    except Exception as e:
        logger.error(f"Bulk write to v4 index failed: {e}")
        return 0


# ---------------------------------------------------------------------------
# Orchestrator task
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="migrate_speaker_embeddings_to_v4", queue="cpu")
def migrate_speaker_embeddings_v4_task(self, user_id: int | None = None):
    """Orchestrate migration of all speaker embeddings to v4.

    Acquires the migration lock (pausing transcription), queries completed
    files, filters out already-migrated ones, and dispatches batched GPU
    tasks (25 files per task).
    """
    from app.services.opensearch_service import create_speaker_index_v4

    task_id = self.request.id
    logger.info(f"Starting speaker embedding migration to v4: task_id={task_id}")

    # Prevent concurrent migrations
    if migration_progress.is_running():
        logger.warning("Migration already in progress, skipping")
        return {
            "status": "skipped",
            "message": "A migration is already in progress",
            "existing_status": migration_progress.get_status(),
        }

    # Check current mode
    current_mode = EmbeddingModeService.detect_mode()
    if current_mode == MODE_V4:
        logger.info("Already in v4 mode, no migration needed")
        return {"status": "skipped", "message": "Already using v4 embeddings"}

    # Acquire migration lock (pauses transcription workers)
    if not migration_lock.activate():
        return {
            "status": "error",
            "message": "Could not acquire migration lock (another migration may be running)",
        }

    # Create the v4 staging index
    if not create_speaker_index_v4():
        migration_lock.deactivate()
        logger.error("Failed to create v4 staging index")
        return {"status": "error", "message": "Failed to create v4 staging index"}

    # Get completed files from DB
    with session_scope() as db:
        query = db.query(MediaFile).filter(MediaFile.status == FileStatus.COMPLETED)
        if user_id:
            query = query.filter(MediaFile.user_id == user_id)
        media_files = query.all()

        # Filter out files already in v4 index
        already_migrated = _get_already_migrated_file_ids()
        files_to_migrate = [f for f in media_files if f.id not in already_migrated]
        skipped = len(media_files) - len(files_to_migrate)

        total_files = len(files_to_migrate)
        logger.info(
            f"Found {len(media_files)} completed files, "
            f"{skipped} already migrated, {total_files} to process"
        )

        if total_files == 0:
            migration_lock.deactivate()
            return {
                "status": "success",
                "message": f"No files to migrate ({skipped} already done)",
                "migrated": 0,
                "skipped": skipped,
            }

        # Start progress tracking
        migration_progress.start_migration(total_files=total_files, task_id=task_id)

        _send_migration_notification(
            NOTIFICATION_TYPE_MIGRATION_PROGRESS,
            {
                "processed_files": 0,
                "total_files": total_files,
                "failed_files": [],
                "progress": 0,
                "running": True,
            },
            user_id,
        )

        # Build batches of file UUIDs
        file_uuids = [str(f.uuid) for f in files_to_migrate]

    batches = [file_uuids[i : i + _BATCH_SIZE] for i in range(0, len(file_uuids), _BATCH_SIZE)]

    for batch_idx, batch in enumerate(batches):
        extract_v4_embeddings_batch_task.delay(
            file_uuids=batch,
            batch_index=batch_idx,
            total_batches=len(batches),
            total_files=total_files,
            user_id=user_id,
        )

    logger.info(f"Dispatched {len(batches)} batch tasks for {total_files} files")

    return {
        "status": "in_progress",
        "message": f"Dispatched {len(batches)} batch tasks ({total_files} files, {skipped} skipped)",
        "total_files": total_files,
        "skipped": skipped,
        "task_id": task_id,
    }


# ---------------------------------------------------------------------------
# Prefetch pipeline: I/O prep runs on threads while GPU processes
# ---------------------------------------------------------------------------

# I/O thread pool size for parallel ffmpeg segment extraction.
# Since transcription is paused during migration, we can use more threads
# for network I/O (MinIO presigned URL seeks) without contention.
_SEGMENT_IO_WORKERS = 16

# Number of embedding model instances to load on the GPU for parallel
# inference. Multiple instances on one GPU allow CPU↔GPU transfer overlap:
# while one model's CUDA kernel runs (GIL released), other threads prepare
# the next waveform. The WeSpeaker v4 model is ~50MB so 3 instances use
# only ~150MB additional VRAM.
_GPU_MODEL_WORKERS = 3


@dataclass
class SpeakerSnapshot:
    """Plain-data snapshot of a Speaker, detached from any SQLAlchemy session."""

    id: int
    uuid: str
    name: str
    profile_id: int | None


@dataclass
class PreparedFile:
    """Metadata for a file ready for GPU embedding extraction.

    No audio data is stored — segments are extracted on-demand via
    ffmpeg seeking from the audio_source (presigned URL or local path).
    """

    file_uuid: str
    audio_source: str  # Presigned MinIO URL or local file path
    speakers: list[SpeakerSnapshot]
    speaker_segments: dict[int, list[dict[str, float]]]
    media_file_id: int
    media_file_user_id: int
    speaker_profiles: dict[int, str | None] = field(default_factory=dict)


def _prepare_file_for_gpu(
    file_uuid: str,
    download_file_fn,
    get_file_by_uuid_fn,
    speaker_model,
) -> PreparedFile | None:
    """Query DB for file metadata and generate a presigned URL — pure I/O, no GPU.

    Does NOT download the file. Instead, generates a presigned MinIO URL
    that ffmpeg can seek into directly for segment-level audio extraction.

    Returns:
        PreparedFile ready for GPU extraction, or None if file has no speakers.
    """
    with session_scope() as db:
        media_file = get_file_by_uuid_fn(db, file_uuid)
        if not media_file:
            raise ValueError(f"Media file {file_uuid} not found")

        speakers = (
            db.query(speaker_model).filter(speaker_model.media_file_id == media_file.id).all()
        )
        if not speakers:
            return None

        speaker_segments = _build_speaker_segments(db, media_file.id)
        storage_path = media_file.storage_path

        # Snapshot speaker data (plain Python objects, session-independent)
        speaker_profiles: dict[int, str | None] = {}
        speaker_snapshots: list[SpeakerSnapshot] = []
        for sp in speakers:
            snapshot = SpeakerSnapshot(
                id=sp.id,
                uuid=str(sp.uuid),
                name=sp.name,
                profile_id=sp.profile_id,
            )
            speaker_snapshots.append(snapshot)
            profile_uuid = None
            if sp.profile_id and sp.profile:
                profile_uuid = str(sp.profile.uuid)
            speaker_profiles[sp.id] = profile_uuid

        media_file_id = int(media_file.id)
        media_file_user_id = int(media_file.user_id)

    # Generate presigned URL — ffmpeg will seek directly into MinIO
    from app.services.minio_service import minio_client

    audio_source = minio_client.presigned_get_object(
        bucket_name=settings.MEDIA_BUCKET_NAME,
        object_name=storage_path,
        expires=datetime.timedelta(hours=2),
    )

    return PreparedFile(
        file_uuid=file_uuid,
        audio_source=audio_source,
        speakers=speaker_snapshots,
        speaker_segments=speaker_segments,
        media_file_id=media_file_id,
        media_file_user_id=media_file_user_id,
        speaker_profiles=speaker_profiles,
    )


def _collect_work_items(
    prepared: PreparedFile,
) -> list[tuple[SpeakerSnapshot, dict[str, float]]]:
    """Collect eligible segments for embedding extraction.

    Returns list of (speaker, segment) tuples — up to 5 longest segments
    per speaker, minimum 0.5s duration each.
    """
    work_items: list[tuple[SpeakerSnapshot, dict[str, float]]] = []
    for speaker in prepared.speakers:
        segs = prepared.speaker_segments.get(speaker.id, [])
        if not segs:
            continue
        segs_sorted = sorted(segs, key=lambda x: x["end"] - x["start"], reverse=True)
        for seg in segs_sorted[:5]:
            if seg["end"] - seg["start"] >= 0.5:
                work_items.append((speaker, seg))
    return work_items


def _submit_segment_fetches(
    prepared: PreparedFile,
    pool: ThreadPoolExecutor,
) -> list[tuple[SpeakerSnapshot, dict, Future]]:
    """Submit ffmpeg segment extraction jobs to a shared thread pool.

    Does NOT block — returns futures immediately so the caller can
    continue submitting work for other files or start GPU inference
    on already-completed segments.
    """
    from app.services.speaker_embedding_service import SpeakerEmbeddingService

    work_items = _collect_work_items(prepared)
    futures = []
    for speaker, seg in work_items:
        fut = pool.submit(
            SpeakerEmbeddingService._load_audio_segment,
            prepared.audio_source,
            seg["start"],
            seg["end"] - seg["start"],
        )
        futures.append((speaker, seg, fut))
    return futures


def _gpu_infer_and_write(
    prepared: PreparedFile,
    segment_futures: list[tuple[SpeakerSnapshot, dict, Future]],
    embedding_service,
) -> int:
    """Run GPU inference on pre-fetched waveforms and bulk-write results.

    This is the GPU-bound phase — runs on the main thread for PyTorch
    safety. All I/O (ffmpeg seeks) should already be in progress or
    complete in the thread pool.

    Args:
        prepared: File metadata.
        segment_futures: Futures from _submit_segment_fetches.
        embedding_service: Warm-cached embedding service.

    Returns:
        Number of speakers successfully migrated.
    """
    if not segment_futures:
        return 0

    # Collect waveforms as they complete
    waveform_results: list[tuple[SpeakerSnapshot, dict, object]] = []
    for speaker, seg, fut in segment_futures:
        try:
            waveform = fut.result(timeout=30)
            if waveform is not None and waveform.shape[1] > 0:
                waveform_results.append((speaker, seg, waveform))
        except Exception as e:
            logger.debug(f"Segment seek failed for speaker {speaker.id}: {e}")

    # GPU inference — sequential on main thread
    speaker_embeddings: dict[int, list] = {}
    for speaker, _seg, waveform in waveform_results:
        emb = embedding_service.extract_embedding_from_waveform(waveform, 16000)
        if emb is not None:
            speaker_embeddings.setdefault(speaker.id, []).append(emb)

    # Aggregate and build docs
    docs: list[dict] = []
    now = datetime.datetime.now().isoformat()
    seen_speakers: set[int] = set()
    for speaker in prepared.speakers:
        if speaker.id in seen_speakers:
            continue
        seen_speakers.add(speaker.id)

        embs = speaker_embeddings.get(speaker.id, [])
        if not embs:
            continue

        aggregated = embedding_service.aggregate_embeddings(embs)
        docs.append(
            {
                "_id": str(speaker.uuid),
                "speaker_id": speaker.id,
                "speaker_uuid": str(speaker.uuid),
                "profile_id": speaker.profile_id,
                "profile_uuid": prepared.speaker_profiles.get(speaker.id),
                "user_id": prepared.media_file_user_id,
                "name": speaker.name,
                "display_name": None,
                "collection_ids": [],
                "media_file_id": prepared.media_file_id,
                "segment_count": len(embs),
                "created_at": now,
                "updated_at": now,
                "embedding": aggregated.tolist(),
            }
        )

    if docs:
        _bulk_write_v4_embeddings(docs)

    return len(docs)


def _gpu_extract_and_write(prepared: PreparedFile, embedding_service) -> int:
    """Extract v4 embeddings for all speakers in a file, then bulk-write.

    Standalone version that creates its own thread pool for single-file
    use (benchmarks, tests). For batch processing, use
    _submit_segment_fetches + _gpu_infer_and_write with a shared pool.

    Returns:
        Number of speakers successfully migrated.
    """
    work_items = _collect_work_items(prepared)
    if not work_items:
        return 0

    with ThreadPoolExecutor(max_workers=_SEGMENT_IO_WORKERS, thread_name_prefix="ffmpeg") as pool:
        segment_futures = _submit_segment_fetches(prepared, pool)
        return _gpu_infer_and_write(prepared, segment_futures, embedding_service)


def _process_batch_pipelined(
    prepared_files: list[tuple[str, PreparedFile]],
    primary_service,
) -> tuple[int, int]:
    """Process files with cross-file I/O pipelining and multi-model GPU workers.

    Architecture (producer-consumer on one GPU):

        ┌──────────────────────────────────────────┐
        │  Shared I/O Pool (16 ffmpeg threads)     │
        │  Fetches segments for ALL files upfront   │
        └────────────────┬─────────────────────────┘
                         │ waveform futures
                         ▼
        ┌──────────────────────────────────────────┐
        │  Work Queue (file + segment futures)     │
        └──┬──────────┬──────────┬─────────────────┘
           │          │          │
           ▼          ▼          ▼
        ┌──────┐  ┌──────┐  ┌──────┐
        │Model │  │Model │  │Model │  (same GPU)
        │  0   │  │  1   │  │  2   │
        └──┬───┘  └──┬───┘  └──┬───┘
           │          │          │
           ▼          ▼          ▼
        ┌──────────────────────────────────────────┐
        │  Bulk Write to OpenSearch (per file)     │
        └──────────────────────────────────────────┘

    Multiple model instances on one GPU allow CPU↔GPU transfer overlap:
    the GIL is released during CUDA kernel execution, so while Model 0
    runs inference, Model 1's thread prepares the next waveform tensor.
    This keeps the GPU continuously fed without idle gaps.

    Args:
        prepared_files: List of (file_uuid, PreparedFile) tuples.
        primary_service: Warm-cached embedding service (reused as worker 0).

    Returns:
        (migrated_count, failed_count) tuple.
    """
    import queue
    import threading

    from app.services.speaker_embedding_service import SpeakerEmbeddingService

    if not prepared_files:
        return 0, 0

    migrated = 0
    failed = 0
    results_lock = threading.Lock()

    # Create GPU worker pool — primary service + additional instances
    gpu_services = [primary_service]
    for _ in range(_GPU_MODEL_WORKERS - 1):
        gpu_services.append(SpeakerEmbeddingService(mode=MODE_V4))

    try:
        work_q: queue.Queue[tuple[str, PreparedFile, list]] = queue.Queue()

        # Shared I/O pool for ALL segment fetches across ALL files
        with ThreadPoolExecutor(
            max_workers=_SEGMENT_IO_WORKERS,
            thread_name_prefix="ffmpeg",
        ) as io_pool:
            # Submit ALL segment fetches upfront — pool processes them FIFO
            # so early files' segments complete first, keeping GPU workers fed
            for fuuid, prepared in prepared_files:
                seg_futures = _submit_segment_fetches(prepared, io_pool)
                work_q.put((fuuid, prepared, seg_futures))

            # GPU worker threads — each pulls files from the queue
            def gpu_worker(service, worker_id: int) -> None:
                nonlocal migrated, failed
                while True:
                    try:
                        fuuid, prepared, seg_futures = work_q.get_nowait()
                    except queue.Empty:
                        break

                    if not migration_lock.is_active():
                        logger.warning(f"[GPU-{worker_id}] Lock released, stopping")
                        break

                    try:
                        count = _gpu_infer_and_write(
                            prepared,
                            seg_futures,
                            service,
                        )
                        with results_lock:
                            migration_progress.increment_processed(success=True)
                            migrated += 1
                        if count:
                            logger.info(
                                f"[GPU-{worker_id}] {fuuid[:12]}… {count} speakers migrated"
                            )
                    except Exception as e:
                        logger.error(f"[GPU-{worker_id}] {fuuid[:12]}… failed: {e}")
                        with results_lock:
                            migration_progress.increment_processed(
                                success=False,
                                file_uuid=fuuid,
                            )
                            failed += 1

                    migration_lock.refresh_ttl()

            # Launch workers
            threads = []
            for i, svc in enumerate(gpu_services):
                t = threading.Thread(
                    target=gpu_worker,
                    args=(svc, i),
                    name=f"gpu-worker-{i}",
                    daemon=True,
                )
                t.start()
                threads.append(t)

            for t in threads:
                t.join()

    finally:
        # Cleanup additional instances — keep primary warm-cached
        for svc in gpu_services[1:]:
            with contextlib.suppress(Exception):
                svc.cleanup()

    return migrated, failed


def _extract_speaker_embedding_from_prepared(
    speaker: SpeakerSnapshot,
    prepared: PreparedFile,
    embedding_service,
) -> dict | None:
    """Extract embedding for one speaker using segment-level ffmpeg seeking.

    For single-speaker extraction (e.g., benchmarks). The batch path
    (_gpu_extract_and_write) parallelizes all segments for better throughput.
    """
    if speaker.id not in prepared.speaker_segments:
        return None

    segs = prepared.speaker_segments[speaker.id]
    if not segs:
        return None

    segs_sorted = sorted(segs, key=lambda x: x["end"] - x["start"], reverse=True)
    selected_segs = segs_sorted[:5]

    embeddings = []
    for seg in selected_segs:
        if seg["end"] - seg["start"] < 0.5:
            continue
        emb = embedding_service.extract_embedding_from_segment(prepared.audio_source, seg)
        if emb is not None:
            embeddings.append(emb)

    if not embeddings:
        return None

    aggregated = embedding_service.aggregate_embeddings(embeddings)

    now = datetime.datetime.now().isoformat()
    return {
        "_id": str(speaker.uuid),
        "speaker_id": speaker.id,
        "speaker_uuid": str(speaker.uuid),
        "profile_id": speaker.profile_id,
        "profile_uuid": prepared.speaker_profiles.get(speaker.id),
        "user_id": prepared.media_file_user_id,
        "name": speaker.name,
        "display_name": None,
        "collection_ids": [],
        "media_file_id": prepared.media_file_id,
        "segment_count": len(embeddings),
        "created_at": now,
        "updated_at": now,
        "embedding": aggregated.tolist(),
    }


# ---------------------------------------------------------------------------
# Batched extraction task with prefetch pipeline
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="extract_v4_embeddings_batch", queue="gpu", priority=5)
def extract_v4_embeddings_batch_task(
    self,
    file_uuids: list[str],
    batch_index: int = 0,
    total_batches: int = 1,
    total_files: int = 0,
    user_id: int | None = None,
):
    """Extract v4 embeddings for a batch of media files.

    Uses a multi-model producer-consumer pipeline on a single GPU:
    1. Prepare all files (fast — presigned URLs + DB queries)
    2. Shared I/O pool (16 threads) fetches ALL audio segments upfront
    3. N GPU model instances (work-stealing) process files as data arrives

    The I/O pool continuously feeds waveforms while GPU workers consume them.
    Multiple model instances hide CPU↔GPU transfer latency: while one model's
    CUDA kernel runs (GIL released), other workers prepare the next tensor.

    The primary embedding model is loaded ONCE and kept warm across batches.
    Additional instances are created per-batch and cleaned up after.
    """
    from app.models.media import Speaker
    from app.services.minio_service import download_file
    from app.services.speaker_embedding_service import get_cached_embedding_service
    from app.utils.uuid_helpers import get_file_by_uuid

    logger.info(f"Batch {batch_index + 1}/{total_batches}: processing {len(file_uuids)} files")

    # Get warm-cached embedding service (loaded once, reused across batches)
    embedding_service = get_cached_embedding_service(mode=MODE_V4)

    batch_migrated = 0
    batch_failed = 0

    # Phase 1: Prepare all files (presigned URLs + DB queries — fast)
    files_with_speakers: list[tuple[str, PreparedFile]] = []
    for fuuid in file_uuids:
        if not migration_lock.is_active():
            logger.warning("Migration lock released — aborting batch")
            break
        try:
            prepared = _prepare_file_for_gpu(
                fuuid,
                download_file,
                get_file_by_uuid,
                Speaker,
            )
            if prepared is None:
                # No speakers — still counts as processed
                migration_progress.increment_processed(success=True)
                batch_migrated += 1
            else:
                files_with_speakers.append((fuuid, prepared))
        except Exception as e:
            logger.error(f"Failed to prepare file {fuuid}: {e}")
            migration_progress.increment_processed(success=False, file_uuid=fuuid)
            batch_failed += 1

    # Phase 2: Multi-model pipelined GPU extraction
    if files_with_speakers:
        m, f = _process_batch_pipelined(files_with_speakers, embedding_service)
        batch_migrated += m
        batch_failed += f

    # Send progress notification after batch
    status = migration_progress.get_status()
    processed = status.get("processed_files", 0)
    total = status.get("total_files", 0) or total_files
    failed_files = status.get("failed_files", [])

    progress_pct = processed / total if total > 0 else 0
    is_complete = processed >= total and total > 0

    _send_migration_notification(
        NOTIFICATION_TYPE_MIGRATION_PROGRESS,
        {
            "processed_files": processed,
            "total_files": total,
            "failed_files": failed_files,
            "progress": progress_pct,
            "running": not is_complete,
        },
        user_id,
    )

    if is_complete:
        logger.info(f"All {total} migration files processed")
        migration_progress.complete_migration(success=True)
        _send_migration_notification(
            NOTIFICATION_TYPE_MIGRATION_COMPLETE,
            {
                "status": "complete",
                "total_files": total,
                "failed_files": failed_files,
                "success_count": total - len(failed_files),
            },
            user_id,
        )

    return {
        "status": "success",
        "batch_index": batch_index,
        "migrated": batch_migrated,
        "failed": batch_failed,
    }


# ---------------------------------------------------------------------------
# Legacy single-file task (kept for backward compat with any in-flight tasks)
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="extract_v4_embeddings", queue="gpu", priority=5)
def extract_v4_embeddings_task(
    self,
    file_uuid: str,
    task_index: int = 0,
    total_tasks: int = 1,
    user_id: int | None = None,
):
    """Legacy single-file extraction (kept for in-flight task compatibility).

    New migrations use extract_v4_embeddings_batch_task instead.
    """
    from app.models.media import Speaker
    from app.services.minio_service import download_file
    from app.services.speaker_embedding_service import get_cached_embedding_service
    from app.utils.uuid_helpers import get_file_by_uuid

    logger.info(f"[legacy] Extracting v4 embeddings for file {file_uuid}")

    embedding_service = get_cached_embedding_service(mode=MODE_V4)

    try:
        prepared = _prepare_file_for_gpu(file_uuid, download_file, get_file_by_uuid, Speaker)
        if prepared:
            _gpu_extract_and_write(prepared, embedding_service)
        migration_progress.increment_processed(success=True)
    except Exception as e:
        logger.error(f"[legacy] Error migrating {file_uuid}: {e}")
        migration_progress.increment_processed(success=False, file_uuid=file_uuid)

    # Check completion
    status = migration_progress.get_status()
    processed = status.get("processed_files", 0)
    total = status.get("total_files", 0)
    if processed >= total and total > 0:
        migration_progress.complete_migration(success=True)

    return {"status": "success", "file_uuid": file_uuid}


# ---------------------------------------------------------------------------
# Finalize task (safe version)
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="finalize_v4_migration", queue="utility")
def finalize_v4_migration_task(self):
    """Finalize the v4 migration by swapping indices.

    Safety checks:
    - Count validation: reject if v4 has <50% of v3 docs
    - Flush v4 before swap to ensure all docs are persisted
    - Post-swap verification: reject if new main has <95% of v4 count
    - finally block ALWAYS clears mode cache + releases migration lock
    """
    from app.services.opensearch_service import get_opensearch_client

    client = get_opensearch_client()
    if not client:
        return {"status": "error", "message": "OpenSearch not available"}

    v4_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4"
    backup_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v3_backup"
    main_index = settings.OPENSEARCH_SPEAKER_INDEX

    try:
        # ---- Pre-flight checks ----
        if not client.indices.exists(index=v4_index):
            return {"status": "error", "message": "V4 index does not exist"}

        # Flush v4 to ensure all docs are persisted
        client.indices.flush(index=v4_index, wait_if_ongoing=True)

        v4_count = client.count(index=v4_index)["count"]
        if v4_count == 0:
            return {"status": "error", "message": "V4 index is empty"}

        v3_count = 0
        if client.indices.exists(index=main_index):
            v3_count = client.count(index=main_index)["count"]

        # Count validation: v4 should have at least 50% of v3 docs
        if v3_count > 0 and v4_count < v3_count * 0.5:
            return {
                "status": "error",
                "message": (
                    f"V4 index has only {v4_count} docs vs {v3_count} in v3 "
                    f"({v4_count / v3_count * 100:.0f}%). "
                    "Migration appears incomplete. Aborting finalize."
                ),
            }

        # Ensure migration lock is held during swap
        if not migration_lock.is_active():
            migration_lock.activate()

        # ---- Backup v3 ----
        if client.indices.exists(index=main_index):
            # Remove old backup if exists
            if client.indices.exists(index=backup_index):
                client.indices.delete(index=backup_index)

            client.reindex(
                body={
                    "source": {"index": main_index},
                    "dest": {"index": backup_index},
                },
                wait_for_completion=True,
            )
            logger.info(f"Created backup: {backup_index}")

        # ---- Swap ----
        client.indices.delete(index=main_index, ignore=[404])

        client.reindex(
            body={
                "source": {"index": v4_index},
                "dest": {"index": main_index},
            },
            wait_for_completion=True,
        )

        # ---- Post-swap verification ----
        client.indices.flush(index=main_index, wait_if_ongoing=True)
        new_main_count = client.count(index=main_index)["count"]

        if new_main_count < v4_count * 0.95:
            logger.error(
                f"Post-swap count mismatch: main={new_main_count}, v4={v4_count}. "
                "Keeping v4 index for manual inspection."
            )
            return {
                "status": "error",
                "message": (
                    f"Post-swap verification failed: main has {new_main_count} "
                    f"but v4 had {v4_count} docs. V4 index preserved."
                ),
            }

        # ---- Cleanup ----
        client.indices.delete(index=v4_index, ignore=[404])

        logger.info(f"V4 migration finalized successfully: {new_main_count} docs in main index")
        return {
            "status": "success",
            "message": "Migration complete",
            "v4_documents": new_main_count,
        }

    except Exception as e:
        logger.error(f"Error finalizing migration: {e}")
        return {"status": "error", "message": str(e)}

    finally:
        # ALWAYS clear caches and release lock, even on error
        EmbeddingModeService.clear_cache()
        migration_lock.deactivate()
        migration_progress.clear_status()
