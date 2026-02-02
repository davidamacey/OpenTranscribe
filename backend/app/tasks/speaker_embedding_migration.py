"""
Celery task for normalizing existing speaker embeddings to L2 unit vectors.

This task runs on backend startup and normalizes all speaker embeddings in OpenSearch
that were created before L2 normalization was added. Normalized embeddings provide
optimal cosine similarity performance for speaker matching.

Uses batch processing and numpy vectorized operations for efficiency.
"""

import logging
from contextlib import suppress
from typing import Any

import numpy as np

from app.core.celery import celery_app
from app.core.config import settings
from app.services.opensearch_service import get_opensearch_client

logger = logging.getLogger(__name__)

# Batch size for scroll API
SCROLL_BATCH_SIZE = 500
SCROLL_TIMEOUT = "5m"

# Tolerance for checking if already normalized
NORM_TOLERANCE = 0.01


def _is_normalized(embedding: list[float]) -> bool:
    """Check if an embedding is already L2 normalized (norm ≈ 1.0)."""
    norm = float(np.linalg.norm(embedding))
    return abs(norm - 1.0) < NORM_TOLERANCE


def _normalize_embeddings_batch(embeddings: list[list[float]]) -> list[list[float]]:
    """Normalize a batch of embeddings using vectorized numpy operations."""
    if not embeddings:
        return []

    arr = np.array(embeddings, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms > 0, norms, 1.0)
    normalized = arr / norms
    result: list[list[float]] = normalized.tolist()
    return result


def _process_hits_batch(
    hits: list[dict[str, Any]], summary: dict[str, Any]
) -> tuple[list[str], list[list[float]]]:
    """Process a batch of hits and return doc IDs and embeddings needing normalization."""
    embeddings_to_normalize: list[list[float]] = []
    doc_ids: list[str] = []

    for hit in hits:
        summary["total_found"] += 1
        doc_id = hit["_id"]
        embedding = hit.get("_source", {}).get("embedding")

        if embedding is None:
            continue

        if _is_normalized(embedding):
            summary["already_normalized"] += 1
            continue

        embeddings_to_normalize.append(embedding)
        doc_ids.append(doc_id)

    return doc_ids, embeddings_to_normalize


def _bulk_update_embeddings(
    client: Any,
    index_name: str,
    doc_ids: list[str],
    normalized_embeddings: list[list[float]],
    summary: dict[str, Any],
) -> None:
    """Bulk update embeddings in OpenSearch."""
    bulk_body: list[dict[str, Any]] = []
    for doc_id, normalized in zip(doc_ids, normalized_embeddings):
        bulk_body.append({"update": {"_index": index_name, "_id": doc_id}})
        bulk_body.append({"doc": {"embedding": normalized}})

    if not bulk_body:
        return

    try:
        bulk_response = client.bulk(body=bulk_body, refresh=False)

        if bulk_response.get("errors"):
            for item in bulk_response.get("items", []):
                if "error" in item.get("update", {}):
                    summary["failed"] += 1
                    logger.error(f"Bulk update error: {item['update']['error']}")
                else:
                    summary["normalized"] += 1
        else:
            summary["normalized"] += len(normalized_embeddings)

    except Exception as e:
        logger.error(f"Bulk update failed: {e}")
        summary["failed"] += len(normalized_embeddings)


@celery_app.task(name="normalize_speaker_embeddings", bind=True, queue="cpu")
def normalize_speaker_embeddings_task(self, batch_size: int = SCROLL_BATCH_SIZE) -> dict[str, Any]:
    """
    Normalize all speaker embeddings in OpenSearch to L2 unit vectors.

    Uses the scroll API for efficient processing of large datasets and
    bulk updates for optimal write performance.

    Args:
        batch_size: Number of embeddings to process per batch.

    Returns:
        Dictionary with migration statistics.
    """
    summary: dict[str, Any] = {
        "total_found": 0,
        "already_normalized": 0,
        "normalized": 0,
        "failed": 0,
        "batches_processed": 0,
    }

    client = get_opensearch_client()
    if not client:
        logger.warning("OpenSearch client not available, skipping embedding normalization")
        summary["error"] = "OpenSearch client not available"
        return summary

    index_name = settings.OPENSEARCH_SPEAKER_INDEX

    # Check if index exists
    try:
        if not client.indices.exists(index=index_name):
            logger.info(f"Speaker index {index_name} does not exist, nothing to migrate")
            return summary
    except Exception as e:
        logger.error(f"Error checking speaker index: {e}")
        summary["error"] = str(e)
        return summary

    scroll_id = None
    try:
        # Initialize scroll
        response = client.search(
            index=index_name,
            body={"size": batch_size, "query": {"match_all": {}}, "_source": ["embedding"]},
            scroll=SCROLL_TIMEOUT,
        )

        scroll_id = response.get("_scroll_id")
        hits = response.get("hits", {}).get("hits", [])

        while hits:
            summary["batches_processed"] += 1

            # Process batch
            doc_ids, embeddings_to_normalize = _process_hits_batch(hits, summary)

            if embeddings_to_normalize:
                normalized = _normalize_embeddings_batch(embeddings_to_normalize)
                _bulk_update_embeddings(client, index_name, doc_ids, normalized, summary)

            # Log progress every 10 batches
            if summary["batches_processed"] % 10 == 0:
                logger.info(
                    f"Embedding normalization progress: {summary['total_found']} checked, "
                    f"{summary['normalized']} normalized, {summary['already_normalized']} already OK"
                )

            # Get next batch
            response = client.scroll(scroll_id=scroll_id, scroll=SCROLL_TIMEOUT)
            scroll_id = response.get("_scroll_id")
            hits = response.get("hits", {}).get("hits", [])

        # Refresh index to make changes visible
        try:
            client.indices.refresh(index=index_name)
        except Exception as e:
            logger.warning(f"Failed to refresh index after normalization: {e}")

        logger.info(
            f"Speaker embedding normalization completed: "
            f"{summary['total_found']} total, {summary['normalized']} normalized, "
            f"{summary['already_normalized']} already normalized, {summary['failed']} failed"
        )

    except Exception as e:
        logger.error(f"Error during embedding normalization: {e}")
        summary["error"] = str(e)

    finally:
        # Clear scroll context
        if scroll_id:
            with suppress(Exception):
                client.clear_scroll(scroll_id=scroll_id)

    return summary
