"""Speaker embedding consistency check and self-healing task.

Detects speakers in PostgreSQL that are missing from the OpenSearch speakers
index (v3 and/or v4) and re-extracts their embeddings from the original audio.

Architecture:
- Orchestrator (CPU queue): lightweight detection via set comparison, dispatches
  GPU batch tasks only when gaps are found.
- GPU batch worker: reuses migration_pipeline for I/O-pipelined extraction.
- Periodic beat schedule: runs every 10 minutes for fast gap detection.

Redis keys:
- embedding_consistency_running      — lock (1hr TTL)
- embedding_consistency_last_run     — last results JSON (7-day TTL)
- embedding_consistency_progress     — current progress data
"""

import contextlib
import json
import logging
import time
from typing import Any
from typing import Literal

from app.core.celery import celery_app
from app.core.config import settings
from app.core.constants import NOTIFICATION_TYPE_EMBEDDING_CONSISTENCY_COMPLETE
from app.core.constants import NOTIFICATION_TYPE_EMBEDDING_CONSISTENCY_PROGRESS
from app.core.constants import CPUPriority
from app.core.constants import GPUPriority
from app.core.redis import get_redis
from app.db.session_utils import session_scope
from app.utils.websocket_notify import send_ws_event

logger = logging.getLogger(__name__)

_REDIS_LOCK_KEY = "embedding_consistency_running"
_REDIS_LAST_RUN_KEY = "embedding_consistency_last_run"
_REDIS_PROGRESS_KEY = "embedding_consistency_progress"
_REDIS_BATCH_IDS_KEY = "embedding_consistency:batch_task_ids"
_LOCK_TTL = 900  # 15 minutes
_BATCH_SIZE = 25


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


def _get_pg_speaker_uuids_with_segments() -> dict[str, int]:
    """Return {speaker_uuid: media_file_id} for speakers that have segments."""
    from sqlalchemy import exists
    from sqlalchemy import select

    from app.models.media import Speaker
    from app.models.media import TranscriptSegment

    with session_scope() as db:
        has_segments = exists(
            select(TranscriptSegment.id).where(TranscriptSegment.speaker_id == Speaker.id)
        )
        rows = db.query(Speaker.uuid, Speaker.media_file_id).filter(has_segments).all()
        return {str(uuid): int(fid) for uuid, fid in rows}


def _get_opensearch_speaker_uuids(index_name: str) -> set[str] | None:
    """Scroll all speaker_uuid values from an OpenSearch index.

    Returns:
        Set of speaker UUID strings, or None if OpenSearch is unreachable
        or the query failed (callers must handle None to avoid treating
        a query failure as "nothing is indexed").
    """
    from app.services.opensearch_service import get_opensearch_client

    client = get_opensearch_client()
    if not client:
        return None

    if not client.indices.exists(index=index_name):
        return set()

    try:
        resp = client.search(
            index=index_name,
            body={
                "size": 0,
                "aggs": {
                    "speaker_uuids": {
                        "terms": {"field": "speaker_uuid", "size": 100000},
                    }
                },
            },
        )
        buckets = resp.get("aggregations", {}).get("speaker_uuids", {}).get("buckets", [])
        return {b["key"] for b in buckets}
    except Exception as e:
        logger.warning("Failed to query speaker UUIDs from %s: %s", index_name, e)
        return None


def _filter_unrepairable_speakers(missing_uuids: set[str]) -> set[str]:
    """Identify speakers whose segments are too short to ever extract embeddings.

    A speaker is unrepairable if, after merging adjacent segments and selecting
    the top ones, no segment meets the minimum duration threshold (0.5s).
    These speakers will always appear as "missing" but can never be fixed.
    """
    from collections import defaultdict

    from app.core.constants import SPEAKER_SHORT_SEGMENT_MIN_DURATION
    from app.services.audio_segment_utils import merge_adjacent_segments
    from app.services.audio_segment_utils import select_top_segments

    if not missing_uuids:
        return set()

    from app.models.media import Speaker
    from app.models.media import TranscriptSegment

    unrepairable: set[str] = set()

    with session_scope() as db:
        # Look up speaker IDs for missing UUIDs
        rows = db.query(Speaker.id, Speaker.uuid).filter(Speaker.uuid.in_(missing_uuids)).all()
        uuid_by_id = {r[0]: str(r[1]) for r in rows}
        speaker_ids = list(uuid_by_id.keys())

        if not speaker_ids:
            return set()

        # Batch-fetch all segments for all missing speakers in one query
        seg_rows = (
            db.query(
                TranscriptSegment.speaker_id,
                TranscriptSegment.start_time,
                TranscriptSegment.end_time,
            )
            .filter(TranscriptSegment.speaker_id.in_(speaker_ids))
            .all()
        )

        # Group segments by speaker_id
        segs_by_speaker: dict[int, list[dict]] = defaultdict(list)
        for speaker_id, start, end in seg_rows:
            segs_by_speaker[speaker_id].append({"start": float(start), "end": float(end)})

        for speaker_id, speaker_uuid in uuid_by_id.items():
            segs = segs_by_speaker.get(speaker_id)
            if not segs:
                unrepairable.add(speaker_uuid)
                continue

            merged = merge_adjacent_segments(segs)
            selected = select_top_segments(merged, min_duration=SPEAKER_SHORT_SEGMENT_MIN_DURATION)
            if not selected:
                unrepairable.add(speaker_uuid)

    return unrepairable


def _group_by_file(missing_uuids: set[str], uuid_to_file: dict[str, int]) -> dict[str, list[str]]:
    """Group missing speaker UUIDs by their media file UUID.

    Returns {file_uuid: [speaker_uuid, ...]} so the GPU pipeline can process
    per-file (it needs the audio source).
    """
    from app.models.media import MediaFile

    # Collect unique file IDs
    file_ids = {uuid_to_file[u] for u in missing_uuids if u in uuid_to_file}
    if not file_ids:
        return {}

    # Map file_id -> file_uuid
    with session_scope() as db:
        rows = db.query(MediaFile.id, MediaFile.uuid).filter(MediaFile.id.in_(file_ids)).all()
        fid_to_fuuid = {int(r[0]): str(r[1]) for r in rows}

    grouped: dict[str, list[str]] = {}
    for speaker_uuid in missing_uuids:
        fid = uuid_to_file.get(speaker_uuid)
        if fid is None:
            continue
        fuuid = fid_to_fuuid.get(fid)
        if fuuid is None:
            continue
        grouped.setdefault(fuuid, []).append(speaker_uuid)

    return grouped


# ---------------------------------------------------------------------------
# Status / counts helpers
# ---------------------------------------------------------------------------


def get_embedding_consistency_status() -> dict[str, Any]:
    """Running state + last run results (from Redis)."""
    r = get_redis()
    running = bool(r.exists(_REDIS_LOCK_KEY))

    progress_raw = r.get(_REDIS_PROGRESS_KEY)
    progress = json.loads(progress_raw) if progress_raw else None

    last_run_raw = r.get(_REDIS_LAST_RUN_KEY)
    last_run = json.loads(last_run_raw) if last_run_raw else None

    return {"running": running, "progress": progress, "last_run": last_run}


def _get_all_pg_speaker_uuids() -> set[str]:
    """Return all Speaker UUIDs in PostgreSQL (with or without segments)."""
    from app.models.media import Speaker

    with session_scope() as db:
        rows = db.query(Speaker.uuid).all()
        return {str(row[0]) for row in rows}


def get_embedding_consistency_counts() -> dict[str, Any]:
    """Dry-run: count missing speakers per index without fixing."""
    pg_speakers = _get_pg_speaker_uuids_with_segments()
    pg_uuids = set(pg_speakers.keys())

    # Also get ALL speaker UUIDs (for orphan detection)
    all_pg_uuids = _get_all_pg_speaker_uuids()

    v3_index = settings.OPENSEARCH_SPEAKER_INDEX
    v4_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4"

    os_v3 = _get_opensearch_speaker_uuids(v3_index)
    if os_v3 is None:
        return {"error": "opensearch_query_failed", "total_pg_speakers": len(pg_uuids)}
    missing_v3 = pg_uuids - os_v3

    # Speakers in OS that are valid PG speakers but have no segments
    # (not orphans — they exist in PG, just have empty segment lists)
    os_no_segments = (os_v3 & all_pg_uuids) - pg_uuids

    # True orphans: in OS but not in PG at all
    os_orphans = os_v3 - all_pg_uuids

    from app.services.embedding_mode_service import EmbeddingModeService
    from app.services.opensearch_service import get_opensearch_client

    client = get_opensearch_client()
    current_mode = EmbeddingModeService.get_current_mode()
    v4_active = current_mode == "v4"
    v4_exists = v4_active and bool(client and client.indices.exists(index=v4_index))

    missing_v4_set: set[str] = set()
    if v4_exists:
        os_v4 = _get_opensearch_speaker_uuids(v4_index)
        if os_v4 is None:
            logger.warning("Cannot query OpenSearch v4 index — reporting v3 data only")
            os_v4 = set()
        missing_v4_set = pg_uuids - os_v4

    # Identify unrepairable speakers (segments too short for embedding extraction)
    # Filter both v3 and v4 consistently
    all_missing = missing_v3 | missing_v4_set
    unrepairable = _filter_unrepairable_speakers(all_missing)

    return {
        "total_pg_speakers": len(pg_uuids),
        "v3_indexed": len(os_v3 & pg_uuids),  # Only count speakers that have segments
        "v3_missing": len(missing_v3 - unrepairable),
        "v3_unrepairable": len(unrepairable),
        "v3_no_segments": len(os_no_segments),
        "v3_orphans": len(os_orphans),
        "v4_exists": v4_exists,
        "v4_missing": len(missing_v4_set - unrepairable),
    }


# ---------------------------------------------------------------------------
# Orchestrator task (CPU queue)
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="speaker_embedding_consistency_check",
    queue="cpu",
    priority=CPUPriority.MAINTENANCE,
)
def speaker_embedding_consistency_check_task(
    self, manual: bool = False, user_id: int = 1
) -> dict[str, Any]:
    """Detect speakers missing from OpenSearch and dispatch GPU repair batches.

    Args:
        manual: If True, triggered by admin UI (always runs even if recently ran).
        user_id: Admin user ID for WebSocket notifications (default 1 for beat schedule).
    """
    r = get_redis()

    # Guard against concurrent runs
    if not r.set(_REDIS_LOCK_KEY, "1", nx=True, ex=_LOCK_TTL):
        logger.info("Embedding consistency check already running, skipping")
        return {"status": "already_running"}

    # Don't run if a migration, reindex, or related heavy task is in progress.
    # Check both the migration progress service AND Redis keys that indicate
    # active batch work (the progress service only tracks the orchestrator).
    from app.services.migration_progress_service import migration_progress

    if migration_progress.is_running():
        r.delete(_REDIS_LOCK_KEY)
        logger.info("Migration in progress, skipping consistency check")
        return {"status": "skipped", "reason": "migration_running"}

    # Check for active v4 embedding migration batches or reindex
    skip_patterns = ["task_progress:embedding_migration*", "reindex_lock:*"]
    for pattern in skip_patterns:
        for _key in r.scan_iter(match=pattern):
            r.delete(_REDIS_LOCK_KEY)
            reason = "embedding_migration_running" if "embedding" in pattern else "reindex_running"
            logger.info("%s in progress, skipping consistency check", reason)
            return {"status": "skipped", "reason": reason}

    start_time = time.time()
    try:
        # Phase 1: Detection (lightweight — two set comparisons)
        pg_speakers = _get_pg_speaker_uuids_with_segments()
        pg_uuids = set(pg_speakers.keys())
        all_pg_uuids = _get_all_pg_speaker_uuids()

        v3_index = settings.OPENSEARCH_SPEAKER_INDEX
        os_v3 = _get_opensearch_speaker_uuids(v3_index)
        if os_v3 is None:
            r.delete(_REDIS_LOCK_KEY)
            logger.error("Cannot query OpenSearch v3 index — skipping consistency check")
            return {"status": "skipped", "reason": "opensearch_query_failed"}
        missing_v3 = pg_uuids - os_v3

        # Only check v4 if the system is actively using v4 mode (migration complete).
        # If the v4 index exists but mode is still v3, the migration is in-progress
        # or pending — the consistency checker should not interfere.
        v4_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4"
        from app.services.embedding_mode_service import EmbeddingModeService
        from app.services.opensearch_service import get_opensearch_client
        from app.services.opensearch_service import remove_speaker_embedding

        client = get_opensearch_client()
        current_mode = EmbeddingModeService.get_current_mode()
        v4_active = current_mode == "v4"
        v4_exists = v4_active and bool(client and client.indices.exists(index=v4_index))
        missing_v4: set[str] = set()
        os_v4: set[str] = set()
        if v4_exists:
            _os_v4_result = _get_opensearch_speaker_uuids(v4_index)
            if _os_v4_result is None:
                r.delete(_REDIS_LOCK_KEY)
                logger.error("Cannot query OpenSearch v4 index — skipping consistency check")
                return {"status": "skipped", "reason": "opensearch_query_failed"}
            os_v4 = _os_v4_result
            missing_v4 = pg_uuids - os_v4

        # Phase 1b: Cleanup stale OS entries (speakers indexed but no longer
        # have segments, or don't exist in PG at all). This is CPU-only work.
        # Check both v3 and v4 indices. remove_speaker_embedding() deletes from both.
        os_all = os_v3 | os_v4
        stale_uuids = (os_all - pg_uuids) & all_pg_uuids  # In OS, in PG, but no segments
        orphan_uuids = os_all - all_pg_uuids  # In OS but not in PG at all
        cleanup_uuids = stale_uuids | orphan_uuids

        cleaned = 0
        if cleanup_uuids:
            for uuid in cleanup_uuids:
                try:
                    remove_speaker_embedding(uuid)
                    cleaned += 1
                except Exception as e:
                    logger.warning("Failed to remove stale speaker %s: %s", uuid, e)

            logger.info(
                "Cleaned %d stale/orphan speaker embeddings from OS (%d no-segment, %d orphan)",
                cleaned,
                len(stale_uuids),
                len(orphan_uuids),
            )

        total_missing = len(missing_v3) + len(missing_v4)

        if total_missing == 0:
            # Healthy — no gaps
            r.delete(_REDIS_LOCK_KEY)
            duration = round(time.time() - start_time, 1)
            last_run = {
                "timestamp": time.time(),
                "status": "healthy",
                "v3_missing": 0,
                "v4_missing": 0,
                "cleaned": cleaned,
                "total_pg_speakers": len(pg_uuids),
                "duration_seconds": duration,
            }
            r.set(_REDIS_LAST_RUN_KEY, json.dumps(last_run), ex=86400 * 7)
            logger.info(
                "Embedding consistency check: healthy (%d speakers, %d cleaned, %.1fs)",
                len(pg_uuids),
                cleaned,
                duration,
            )
            return {
                "status": "healthy",
                "total_pg_speakers": len(pg_uuids),
                "cleaned": cleaned,
            }

        # Filter out unrepairable speakers (segments too short for embeddings)
        unrepairable = _filter_unrepairable_speakers(missing_v3 | missing_v4)
        missing_v3 -= unrepairable
        missing_v4 -= unrepairable
        total_missing = len(missing_v3) + len(missing_v4)

        if total_missing == 0:
            # All missing speakers are unrepairable — nothing to fix
            r.delete(_REDIS_LOCK_KEY)
            duration = round(time.time() - start_time, 1)
            last_run = {
                "timestamp": time.time(),
                "status": "healthy",
                "v3_missing": 0,
                "v4_missing": 0,
                "unrepairable": len(unrepairable),
                "total_pg_speakers": len(pg_uuids),
                "duration_seconds": duration,
            }
            r.set(_REDIS_LAST_RUN_KEY, json.dumps(last_run), ex=86400 * 7)
            logger.info(
                "Embedding consistency check: healthy (%d speakers, %d unrepairable, %.1fs)",
                len(pg_uuids),
                len(unrepairable),
                duration,
            )
            return {
                "status": "healthy",
                "total_pg_speakers": len(pg_uuids),
                "unrepairable": len(unrepairable),
            }

        logger.info(
            "Embedding consistency: %d missing from v3, %d missing from v4, %d unrepairable",
            len(missing_v3),
            len(missing_v4),
            len(unrepairable),
        )

        # Phase 2: Group by file and dispatch GPU batch tasks
        # Combine missing sets — the batch worker will write to whichever
        # indices each speaker is missing from
        all_missing = missing_v3 | missing_v4
        grouped = _group_by_file(all_missing, pg_speakers)

        if not grouped:
            r.delete(_REDIS_LOCK_KEY)
            return {"status": "no_repairable", "missing": total_missing}

        file_uuids = list(grouped.keys())
        total_files = len(file_uuids)

        # Initialize ProgressTracker for ETA + queue status integration
        from app.services.progress_tracker import ProgressTracker

        tracker = ProgressTracker(
            task_type="embedding_consistency",
            user_id=user_id,
            total=total_files,
        )
        tracker.start(message="Starting embedding consistency repair...")

        # Store progress (include user_id so batch workers can send notifications)
        progress_data = {
            "total_files": total_files,
            "processed_files": 0,
            "v3_missing": len(missing_v3),
            "v4_missing": len(missing_v4),
            "v4_exists": v4_exists,
            "unrepairable": len(unrepairable),
            "failed_files": [],
            "repaired": 0,
            "skipped": 0,
            "running": True,
            "start_time": time.time(),
            "user_id": user_id,
        }
        r.set(_REDIS_PROGRESS_KEY, json.dumps(progress_data), ex=_LOCK_TTL)

        # Send initial progress
        send_ws_event(user_id, NOTIFICATION_TYPE_EMBEDDING_CONSISTENCY_PROGRESS, progress_data)

        # Dispatch batches
        batches = [file_uuids[i : i + _BATCH_SIZE] for i in range(0, len(file_uuids), _BATCH_SIZE)]

        batch_task_ids = []
        for batch_idx, batch in enumerate(batches):
            result = speaker_embedding_consistency_repair_batch_task.apply_async(
                kwargs={
                    "file_uuids": batch,
                    "batch_index": batch_idx,
                    "total_batches": len(batches),
                    "total_files": total_files,
                    "missing_v3_uuids": list(missing_v3),
                    "missing_v4_uuids": list(missing_v4) if v4_exists else [],
                    "v4_exists": v4_exists,
                },
                priority=GPUPriority.ADMIN_MIGRATION,
            )
            batch_task_ids.append(result.id)

        # Store batch IDs for revocation
        r.set(_REDIS_BATCH_IDS_KEY, json.dumps(batch_task_ids), ex=86400)

        logger.info("Dispatched %d repair batches for %d files", len(batches), total_files)
        return {
            "status": "repairing",
            "total_files": total_files,
            "v3_missing": len(missing_v3),
            "v4_missing": len(missing_v4),
            "batches": len(batches),
        }

    except Exception as e:
        logger.error("Embedding consistency check failed: %s", e, exc_info=True)
        r.delete(_REDIS_LOCK_KEY)
        send_ws_event(
            user_id,
            NOTIFICATION_TYPE_EMBEDDING_CONSISTENCY_COMPLETE,
            {"status": "error", "error": "Embedding consistency check failed"},
        )
        return {"status": "error", "error": str(e)}


def stop_consistency_repair() -> dict[str, Any]:
    """Cancel a running consistency repair by revoking batch tasks."""
    from app.services.progress_tracker import ProgressTracker

    r = get_redis()

    if not r.exists(_REDIS_LOCK_KEY):
        return {"status": "not_running"}

    # Retrieve user_id from progress data (stored by orchestrator)
    raw = r.get(_REDIS_PROGRESS_KEY)
    notify_user_id = 1
    if raw:
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            notify_user_id = json.loads(raw).get("user_id", 1)

    # Revoke pending batch tasks
    batch_ids_raw = r.get(_REDIS_BATCH_IDS_KEY)
    revoked = 0
    if batch_ids_raw:
        batch_ids = json.loads(batch_ids_raw)
        for tid in batch_ids:
            celery_app.control.revoke(tid, terminate=True)
            revoked += 1
        r.delete(_REDIS_BATCH_IDS_KEY)

    # Clear ProgressTracker so queue status clears
    tracker = ProgressTracker(
        task_type="embedding_consistency",
        user_id=notify_user_id,
        total=0,
    )
    tracker.complete(message="Stopped")

    # Clear lock and progress
    r.delete(_REDIS_LOCK_KEY)
    r.delete(_REDIS_PROGRESS_KEY)

    send_ws_event(
        notify_user_id,
        NOTIFICATION_TYPE_EMBEDDING_CONSISTENCY_COMPLETE,
        {"status": "stopped"},
    )

    return {"status": "stopped", "revoked_tasks": revoked}


# ---------------------------------------------------------------------------
# GPU batch worker
# ---------------------------------------------------------------------------


def _v3_result_writer(
    prepared,
    results_by_model: dict,
    target_uuids: set[str],
) -> int:
    """Write extracted embeddings to the v3 main speaker index."""
    import numpy as np

    from app.services.opensearch_service import add_speaker_embedding

    embedding_results = results_by_model.get("embedding", [])
    if not embedding_results:
        return 0

    # Group by speaker
    speaker_embeddings: dict[int, list] = {}
    for sr in embedding_results:
        speaker_embeddings.setdefault(sr.speaker_id, []).append(sr.value)

    speaker_by_id = {sp.id: sp for sp in prepared.speakers}
    written = 0

    for speaker_id, embs in speaker_embeddings.items():
        speaker = speaker_by_id.get(speaker_id)
        if not speaker or speaker.uuid not in target_uuids:
            continue

        if len(embs) == 1:
            aggregated = embs[0]
            norm = np.linalg.norm(aggregated)
            if norm > 0:
                aggregated = aggregated / norm
        else:
            stacked = np.vstack(embs)
            aggregated = np.mean(stacked, axis=0)
            norm = np.linalg.norm(aggregated)
            if norm > 0:
                aggregated = aggregated / norm

        result = add_speaker_embedding(
            speaker_id=speaker.id,
            speaker_uuid=speaker.uuid,
            user_id=prepared.user_id,
            name=speaker.name,
            embedding=aggregated.tolist(),
            media_file_id=prepared.media_file_id,
            segment_count=len(embs),
        )
        if result is not None:
            written += 1

    return written


def _v4_result_writer(
    prepared,
    results_by_model: dict,
    target_uuids: set[str],
) -> int:
    """Write extracted embeddings to the v4 staging index."""
    import numpy as np

    from app.services.opensearch_service import add_speaker_embedding_v4

    embedding_results = results_by_model.get("embedding", [])
    if not embedding_results:
        return 0

    speaker_embeddings: dict[int, list] = {}
    for sr in embedding_results:
        speaker_embeddings.setdefault(sr.speaker_id, []).append(sr.value)

    speaker_by_id = {sp.id: sp for sp in prepared.speakers}
    written = 0

    for speaker_id, embs in speaker_embeddings.items():
        speaker = speaker_by_id.get(speaker_id)
        if not speaker or speaker.uuid not in target_uuids:
            continue

        if len(embs) == 1:
            aggregated = embs[0]
            norm = np.linalg.norm(aggregated)
            if norm > 0:
                aggregated = aggregated / norm
        else:
            stacked = np.vstack(embs)
            aggregated = np.mean(stacked, axis=0)
            norm = np.linalg.norm(aggregated)
            if norm > 0:
                aggregated = aggregated / norm

        result = add_speaker_embedding_v4(
            speaker_id=speaker.id,
            speaker_uuid=speaker.uuid,
            user_id=prepared.user_id,
            name=speaker.name,
            embedding=aggregated.tolist(),
            media_file_id=prepared.media_file_id,
            segment_count=len(embs),
        )
        if result is not None:
            written += 1

    return written


def _update_repair_progress(
    total_files: int,
    success: bool = True,
    file_uuid: str | None = None,
    repaired_count: int = 0,
    user_id: int = 1,
) -> dict[str, Any] | None:
    """Atomically update repair progress in Redis + emit via ProgressTracker.

    Uses Redis WATCH/MULTI for optimistic locking to prevent lost updates
    when multiple GPU batch workers complete concurrently.
    """
    from app.services.progress_tracker import ProgressTracker
    from app.services.progress_tracker import emit_progress_notification

    r = get_redis()
    progress: dict[str, Any] = {}
    processed = 0

    # Optimistic locking: retry on concurrent modification
    for _attempt in range(5):
        try:
            pipe = r.pipeline(True)  # transactional pipeline
            pipe.watch(_REDIS_PROGRESS_KEY)

            raw_val: str | bytes | None = pipe.get(_REDIS_PROGRESS_KEY)  # type: ignore[assignment]
            if not raw_val:
                pipe.unwatch()
                return None

            progress = json.loads(str(raw_val))
            progress["processed_files"] = progress.get("processed_files", 0) + 1
            progress["repaired"] = progress.get("repaired", 0) + repaired_count

            if not success and file_uuid:
                failed = progress.get("failed_files", [])
                failed.append(file_uuid)
                progress["failed_files"] = failed

            processed = progress["processed_files"]
            progress["running"] = processed < total_files

            pipe.multi()
            pipe.set(_REDIS_PROGRESS_KEY, json.dumps(progress), ex=_LOCK_TTL)
            pipe.execute()
            break  # success
        except Exception:  # noqa: S112  # nosec B112 — intentional retry on Redis WatchError
            continue
    else:
        # All retries exhausted; read current state for notification
        fallback_raw = r.get(_REDIS_PROGRESS_KEY)
        if not fallback_raw:
            return None
        progress = json.loads(str(fallback_raw))
        processed = progress.get("processed_files", 0)

    # Use ProgressTracker for ETA + queue status integration
    tracker = ProgressTracker(
        task_type="embedding_consistency",
        user_id=user_id,
        total=total_files,
    )
    existing = ProgressTracker.get_state("embedding_consistency", user_id)
    if existing:
        tracker.resume_from_state(existing)

    emit_progress_notification(
        tracker=tracker,
        processed=processed,
        user_id=user_id,
        notification_type=NOTIFICATION_TYPE_EMBEDDING_CONSISTENCY_PROGRESS,
        extra_data={
            "processed_files": processed,
            "total_files": total_files,
            "repaired": progress.get("repaired", 0),
            "failed_files": progress.get("failed_files", []),
            "running": progress["running"],
        },
        message=f"Repaired {processed} of {total_files} files",
        failed_item=file_uuid if not success else None,
    )
    return progress  # type: ignore[return-value]


def _run_repair_phase(
    mode: Literal["v3", "v4"],
    target_uuids: set[str],
    result_writer_fn,
    files_with_speakers: list,
    file_written: dict[str, int],
    is_running_check,
    batch_index: int,
) -> int:
    """Run a single repair phase (v3 or v4) using the migration pipeline."""
    from app.core.constants import SPEAKER_SHORT_SEGMENT_MIN_DURATION
    from app.services.speaker_analysis_models import EmbeddingModelAdapter
    from app.services.speaker_analysis_models import MultiModelRunner
    from app.services.speaker_embedding_service import get_cached_embedding_service
    from app.tasks.migration_pipeline import process_batch_pipelined

    try:
        embedding_service = get_cached_embedding_service(mode=mode)
        runner = MultiModelRunner([EmbeddingModelAdapter(embedding_service)])

        # Track actual embeddings written per file via closure.
        # Safe because process_batch_pipelined processes files sequentially:
        # writer runs, then on_success, before moving to the next file.
        last_write_count = 0

        def writer(prep, results):
            nonlocal last_write_count
            count = result_writer_fn(prep, results, target_uuids)
            last_write_count = count
            return count

        def on_success(fuuid: str) -> None:
            file_written[fuuid] = file_written.get(fuuid, 0) + last_write_count

        success, _ = process_batch_pipelined(
            prepared_files=files_with_speakers,
            runner=runner,
            result_writer=writer,
            is_running_check=is_running_check,
            on_file_success=on_success,
            on_file_failure=lambda fuuid, _: None,
            min_duration=SPEAKER_SHORT_SEGMENT_MIN_DURATION,
        )
        return success
    except Exception as e:
        logger.error("%s repair failed for batch %d: %s", mode, batch_index, e)
        return 0


@celery_app.task(
    bind=True,
    name="speaker_embedding_consistency_repair_batch",
    queue="gpu",
    priority=GPUPriority.ADMIN_MIGRATION,
)
def speaker_embedding_consistency_repair_batch_task(
    self,
    file_uuids: list[str],
    batch_index: int = 0,
    total_batches: int = 1,
    total_files: int = 0,
    missing_v3_uuids: list[str] | None = None,
    missing_v4_uuids: list[str] | None = None,
    v4_exists: bool = False,
) -> dict[str, Any]:
    """Re-extract embeddings for speakers missing from OpenSearch indices."""
    from app.services.embedding_mode_service import MODE_V3
    from app.services.embedding_mode_service import MODE_V4
    from app.tasks.migration_pipeline import prepare_file

    logger.info(
        "Consistency repair batch %d/%d: processing %d files",
        batch_index + 1,
        total_batches,
        len(file_uuids),
    )

    r = get_redis()
    missing_v3_set = set(missing_v3_uuids or [])
    missing_v4_set = set(missing_v4_uuids or [])

    need_v3 = bool(missing_v3_set)
    need_v4 = bool(missing_v4_set) and v4_exists

    if not need_v3 and not need_v4:
        return {"status": "nothing_to_do", "batch_index": batch_index}

    # Retrieve user_id from progress data for notifications
    raw = r.get(_REDIS_PROGRESS_KEY)
    notify_user_id = 1
    if raw:
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            notify_user_id = json.loads(raw).get("user_id", 1)

    # Phase 1: Prepare files
    files_with_speakers: list[tuple[str, Any]] = []
    for fuuid in file_uuids:
        if not r.exists(_REDIS_LOCK_KEY):
            logger.warning("Consistency repair stopped — aborting batch")
            break
        try:
            prepared = prepare_file(fuuid)
            if prepared is None:
                _update_repair_progress(total_files, success=True, user_id=notify_user_id)
            else:
                files_with_speakers.append((fuuid, prepared))
        except Exception as e:
            logger.error("Failed to prepare file %s: %s", fuuid, e)
            _update_repair_progress(
                total_files, success=False, file_uuid=fuuid, user_id=notify_user_id
            )

    if not files_with_speakers:
        _check_repair_completion(total_files, user_id=notify_user_id)
        return {"status": "no_files", "batch_index": batch_index}

    file_written: dict[str, int] = {}

    def is_running():
        return bool(r.exists(_REDIS_LOCK_KEY))

    # Phase 2: V3 repair
    v3_repaired = 0
    if need_v3:
        v3_repaired = _run_repair_phase(
            MODE_V3,
            missing_v3_set,
            _v3_result_writer,
            files_with_speakers,
            file_written,
            is_running,
            batch_index,
        )

    # Phase 3: V4 repair
    v4_repaired = 0
    if need_v4:
        v4_repaired = _run_repair_phase(
            MODE_V4,
            missing_v4_set,
            _v4_result_writer,
            files_with_speakers,
            file_written,
            is_running,
            batch_index,
        )

    # Update progress per file — count actual embeddings written, not files
    for fuuid, _ in files_with_speakers:
        count = file_written.get(fuuid, 0)
        _update_repair_progress(
            total_files,
            success=count > 0,
            file_uuid=fuuid if count == 0 else None,
            repaired_count=count,
            user_id=notify_user_id,
        )

    _check_repair_completion(total_files, user_id=notify_user_id)

    # Free intermediate CUDA tensors for follow-on tasks
    from app.tasks.migration_pipeline import cleanup_gpu_memory

    cleanup_gpu_memory()

    return {
        "status": "success",
        "batch_index": batch_index,
        "v3_repaired": v3_repaired,
        "v4_repaired": v4_repaired,
    }


def _check_repair_completion(total_files: int, user_id: int = 1) -> None:
    """Check if all batches are done and finalize."""
    from app.services.progress_tracker import ProgressTracker

    r = get_redis()
    raw = r.get(_REDIS_PROGRESS_KEY)
    if not raw:
        return

    progress = json.loads(raw)
    processed = progress.get("processed_files", 0)
    # Prefer user_id from progress data (set by orchestrator)
    notify_user_id = progress.get("user_id", user_id)

    if processed >= total_files:
        duration = round(time.time() - (progress.get("start_time", time.time())), 1)
        last_run = {
            "timestamp": time.time(),
            "status": "repaired",
            "repaired": progress.get("repaired", 0),
            "unrepairable": progress.get("unrepairable", 0),
            "failed_files": progress.get("failed_files", []),
            "total_files": total_files,
            "duration_seconds": duration,
        }
        r.set(_REDIS_LAST_RUN_KEY, json.dumps(last_run), ex=86400 * 7)

        # Complete the ProgressTracker so queue status clears
        tracker = ProgressTracker(
            task_type="embedding_consistency",
            user_id=notify_user_id,
            total=total_files,
        )
        tracker.complete(message="Embedding consistency repair complete")

        send_ws_event(
            notify_user_id,
            NOTIFICATION_TYPE_EMBEDDING_CONSISTENCY_COMPLETE,
            {
                "status": "completed",
                "repaired": progress.get("repaired", 0),
                "unrepairable": progress.get("unrepairable", 0),
                "failed_files": progress.get("failed_files", []),
                "total_files": total_files,
                "duration_seconds": duration,
            },
        )

        # Release lock
        r.delete(_REDIS_LOCK_KEY)
        r.delete(_REDIS_PROGRESS_KEY)
        logger.info("Embedding consistency repair complete: %d files processed", total_files)
