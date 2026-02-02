"""Search API endpoints with hybrid BM25 + vector search."""
import logging
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Query

from app.api.endpoints.auth import get_current_active_user
from app.api.endpoints.auth import get_current_admin_user
from app.core.config import settings
from app.core.constants import EMBEDDING_MODELS
from app.core.constants import SEARCH_DEFAULT_PAGE_SIZE
from app.core.constants import SEARCH_MAX_PAGE_SIZE
from app.models.user import User
from app.schemas.search import SetEmbeddingModelSchema

logger = logging.getLogger(__name__)

router = APIRouter()


def _search_response_to_schema(response) -> dict[str, Any]:
    """Convert HybridSearchService response to serializable dict."""
    return {
        "query": response.query,
        "results": [
            {
                "file_uuid": hit.file_uuid,
                "file_id": hit.file_id,
                "title": hit.title,
                "speakers": hit.speakers,
                "tags": hit.tags,
                "upload_time": hit.upload_time,
                "language": hit.language,
                "content_type": hit.content_type,
                "relevance_score": hit.relevance_score,
                "occurrences": [
                    {
                        "snippet": occ.snippet,
                        "speaker": occ.speaker,
                        "speaker_highlighted": occ.speaker_highlighted,
                        "start_time": occ.start_time,
                        "end_time": occ.end_time,
                        "chunk_index": occ.chunk_index,
                        "score": occ.score,
                        "match_type": occ.match_type,
                        "has_keyword_match": occ.has_keyword_match,
                        "highlight_type": occ.highlight_type,
                    }
                    for occ in hit.occurrences
                ],
                "total_occurrences": hit.total_occurrences,
                "title_highlighted": hit.title_highlighted,
                "keyword_occurrences": hit.keyword_occurrences,
                "semantic_only": hit.semantic_only,
                "semantic_confidence": hit.semantic_confidence,
                "match_sources": hit.match_sources,
                "relevance_percent": hit.relevance_percent,
                "duration": hit.duration,
                "file_size": hit.file_size,
            }
            for hit in response.results
        ],
        "total_results": response.total_results,
        "total_files": response.total_files,
        "page": response.page,
        "page_size": response.page_size,
        "total_pages": response.total_pages,
        "search_time_ms": response.search_time_ms,
        "filters_applied": response.filters_applied,
        "search_mode": getattr(response, "search_mode", "hybrid"),
    }


@router.get("")
def search_transcripts(
    q: str = Query(..., min_length=1, description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(
        SEARCH_DEFAULT_PAGE_SIZE, ge=1, le=SEARCH_MAX_PAGE_SIZE, description="Results per page"
    ),
    speakers: list[str] = Query(None, description="Filter by speaker names"),
    tags: list[str] = Query(None, description="Filter by tags"),
    date_from: str | None = Query(None, description="Filter from date (ISO format)"),
    date_to: str | None = Query(None, description="Filter to date (ISO format)"),
    sort_by: str = Query(
        "relevance",
        description=(
            "Sort by: relevance, upload_time, completed_at, filename, duration, file_size. "
            "Note: completed_at uses upload_time for search results (completion time not indexed)."
        ),
    ),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    search_mode: str = Query("hybrid", description="Search mode: hybrid or keyword"),
    file_type: list[str] | None = Query(None, description="Filter by file type: audio, video"),
    collection_id: int | None = Query(None, description="Filter by collection ID"),
    min_duration: float | None = Query(None, description="Minimum duration in seconds"),
    max_duration: float | None = Query(None, description="Maximum duration in seconds"),
    min_file_size: int | None = Query(None, description="Minimum file size in bytes"),
    max_file_size: int | None = Query(None, description="Maximum file size in bytes"),
    language: str | None = Query(None, description="Filter by language code"),
    title_filter: str | None = Query(
        None, description="Filter by filename/title (substring match)"
    ),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """
    Google-style hybrid search across all transcripts.

    Returns results grouped by file with timestamped occurrences.
    Uses BM25 + vector search with Reciprocal Rank Fusion (RRF).

    Args:
        q: Search query text.
        page: Page number (1-indexed).
        page_size: Number of results per page.
        speakers: Optional speaker name filters.
        tags: Optional tag filters.
        date_from: Optional start date filter.
        date_to: Optional end date filter.
        sort_by: Sort field - relevance, upload_time, completed_at, filename, duration, file_size.
        sort_order: Sort direction - asc or desc.

    Returns:
        Search results grouped by file with highlighted snippets.

    Notes:
        - Sorting by 'relevance' always places keyword matches before semantic-only matches,
          regardless of sort_order.
        - Sorting by 'completed_at' uses upload_time as a fallback since the completion
          timestamp is not indexed in the search layer.
    """
    valid_sort_fields = (
        "relevance",
        "upload_time",
        "completed_at",
        "filename",
        "duration",
        "file_size",
    )
    if sort_by not in valid_sort_fields:
        raise HTTPException(
            status_code=400,
            detail=f"sort_by must be one of: {', '.join(valid_sort_fields)}",
        )

    if sort_order not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="sort_order must be: asc or desc")

    if search_mode not in ("hybrid", "keyword"):
        raise HTTPException(status_code=400, detail="search_mode must be: hybrid or keyword")

    from app.services.search.hybrid_search_service import HybridSearchService

    search_service = HybridSearchService()
    response = search_service.search(
        query=q,
        user_id=int(current_user.id),
        page=page,
        page_size=page_size,
        speakers=speakers,
        tags=tags,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order,
        search_mode=search_mode,
        file_type=file_type,
        collection_id=collection_id,
        min_duration=min_duration,
        max_duration=max_duration,
        min_file_size=min_file_size,
        max_file_size=max_file_size,
        language=language,
        title_filter=title_filter,
    )

    return _search_response_to_schema(response)


@router.get("/suggestions")
def search_suggestions(
    q: str = Query(..., min_length=2, description="Search prefix"),
    limit: int = Query(8, ge=1, le=20, description="Max suggestions"),
    current_user: User = Depends(get_current_active_user),
) -> list[dict[str, Any]]:
    """
    Auto-complete suggestions as user types.

    Returns ranked suggestions from title prefix matches,
    speaker name matches, and frequent content terms.

    Args:
        q: Search prefix text.
        limit: Maximum number of suggestions.

    Returns:
        List of suggestion items with type and text.
    """
    from app.services.search.hybrid_search_service import HybridSearchService

    search_service = HybridSearchService()
    return search_service.get_suggestions(
        prefix=q,
        user_id=int(current_user.id),
        limit=limit,
    )


@router.get("/filters")
def get_available_filters(
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """
    Return available filter options (speakers, tags, date range).

    Returns:
        Dict with speakers, tags, and date_range filter options.
    """
    from app.services.search.hybrid_search_service import HybridSearchService

    search_service = HybridSearchService()
    return search_service.get_available_filters(user_id=int(current_user.id))


@router.post("/reindex")
def trigger_reindex(
    file_uuids: list[str] | None = None,
    pending_only: bool = Query(False, description="Only reindex files without chunks"),
    current_user: User = Depends(get_current_admin_user),
) -> dict[str, Any]:
    """
    Trigger re-indexing of existing transcripts as a background Celery task.

    Args:
        file_uuids: Optional list of specific file UUIDs. None = all files.
        pending_only: If True, only reindex files that have no chunks in OpenSearch.

    Returns:
        Dict with task_id and status.
    """
    if pending_only and file_uuids is None:
        # Find file UUIDs that are NOT yet indexed in OpenSearch
        from app.db.session_utils import session_scope
        from app.models.media import FileStatus
        from app.models.media import MediaFile
        from app.services.opensearch_service import opensearch_client

        # Get all completed file UUIDs from PostgreSQL
        with session_scope() as db:
            completed_files = (
                db.query(MediaFile.file_uuid)
                .filter(
                    MediaFile.user_id == int(current_user.id),
                    MediaFile.status == FileStatus.COMPLETED,
                )
                .all()
            )
            all_uuids = {str(row[0]) for row in completed_files}

        if not all_uuids:
            return {
                "task_id": None,
                "status": "no_pending",
                "message": "No completed files found to index.",
            }

        # Find which file UUIDs already have chunks in OpenSearch
        indexed_uuids: set[str] = set()
        if opensearch_client:
            try:
                index_name = settings.OPENSEARCH_CHUNKS_INDEX
                if opensearch_client.indices.exists(index=index_name):
                    agg_response = opensearch_client.search(
                        index=index_name,
                        body={
                            "size": 0,
                            "query": {"term": {"user_id": int(current_user.id)}},
                            "aggs": {
                                "indexed_files": {
                                    "terms": {
                                        "field": "file_uuid",
                                        "size": len(all_uuids) + 100,
                                    }
                                }
                            },
                        },
                    )
                    buckets = (
                        agg_response.get("aggregations", {})
                        .get("indexed_files", {})
                        .get("buckets", [])
                    )
                    indexed_uuids = {b["key"] for b in buckets}
            except Exception as e:
                logger.error(f"Error querying indexed files: {e}")

        # Compute the difference: files that need indexing
        pending_uuids = list(all_uuids - indexed_uuids)

        if not pending_uuids:
            return {
                "task_id": None,
                "status": "no_pending",
                "message": "All files are already indexed.",
            }

        file_uuids = pending_uuids
        logger.info(
            f"Pending-only reindex: {len(pending_uuids)} files need indexing "
            f"(out of {len(all_uuids)} total)"
        )

    from app.tasks.reindex_task import reindex_transcripts_task

    task = reindex_transcripts_task.delay(
        user_id=int(current_user.id),
        file_uuids=file_uuids,
    )

    logger.info(
        f"Re-index task {task.id} started for user {current_user.id}, "
        f"files: {len(file_uuids) if file_uuids else 'all'}"
    )

    return {
        "task_id": task.id,
        "status": "started",
        "message": "Re-indexing started. Progress will be sent via WebSocket.",
    }


def _check_reindex_task_active(user_id: int) -> bool:
    """Check if a reindex task is currently active for this user.

    Uses Celery's inspect API to check for active tasks. Returns False
    on any error to avoid blocking the status endpoint.

    Args:
        user_id: The user ID to check for active reindex tasks.

    Returns:
        True if a reindex task is actively running for this user.
    """
    try:
        from app.core.celery import celery_app

        # Inspect active tasks across all workers (with short timeout)
        inspector = celery_app.control.inspect(timeout=1.0)
        active_tasks = inspector.active()

        if not active_tasks:
            return False

        # Check all workers for active reindex tasks for this user
        for _worker, tasks in active_tasks.items():
            for task in tasks:
                if task.get("name") == "reindex_transcripts":
                    # Check if task args contain this user_id
                    task_kwargs = task.get("kwargs", {})
                    if task_kwargs.get("user_id") == user_id:
                        return True
    except Exception as e:
        # Log but don't fail the status endpoint
        logger.debug(f"Could not check Celery task state: {e}")

    return False


@router.get("/reindex/status")
def reindex_status(
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """
    Check re-indexing status and index health.

    Returns:
        Dict with total_files, indexed_files, pending info, current model.
    """
    from app.db.session_utils import session_scope
    from app.models.media import FileStatus
    from app.models.media import MediaFile
    from app.services.opensearch_service import opensearch_client

    with session_scope() as db:
        total_files = (
            db.query(MediaFile)
            .filter(
                MediaFile.user_id == int(current_user.id),
                MediaFile.status == FileStatus.COMPLETED,
            )
            .count()
        )

    # Count indexed files in OpenSearch chunks index
    indexed_files = 0
    last_indexed_at = None
    if opensearch_client:
        try:
            index_name = settings.OPENSEARCH_CHUNKS_INDEX
            if opensearch_client.indices.exists(index=index_name):
                count_response = opensearch_client.search(
                    index=index_name,
                    body={
                        "size": 0,
                        "query": {"term": {"user_id": int(current_user.id)}},
                        "aggs": {
                            "unique_files": {"cardinality": {"field": "file_uuid"}},
                            "last_indexed": {"max": {"field": "indexed_at"}},
                        },
                    },
                )
                aggs = count_response.get("aggregations", {})
                indexed_files = aggs.get("unique_files", {}).get("value", 0)
                last_indexed_at = aggs.get("last_indexed", {}).get("value_as_string")
        except Exception as e:
            logger.error(f"Error checking index status: {e}")

    # Check if a reindex task is actively running for this user
    in_progress = _check_reindex_task_active(int(current_user.id))

    return {
        "total_files": total_files,
        "indexed_files": indexed_files,
        "pending_files": max(0, total_files - indexed_files),
        "in_progress": in_progress,
        "current_model": settings.SEARCH_EMBEDDING_MODEL,
        "current_dimension": settings.SEARCH_EMBEDDING_DIMENSION,
        "last_indexed_at": last_indexed_at,
    }


@router.get("/models")
def get_embedding_models(
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """
    Return available embedding models with current selection.

    Returns:
        Dict with models list, current_model_id, and current_dimension.
    """
    models = []
    for model_id, info in EMBEDDING_MODELS.items():
        models.append(
            {
                "model_id": model_id,
                "name": info["name"],
                "dimension": info["dimension"],
                "description": info["description"],
                "size_mb": info["size_mb"],
            }
        )

    return {
        "models": models,
        "current_model_id": settings.SEARCH_EMBEDDING_MODEL,
        "current_dimension": settings.SEARCH_EMBEDDING_DIMENSION,
    }


@router.post("/models")
def set_embedding_model(
    body: SetEmbeddingModelSchema,
    current_user: User = Depends(get_current_admin_user),
) -> dict[str, Any]:
    """
    Change embedding model. Triggers full re-index with new model.

    Search falls back to BM25 during re-indexing.

    Args:
        body: Request with model_id to switch to.

    Returns:
        Dict with status and re-index task info.
    """
    model_id = body.model_id

    if model_id not in EMBEDDING_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model: {model_id}. Available: {list(EMBEDDING_MODELS.keys())}",
        )

    model_info = EMBEDDING_MODELS[model_id]
    new_dimension: int = model_info["dimension"]  # type: ignore[assignment]

    # Persist to database so all processes (API + workers) can read it
    from app.services.search.settings_service import save_search_embedding_model

    save_search_embedding_model(model_id, new_dimension)

    # Update in-memory settings for this process
    settings.SEARCH_EMBEDDING_MODEL = model_id
    settings.SEARCH_EMBEDDING_DIMENSION = new_dimension

    # Reset the embedding service singleton on this process too
    from app.services.search.embedding_service import SearchEmbeddingService

    SearchEmbeddingService.reset()

    # Reset the index verified cache so search rechecks
    from app.services.search import hybrid_search_service

    hybrid_search_service._index_verified = False

    # Clear search cache on model switch
    from app.services.search.hybrid_search_service import clear_search_cache

    clear_search_cache()

    # Trigger full re-index with new model
    # Pass model_id to Celery worker so it updates its own settings
    from app.tasks.reindex_task import reindex_transcripts_task

    task = reindex_transcripts_task.delay(
        user_id=int(current_user.id),
        file_uuids=None,  # All files
        model_id=model_id,  # Propagate to worker
    )

    logger.info(
        f"Model switch to {model_id} ({new_dimension}d) for user {current_user.id}, "
        f"re-index task: {task.id}"
    )

    return {
        "status": "model_changed",
        "model_id": model_id,
        "dimension": new_dimension,
        "reindex_task_id": task.id,
        "message": (
            f"Switched to {model_info['name']}. "
            f"Re-indexing all transcripts. Search will use keyword-only mode during re-indexing."
        ),
    }
