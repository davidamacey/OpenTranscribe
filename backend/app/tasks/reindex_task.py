"""Celery task for re-indexing transcripts with chunk-level embeddings."""
import logging
from typing import Any

from app.core.celery import celery_app
from app.core.config import settings
from app.core.constants import NOTIFICATION_TYPE_REINDEX_COMPLETE
from app.core.constants import NOTIFICATION_TYPE_REINDEX_PROGRESS

logger = logging.getLogger(__name__)


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
        segment_dicts.append(
            {
                "start": float(seg.start_time),
                "end": float(seg.end_time),
                "text": seg.text or "",
                "speaker": speaker_name,
            }
        )

    # Get unique speaker names
    speaker_names: list[str] = list(
        set(str(s["speaker"]) for s in segment_dicts if s["speaker"] != "Unknown")
    )

    # Get tags
    tag_names = []
    if hasattr(media_file, "tags") and media_file.tags:
        tag_names = [t.name for t in media_file.tags]

    collection_id_list = []
    if hasattr(media_file, "collections") and media_file.collections:
        collection_id_list = [c.id for c in media_file.collections]

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


@celery_app.task(bind=True, name="reindex_transcripts", queue="cpu")
def reindex_transcripts_task(
    self,
    user_id: int,
    file_uuids: list[str] | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    """
    Re-index existing transcripts with chunk-level embeddings.

    Process:
    1. If model_id is provided, switch to that model and recreate the index
    2. Query PostgreSQL for transcript segments (by file or all)
    3. For each file:
       a. Load segments from DB
       b. Chunk using speaker-turn strategy
       c. Batch embed chunks (GPU if available)
       d. Bulk index to OpenSearch
       e. Send progress via WebSocket
    4. Refresh the index to make all chunks searchable
    5. Return summary stats

    Args:
        user_id: ID of the user triggering the re-index.
        file_uuids: Optional list of specific file UUIDs to re-index. None = all.
        model_id: Optional embedding model ID to switch to before re-indexing.

    Returns:
        Dict with indexing stats.
    """
    from app.db.session_utils import session_scope
    from app.models.media import FileStatus
    from app.models.media import MediaFile
    from app.services.search.indexing_service import TranscriptIndexingService

    task_id = self.request.id
    logger.info(f"Re-index task {task_id} started for user {user_id}")

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

    indexing_service = TranscriptIndexingService()
    stats: dict[str, Any] = {
        "total_files": 0,
        "indexed_files": 0,
        "failed_files": 0,
        "total_chunks": 0,
        "skipped_files": 0,
    }

    try:
        with session_scope() as db:
            # Query files to re-index
            query = db.query(MediaFile).filter(
                MediaFile.user_id == user_id,
                MediaFile.status == FileStatus.COMPLETED,
            )

            if file_uuids:
                query = query.filter(MediaFile.uuid.in_(file_uuids))

            files = query.all()
            stats["total_files"] = len(files)

            if not files:
                logger.info(f"No files to re-index for user {user_id}")
                return stats

            logger.info(f"Re-indexing {len(files)} files for user {user_id}")

            for i, media_file in enumerate(files):
                file_uuid = str(media_file.uuid)

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

                    # Send progress notification
                    progress = (i + 1) / len(files)
                    _send_reindex_progress(
                        user_id, progress, stats["indexed_files"], stats["total_files"]
                    )

                    logger.info(
                        f"Re-indexed file {file_uuid}: {chunk_count} chunks "
                        f"({i + 1}/{len(files)})"
                    )

                except Exception as e:
                    logger.error(f"Error re-indexing file {file_uuid}: {e}")
                    stats["failed_files"] += 1

        _refresh_index_and_clear_cache()

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
    """Send re-index progress via WebSocket."""
    try:
        import asyncio

        from app.api.websockets import send_notification

        data = {
            "progress": round(progress, 2),
            "indexed_files": indexed,
            "total_files": total,
        }
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(
                    send_notification(user_id, NOTIFICATION_TYPE_REINDEX_PROGRESS, data)
                )
            else:
                loop.run_until_complete(
                    send_notification(user_id, NOTIFICATION_TYPE_REINDEX_PROGRESS, data)
                )
        except RuntimeError:
            asyncio.run(send_notification(user_id, NOTIFICATION_TYPE_REINDEX_PROGRESS, data))
    except Exception as e:
        logger.debug(f"Failed to send reindex progress notification: {e}")


def _send_reindex_complete(user_id: int, stats: dict[str, Any]) -> None:
    """Send re-index completion via WebSocket."""
    try:
        import asyncio

        from app.api.websockets import send_notification

        data = {"stats": stats}
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(
                    send_notification(user_id, NOTIFICATION_TYPE_REINDEX_COMPLETE, data)
                )
            else:
                loop.run_until_complete(
                    send_notification(user_id, NOTIFICATION_TYPE_REINDEX_COMPLETE, data)
                )
        except RuntimeError:
            asyncio.run(send_notification(user_id, NOTIFICATION_TYPE_REINDEX_COMPLETE, data))
    except Exception as e:
        logger.debug(f"Failed to send reindex completion notification: {e}")
