"""Periodic search index maintenance task."""

import logging
from typing import Any

from app.core.celery import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)


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


@celery_app.task(name="search_index_maintenance", queue="cpu")
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
    from app.db.session_utils import session_scope
    from app.models.media import FileStatus
    from app.models.media import MediaFile

    stats: dict[str, int | bool | str] = {
        "total_completed_files": 0,
        "indexed_files": 0,
        "unindexed_files": 0,
        "reindex_triggered": False,
    }

    try:
        with session_scope() as db:
            completed_files = (
                db.query(MediaFile).filter(MediaFile.status == FileStatus.COMPLETED).all()
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
