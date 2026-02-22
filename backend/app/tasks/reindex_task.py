"""Celery task for re-indexing transcripts with chunk-level embeddings."""

import functools
import logging
from typing import Any

from app.core.celery import celery_app
from app.core.config import settings
from app.core.constants import NOTIFICATION_TYPE_REINDEX_COMPLETE
from app.core.constants import NOTIFICATION_TYPE_REINDEX_PROGRESS
from app.core.constants import NOTIFICATION_TYPE_REINDEX_STOPPED

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def _get_notification_redis():
    """Get or create a module-level Redis client for notifications."""
    import redis as sync_redis

    return sync_redis.from_url(settings.REDIS_URL)


def _ensure_neural_pipeline_ready() -> bool:
    """Ensure neural search pipeline is ready for indexing.

    Returns:
        True if neural search is available and pipeline is ready.
    """
    if not settings.OPENSEARCH_NEURAL_SEARCH_ENABLED:
        return False

    try:
        from app.services.search.indexing_service import ensure_neural_ingest_pipeline
        from app.services.search.indexing_service import reset_neural_pipeline_state

        # Reset state to force re-check
        reset_neural_pipeline_state()

        if ensure_neural_ingest_pipeline():
            logger.info("Neural ingest pipeline ready for reindexing")
            return True
        else:
            logger.warning("Neural ingest pipeline not available")
            return False
    except Exception as e:
        logger.warning(f"Could not setup neural pipeline: {e}")
        return False


def _handle_model_switch(model_id: str) -> dict[str, Any] | None:
    """Switch embedding model if valid. Returns error dict on failure, None on success.

    Only handles OpenSearch neural models.
    """
    from app.core.constants import OPENSEARCH_EMBEDDING_MODELS
    from app.services.search.indexing_service import recreate_index_for_dimension

    if model_id in OPENSEARCH_EMBEDDING_MODELS:
        model_info = OPENSEARCH_EMBEDDING_MODELS[model_id]
        new_dimension: int = model_info["dimension"]  # type: ignore[assignment]

        # Recreate index with new dimension if needed
        if not recreate_index_for_dimension(new_dimension):
            logger.error(f"Failed to recreate index for dimension {new_dimension}")
            return {"error": "Failed to recreate index for new model dimension"}

        logger.info(f"Worker using neural model {model_id} ({new_dimension}d)")
        return None

    logger.warning(f"Unknown model_id: {model_id}, using current model")
    return None


def _extract_file_metadata(db: Any, media_file: Any) -> dict[str, Any] | None:
    """Extract segments and metadata from a media file for indexing.

    Returns:
        Dict with segments, title, speakers, tags, and other metadata,
        or None if the file has no segments.
    """
    from app.models.media import Speaker
    from app.models.media import TranscriptSegment

    file_id = int(media_file.id)
    file_uuid = str(media_file.uuid)

    # Load transcript segments
    segments = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.media_file_id == file_id)
        .order_by(TranscriptSegment.start_time)
        .all()
    )

    if not segments:
        logger.info(f"No segments for file {file_uuid}, skipping")
        return None

    # Batch-fetch all speakers for this file (avoid N+1 queries)
    speaker_ids = {seg.speaker_id for seg in segments if seg.speaker_id}
    speakers_map: dict[int, str] = {}
    if speaker_ids:
        speaker_rows = db.query(Speaker).filter(Speaker.id.in_(speaker_ids)).all()
        speakers_map = {s.id: s.display_name or s.name or "Unknown" for s in speaker_rows}

    # Convert ORM objects to dicts
    segment_dicts = []
    for seg in segments:
        speaker_name = speakers_map.get(seg.speaker_id, "Unknown") if seg.speaker_id else "Unknown"
        seg_dict = {
            "start": float(seg.start_time),
            "end": float(seg.end_time),
            "text": seg.text or "",
            "speaker": speaker_name,
        }
        if seg.words:
            seg_dict["words"] = seg.words  # Already a list of dicts from JSONB
        segment_dicts.append(seg_dict)

    # Get unique speaker names
    speaker_names: list[str] = list(
        set(str(s["speaker"]) for s in segment_dicts if s["speaker"] != "Unknown")
    )

    # Get tags via FileTag -> Tag relationship
    tag_names = []
    if hasattr(media_file, "file_tags") and media_file.file_tags:
        tag_names = [ft.tag.name for ft in media_file.file_tags if ft.tag]

    # Get collection IDs via CollectionMember relationship
    collection_id_list = []
    if hasattr(media_file, "collection_memberships") and media_file.collection_memberships:
        collection_id_list = [int(cm.collection_id) for cm in media_file.collection_memberships]

    return {
        "file_id": file_id,
        "file_uuid": file_uuid,
        "segments": segment_dicts,
        "title": media_file.title or media_file.filename or f"File {file_id}",
        "upload_time": (media_file.upload_time.isoformat() if media_file.upload_time else None),
        "language": media_file.language or "en",
        "speakers": speaker_names,
        "tags": tag_names,
        "content_type": media_file.content_type or "",
        "duration": media_file.duration,
        "file_size": media_file.file_size,
        "collection_ids": collection_id_list,
    }


def _refresh_index_and_clear_cache() -> None:
    """Refresh the search index and clear the search cache."""
    try:
        from app.services.opensearch_service import opensearch_client

        if opensearch_client:
            opensearch_client.indices.refresh(index=settings.OPENSEARCH_CHUNKS_INDEX)
            logger.info("Refreshed search index after reindex completion")
    except Exception as e:
        logger.warning(f"Index refresh after reindex failed: {e}")

    try:
        from app.services.search.hybrid_search_service import clear_search_cache

        clear_search_cache()
    except Exception as e:
        logger.warning(f"Failed to clear search cache: {e}")


def _set_bulk_indexing_mode() -> None:
    """Temporarily disable refresh_interval for faster bulk ingestion.

    During large reindex operations, the default 1-second refresh creates
    unnecessary Lucene segments. Explicit _periodic_refresh() calls still
    work independently of this setting.
    """
    try:
        from app.services.opensearch_service import opensearch_client

        if opensearch_client:
            opensearch_client.indices.put_settings(
                index=settings.OPENSEARCH_CHUNKS_INDEX,
                body={"index": {"refresh_interval": "-1"}},
            )
            logger.info("Set refresh_interval=-1 for bulk reindex")
    except Exception as e:
        logger.warning(f"Could not set bulk indexing mode: {e}")


def _restore_normal_mode() -> None:
    """Restore normal refresh_interval after bulk ingestion."""
    try:
        from app.services.opensearch_service import opensearch_client

        if opensearch_client:
            opensearch_client.indices.put_settings(
                index=settings.OPENSEARCH_CHUNKS_INDEX,
                body={"index": {"refresh_interval": "1s"}},
            )
            logger.info("Restored refresh_interval=1s after reindex")
    except Exception as e:
        logger.warning(f"Could not restore normal mode: {e}")


def _force_merge_after_reindex() -> None:
    """Force merge to consolidate Lucene segments after a full reindex.

    For HNSW kNN, each segment has its own graph — fewer segments means
    better recall. This is only called after a full reindex, not per-file.
    """
    try:
        from app.services.opensearch_service import opensearch_client

        if opensearch_client:
            opensearch_client.indices.forcemerge(
                index=settings.OPENSEARCH_CHUNKS_INDEX,
                max_num_segments=1,
                params={"wait_for_completion": "false"},
            )
            logger.info("Force merge initiated (running in background)")
    except Exception as e:
        logger.warning(f"Force merge after reindex failed (non-fatal): {e}")


def _periodic_refresh(files_since_refresh: int) -> int:
    """Trigger a Lucene segment flush if enough files have been indexed.

    Called periodically during large reindex operations to keep search
    results fresh rather than waiting until the very end.

    Args:
        files_since_refresh: Number of files indexed since the last refresh.

    Returns:
        0 if refresh was triggered (counter reset), otherwise the unchanged count.
    """
    interval = settings.SEARCH_REINDEX_REFRESH_INTERVAL
    if files_since_refresh < interval:
        return files_since_refresh

    try:
        from app.services.opensearch_service import opensearch_client

        if opensearch_client:
            opensearch_client.indices.refresh(index=settings.OPENSEARCH_CHUNKS_INDEX)
            logger.info(f"Periodic index refresh after {files_since_refresh} files")
    except Exception as e:
        logger.warning(f"Periodic index refresh failed: {e}")

    return 0


def _check_and_recreate_stale_index() -> None:
    """Check if the search index has a stale schema and recreate if needed.

    When _INDEX_VERSION bumps (new analyzers, fields, etc.), the existing
    index mapping is incompatible. A full reindex is the right time to
    recreate the index with the latest mapping.
    """
    try:
        from app.services.opensearch_service import opensearch_client
        from app.services.search.indexing_service import _INDEX_VERSION
        from app.services.search.indexing_service import _get_index_body_with_dimension

        if not opensearch_client:
            return

        index_name = settings.OPENSEARCH_CHUNKS_INDEX
        if not opensearch_client.indices.exists(index=index_name):
            return

        # Read stored version from index _meta
        mapping = opensearch_client.indices.get_mapping(index=index_name)
        meta = mapping.get(index_name, {}).get("mappings", {}).get("_meta", {})
        stored_version = meta.get("version", 0)

        if stored_version >= _INDEX_VERSION:
            logger.debug(
                f"Index '{index_name}' is at version {stored_version}, no recreation needed"
            )
            return

        logger.warning(
            f"Index '{index_name}' is version {stored_version}, "
            f"latest is {_INDEX_VERSION}. Recreating index with updated mapping."
        )

        # Get current dimension before deleting
        current_dim = (
            mapping.get(index_name, {})
            .get("mappings", {})
            .get("properties", {})
            .get("embedding", {})
            .get("dimension", 384)
        )

        # Remove alias if it exists
        alias_name = "transcript_search"
        try:
            if opensearch_client.indices.exists_alias(name=alias_name):
                opensearch_client.indices.delete_alias(index=index_name, name=alias_name)
        except Exception as e:
            logger.debug(f"Could not remove alias '{alias_name}': {e}")

        # Delete and recreate
        opensearch_client.indices.delete(index=index_name)
        index_body = _get_index_body_with_dimension(current_dim)
        opensearch_client.indices.create(index=index_name, body=index_body)

        # Recreate alias
        opensearch_client.indices.put_alias(index=index_name, name=alias_name)

        logger.info(f"Recreated index '{index_name}' with version {_INDEX_VERSION}")

    except Exception as e:
        logger.error(f"Failed to check/recreate stale index: {e}")


def _is_cancellation_requested(user_id: int) -> bool:
    """Check if a reindex cancellation has been requested via Redis.

    Args:
        user_id: The user whose reindex to check.

    Returns:
        True if cancellation was requested.
    """
    try:
        redis_client = _get_notification_redis()
        return bool(redis_client.get(f"reindex_cancel:{user_id}"))
    except Exception as e:
        logger.warning(f"Could not check cancellation flag: {e}")
        return False


def _clear_cancellation_flag(user_id: int) -> None:
    """Clear the reindex cancellation flag in Redis.

    Args:
        user_id: The user whose cancellation flag to clear.
    """
    try:
        redis_client = _get_notification_redis()
        redis_client.delete(f"reindex_cancel:{user_id}")
    except Exception as e:
        logger.warning(f"Could not clear cancellation flag: {e}")


def _send_reindex_stopped(user_id: int, stats: dict[str, Any]) -> None:
    """Send re-index stopped notification via Redis pub/sub for WebSocket delivery."""
    try:
        import json

        redis_client = _get_notification_redis()

        notification = {
            "user_id": user_id,
            "type": NOTIFICATION_TYPE_REINDEX_STOPPED,
            "data": {"stats": stats, "reason": "cancelled_by_user"},
        }

        redis_client.publish("websocket_notifications", json.dumps(notification))
        logger.info(f"Published reindex stopped via Redis: {stats}")

    except Exception as e:
        logger.error(f"Failed to send reindex stopped notification: {e}")


@celery_app.task(bind=True, name="reindex_transcripts", queue="cpu")
def reindex_transcripts_task(
    self,
    user_id: int,
    file_uuids: list[str] | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    """
    Re-index existing transcripts with chunk-level embeddings.

    Uses keyset (cursor) pagination to avoid loading all MediaFile
    ORM objects into memory at once. Each page gets its own DB session.

    Process:
    1. If model_id is provided, switch to that model and recreate the index
    2. Count total files to re-index
    3. Page through files in batches of 50:
       a. Load one page of files from DB
       b. For each file: extract metadata, chunk, embed, bulk index
       c. Send progress via WebSocket
       d. Periodically refresh the index for search freshness
    4. Final refresh and cache clear
    5. Return summary stats

    Args:
        user_id: ID of the user triggering the re-index.
        file_uuids: Optional list of specific file UUIDs to re-index. None = all.
        model_id: Optional embedding model ID to switch to before re-indexing.

    Returns:
        Dict with indexing stats.
    """
    from sqlalchemy import func

    from app.db.session_utils import session_scope
    from app.models.media import FileStatus
    from app.models.media import MediaFile
    from app.services.search.indexing_service import TranscriptIndexingService

    task_id = self.request.id
    logger.info(f"Re-index task {task_id} started for user {user_id}")
    _clear_cancellation_flag(user_id)

    if model_id:
        error = _handle_model_switch(model_id)
        if error:
            return error

    # Ensure neural pipeline is ready if enabled
    use_neural = _ensure_neural_pipeline_ready()
    if use_neural:
        logger.info("Reindex will use neural embedding mode")
    else:
        logger.warning("Neural embedding not available - reindex may not generate embeddings")

    # Recreate stale index if schema version has changed
    _check_and_recreate_stale_index()

    indexing_service = TranscriptIndexingService()
    stats: dict[str, Any] = {
        "total_files": 0,
        "indexed_files": 0,
        "failed_files": 0,
        "total_chunks": 0,
        "skipped_files": 0,
    }

    page_size = 50
    files_since_refresh = 0

    try:
        # Step 1: Count total files in a lightweight query
        with session_scope() as db:
            count_query = db.query(func.count(MediaFile.id)).filter(
                MediaFile.user_id == user_id,
                MediaFile.status == FileStatus.COMPLETED,
            )
            if file_uuids:
                count_query = count_query.filter(MediaFile.uuid.in_(file_uuids))
            total_files: int = count_query.scalar() or 0

        stats["total_files"] = total_files

        if total_files == 0:
            logger.info(f"No files to re-index for user {user_id}")
            return stats

        logger.info(f"Re-indexing {total_files} files for user {user_id}")

        # Safety: restore normal refresh_interval in case a previous reindex was killed
        _restore_normal_mode()

        # Step 2: Disable auto-refresh during bulk ingestion
        _set_bulk_indexing_mode()

        try:
            # Step 3: Page through files with keyset (cursor) pagination
            # Using id > last_id avoids data-shift issues with offset/limit
            global_index = 0
            last_id = 0

            while True:
                with session_scope() as db:
                    page_query = db.query(MediaFile).filter(
                        MediaFile.user_id == user_id,
                        MediaFile.status == FileStatus.COMPLETED,
                        MediaFile.id > last_id,
                    )
                    if file_uuids:
                        page_query = page_query.filter(MediaFile.uuid.in_(file_uuids))

                    page_files = page_query.order_by(MediaFile.id).limit(page_size).all()

                    if not page_files:
                        break

                    last_id = int(page_files[-1].id)

                    for media_file in page_files:
                        file_uuid = str(media_file.uuid)
                        global_index += 1

                        # Check for user-requested cancellation
                        if _is_cancellation_requested(user_id):
                            logger.info(
                                f"Re-index task {task_id} cancelled by user after "
                                f"{stats['indexed_files']}/{total_files} files"
                            )
                            stats["cancelled"] = True
                            _send_reindex_stopped(user_id, stats)
                            _clear_cancellation_flag(user_id)
                            return stats

                        try:
                            metadata = _extract_file_metadata(db, media_file)
                            if metadata is None:
                                stats["skipped_files"] += 1
                                continue

                            chunk_count = indexing_service.reindex_transcript(
                                file_id=metadata["file_id"],
                                file_uuid=metadata["file_uuid"],
                                user_id=user_id,
                                segments=metadata["segments"],
                                title=metadata["title"],
                                speakers=metadata["speakers"],
                                tags=metadata["tags"],
                                upload_time=metadata["upload_time"],
                                language=metadata["language"],
                                content_type=metadata["content_type"],
                                duration=metadata["duration"],
                                file_size=metadata["file_size"],
                                collection_ids=metadata["collection_ids"],
                            )

                            stats["indexed_files"] += 1
                            stats["total_chunks"] += chunk_count
                            files_since_refresh += 1

                            # Send progress notification
                            progress = global_index / total_files
                            _send_reindex_progress(
                                user_id, progress, stats["indexed_files"], total_files
                            )

                            logger.debug(
                                f"Re-indexed file {file_uuid}: "
                                f"{chunk_count} chunks ({global_index}/{total_files})"
                            )

                            # Periodic refresh to keep search results fresh
                            files_since_refresh = _periodic_refresh(files_since_refresh)

                        except Exception as e:
                            logger.error(f"Error re-indexing file {file_uuid}: {e}")
                            stats["failed_files"] += 1
        finally:
            _restore_normal_mode()

        _refresh_index_and_clear_cache()
        _force_merge_after_reindex()

        # Send completion notification
        _send_reindex_complete(user_id, stats)

        logger.info(
            f"Re-index task {task_id} completed: "
            f"{stats['indexed_files']}/{stats['total_files']} files, "
            f"{stats['total_chunks']} chunks, "
            f"{stats['failed_files']} failures"
        )
        return stats

    except Exception as e:
        logger.error(f"Re-index task {task_id} failed: {e}")
        stats["error"] = str(e)
        return stats


def _send_reindex_progress(user_id: int, progress: float, indexed: int, total: int) -> None:
    """Send re-index progress via Redis pub/sub for WebSocket delivery."""
    try:
        import json

        redis_client = _get_notification_redis()

        notification = {
            "user_id": user_id,
            "type": NOTIFICATION_TYPE_REINDEX_PROGRESS,
            "data": {
                "progress": round(progress, 2),
                "indexed_files": indexed,
                "total_files": total,
            },
        }

        redis_client.publish("websocket_notifications", json.dumps(notification))
        logger.debug(f"Published reindex progress via Redis: {indexed}/{total}")

    except Exception as e:
        logger.error(f"Failed to send reindex progress notification: {e}")


def _send_reindex_complete(user_id: int, stats: dict[str, Any]) -> None:
    """Send re-index completion via Redis pub/sub for WebSocket delivery."""
    try:
        import json

        redis_client = _get_notification_redis()

        notification = {
            "user_id": user_id,
            "type": NOTIFICATION_TYPE_REINDEX_COMPLETE,
            "data": {"stats": stats},
        }

        redis_client.publish("websocket_notifications", json.dumps(notification))
        logger.info(f"Published reindex complete via Redis: {stats}")

    except Exception as e:
        logger.error(f"Failed to send reindex completion notification: {e}")
