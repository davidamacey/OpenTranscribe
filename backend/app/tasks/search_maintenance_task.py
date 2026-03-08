"""Periodic search index maintenance tasks.

Includes:
- search_index_maintenance: Detects unindexed files and dispatches reindex tasks.
- opensearch_orphan_cleanup: Detects and removes orphaned OpenSearch documents
  across all indices (speakers, speakers_v4, transcripts, transcript_chunks,
  transcript_summaries) for file IDs that no longer exist in PostgreSQL.
"""

import contextlib
import json
import logging
import time
from typing import Any

from app.core.celery import celery_app
from app.core.config import settings
from app.core.constants import NOTIFICATION_TYPE_DATA_INTEGRITY_COMPLETE
from app.core.constants import NOTIFICATION_TYPE_DATA_INTEGRITY_PROGRESS
from app.core.constants import CPUPriority
from app.core.redis import get_redis
from app.utils.websocket_notify import send_ws_event

logger = logging.getLogger(__name__)

_REDIS_LOCK_KEY = "data_integrity_running"
_REDIS_LAST_RUN_KEY = "data_integrity_last_run"


def _get_indexed_uuids() -> set[str]:
    """Query OpenSearch to get all file UUIDs currently in the chunks index.

    Returns:
        Set of file UUID strings already indexed.
    """
    from app.services.opensearch_service import opensearch_client

    if not opensearch_client:
        return set()

    index_name = settings.OPENSEARCH_CHUNKS_INDEX
    try:
        if not opensearch_client.indices.exists(index=index_name):
            return set()

        response = opensearch_client.search(
            index=index_name,
            body={
                "size": 0,
                "aggs": {
                    "file_uuids": {
                        "terms": {
                            "field": "file_uuid",
                            "size": 50000,
                        }
                    }
                },
            },
        )
        buckets = response.get("aggregations", {}).get("file_uuids", {}).get("buckets", [])
        return {b["key"] for b in buckets}
    except Exception as e:
        logger.warning(f"Could not check indexed files: {e}")
        return set()


def _find_unindexed_by_user(
    completed_files: list[Any], indexed_uuids: set[str]
) -> dict[int, list[str]]:
    """Group unindexed files by user ID.

    Args:
        completed_files: List of MediaFile ORM objects with status COMPLETED.
        indexed_uuids: Set of file UUIDs already in the search index.

    Returns:
        Dict mapping user_id to list of unindexed file UUID strings.
    """
    unindexed_by_user: dict[int, list[str]] = {}
    for f in completed_files:
        file_uuid = str(f.uuid)
        if file_uuid not in indexed_uuids:
            user_id = int(f.user_id)
            if user_id not in unindexed_by_user:
                unindexed_by_user[user_id] = []
            unindexed_by_user[user_id].append(file_uuid)
    return unindexed_by_user


def _dispatch_reindex_tasks(unindexed_by_user: dict[int, list[str]]) -> None:
    """Dispatch reindex Celery tasks for each user with unindexed files.

    Args:
        unindexed_by_user: Dict mapping user_id to list of file UUIDs.
    """
    from app.tasks.reindex_task import reindex_transcripts_task

    for user_id, file_uuids in unindexed_by_user.items():
        try:
            reindex_transcripts_task.delay(
                user_id=user_id,
                file_uuids=file_uuids,
            )
            logger.info(f"Dispatched reindex for user {user_id}: {len(file_uuids)} files")
        except Exception as e:
            logger.error(f"Failed to dispatch reindex for user {user_id}: {e}")


@celery_app.task(name="search_index_maintenance", queue="cpu", priority=CPUPriority.MAINTENANCE)
def search_index_maintenance_task() -> dict[str, Any]:
    """
    Check for completed files missing from the search index and trigger re-indexing.

    This task runs periodically via Celery Beat and on startup to ensure
    all completed transcripts are searchable. This handles:
    - First-time setup: existing files before search feature was added
    - Failed indexing: files where chunk indexing failed during transcription
    - Index recovery: after OpenSearch data loss or index recreation

    Returns:
        Dict with maintenance stats.
    """
    from sqlalchemy import exists
    from sqlalchemy import select

    from app.db.session_utils import session_scope
    from app.models.media import FileStatus
    from app.models.media import MediaFile
    from app.models.media import TranscriptSegment

    stats: dict[str, int | bool | str] = {
        "total_completed_files": 0,
        "indexed_files": 0,
        "unindexed_files": 0,
        "reindex_triggered": False,
    }

    try:
        with session_scope() as db:
            # Only consider completed files that have transcript segments
            has_segments = exists(
                select(TranscriptSegment.id).where(TranscriptSegment.media_file_id == MediaFile.id)
            )
            completed_files = (
                db.query(MediaFile)
                .filter(MediaFile.status == FileStatus.COMPLETED, has_segments)
                .all()
            )

            if not completed_files:
                logger.info("No completed files found, nothing to maintain")
                return stats

            stats["total_completed_files"] = len(completed_files)

            indexed_uuids = _get_indexed_uuids()
            stats["indexed_files"] = len(indexed_uuids)

            unindexed_by_user = _find_unindexed_by_user(completed_files, indexed_uuids)
            total_unindexed = sum(len(uuids) for uuids in unindexed_by_user.values())
            stats["unindexed_files"] = total_unindexed

            if total_unindexed == 0:
                logger.info(f"All {stats['total_completed_files']} completed files are indexed")
                return stats

            logger.info(
                f"Found {total_unindexed} unindexed files across "
                f"{len(unindexed_by_user)} users. Dispatching reindex tasks."
            )

            _dispatch_reindex_tasks(unindexed_by_user)
            stats["reindex_triggered"] = True

    except Exception as e:
        logger.error(f"Search maintenance task failed: {e}")
        stats["error"] = str(e)

    return stats


# ---------------------------------------------------------------------------
# Orphan cleanup helpers
# ---------------------------------------------------------------------------


def _get_all_file_ids_from_db() -> set[int]:
    """Return all MediaFile IDs that exist in PostgreSQL."""
    from app.db.session_utils import session_scope
    from app.models.media import MediaFile

    with session_scope() as db:
        rows = db.query(MediaFile.id).all()
        return {int(row[0]) for row in rows}


def _get_all_file_uuids_from_db() -> set[str]:
    """Return all MediaFile UUIDs that exist in PostgreSQL."""
    from app.db.session_utils import session_scope
    from app.models.media import MediaFile

    with session_scope() as db:
        rows = db.query(MediaFile.uuid).all()
        return {str(row[0]) for row in rows}


def _get_all_speaker_uuids_from_db() -> set[str]:
    """Return all Speaker UUIDs that exist in PostgreSQL.

    Used to detect orphaned speaker embeddings from speakers that were
    deleted via merges, reprocessing, or direct deletion without OpenSearch
    cleanup.
    """
    from app.db.session_utils import session_scope
    from app.models.media import Speaker

    with session_scope() as db:
        rows = db.query(Speaker.uuid).all()
        return {str(row[0]) for row in rows}


def _cleanup_index_by_field(
    client: Any,
    index_name: str,
    field_name: str,
    valid_values: set,
    dry_run: bool = False,
) -> dict[str, int]:
    """Remove documents from an OpenSearch index where field_name is not in valid_values.

    Args:
        client: OpenSearch client.
        index_name: Index to scan.
        field_name: Document field containing the file identifier.
        valid_values: Set of valid values (file IDs or UUIDs that exist in DB).
        dry_run: If True, count orphans without deleting.

    Returns:
        Dict with total_docs, orphaned_docs, deleted_docs.
    """
    result: dict[str, int] = {"total_docs": 0, "orphaned_docs": 0, "deleted_docs": 0}

    if not client.indices.exists(index=index_name):
        return result

    with contextlib.suppress(Exception):
        count_resp = client.count(index=index_name)
        result["total_docs"] = count_resp.get("count", 0)

    # Use terms aggregation to find all unique file identifiers in the index
    try:
        agg_resp = client.search(
            index=index_name,
            body={
                "size": 0,
                "aggs": {
                    "file_ids": {
                        "terms": {"field": field_name, "size": 50000},
                    }
                },
            },
        )
        buckets = agg_resp.get("aggregations", {}).get("file_ids", {}).get("buckets", [])
    except Exception as e:
        logger.warning(f"Aggregation on {index_name}.{field_name} failed: {e}")
        return result

    orphan_values: list[Any] = []
    for bucket in buckets:
        key = bucket["key"]
        # Coerce to the same type as valid_values for comparison
        comparable_key = str(key) if isinstance(next(iter(valid_values), None), str) else int(key)
        if comparable_key not in valid_values:
            orphan_values.append(key)
            result["orphaned_docs"] += bucket["doc_count"]

    if not orphan_values or dry_run:
        return result

    # Delete orphaned documents in batches
    for i in range(0, len(orphan_values), 100):
        batch = orphan_values[i : i + 100]
        try:
            del_resp = client.delete_by_query(
                index=index_name,
                body={"query": {"terms": {field_name: batch}}},
                refresh=True,
            )
            result["deleted_docs"] += del_resp.get("deleted", 0)
        except Exception as e:
            logger.warning(f"delete_by_query on {index_name} failed for batch: {e}")

    return result


def run_orphan_cleanup(dry_run: bool = False) -> dict[str, Any]:
    """Scan all OpenSearch indices and remove orphaned documents.

    Speaker indices are checked at the speaker UUID level (not file level)
    so that embeddings from merged or deleted speakers are caught even when
    the parent file still exists.

    Args:
        dry_run: If True, count orphans without deleting them.

    Returns:
        Per-index stats: {index_name: {total_docs, orphaned_docs, deleted_docs}}.
    """
    from app.services.opensearch_service import get_opensearch_client

    client = get_opensearch_client()
    if not client:
        return {"error": "OpenSearch not available"}

    valid_file_ids = _get_all_file_ids_from_db()
    valid_file_uuids = _get_all_file_uuids_from_db()
    valid_speaker_uuids = _get_all_speaker_uuids_from_db()

    # Index configs: (index_name, field_name, valid_set)
    # Speaker indices use speaker_uuid (not media_file_id) so that orphans from
    # speaker merges and reprocessing (where the file still exists but the specific
    # speaker was deleted) are also caught — not just orphans from deleted files.
    index_configs: list[tuple[str, str, set]] = [
        (settings.OPENSEARCH_SPEAKER_INDEX, "speaker_uuid", valid_speaker_uuids),
        (f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4", "speaker_uuid", valid_speaker_uuids),
        (settings.OPENSEARCH_TRANSCRIPT_INDEX, "file_uuid", valid_file_uuids),
        (settings.OPENSEARCH_CHUNKS_INDEX, "file_uuid", valid_file_uuids),
        (settings.OPENSEARCH_SUMMARY_INDEX, "file_id", valid_file_ids),
    ]

    results: dict[str, Any] = {}
    total_orphans = 0
    total_deleted = 0

    for idx, (index_name, field_name, valid_set) in enumerate(index_configs):
        logger.info(f"Scanning index {index_name} for orphans...")
        stats = _cleanup_index_by_field(client, index_name, field_name, valid_set, dry_run)
        results[index_name] = stats
        total_orphans += stats["orphaned_docs"]
        total_deleted += stats["deleted_docs"]

        # Send progress notification
        send_ws_event(
            1,
            NOTIFICATION_TYPE_DATA_INTEGRITY_PROGRESS,
            {
                "current_index": index_name,
                "processed_indices": idx + 1,
                "total_indices": len(index_configs),
                "progress": round((idx + 1) / len(index_configs) * 100),
                "running": True,
            },
        )

    results["summary"] = {
        "total_orphans_found": total_orphans,
        "total_deleted": total_deleted,
        "dry_run": dry_run,
    }

    action = "Found" if dry_run else "Cleaned"
    logger.info(
        f"Orphan cleanup complete: {action} {total_orphans} orphaned documents "
        f"across {len(index_configs)} indices"
    )

    return results


@celery_app.task(name="opensearch_orphan_cleanup", queue="cpu", priority=CPUPriority.MAINTENANCE)
def opensearch_orphan_cleanup_task() -> dict[str, Any]:
    """Celery task: scan all OpenSearch indices and remove orphaned documents.

    Guarded by a Redis lock to prevent concurrent runs.

    Returns:
        Per-index cleanup stats.
    """
    r = get_redis()

    # Guard against concurrent runs
    if not r.set(_REDIS_LOCK_KEY, "1", nx=True, ex=3600):
        logger.info("Orphan cleanup already running, skipping")
        return {"status": "already_running"}

    start_time = time.time()
    try:
        results = run_orphan_cleanup(dry_run=False)

        # Store last run results
        last_run_data = {
            "timestamp": time.time(),
            "results": results,
            "duration_seconds": round(time.time() - start_time, 1),
        }
        r.set(_REDIS_LAST_RUN_KEY, json.dumps(last_run_data), ex=86400 * 7)  # Keep 7 days

        # Send completion notification
        send_ws_event(
            1,
            NOTIFICATION_TYPE_DATA_INTEGRITY_COMPLETE,
            {
                "status": "completed",
                "results": results,
                "duration_seconds": last_run_data["duration_seconds"],
            },
        )

        return results

    except Exception as e:
        logger.error(f"Orphan cleanup task failed: {e}", exc_info=True)
        send_ws_event(
            1,
            NOTIFICATION_TYPE_DATA_INTEGRITY_COMPLETE,
            {"status": "error", "error": str(e)},
        )
        return {"error": str(e)}
    finally:
        r.delete(_REDIS_LOCK_KEY)


def get_integrity_status() -> dict[str, Any]:
    """Get the current data integrity status (running? last results?).

    Returns:
        Dict with running, last_run timestamp, and last_run results.
    """
    r = get_redis()

    running = bool(r.exists(_REDIS_LOCK_KEY))

    last_run_raw = r.get(_REDIS_LAST_RUN_KEY)
    last_run = json.loads(last_run_raw) if last_run_raw else None

    return {
        "running": running,
        "last_run": last_run,
    }


def get_integrity_counts() -> dict[str, Any]:
    """Quick count-only scan (dry_run) to show orphan counts without deletion."""
    return run_orphan_cleanup(dry_run=True)
