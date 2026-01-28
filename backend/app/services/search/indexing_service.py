"""Transcript indexing service for OpenSearch chunk-level search."""
import datetime
import logging
import time
from typing import Any

from app.core.config import settings
from app.services.opensearch_service import get_opensearch_client
from app.services.opensearch_service import opensearch_client

from .chunking_service import chunk_transcript_by_speaker_turns
from .embedding_service import SearchEmbeddingService

logger = logging.getLogger(__name__)

# Index config for transcript chunks
TRANSCRIPT_CHUNKS_INDEX_BODY = {
    "settings": {
        "index": {
            "knn": True,
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        "analysis": {
            "analyzer": {
                "english_transcript": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": [
                        "lowercase",
                        "english_stop",
                        "kstem",
                        "shingle_filter",
                    ],
                }
            },
            "filter": {
                "english_stop": {"type": "stop", "stopwords": "_english_"},
                "shingle_filter": {
                    "type": "shingle",
                    "min_shingle_size": 2,
                    "max_shingle_size": 3,
                    "output_unigrams": True,
                },
            },
        },
    },
    "mappings": {
        "properties": {
            # Identity
            "file_id": {"type": "integer"},
            "file_uuid": {"type": "keyword"},
            "user_id": {"type": "integer"},
            "chunk_index": {"type": "integer"},
            # Content (BM25 searchable)
            "content": {
                "type": "text",
                "analyzer": "english_transcript",
                "fields": {"exact": {"type": "text", "analyzer": "standard"}},
            },
            "title": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword"}},
            },
            # Metadata (filterable)
            "speaker": {"type": "keyword"},
            "speakers": {"type": "keyword"},
            "tags": {"type": "keyword"},
            "upload_time": {"type": "date"},
            "language": {"type": "keyword"},
            # Timestamps (for video navigation)
            "start_time": {"type": "float"},
            "end_time": {"type": "float"},
            # Vector embedding
            "embedding": {
                "type": "knn_vector",
                "dimension": 384,  # Updated dynamically at index creation time
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "lucene",
                    "parameters": {
                        "ef_construction": 256,
                        "m": 16,
                    },
                },
            },
            # Tracking
            "embedding_model": {"type": "keyword"},
            "indexed_at": {"type": "date"},
        }
    },
}

# RRF search pipeline: rank-based fusion that doesn't require score normalization.
# rank_constant=60 (default from the original RRF paper).
HYBRID_SEARCH_PIPELINE = {
    "description": "Hybrid BM25 + vector search with RRF",
    "phase_results_processors": [
        {
            "score-ranker-processor": {
                "combination": {
                    "technique": "rrf",
                    "rank_constant": 60,
                }
            }
        }
    ],
}


def ensure_chunks_index_exists() -> bool:
    """Ensure the transcript chunks index exists with proper kNN config.

    Returns:
        True if index exists or was created, False on error.
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return False

    index_name = settings.OPENSEARCH_CHUNKS_INDEX
    try:
        if opensearch_client.indices.exists(index=index_name):
            return True

        # Set dimension from config
        index_body = _get_index_body_with_dimension(settings.SEARCH_EMBEDDING_DIMENSION)

        opensearch_client.indices.create(index=index_name, body=index_body)
        logger.info(f"Created transcript chunks index: {index_name}")

        # Create alias
        alias_name = "transcript_search"
        if not opensearch_client.indices.exists_alias(name=alias_name):
            opensearch_client.indices.put_alias(index=index_name, name=alias_name)
            logger.info(f"Created alias {alias_name} -> {index_name}")

        return True
    except Exception as e:
        logger.error(f"Error creating chunks index: {e}")
        return False


def recreate_index_for_dimension(dimension: int) -> bool:
    """Recreate the chunks index if the embedding dimension has changed.

    This is called during model switch to ensure the index mapping matches
    the new model's vector dimension. The old index is deleted and a new
    one is created with the correct dimension.

    Args:
        dimension: The new embedding vector dimension.

    Returns:
        True if index was recreated or already correct, False on error.
    """
    if not opensearch_client:
        return False

    index_name = settings.OPENSEARCH_CHUNKS_INDEX
    try:
        if opensearch_client.indices.exists(index=index_name):
            # Check current dimension from mapping
            mapping = opensearch_client.indices.get_mapping(index=index_name)
            current_dim = (
                mapping.get(index_name, {})
                .get("mappings", {})
                .get("properties", {})
                .get("embedding", {})
                .get("dimension", 0)
            )

            if current_dim == dimension:
                logger.info(
                    f"Index {index_name} already has dimension {dimension}, no recreation needed"
                )
                return True

            logger.info(
                f"Dimension mismatch: index has {current_dim}, need {dimension}. "
                f"Recreating index."
            )

            # Remove alias first if it exists
            alias_name = "transcript_search"
            try:
                if opensearch_client.indices.exists_alias(name=alias_name):
                    opensearch_client.indices.delete_alias(index=index_name, name=alias_name)
            except Exception as e:
                logger.debug(f"Could not remove alias {alias_name} before index recreation: {e}")

            # Delete the old index
            opensearch_client.indices.delete(index=index_name)
            logger.info(f"Deleted old index {index_name}")

        # Create with new dimension
        index_body = _get_index_body_with_dimension(dimension)
        opensearch_client.indices.create(index=index_name, body=index_body)
        logger.info(f"Created index {index_name} with dimension {dimension}")

        # Recreate alias
        alias_name = "transcript_search"
        opensearch_client.indices.put_alias(index=index_name, name=alias_name)
        logger.info(f"Created alias {alias_name} -> {index_name}")

        return True
    except Exception as e:
        logger.error(f"Error recreating index for dimension {dimension}: {e}")
        return False


def ensure_search_pipeline_exists() -> bool:
    """Ensure the hybrid search pipeline exists.

    Returns:
        True if pipeline exists or was created, False on error.
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return False

    pipeline_id = settings.OPENSEARCH_SEARCH_PIPELINE
    try:
        # Check if pipeline exists
        try:
            opensearch_client.transport.perform_request("GET", f"/_search/pipeline/{pipeline_id}")
            return True
        except Exception:
            logger.debug(f"Search pipeline {pipeline_id} not found, will create it")

        # Create pipeline
        opensearch_client.transport.perform_request(
            "PUT",
            f"/_search/pipeline/{pipeline_id}",
            body=HYBRID_SEARCH_PIPELINE,
        )
        logger.info(f"Created search pipeline: {pipeline_id}")
        return True
    except Exception as e:
        logger.error(f"Error creating search pipeline: {e}")
        return False


def _get_index_body_with_dimension(dimension: int) -> dict[str, Any]:
    """Get index body with the correct embedding dimension."""
    import copy

    body: dict[str, Any] = copy.deepcopy(TRANSCRIPT_CHUNKS_INDEX_BODY)
    body["mappings"]["properties"]["embedding"]["dimension"] = dimension
    return body


class TranscriptIndexingService:
    """Handles chunking, embedding, and indexing transcripts into OpenSearch."""

    def index_transcript_chunks(
        self,
        file_id: int,
        file_uuid: str,
        user_id: int,
        segments: list[dict[str, Any]],
        title: str,
        speakers: list[str],
        tags: list[str],
        upload_time: str | None = None,
        language: str = "en",
        content_type: str = "",
        duration: float | None = None,
        file_size: int | None = None,
        collection_ids: list[int] | None = None,
    ) -> dict[str, Any] | int:
        """Chunk, embed, and index a transcript.

        Args:
            file_id: Media file integer ID.
            file_uuid: Media file UUID.
            user_id: Owner user ID.
            segments: Transcript segments with start, end, text, speaker.
            title: File title.
            speakers: All speaker names in the file.
            tags: Tags associated with the file.
            upload_time: Upload time ISO string (defaults to now).
            language: Language code.
            content_type: MIME content type of the file.
            duration: Duration in seconds.
            file_size: File size in bytes.
            collection_ids: List of collection IDs the file belongs to.

        Returns:
            Number of chunks indexed.
        """
        client = get_opensearch_client()
        if not client:
            logger.warning("OpenSearch client not initialized, skipping chunk indexing")
            return 0

        if not segments:
            logger.warning(f"No segments to index for file {file_uuid}")
            return 0

        ensure_chunks_index_exists()
        ensure_search_pipeline_exists()

        if upload_time is None:
            upload_time = datetime.datetime.now().isoformat()

        # 1. Chunk segments
        t_chunk_start = time.time()
        chunks = chunk_transcript_by_speaker_turns(
            segments=segments,
            file_uuid=file_uuid,
            file_id=file_id,
            user_id=user_id,
            title=title,
            speakers=speakers,
            tags=tags,
            upload_time=upload_time,
            language=language,
            content_type=content_type,
            duration=duration,
            file_size=file_size,
            collection_ids=collection_ids,
        )
        chunk_ms = round((time.time() - t_chunk_start) * 1000)

        if not chunks:
            logger.warning(f"No chunks generated for file {file_uuid}")
            return 0

        # 2. Batch embed chunk texts
        t_embed_start = time.time()
        chunk_texts = [c["content"] for c in chunks]
        try:
            embedding_service = SearchEmbeddingService.get_instance()
            embeddings = embedding_service.embed_texts(chunk_texts)
            model_name = embedding_service.model_name

            for i, chunk in enumerate(chunks):
                chunk["embedding"] = embeddings[i]
                chunk["embedding_model"] = model_name
        except Exception as e:
            logger.warning(f"Embedding failed for file {file_uuid}, indexing text-only: {e}")
            model_name = None
            for chunk in chunks:
                chunk["embedding_model"] = None
        embed_ms = round((time.time() - t_embed_start) * 1000)

        # 3. Add indexed_at timestamp
        now = datetime.datetime.now().isoformat()
        for chunk in chunks:
            chunk["indexed_at"] = now

        # 4. Bulk index to OpenSearch
        t_index_start = time.time()
        try:
            indexed = self._bulk_index_chunks(chunks)
            index_ms = round((time.time() - t_index_start) * 1000)
            total_ms = chunk_ms + embed_ms + index_ms

            logger.info(
                f"Indexed {indexed} chunks for file {file_uuid} "
                f"(model: {model_name or 'text-only'}, "
                f"chunk={chunk_ms}ms, embed={embed_ms}ms, index={index_ms}ms, total={total_ms}ms)"
            )
            return {
                "chunk_count": indexed,
                "chunk_ms": chunk_ms,
                "embed_ms": embed_ms,
                "index_ms": index_ms,
                "total_ms": total_ms,
                "model": model_name or "text-only",
            }
        except Exception as e:
            logger.error(f"Bulk indexing failed for file {file_uuid}: {e}")
            return 0

    def delete_transcript_chunks(self, file_uuid: str) -> int:
        """Delete all chunks for a file.

        Args:
            file_uuid: UUID of the file to delete chunks for.

        Returns:
            Number of chunks deleted.
        """
        if not opensearch_client:
            return 0

        index_name = settings.OPENSEARCH_CHUNKS_INDEX
        try:
            if not opensearch_client.indices.exists(index=index_name):
                return 0

            response = opensearch_client.delete_by_query(
                index=index_name,
                body={"query": {"term": {"file_uuid": file_uuid}}},
                refresh=True,
            )
            deleted: int = response.get("deleted", 0)
            logger.info(f"Deleted {deleted} chunks for file {file_uuid}")
            return deleted
        except Exception as e:
            logger.error(f"Error deleting chunks for file {file_uuid}: {e}")
            return 0

    def reindex_transcript(
        self,
        file_id: int,
        file_uuid: str,
        user_id: int,
        segments: list[dict[str, Any]],
        title: str,
        speakers: list[str],
        tags: list[str],
        upload_time: str | None = None,
        language: str = "en",
        content_type: str = "",
        duration: float | None = None,
        file_size: int | None = None,
        collection_ids: list[int] | None = None,
    ) -> int:
        """Re-chunk and re-index a single transcript.

        Args:
            Same as index_transcript_chunks.

        Returns:
            Number of chunks indexed.
        """
        # Delete existing chunks first
        self.delete_transcript_chunks(file_uuid)

        # Re-index
        result = self.index_transcript_chunks(
            file_id=file_id,
            file_uuid=file_uuid,
            user_id=user_id,
            segments=segments,
            title=title,
            speakers=speakers,
            tags=tags,
            upload_time=upload_time,
            language=language,
            content_type=content_type,
            duration=duration,
            file_size=file_size,
            collection_ids=collection_ids,
        )
        # Extract chunk count from result (dict or int)
        if isinstance(result, dict):
            chunk_count: int = result.get("chunk_count", 0)
            return chunk_count
        return result

    def _bulk_index_chunks(self, chunks: list[dict[str, Any]]) -> int:
        """Bulk index chunks to OpenSearch.

        Args:
            chunks: List of chunk documents to index.

        Returns:
            Number of successfully indexed chunks.
        """
        index_name = settings.OPENSEARCH_CHUNKS_INDEX
        bulk_body = []

        for _, chunk in enumerate(chunks):
            doc_id = f"{chunk['file_uuid']}_{chunk['chunk_index']}"
            bulk_body.append(
                {
                    "index": {
                        "_index": index_name,
                        "_id": doc_id,
                    }
                }
            )
            bulk_body.append(chunk)

        if not opensearch_client:
            raise RuntimeError("OpenSearch client not initialized")

        response = opensearch_client.bulk(body=bulk_body, refresh=False)

        if response.get("errors"):
            error_count = sum(1 for item in response["items"] if "error" in item.get("index", {}))
            logger.error(f"Bulk indexing had {error_count} errors out of {len(chunks)}")
            return len(chunks) - error_count

        return len(chunks)
