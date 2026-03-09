import datetime
import logging
import time
from collections.abc import Generator
from typing import Any

from opensearchpy import OpenSearch
from opensearchpy import RequestsHttpConnection

from app.core.config import settings
from app.core.constants import PYANNOTE_EMBEDDING_DIMENSION_V4
from app.core.constants import SENTENCE_TRANSFORMER_DIMENSION

# Setup logging
logger = logging.getLogger(__name__)

# Cache for get_active_speaker_index() — avoids hundreds of OpenSearch
# round-trips during batch re-clustering (#17).
_active_index_cache: tuple[str, float] | None = None
_ACTIVE_INDEX_CACHE_TTL = 30.0  # seconds

# Flag to avoid redundant ensure_indices_exist() calls during batch operations.
_indices_verified = False

# Lazy singleton for SentenceTransformer model (~80MB) — loaded once.
_sentence_transformer_model = None


def _get_sentence_transformer():
    """Lazy singleton for SentenceTransformer model."""
    global _sentence_transformer_model
    if _sentence_transformer_model is None:
        from sentence_transformers import SentenceTransformer

        _sentence_transformer_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _sentence_transformer_model


# Initialize the OpenSearch client (skipped when OPENSEARCH_ENABLED=false)
opensearch_client: OpenSearch | None
if not settings.OPENSEARCH_ENABLED:
    logger.info("OpenSearch is disabled (OPENSEARCH_ENABLED=false), skipping client initialization")
    opensearch_client = None
else:
    try:
        opensearch_client = OpenSearch(
            hosts=[{"host": settings.OPENSEARCH_HOST, "port": int(settings.OPENSEARCH_PORT)}],
            http_auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
            use_ssl=settings.OPENSEARCH_USE_TLS,
            verify_certs=settings.OPENSEARCH_VERIFY_CERTS,
            ssl_show_warn=False,
            connection_class=RequestsHttpConnection,
        )
        logger.info("OpenSearch client initialized successfully")
    except (ConnectionError, ValueError) as e:
        logger.error(f"Configuration error initializing OpenSearch client: {e}")
        opensearch_client = None
    except Exception as e:
        logger.error(f"Unexpected error initializing OpenSearch client: {e}")
        opensearch_client = None


def get_opensearch_client() -> "OpenSearch | None":
    """Get the OpenSearch client, attempting lazy initialization if None.

    If the client was not initialized at module load time (e.g., OpenSearch
    was not yet available), this function attempts to create a new client.

    Returns:
        OpenSearch client instance, or None if connection fails.
    """
    global opensearch_client
    if opensearch_client is not None:
        return opensearch_client

    try:
        opensearch_client = OpenSearch(
            hosts=[{"host": settings.OPENSEARCH_HOST, "port": int(settings.OPENSEARCH_PORT)}],
            http_auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
            use_ssl=settings.OPENSEARCH_USE_TLS,
            verify_certs=settings.OPENSEARCH_VERIFY_CERTS,
            ssl_show_warn=False,
            connection_class=RequestsHttpConnection,
        )
        logger.info("OpenSearch client lazily initialized successfully")
        return opensearch_client
    except Exception as e:
        logger.warning(f"Lazy OpenSearch client initialization failed: {e}")
        return None


def get_speaker_embedding_dimension() -> int:
    """
    Get the speaker embedding dimension from the existing index, or default to v4 for new installs.

    Returns:
        512 for v3 mode (existing pyannote/embedding data)
        256 for v4 mode (new WeSpeaker data or fresh install)
    """
    from app.services.embedding_mode_service import EmbeddingModeService

    return EmbeddingModeService.get_embedding_dimension()


def get_active_speaker_index() -> str:
    """Return the index that currently holds the majority of speaker embeddings.

    During v4 migration, new transcriptions write to 'speakers_v4' while
    the bulk of existing embeddings remain in 'speakers' (v3).  Only after
    finalization does 'speakers_v4' get swapped into 'speakers'.

    Logic: use whichever index has more documents.  This correctly handles:
      - v3 mode (no migration): speakers has data, v4 doesn't exist → speakers
      - v4 pre-finalization: speakers (v3) has bulk data, v4 has few → speakers
      - v4 post-finalization: v4 swapped into speakers, v4 deleted → speakers
      - Fresh v4 install (no v3 data): speakers empty, v4 has data → v4

    Results are cached for 30s to avoid hundreds of round-trips during
    batch re-clustering.
    """
    global _active_index_cache

    now = time.monotonic()
    if _active_index_cache is not None:
        cached_index, cached_at = _active_index_cache
        if now - cached_at < _ACTIVE_INDEX_CACHE_TTL:
            return cached_index

    v4_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4"
    main_index = settings.OPENSEARCH_SPEAKER_INDEX

    if not opensearch_client:
        return main_index

    result = main_index
    try:
        main_count = 0
        v4_count = 0

        if opensearch_client.indices.exists(index=main_index):
            main_count = opensearch_client.count(index=main_index)["count"]

        if opensearch_client.indices.exists(index=v4_index):
            v4_count = opensearch_client.count(index=v4_index)["count"]

        if v4_count > main_count:
            logger.debug(
                "Using v4 index '%s' (%d docs > %d in main)",
                v4_index,
                v4_count,
                main_count,
            )
            result = v4_index

    except Exception as e:
        logger.debug("Error detecting active speaker index: %s", e)

    _active_index_cache = (result, now)
    return result


def invalidate_active_speaker_index_cache() -> None:
    """Force the next call to get_active_speaker_index() to re-query OpenSearch."""
    global _active_index_cache
    _active_index_cache = None


def _repair_index(index_name: str, db: "Any | None" = None) -> bool:
    """Attempt to repair a corrupted OpenSearch index.

    Tries close/reopen first (fixes stale file handles on HNSW vector segments),
    then falls back to force merge if close/reopen is insufficient. As a last
    resort for kNN speaker indices, rebuilds from PostgreSQL data.

    Args:
        index_name: Name of the index to repair.
        db: Optional SQLAlchemy session for DB-based rebuild (Strategy 3).

    Returns:
        True if the index was successfully repaired.
    """
    if not opensearch_client:
        return False

    # Strategy 1: Close and reopen to force re-acquisition of file handles
    try:
        opensearch_client.indices.close(index=index_name)
        opensearch_client.indices.open(index=index_name)
        opensearch_client.search(index=index_name, body={"query": {"match_all": {}}, "size": 0})
        logger.info(f"Index {index_name} repaired via close/reopen")
        return True
    except Exception as e:
        logger.warning(f"Close/reopen failed for {index_name}: {e}")

    # Strategy 2: Force merge to compact corrupted segments
    try:
        opensearch_client.indices.forcemerge(index=index_name, max_num_segments=1)
        opensearch_client.search(index=index_name, body={"query": {"match_all": {}}, "size": 0})
        logger.info(f"Index {index_name} repaired via force merge")
        return True
    except Exception as e:
        logger.warning(f"Force merge failed for {index_name}: {e}")

    # Strategy 3: For kNN indices, rebuild from PostgreSQL data (last resort)
    try:
        mapping = opensearch_client.indices.get_mapping(index=index_name)
        properties = mapping.get(index_name, {}).get("mappings", {}).get("properties", {})
        has_knn = any(
            prop.get("type") == "knn_vector"
            for prop in properties.values()
            if isinstance(prop, dict)
        )
        if has_knn and index_name == settings.OPENSEARCH_SPEAKER_INDEX and db is not None:
            logger.info(f"Attempting rebuild of kNN index {index_name} from PostgreSQL data...")
            result = rebuild_speaker_index(db)
            if result.get("status") == "rebuilt":
                logger.info(
                    f"Index {index_name} rebuilt from DB: {result.get('speakers_indexed', 0)} speakers"
                )
                return True
    except Exception as rebuild_err:
        logger.error(f"Rebuild from DB failed for {index_name}: {rebuild_err}")

    logger.error(f"All repair strategies failed for {index_name}")
    return False


def rebuild_speaker_index(db: "Any") -> dict[str, Any]:
    """Rebuild the speakers index from PostgreSQL + speakers_v4 data.

    Creates a temporary index, copies valid speaker data from the working
    speakers_v4 index, then swaps it in as the new speakers index. This is
    the nuclear option for when the speakers index has corrupted kNN segments
    that cannot be repaired via close/reopen or force-merge.

    Args:
        db: SQLAlchemy Session for querying Speaker rows.

    Returns:
        Dict with rebuild status and count of speakers indexed.
    """
    from sqlalchemy.orm import Session as SASession

    if not isinstance(db, SASession):
        return {"status": "error", "message": "Invalid database session", "speakers_indexed": 0}

    if not opensearch_client:
        return {
            "status": "error",
            "message": "OpenSearch client not available",
            "speakers_indexed": 0,
        }

    from app.models.media import Speaker

    speaker_index = settings.OPENSEARCH_SPEAKER_INDEX
    v4_index = f"{speaker_index}_v4"
    rebuild_index = f"{speaker_index}_rebuild"

    try:
        # Step 1: Query speakers with cluster_id from PostgreSQL
        speakers = db.query(Speaker).filter(Speaker.cluster_id.isnot(None)).all()
        logger.info(f"Rebuild: found {len(speakers)} speakers with cluster assignments in DB")

        # Step 2: Build a lookup of speaker_uuid -> Speaker from DB
        speaker_map = {str(s.uuid): s for s in speakers}

        # Step 3: Fetch embeddings from speakers_v4 index
        docs_to_index: list[dict[str, Any]] = []
        if opensearch_client.indices.exists(index=v4_index):
            # Paginate through all speaker docs in v4 index
            search_after = None
            while True:
                query: dict[str, Any] = {
                    "size": 500,
                    "query": {
                        "bool": {
                            "must_not": [
                                {"exists": {"field": "document_type"}},
                            ],
                        }
                    },
                    "sort": [{"_id": "asc"}],
                    "_source": [
                        "speaker_uuid",
                        "speaker_id",
                        "user_id",
                        "name",
                        "display_name",
                        "profile_id",
                        "profile_uuid",
                        "collection_ids",
                        "media_file_id",
                        "segment_count",
                        "embedding",
                    ],
                }
                if search_after:
                    query["search_after"] = search_after

                response = opensearch_client.search(index=v4_index, body=query)
                hits = response["hits"]["hits"]
                if not hits:
                    break

                for hit in hits:
                    source = hit["_source"]
                    speaker_uuid = source.get("speaker_uuid")
                    embedding = source.get("embedding")
                    if speaker_uuid and embedding and speaker_uuid in speaker_map:
                        docs_to_index.append(source)

                search_after = hits[-1]["sort"]

            logger.info(f"Rebuild: fetched {len(docs_to_index)} embeddings from {v4_index}")
        else:
            logger.warning(f"Rebuild: {v4_index} index does not exist, no embeddings to recover")

        # Step 4: Create temporary rebuild index with correct mapping
        if opensearch_client.indices.exists(index=rebuild_index):
            opensearch_client.indices.delete(index=rebuild_index)

        speaker_index_config = {
            "settings": {
                "index": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                    "knn": True,
                }
            },
            "mappings": {
                "properties": {
                    "speaker_id": {"type": "integer"},
                    "speaker_uuid": {"type": "keyword"},
                    "profile_id": {"type": "integer"},
                    "profile_uuid": {"type": "keyword"},
                    "user_id": {"type": "integer"},
                    "name": {"type": "keyword"},
                    "collection_ids": {"type": "integer"},
                    "media_file_id": {"type": "integer"},
                    "segment_count": {"type": "integer"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": get_speaker_embedding_dimension(),
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "lucene",
                            "parameters": {
                                "ef_construction": 128,
                                "m": 24,
                            },
                        },
                    },
                }
            },
        }

        opensearch_client.indices.create(index=rebuild_index, body=speaker_index_config)
        logger.info(f"Rebuild: created temporary index {rebuild_index}")

        # Step 5: Bulk-index documents into rebuild index
        indexed_count = 0
        if docs_to_index:
            bulk_body: list[dict[str, Any]] = []
            for source in docs_to_index:
                bulk_body.append(
                    {
                        "index": {
                            "_index": rebuild_index,
                            "_id": str(source["speaker_uuid"]),
                        }
                    }
                )
                doc = {
                    "speaker_id": source.get("speaker_id"),
                    "speaker_uuid": str(source["speaker_uuid"]),
                    "profile_id": source.get("profile_id"),
                    "profile_uuid": str(source["profile_uuid"])
                    if source.get("profile_uuid")
                    else None,
                    "user_id": source.get("user_id"),
                    "name": source.get("name"),
                    "display_name": source.get("display_name"),
                    "collection_ids": source.get("collection_ids", []),
                    "media_file_id": source.get("media_file_id"),
                    "segment_count": source.get("segment_count", 1),
                    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "embedding": source["embedding"],
                }
                bulk_body.append(doc)

            # Bulk index in batches of 500
            batch_size = 1000  # 500 action pairs
            for i in range(0, len(bulk_body), batch_size):
                batch = bulk_body[i : i + batch_size]
                resp = opensearch_client.bulk(body=batch, refresh="wait_for")
                if not resp.get("errors"):
                    indexed_count += len(batch) // 2
                else:
                    # Count successes individually
                    for item in resp.get("items", []):
                        if item.get("index", {}).get("status") in (200, 201):
                            indexed_count += 1

        logger.info(f"Rebuild: indexed {indexed_count} speakers into {rebuild_index}")

        # Step 6: Delete the corrupted speakers index
        if opensearch_client.indices.exists(index=speaker_index):
            opensearch_client.indices.delete(index=speaker_index)
            logger.info(f"Rebuild: deleted corrupted index {speaker_index}")

        # Step 7: Create new speakers index with correct mapping
        opensearch_client.indices.create(index=speaker_index, body=speaker_index_config)
        logger.info(f"Rebuild: created fresh index {speaker_index}")

        # Step 8: Copy data from rebuild index to new speakers index
        if indexed_count > 0:
            # Read all docs from rebuild index and bulk-index into new speakers index
            search_after = None
            copy_count = 0
            while True:
                query = {
                    "size": 500,
                    "query": {"match_all": {}},
                    "sort": [{"_id": "asc"}],
                }
                if search_after:
                    query["search_after"] = search_after

                response = opensearch_client.search(index=rebuild_index, body=query)
                hits = response["hits"]["hits"]
                if not hits:
                    break

                copy_bulk: list[dict[str, Any]] = []
                for hit in hits:
                    copy_bulk.append(
                        {
                            "index": {
                                "_index": speaker_index,
                                "_id": hit["_id"],
                            }
                        }
                    )
                    copy_bulk.append(hit["_source"])

                resp = opensearch_client.bulk(body=copy_bulk, refresh="wait_for")
                if not resp.get("errors"):
                    copy_count += len(hits)

                search_after = hits[-1]["sort"]

            logger.info(f"Rebuild: copied {copy_count} docs to new {speaker_index}")

        # Step 9: Clean up rebuild index
        if opensearch_client.indices.exists(index=rebuild_index):
            opensearch_client.indices.delete(index=rebuild_index)
            logger.info(f"Rebuild: deleted temporary index {rebuild_index}")

        logger.info(f"Speaker index rebuild complete: {indexed_count} speakers re-indexed")
        return {
            "status": "rebuilt",
            "speakers_indexed": indexed_count,
        }

    except Exception as e:
        # Clean up rebuild index on failure
        try:
            if opensearch_client.indices.exists(index=rebuild_index):
                opensearch_client.indices.delete(index=rebuild_index)
        except Exception as cleanup_err:
            logger.debug("Failed to clean up rebuild index: %s", cleanup_err)
        logger.error(f"Speaker index rebuild failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "speakers_indexed": 0,
        }


def _is_index_corruption_error(error: Exception) -> bool:
    """Check if an exception indicates OpenSearch index corruption."""
    error_str = str(error).lower()
    return any(
        indicator in error_str
        for indicator in [
            "503",
            "search_phase_execution_exception",
            "already_closed",
            "no_shard_available",
        ]
    )


def check_and_repair_indices() -> list[str]:
    """Check OpenSearch indices health and auto-repair corrupted shards.

    Runs a simple match_all query (size=0) against each index. If a 503 or
    search_phase_execution_exception is returned (typically caused by corrupted
    Lucene HNSW vector segment files after unclean shutdowns), the index is
    closed and reopened to force OpenSearch to re-open all segment file handles.

    Returns:
        List of index names that were repaired (empty if all healthy).
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized, skipping health check")
        return []

    v4_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4"
    indices = [
        settings.OPENSEARCH_SPEAKER_INDEX,
        settings.OPENSEARCH_TRANSCRIPT_INDEX,
        v4_index,
    ]
    repaired: list[str] = []

    for index_name in indices:
        if not opensearch_client.indices.exists(index=index_name):
            continue
        try:
            opensearch_client.search(index=index_name, body={"query": {"match_all": {}}, "size": 0})
            logger.info(f"Index health check passed: {index_name}")
        except Exception as e:
            if _is_index_corruption_error(e):
                logger.warning(f"Index {index_name} unhealthy, attempting repair: {e}")
                if _repair_index(index_name):
                    repaired.append(index_name)
                else:
                    logger.error(f"Index {index_name} could not be repaired automatically")
            else:
                logger.error(f"Index health check failed for {index_name}: {e}")

    return repaired


def ensure_indices_exist():
    """
    Ensure the transcript and speaker indices exist, creating them if necessary
    """
    if not settings.OPENSEARCH_ENABLED:
        return
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized, skipping index creation")
        return

    try:
        # Create transcript index if it doesn't exist
        if not opensearch_client.indices.exists(index=settings.OPENSEARCH_TRANSCRIPT_INDEX):
            transcript_index_config = {
                "settings": {
                    "index": {"number_of_shards": 1, "number_of_replicas": 0},
                    "analysis": {"analyzer": {"default": {"type": "standard"}}},
                },
                "mappings": {
                    "properties": {
                        "file_id": {"type": "integer"},
                        "file_uuid": {"type": "keyword"},
                        "user_id": {"type": "integer"},
                        "content": {"type": "text"},
                        "speakers": {"type": "keyword"},
                        "tags": {"type": "keyword"},
                        "upload_time": {"type": "date"},
                        "title": {"type": "text"},
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": SENTENCE_TRANSFORMER_DIMENSION,
                        },
                    }
                },
            }

            opensearch_client.indices.create(
                index=settings.OPENSEARCH_TRANSCRIPT_INDEX, body=transcript_index_config
            )

            logger.info(f"Created transcript index: {settings.OPENSEARCH_TRANSCRIPT_INDEX}")

        # Create speaker index if it doesn't exist
        if not opensearch_client.indices.exists(index=settings.OPENSEARCH_SPEAKER_INDEX):
            speaker_index_config = {
                "settings": {
                    "index": {
                        "number_of_shards": 1,
                        "number_of_replicas": 0,
                        "knn": True,
                    }
                },
                "mappings": {
                    "properties": {
                        "speaker_id": {"type": "integer"},
                        "speaker_uuid": {"type": "keyword"},
                        "profile_id": {"type": "integer"},
                        "profile_uuid": {"type": "keyword"},
                        "user_id": {"type": "integer"},
                        "name": {"type": "keyword"},
                        "collection_ids": {"type": "integer"},  # Array of collection IDs
                        "media_file_id": {"type": "integer"},  # Source media file
                        "segment_count": {"type": "integer"},  # Number of segments used
                        "created_at": {"type": "date"},
                        "updated_at": {"type": "date"},
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": get_speaker_embedding_dimension(),  # Dynamic based on mode
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "lucene",  # Use lucene engine for better filtering
                                "parameters": {
                                    "ef_construction": 128,
                                    "m": 24,
                                },
                            },
                        },
                    }
                },
            }

            opensearch_client.indices.create(
                index=settings.OPENSEARCH_SPEAKER_INDEX, body=speaker_index_config
            )

            logger.info(f"Created speaker index: {settings.OPENSEARCH_SPEAKER_INDEX}")

    except ConnectionError as e:
        logger.error(f"Connection error creating indices: {e}")
    except ValueError as e:
        logger.error(f"Configuration error creating indices: {e}")
    except Exception as e:
        logger.error(f"Unexpected error creating indices: {e}")


def create_speaker_index_v4(index_name: str | None = None) -> bool:
    """
    Create a new speaker index with v4 dimensions (256-dim).
    Used for migration from v3 to v4.

    Args:
        index_name: Name for the new index (defaults to speakers_v4)

    Returns:
        True if successful
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return False

    index_name = index_name or f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4"

    try:
        # Check if index already exists
        if opensearch_client.indices.exists(index=index_name):
            logger.info(f"V4 speaker index already exists: {index_name}")
            return True

        speaker_index_config = {
            "settings": {
                "index": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                    "knn": True,
                }
            },
            "mappings": {
                "properties": {
                    "document_type": {"type": "keyword"},
                    "speaker_id": {"type": "integer"},
                    "speaker_uuid": {"type": "keyword"},
                    "profile_id": {"type": "integer"},
                    "profile_uuid": {"type": "keyword"},
                    "profile_name": {"type": "keyword"},
                    "user_id": {"type": "integer"},
                    "name": {"type": "keyword"},
                    "display_name": {"type": "keyword"},
                    "collection_ids": {"type": "integer"},
                    "media_file_id": {"type": "integer"},
                    "segment_count": {"type": "integer"},
                    "speaker_count": {"type": "integer"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": PYANNOTE_EMBEDDING_DIMENSION_V4,  # 256-dim for v4
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "lucene",
                            "parameters": {
                                "ef_construction": 128,
                                "m": 24,
                            },
                        },
                    },
                }
            },
        }

        opensearch_client.indices.create(index=index_name, body=speaker_index_config)
        logger.info(f"Created v4 speaker index: {index_name}")
        return True

    except Exception as e:
        logger.error(f"Error creating v4 speaker index: {e}")
        return False


def ensure_v4_index_exists() -> bool:
    """Ensure speakers_v4 index exists, creating if needed. Idempotent."""
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return False

    v4_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4"
    try:
        if opensearch_client.indices.exists(index=v4_index):
            return True
    except Exception as e:
        logger.warning(f"Error checking v4 index existence: {e}")

    return create_speaker_index_v4()


def add_speaker_embedding_v4(
    speaker_id: int,
    speaker_uuid: str,
    user_id: int,
    name: str,
    embedding: list[float],
    profile_id: int | None = None,
    profile_uuid: str | None = None,
    collection_ids: list[int] | None = None,
    media_file_id: int | None = None,
    segment_count: int = 1,
    display_name: str | None = None,
):
    """
    Add a speaker embedding to the v4 staging index during migration.

    This function indexes to the _v4 staging index instead of the main speaker index,
    allowing migration to proceed without affecting the production index.

    Args:
        speaker_id: ID of the speaker in the database (for internal queries)
        speaker_uuid: UUID of the speaker (used as document ID)
        user_id: ID of the user who owns the speaker profile
        name: Name of the speaker
        embedding: Vector embedding of the speaker's voice (256-dim for v4)
        profile_id: Optional speaker profile ID (for internal queries)
        profile_uuid: Optional speaker profile UUID
        collection_ids: Optional list of collection IDs
        media_file_id: Optional source media file ID
        segment_count: Number of segments used to create embedding
        display_name: Optional display name for the speaker
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized, skipping speaker embedding")
        return

    v4_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4"

    try:
        # Validate embedding before indexing
        if embedding is None:
            logger.error(f"Cannot index speaker {speaker_uuid}: embedding is None")
            return

        if not isinstance(embedding, list) or len(embedding) == 0:
            logger.error(f"Cannot index speaker {speaker_uuid}: invalid embedding format")
            return

        logger.info(
            f"Indexing speaker {speaker_uuid} (ID: {speaker_id}) to v4 index with embedding length: {len(embedding)}"
        )

        # Prepare document
        doc = {
            "speaker_id": speaker_id,
            "speaker_uuid": str(speaker_uuid),
            "profile_id": profile_id,
            "profile_uuid": str(profile_uuid) if profile_uuid else None,
            "user_id": user_id,
            "name": name,
            "display_name": display_name,
            "collection_ids": collection_ids or [],
            "media_file_id": media_file_id,
            "segment_count": segment_count,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "embedding": embedding,
        }

        # Index the document to the v4 staging index using UUID as document ID
        response = opensearch_client.index(
            index=v4_index,
            body=doc,
            id=str(speaker_uuid),  # Use speaker_uuid as document ID
        )

        logger.info(
            f"Indexed speaker embedding for speaker {speaker_uuid} (ID: {speaker_id}) to v4 index: {response}"
        )
        return response

    except Exception as e:
        logger.error(
            f"Error indexing speaker embedding to v4 for speaker {speaker_uuid} (ID: {speaker_id}): {e}"
        )


def store_profile_embedding_v4(
    profile_id: int,
    profile_uuid: str,
    profile_name: str,
    embedding: list[float],
    speaker_count: int,
    user_id: int,
) -> bool:
    """Store consolidated profile embedding in the v4 staging index.

    Same document structure as store_profile_embedding() but targets
    speakers_v4 index for migration pre-population.

    Args:
        profile_id: ID of the speaker profile.
        profile_uuid: UUID of the speaker profile (used as document ID).
        profile_name: Name of the speaker profile.
        embedding: Averaged 256-dim embedding vector.
        speaker_count: Number of speakers contributing to this embedding.
        user_id: ID of the user who owns the profile.

    Returns:
        True if successful, False otherwise.
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return False

    v4_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4"

    try:
        doc = {
            "document_type": "profile",
            "profile_id": profile_id,
            "profile_uuid": str(profile_uuid),
            "profile_name": profile_name,
            "user_id": user_id,
            "embedding": embedding,
            "speaker_count": speaker_count,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        opensearch_client.index(
            index=v4_index,
            body=doc,
            id=f"profile_{profile_uuid}",
            refresh="wait_for",
        )

        logger.info(
            f"Stored v4 profile {profile_uuid} ({profile_name}) embedding "
            f"with {speaker_count} speakers"
        )
        return True

    except Exception as e:
        logger.error(f"Error storing v4 profile embedding for {profile_uuid}: {e}")
        return False


def index_transcript(
    file_id: int,
    file_uuid: str,
    user_id: int,
    transcript_text: str,
    speakers: list[str],
    title: str,
    tags: list[str] | None = None,
    embedding: list[float] | None = None,
):
    """
    Index a transcript in OpenSearch

    Args:
        file_id: ID of the media file (for internal queries)
        file_uuid: UUID of the media file (used as document ID)
        user_id: ID of the user who owns the file
        transcript_text: Full transcript text
        speakers: List of speaker names/IDs in the transcript
        title: Title of the media file (filename)
        tags: Optional list of tags associated with the file
        embedding: Optional vector embedding of the transcript (if not provided, we'd compute it)
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized, skipping indexing")
        return

    try:
        ensure_indices_exist()

        # Skip embedding if not provided - let OpenSearch handle text search without vector similarity
        if embedding is None:
            logger.info(
                f"No embedding provided for transcript {file_uuid}, indexing with text search only"
            )
            # Don't include embedding field when none is provided

        # Prepare document
        doc = {
            "file_id": file_id,
            "file_uuid": str(file_uuid),
            "user_id": user_id,
            "content": transcript_text,
            "speakers": speakers,
            "title": title,
            "tags": tags or [],
            "upload_time": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),  # ISO-8601 format
        }

        # Only include embedding if provided
        if embedding is not None:
            doc["embedding"] = embedding

        # Index the document using UUID as document ID
        response = opensearch_client.index(
            index=settings.OPENSEARCH_TRANSCRIPT_INDEX,
            body=doc,
            id=str(file_uuid),  # Use file_uuid as document ID
        )

        logger.info(f"Indexed transcript for file {file_uuid} (ID: {file_id}): {response}")
        return response

    except Exception as e:
        logger.error(f"Error indexing transcript for file {file_uuid} (ID: {file_id}): {e}")


def update_transcript_title(file_uuid: str, new_title: str):
    """
    Update the title of an indexed transcript in OpenSearch

    Args:
        file_uuid: UUID of the media file
        new_title: New title to update
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized, skipping title update")
        return

    try:
        # Update the document with the new title
        update_body = {"doc": {"title": new_title}}

        response = opensearch_client.update(
            index=settings.OPENSEARCH_TRANSCRIPT_INDEX,
            id=str(file_uuid),
            body=update_body,
        )

        logger.info(f"Updated transcript title for file {file_uuid}: {response}")
        return response

    except Exception as e:
        # If the document doesn't exist yet, that's okay - it will be indexed later
        if "not_found" in str(e).lower():
            logger.info(
                f"Document not found for file {file_uuid}, will be indexed when transcription completes"
            )
        else:
            logger.error(f"Error updating transcript title for file {file_uuid}: {e}")


def add_speaker_embedding(
    speaker_id: int,
    speaker_uuid: str,
    user_id: int,
    name: str,
    embedding: list[float],
    profile_id: int | None = None,
    profile_uuid: str | None = None,
    collection_ids: list[int] | None = None,
    media_file_id: int | None = None,
    segment_count: int = 1,
    display_name: str | None = None,
):
    """
    Add a speaker embedding to OpenSearch with collection support

    Args:
        speaker_id: ID of the speaker in the database (for internal queries)
        speaker_uuid: UUID of the speaker (used as document ID)
        user_id: ID of the user who owns the speaker profile
        name: Name of the speaker
        embedding: Vector embedding of the speaker's voice
        profile_id: Optional speaker profile ID (for internal queries)
        profile_uuid: Optional speaker profile UUID
        collection_ids: Optional list of collection IDs
        media_file_id: Optional source media file ID
        segment_count: Number of segments used to create embedding
        display_name: Optional display name for the speaker
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized, skipping speaker embedding")
        return

    try:
        ensure_indices_exist()

        # Validate embedding before indexing
        if embedding is None:
            logger.error(f"Cannot index speaker {speaker_uuid}: embedding is None")
            return

        if not isinstance(embedding, list) or len(embedding) == 0:
            logger.error(f"Cannot index speaker {speaker_uuid}: invalid embedding format")
            return

        logger.info(
            f"Indexing speaker {speaker_uuid} (ID: {speaker_id}) with embedding length: {len(embedding)}"
        )

        # Prepare document
        doc = {
            "speaker_id": speaker_id,
            "speaker_uuid": str(speaker_uuid),
            "profile_id": profile_id,
            "profile_uuid": str(profile_uuid) if profile_uuid else None,
            "user_id": user_id,
            "name": name,
            "display_name": display_name,
            "collection_ids": collection_ids or [],
            "media_file_id": media_file_id,
            "segment_count": segment_count,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "embedding": embedding,
        }

        # Index the document using UUID as document ID
        response = opensearch_client.index(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            body=doc,
            id=str(speaker_uuid),  # Use speaker_uuid as document ID
        )

        logger.info(
            f"Indexed speaker embedding for speaker {speaker_uuid} (ID: {speaker_id}): {response}"
        )
        return response

    except Exception as e:
        # Retry once for transient connection errors before falling through
        # to the index corruption check below
        if isinstance(e, (ConnectionError, OSError)):
            logger.warning(f"Transient error indexing speaker {speaker_uuid}, retrying once: {e}")
            import time as _time

            _time.sleep(0.5)
            try:
                response = opensearch_client.index(
                    index=settings.OPENSEARCH_SPEAKER_INDEX,
                    body=doc,
                    id=str(speaker_uuid),
                )
                logger.info(
                    f"Retry succeeded: indexed speaker {speaker_uuid} after transient error"
                )
                return response
            except Exception as retry_err:
                logger.error(f"Retry failed for speaker {speaker_uuid}: {retry_err}")
                # Fall through to index corruption check with the retry error
                e = retry_err
        if _is_index_corruption_error(e):
            logger.warning(
                f"Index corruption detected indexing speaker {speaker_uuid}, attempting repair..."
            )
            if _repair_index(settings.OPENSEARCH_SPEAKER_INDEX):
                try:
                    doc = {
                        "speaker_id": speaker_id,
                        "speaker_uuid": str(speaker_uuid),
                        "profile_id": profile_id,
                        "profile_uuid": str(profile_uuid) if profile_uuid else None,
                        "user_id": user_id,
                        "name": name,
                        "display_name": display_name,
                        "collection_ids": collection_ids or [],
                        "media_file_id": media_file_id,
                        "segment_count": segment_count,
                        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "embedding": embedding,
                    }
                    response = opensearch_client.index(
                        index=settings.OPENSEARCH_SPEAKER_INDEX,
                        body=doc,
                        id=str(speaker_uuid),
                    )
                    logger.info(f"Retry succeeded: indexed speaker {speaker_uuid} after repair")
                    return response
                except Exception as retry_err:
                    logger.error(
                        f"Retry after repair failed for speaker {speaker_uuid}: {retry_err}"
                    )
        else:
            logger.error(
                f"Error indexing speaker embedding for speaker {speaker_uuid} (ID: {speaker_id}): {e}"
            )


def bulk_add_speaker_embeddings(embeddings_data: list[dict[str, Any]]):
    """
    Bulk add multiple speaker embeddings for efficient indexing

    Args:
        embeddings_data: List of embedding data dictionaries with speaker_uuid
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return

    try:
        ensure_indices_exist()

        # Prepare bulk operations
        bulk_body = []
        for data in embeddings_data:
            # Index action using UUID as document ID
            bulk_body.append(
                {
                    "index": {
                        "_index": settings.OPENSEARCH_SPEAKER_INDEX,
                        "_id": str(data["speaker_uuid"]),
                    }
                }
            )

            # Document
            doc_data: dict[str, Any] = {
                "speaker_id": data["speaker_id"],
                "speaker_uuid": str(data["speaker_uuid"]),
                "profile_id": data.get("profile_id"),
                "profile_uuid": str(data.get("profile_uuid")) if data.get("profile_uuid") else None,
                "user_id": data["user_id"],
                "name": data["name"],
                "collection_ids": data.get("collection_ids", []),
                "media_file_id": data.get("media_file_id"),
                "segment_count": data.get("segment_count", 1),
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "embedding": data["embedding"],
            }
            bulk_body.append(doc_data)

        # Execute bulk operation
        response = opensearch_client.bulk(body=bulk_body)

        if response["errors"]:
            logger.error(f"Bulk indexing had errors: {response}")
        else:
            logger.info(f"Successfully bulk indexed {len(embeddings_data)} speaker embeddings")

        return response

    except Exception as e:
        logger.error(f"Error bulk indexing speaker embeddings: {e}")


def search_transcripts(  # noqa: C901
    query: str,
    user_id: int,
    speaker: str | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
    use_semantic: bool = True,
) -> list[dict[str, Any]]:
    """
    Search for transcripts matching the query

    Args:
        query: Search query text
        user_id: ID of the user performing the search
        speaker: Optional speaker name to filter by
        tags: Optional list of tags to filter by
        limit: Maximum number of results to return
        use_semantic: Whether to use semantic (vector) search in addition to text search

    Returns:
        List of matching documents
    """
    # Return empty results when OpenSearch is disabled or unavailable
    if not settings.OPENSEARCH_ENABLED:
        logger.debug("OpenSearch is disabled, returning empty search results")
        return []
    if not opensearch_client:
        logger.debug("OpenSearch client not initialized, returning empty search results")
        return []

    try:
        # Build the search query
        must_conditions: list[dict[str, Any]] = [
            {"term": {"user_id": user_id}}  # Restrict to user's files
        ]

        # Add full-text search
        if query:
            must_conditions.append({"match": {"content": {"query": query, "fuzziness": "AUTO"}}})

        # Add speaker filter if specified
        if speaker:
            must_conditions.append({"term": {"speakers": speaker}})

        # Add tags filter if specified
        if tags and len(tags) > 0:
            must_conditions.append({"terms": {"tags": tags}})

        # Construct basic search
        search_body = {
            "query": {"bool": {"must": must_conditions}},
            "size": limit,
            "_source": [
                "file_id",
                "file_uuid",
                "title",
                "content",
                "speakers",
                "tags",
                "upload_time",
            ],
            "highlight": {
                "fields": {
                    "content": {
                        "pre_tags": ["<em>"],
                        "post_tags": ["</em>"],
                        "fragment_size": 150,
                    }
                }
            },
        }

        # Add semantic search if requested
        if use_semantic and query:
            # Compute the query embedding using sentence-transformers
            try:
                embedding_model = _get_sentence_transformer()

                # Generate embedding for the query
                query_embedding = embedding_model.encode(query, normalize_embeddings=True).tolist()
                logger.info(f"Generated embedding for query: {query[:30]}...")
            except ImportError:
                logger.warning(
                    "sentence-transformers package not installed, using fallback embedding"
                )
                # Fallback to zero vector
                query_embedding = [0.0] * SENTENCE_TRANSFORMER_DIMENSION
            except Exception as e:
                logger.warning(f"Error generating query embedding: {e}")
                # Fallback to zero vector
                query_embedding = [0.0] * SENTENCE_TRANSFORMER_DIMENSION

            # Add kNN query
            knn_query: dict[str, Any] = {
                "knn": {"embedding": {"vector": query_embedding, "k": limit}}
            }

            # Combine text search with vector search
            search_body_query = search_body["query"]
            if isinstance(search_body_query, dict) and "bool" in search_body_query:
                search_body_query["bool"]["should"] = [knn_query]

        # Execute search
        response = opensearch_client.search(
            index=settings.OPENSEARCH_TRANSCRIPT_INDEX, body=search_body
        )

        # Process results
        results = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            result = {
                "file_id": source["file_id"],
                "file_uuid": source.get("file_uuid"),
                "title": source["title"],
                "speakers": source["speakers"],
                "upload_time": source["upload_time"],
            }

            # Add highlighted snippet if available
            if "highlight" in hit and "content" in hit["highlight"]:
                result["snippet"] = "...".join(hit["highlight"]["content"])
            else:
                # Fallback to first part of content
                content = source.get("content", "")
                result["snippet"] = content[:150] + "..." if len(content) > 150 else content

            results.append(result)

        return results

    except Exception as e:
        logger.error(f"Error searching transcripts: {e}")
        return []


def find_matching_speaker(
    embedding: list[float],
    user_id: int,
    threshold: float = 0.5,
    collection_ids: list[int] | None = None,
    exclude_speaker_ids: list[int] | None = None,
    accessible_user_ids: list[int] | None = None,
) -> dict[str, Any] | None:
    """
    Find a matching speaker for a given embedding with confidence score

    Args:
        embedding: Speaker embedding vector
        user_id: ID of the user
        threshold: Minimum similarity threshold (0-1) for matching
        collection_ids: Optional list of collection IDs to search within
        exclude_speaker_ids: Optional list of speaker IDs to exclude
        accessible_user_ids: Optional list of user IDs to search within
            (for shared profile scope). If None, filters by user_id.

    Returns:
        Dictionary with speaker info and confidence if a match is found, None otherwise
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized, skipping speaker matching")
        return None

    try:
        # Ensure indices exist before searching
        ensure_indices_exist()

        # Build filter conditions - use accessible user IDs for shared profile scope
        filters: list[dict[str, Any]]
        if accessible_user_ids:
            filters = [{"terms": {"user_id": accessible_user_ids}}]
        else:
            filters = [{"term": {"user_id": user_id}}]

        # Add collection filter if specified
        if collection_ids:
            filters.append({"terms": {"collection_ids": collection_ids}})

        # Add exclusion filter if specified
        if exclude_speaker_ids:
            filters.append({"bool": {"must_not": {"terms": {"speaker_id": exclude_speaker_ids}}}})

        # Build a kNN query to find similar speaker embeddings
        # Using the proper OpenSearch knn query syntax based on documentation
        query = {
            "size": 5,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": embedding,
                        "k": 5,
                        "filter": {"bool": {"filter": filters}},
                    }
                }
            },
        }

        # Execute search
        response = opensearch_client.search(index=settings.OPENSEARCH_SPEAKER_INDEX, body=query)

        # Check if we have a match
        if len(response["hits"]["hits"]) > 0:
            hit = response["hits"]["hits"][0]
            # Get the score (normalized 0-1)
            score = hit["_score"]

            # Check if score meets our threshold
            if score >= threshold:
                source = hit["_source"]
                # Skip profile documents that don't have speaker_id
                if "speaker_id" not in source:
                    logger.debug(
                        f"Skipping profile document in speaker matching: {source.get('profile_id')}"
                    )
                    return None

                return {
                    "speaker_id": source["speaker_id"],
                    "speaker_uuid": source.get("speaker_uuid"),
                    "profile_id": source.get("profile_id"),
                    "profile_uuid": source.get("profile_uuid"),
                    "name": source["name"],
                    "confidence": score,
                    "media_file_id": source.get("media_file_id"),
                    "collection_ids": source.get("collection_ids", []),
                }

        # No match found or score below threshold
        return None

    except Exception as e:
        if _is_index_corruption_error(e):
            logger.warning(
                "Index corruption detected during speaker matching, attempting repair..."
            )
            if _repair_index(settings.OPENSEARCH_SPEAKER_INDEX):
                try:
                    response = opensearch_client.search(
                        index=settings.OPENSEARCH_SPEAKER_INDEX, body=query
                    )
                    if len(response["hits"]["hits"]) > 0:
                        hit = response["hits"]["hits"][0]
                        score = hit["_score"]
                        if score >= threshold:
                            source = hit["_source"]
                            if "speaker_id" not in source:
                                return None
                            return {
                                "speaker_id": source["speaker_id"],
                                "speaker_uuid": source.get("speaker_uuid"),
                                "profile_id": source.get("profile_id"),
                                "profile_uuid": source.get("profile_uuid"),
                                "name": source["name"],
                                "confidence": score,
                                "media_file_id": source.get("media_file_id"),
                                "collection_ids": source.get("collection_ids", []),
                            }
                    return None
                except Exception as retry_err:
                    logger.error(f"Retry after repair failed for speaker matching: {retry_err}")
                    return None
        logger.error(f"Error finding matching speaker: {e}")
        return None


def batch_find_matching_speakers(
    embeddings: list[dict[str, Any]],
    user_id: int,
    threshold: float = 0.5,
    max_candidates: int = 5,
) -> list[dict[str, Any]]:
    """
    Find matching speakers for multiple embeddings in a single query (efficient batch operation)

    Args:
        embeddings: List of dicts with 'id' and 'embedding' keys
        user_id: ID of the user
        threshold: Minimum similarity threshold
        max_candidates: Maximum candidates per embedding

    Returns:
        List of match results for each input embedding
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return []

    try:
        # Ensure indices exist before searching
        ensure_indices_exist()

        # Use multi-search for efficient batch processing
        msearch_body: list[dict[str, Any]] = []

        for emb_data in embeddings:
            # Add search header
            msearch_body.append({"index": settings.OPENSEARCH_SPEAKER_INDEX})

            # Add search query with self-exclusion
            query_body: dict[str, Any] = {
                "size": max_candidates,
                "query": {
                    "bool": {
                        "filter": [{"term": {"user_id": user_id}}],
                        "must_not": [
                            {"term": {"speaker_id": emb_data["id"]}},  # Exclude self
                            {"exists": {"field": "document_type"}},  # Exclude profile documents
                        ],
                    }
                },
                "knn": {
                    "embedding": {
                        "vector": emb_data["embedding"],
                        "k": max_candidates,
                    }
                },
            }
            msearch_body.append(query_body)

        # Execute multi-search
        response = opensearch_client.msearch(body=msearch_body)

        # Process results
        results = []
        for i, emb_data in enumerate(embeddings):
            search_response = response["responses"][i]

            matches = []
            if "hits" in search_response and search_response["hits"]["hits"]:
                for hit in search_response["hits"]["hits"]:
                    score = hit["_score"]
                    if score >= threshold:
                        source = hit["_source"]
                        matches.append(
                            {
                                "speaker_id": source["speaker_id"],
                                "speaker_uuid": source.get("speaker_uuid"),
                                "profile_id": source.get("profile_id"),
                                "profile_uuid": source.get("profile_uuid"),
                                "name": source["name"],
                                "confidence": score,
                                "media_file_id": source.get("media_file_id"),
                            }
                        )

            results.append({"input_id": emb_data["id"], "matches": matches})

        return results

    except Exception as e:
        logger.error(f"Error in batch speaker matching: {e}")
        return []


def find_speaker_across_media(speaker_uuid: str, user_id: int) -> list[dict[str, Any]]:
    """
    Find all media files where a specific speaker appears

    Args:
        speaker_uuid: UUID of the speaker
        user_id: ID of the user

    Returns:
        List of media files where this speaker appears
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return []

    try:
        # Ensure indices exist before searching
        ensure_indices_exist()

        # First, get the speaker's name from the speaker index using UUID
        speaker_doc = opensearch_client.get(
            index=settings.OPENSEARCH_SPEAKER_INDEX, id=str(speaker_uuid)
        )

        if not speaker_doc or "_source" not in speaker_doc:
            return []

        speaker_name = speaker_doc["_source"]["name"]

        # Search for transcripts containing this speaker
        size_limit = 100
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"user_id": user_id}},
                        {"term": {"speakers": speaker_name}},
                    ]
                }
            },
            "size": size_limit,  # Max media files returned; increase if users have very large libraries
            "_source": ["file_id", "file_uuid", "title", "upload_time"],
        }

        response = opensearch_client.search(index=settings.OPENSEARCH_TRANSCRIPT_INDEX, body=query)

        total_hits = response["hits"]["total"]["value"]
        if total_hits > size_limit:
            logger.warning(
                "Results truncated: %d hits but size limit is %d",
                total_hits,
                size_limit,
            )

        # Process results
        results = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            results.append(
                {
                    "file_id": source["file_id"],
                    "file_uuid": source.get("file_uuid"),
                    "title": source["title"],
                    "upload_time": source["upload_time"],
                }
            )

        return results

    except Exception as e:
        logger.error(f"Error finding speaker across media: {e}")
        return []


def update_speaker_collections(
    speaker_uuid: str, profile_id: int, profile_uuid: str, collection_ids: list[int]
):
    """
    Update speaker embedding collections when a speaker is labeled/assigned to profile

    Args:
        speaker_uuid: Speaker UUID
        profile_id: Profile ID the speaker is assigned to (for internal queries)
        profile_uuid: Profile UUID the speaker is assigned to
        collection_ids: List of collection IDs to assign
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return

    try:
        # Update the speaker document in OpenSearch using UUID
        update_body = {
            "doc": {
                "profile_id": profile_id,
                "profile_uuid": str(profile_uuid) if profile_uuid else None,
                "collection_ids": collection_ids,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        }

        response = opensearch_client.update(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            id=str(speaker_uuid),
            body=update_body,
        )

        logger.info(f"Updated speaker {speaker_uuid} collections: {collection_ids}")
        return response

    except Exception as e:
        logger.error(f"Error updating speaker collections: {e}")


def move_speaker_to_profile_collection(
    unlabeled_speaker_uuid: str,
    target_profile_id: int,
    target_profile_uuid: str,
    target_collection_ids: list[int],
):
    """
    Move an unlabeled speaker embedding to a profile's collection

    Args:
        unlabeled_speaker_uuid: UUID of the unlabeled speaker
        target_profile_id: ID of the target profile (for internal queries)
        target_profile_uuid: UUID of the target profile
        target_collection_ids: Target collection IDs
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return

    try:
        # Update the speaker's profile and collection assignments using UUID
        update_body = {
            "doc": {
                "profile_id": target_profile_id,
                "profile_uuid": str(target_profile_uuid) if target_profile_uuid else None,
                "collection_ids": target_collection_ids,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        }

        response = opensearch_client.update(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            id=str(unlabeled_speaker_uuid),
            body=update_body,
        )

        logger.info(f"Moved speaker {unlabeled_speaker_uuid} to profile {target_profile_uuid}")
        return response

    except Exception as e:
        logger.error(f"Error moving speaker to profile collection: {e}")


def bulk_update_collection_assignments(updates: list[dict[str, Any]]):
    """
    Bulk update collection assignments for multiple speakers

    Args:
        updates: List of update dictionaries with speaker_uuid, profile_id, profile_uuid, collection_ids
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return

    try:
        # Prepare bulk update operations
        bulk_body: list[dict[str, Any]] = []
        for update in updates:
            # Update action using UUID as document ID
            bulk_body.append(
                {
                    "update": {
                        "_index": settings.OPENSEARCH_SPEAKER_INDEX,
                        "_id": str(update["speaker_uuid"]),
                    }
                }
            )

            # Update document
            doc_update: dict[str, Any] = {
                "doc": {
                    "profile_id": update.get("profile_id"),
                    "profile_uuid": str(update.get("profile_uuid"))
                    if update.get("profile_uuid")
                    else None,
                    "collection_ids": update.get("collection_ids", []),
                    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
            }
            bulk_body.append(doc_update)

        # Execute bulk operation
        response = opensearch_client.bulk(body=bulk_body)

        if response["errors"]:
            logger.error(f"Bulk collection update had errors: {response}")
        else:
            logger.info(f"Successfully updated collections for {len(updates)} speakers")

        return response

    except Exception as e:
        logger.error(f"Error bulk updating collection assignments: {e}")


def get_speakers_in_collection(collection_id: int, user_id: int) -> list[dict[str, Any]]:
    """
    Get all speakers in a specific collection

    Args:
        collection_id: Collection ID
        user_id: User ID

    Returns:
        List of speaker documents in the collection
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return []

    try:
        # Ensure indices exist before searching
        ensure_indices_exist()

        size_limit = 1000
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"user_id": user_id}},
                        {"term": {"collection_ids": collection_id}},
                    ]
                }
            },
            "size": size_limit,  # Upper bound for speakers per collection; log warning if exceeded
            "_source": [
                "speaker_id",
                "speaker_uuid",
                "profile_id",
                "profile_uuid",
                "name",
                "media_file_id",
                "segment_count",
                "created_at",
            ],
        }

        response = opensearch_client.search(index=settings.OPENSEARCH_SPEAKER_INDEX, body=query)

        total_hits = response["hits"]["total"]["value"]
        if total_hits > size_limit:
            logger.warning(
                "Results truncated: %d hits but size limit is %d",
                total_hits,
                size_limit,
            )

        speakers = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            speakers.append(
                {
                    "speaker_id": source["speaker_id"],
                    "speaker_uuid": source.get("speaker_uuid"),
                    "profile_id": source.get("profile_id"),
                    "profile_uuid": source.get("profile_uuid"),
                    "name": source["name"],
                    "media_file_id": source.get("media_file_id"),
                    "segment_count": source.get("segment_count", 1),
                    "created_at": source.get("created_at"),
                }
            )

        return speakers

    except Exception as e:
        logger.error(f"Error getting speakers in collection: {e}")
        return []


def merge_speaker_embeddings(
    source_speaker_uuid: str, target_speaker_uuid: str, new_collection_ids: list[int]
):
    """
    Merge two speaker embeddings (used when combining speakers)

    Args:
        source_speaker_uuid: UUID of speaker to merge from
        target_speaker_uuid: UUID of speaker to merge into
        new_collection_ids: Updated collection IDs for the target
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return

    try:
        # Delete the source speaker document from main index
        opensearch_client.delete(
            index=settings.OPENSEARCH_SPEAKER_INDEX, id=str(source_speaker_uuid)
        )

        # Also remove source from v4 staging index if it exists (mid-migration cleanup)
        import contextlib as _ctx

        v4_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4"
        with _ctx.suppress(Exception):
            if opensearch_client.indices.exists(index=v4_index):
                opensearch_client.delete(index=v4_index, id=str(source_speaker_uuid))

        # Update the target speaker's collections using UUID
        update_body = {
            "doc": {
                "collection_ids": new_collection_ids,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        }

        response = opensearch_client.update(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            id=str(target_speaker_uuid),
            body=update_body,
        )

        logger.info(f"Merged speaker {source_speaker_uuid} into {target_speaker_uuid}")
        return response

    except Exception as e:
        logger.error(f"Error merging speaker embeddings: {e}")


def cleanup_orphaned_embeddings(user_id: int) -> dict:
    """Count potentially orphaned speaker embeddings.

    NOTE: This is a diagnostic stub. Actual cleanup requires database
    validation and is not yet implemented. Use
    ``cleanup_orphaned_speaker_embeddings()`` for real orphan removal.

    Args:
        user_id: User ID to inspect.

    Returns:
        Dict with embedding_count and diagnostic status.
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return {"embedding_count": 0, "status": "diagnostic_only"}

    try:
        # Ensure indices exist before searching
        ensure_indices_exist()

        # Find all embeddings for user
        query = {
            "query": {"term": {"user_id": user_id}},
            "size": 1000,
            "_source": ["speaker_id", "profile_id"],
        }

        response = opensearch_client.search(index=settings.OPENSEARCH_SPEAKER_INDEX, body=query)

        count = len(response["hits"]["hits"])
        logger.info(
            f"Found {count} embeddings for user {user_id} (diagnostic only, no cleanup performed)"
        )

        return {"embedding_count": count, "status": "diagnostic_only"}

    except Exception as e:
        logger.error(f"Error counting orphaned embeddings: {e}")
        return {"embedding_count": 0, "status": "diagnostic_only"}


def get_speaker_document(speaker_uuid: str) -> dict[str, Any] | None:
    """
    Get full speaker document (embedding + segment_count) from OpenSearch.

    Args:
        speaker_uuid: UUID of the speaker

    Returns:
        Dict with 'embedding' and 'segment_count' keys, or None if not found
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return None

    try:
        ensure_indices_exist()

        response = opensearch_client.get(
            index=settings.OPENSEARCH_SPEAKER_INDEX, id=str(speaker_uuid)
        )

        if response and "_source" in response:
            source = response["_source"]
            embedding = source.get("embedding")
            if embedding is not None:
                return {
                    "embedding": list(embedding),
                    "segment_count": int(source.get("segment_count", 1)),
                }
            return None

        return None

    except Exception as e:
        logger.error(f"Error getting speaker document for {speaker_uuid}: {e}")
        return None


def get_speaker_embedding(speaker_uuid: str) -> list[float] | None:
    """Get the embedding vector for a speaker from the active index.

    Queries only the active speaker index (v3 or v4, whichever holds the
    bulk of embeddings).  No cross-index fallback — this guarantees all
    returned embeddings have the same dimensionality.

    Args:
        speaker_uuid: UUID of the speaker

    Returns:
        Embedding vector or None if not found
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return None

    try:
        ensure_indices_exist()

        active_index = get_active_speaker_index()
        response = opensearch_client.get(index=active_index, id=str(speaker_uuid))

        if response and "_source" in response:
            embedding = response["_source"].get("embedding")
            if embedding is not None:
                return list(embedding)

        return None

    except Exception as e:
        if _is_index_corruption_error(e):
            logger.warning(
                f"Index corruption detected getting speaker {speaker_uuid}, attempting repair..."
            )
            active_index = get_active_speaker_index()
            if _repair_index(active_index):
                try:
                    response = opensearch_client.get(index=active_index, id=str(speaker_uuid))
                    if response and "_source" in response:
                        embedding = response["_source"].get("embedding")
                        if embedding is not None:
                            return list(embedding)
                except Exception as retry_err:
                    logger.error(
                        f"Retry after repair failed for speaker {speaker_uuid}: {retry_err}"
                    )
            return None
        # NotFoundError is expected for speakers not in active index
        if "NotFoundError" not in type(e).__name__:
            logger.error(f"Error getting speaker embedding: {e}")
        return None


def get_speaker_embeddings_batch(speaker_uuids: list[str]) -> dict[str, list[float]]:
    """Get embeddings for multiple speakers in a single mget request.

    Args:
        speaker_uuids: List of speaker UUIDs

    Returns:
        Dict mapping speaker_uuid -> embedding vector (only for found speakers)
    """
    if not opensearch_client or not speaker_uuids:
        return {}

    try:
        ensure_indices_exist()
        active_index = get_active_speaker_index()

        body = {"docs": [{"_index": active_index, "_id": str(uid)} for uid in speaker_uuids]}
        response = opensearch_client.mget(body=body)

        results: dict[str, list[float]] = {}
        for doc in response.get("docs", []):
            if doc.get("found") and "_source" in doc:
                embedding = doc["_source"].get("embedding")
                if embedding is not None:
                    results[doc["_id"]] = list(embedding)
        return results

    except Exception as e:
        logger.error(f"Error batch-fetching speaker embeddings: {e}")
        return {}


def get_profile_embedding(profile_uuid: str) -> list[float] | None:
    """
    Get the embedding vector for a speaker profile from OpenSearch

    Args:
        profile_uuid: UUID of the speaker profile

    Returns:
        Embedding vector or None if not found
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return None

    try:
        # Ensure indices exist before searching
        ensure_indices_exist()

        # Use UUID-based document ID for profiles
        response = opensearch_client.get(
            index=settings.OPENSEARCH_SPEAKER_INDEX, id=f"profile_{profile_uuid}"
        )

        if response and "_source" in response:
            embedding = response["_source"].get("embedding")
            if embedding is not None:
                return list(embedding)  # Explicit conversion to list[float]
            return None

        return None

    except Exception as e:
        logger.error(f"Error getting profile embedding: {e}")
        return None


def store_profile_embedding(
    profile_id: int,
    profile_uuid: str,
    profile_name: str,
    embedding: list[float],
    speaker_count: int,
    user_id: int,
) -> bool:
    """
    Store profile embedding with distinct document type for proper filtering.

    Args:
        profile_id: ID of the speaker profile (for internal queries)
        profile_uuid: UUID of the speaker profile (used as document ID)
        profile_name: Name of the speaker profile
        embedding: Embedding vector
        speaker_count: Number of speakers contributing to this embedding
        user_id: ID of the user who owns the profile

    Returns:
        True if successful, False otherwise
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return False

    try:
        ensure_indices_exist()

        doc = {
            "document_type": "profile",  # CRITICAL: Distinguish from speakers
            "profile_id": profile_id,
            "profile_uuid": str(profile_uuid),
            "profile_name": profile_name,
            "user_id": user_id,
            "embedding": embedding,
            "speaker_count": speaker_count,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        # Use UUID-based prefixed ID to avoid conflicts with speaker documents
        # Use refresh='wait_for' to ensure the update is immediately searchable
        # This prevents race conditions where voice_suggestions show stale profile names
        opensearch_client.index(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            body=doc,
            id=f"profile_{profile_uuid}",
            refresh="wait_for",
        )

        logger.info(
            f"Stored profile {profile_uuid} ({profile_name}) embedding in OpenSearch with {speaker_count} speakers"
        )
        return True

    except Exception as e:
        logger.error(f"Error storing profile embedding: {e}")
        return False


def update_profile_embedding(
    profile_id: int, profile_uuid: str, embedding: list[float], embedding_count: int
) -> bool:
    """
    Update or create a profile embedding in OpenSearch

    Args:
        profile_id: ID of the speaker profile (for internal queries)
        profile_uuid: UUID of the speaker profile (used as document ID)
        embedding: Embedding vector
        embedding_count: Number of speakers contributing to this embedding

    Returns:
        True if successful, False otherwise
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return False

    try:
        ensure_indices_exist()

        doc = {
            "document_type": "profile",  # CRITICAL: Distinguish from speakers
            "profile_id": profile_id,
            "profile_uuid": str(profile_uuid),
            "embedding": embedding,
            "embedding_count": embedding_count,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        # Use UUID-based prefixed ID
        # Use refresh='wait_for' to ensure the update is immediately searchable
        opensearch_client.index(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            id=f"profile_{profile_uuid}",
            body=doc,
            refresh="wait_for",
        )

        logger.info(f"Updated profile {profile_uuid} embedding in OpenSearch")
        return True

    except Exception as e:
        logger.error(f"Error updating profile embedding: {e}")
        return False


def remove_profile_embedding(profile_uuid: str) -> bool:
    """Remove a profile embedding from all speaker indices (main + v4 staging).

    Profiles are stored with doc ID ``profile_{uuid}`` in both the main index
    and the v4 staging index. Both are cleaned here.

    Args:
        profile_uuid: UUID of the speaker profile

    Returns:
        True if the main index deletion succeeded, False otherwise
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return False

    doc_id = f"profile_{profile_uuid}"
    success = False
    try:
        opensearch_client.delete(index=settings.OPENSEARCH_SPEAKER_INDEX, id=doc_id)
        logger.info(f"Removed profile {profile_uuid} embedding from main index")
        success = True
    except Exception as e:
        logger.warning(f"Error removing profile embedding from main index (may not exist): {e}")

    # Also clean v4 staging index if it exists
    try:
        v4_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4"
        if opensearch_client.indices.exists(index=v4_index):
            opensearch_client.delete(index=v4_index, id=doc_id)
            logger.debug(f"Removed profile {profile_uuid} from v4 staging index")
    except Exception:  # nosec B110
        pass  # Non-fatal

    return success


def store_cluster_embedding(
    cluster_uuid: str,
    user_id: int,
    embedding: list[float],
    label: str | None = None,
    refresh: str | bool = "wait_for",
) -> bool:
    """Store a cluster centroid embedding in OpenSearch.

    Args:
        cluster_uuid: UUID of the speaker cluster.
        user_id: Owner user ID.
        embedding: L2-normalized centroid embedding vector.
        label: Optional cluster label.
        refresh: Index refresh policy. Use ``False`` during batch operations
            and issue a single ``indices.refresh()`` at the end.

    Returns:
        True if successful, False otherwise.
    """
    global _indices_verified

    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return False

    try:
        if not _indices_verified:
            ensure_indices_exist()
            _indices_verified = True
        active_index = get_active_speaker_index()

        doc = {
            "document_type": "cluster",
            "cluster_uuid": str(cluster_uuid),
            "user_id": user_id,
            "embedding": embedding,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        if label:
            doc["label"] = label

        opensearch_client.index(
            index=active_index,
            body=doc,
            id=f"cluster_{cluster_uuid}",
            refresh=refresh,
        )

        logger.info(f"Stored cluster {cluster_uuid} centroid in OpenSearch")
        return True

    except Exception as e:
        logger.error(f"Error storing cluster embedding: {e}")
        return False


def delete_cluster_embedding(cluster_uuid: str) -> bool:
    """Delete a cluster centroid from OpenSearch.

    Args:
        cluster_uuid: UUID of the speaker cluster.

    Returns:
        True if successful, False otherwise.
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return False

    try:
        active_index = get_active_speaker_index()
        opensearch_client.delete(
            index=active_index,
            id=f"cluster_{cluster_uuid}",
        )
        logger.info(f"Removed cluster {cluster_uuid} embedding from OpenSearch")
        return True

    except Exception as e:
        logger.warning(f"Error removing cluster embedding (may not exist): {e}")
        return False


def find_matching_clusters(
    embedding: list[float],
    user_id: int,
    k: int = 5,
    threshold: float = 0.75,
) -> list[dict]:
    """Find matching cluster centroids for a speaker embedding using kNN.

    Args:
        embedding: L2-normalized speaker embedding vector.
        user_id: Owner user ID.
        k: Number of nearest neighbors.
        threshold: Minimum cosine similarity.

    Returns:
        List of dicts with cluster_uuid, similarity, label.
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return []

    try:
        active_index = get_active_speaker_index()
        query = {
            "size": k,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": embedding,
                        "k": k,
                        "filter": {
                            "bool": {
                                "filter": [
                                    {"term": {"document_type": "cluster"}},
                                    {"term": {"user_id": user_id}},
                                ]
                            }
                        },
                    }
                }
            },
        }

        response = opensearch_client.search(index=active_index, body=query)

        matches = []
        for hit in response["hits"]["hits"]:
            score = hit["_score"]
            # OpenSearch Lucene engine with cosinesimil space returns:
            #   score = (1 + cosine_similarity) / 2
            # Convert back to raw cosine similarity for threshold comparison.
            cosine_sim = 2.0 * score - 1.0
            if cosine_sim < threshold:
                continue
            source = hit["_source"]
            matches.append(
                {
                    "cluster_uuid": source.get("cluster_uuid"),
                    "similarity": float(cosine_sim),
                    "label": source.get("label"),
                }
            )

        return matches

    except Exception as e:
        logger.error(f"Error finding matching clusters: {e}")
        return []


def msearch_speaker_similarities(
    speaker_data: list[dict],
    user_id: int,
    k: int = 10,
    batch_size: int = 50,
) -> list[list[dict]]:
    """Batch kNN search for building a similarity graph.

    Args:
        speaker_data: List of dicts with speaker_uuid and embedding.
        user_id: Owner user ID.
        k: Number of nearest neighbors per query.
        batch_size: Number of speakers per msearch request.

    Returns:
        List of result lists, one per input embedding.
    """
    if not opensearch_client or not speaker_data:
        return [[] for _ in speaker_data]

    try:
        import json

        active_index = get_active_speaker_index()
        all_results: list[list[dict]] = []

        # Process in batches to avoid memory issues
        for batch_start in range(0, len(speaker_data), batch_size):
            batch = speaker_data[batch_start : batch_start + batch_size]

            # Build msearch body for this batch
            body_parts: list[str] = []
            for sd in batch:
                header = {"index": active_index}
                query = {
                    "size": k,
                    "query": {
                        "knn": {
                            "embedding": {
                                "vector": sd["embedding"],
                                "k": k,
                                "filter": {
                                    "bool": {
                                        "filter": [
                                            {"term": {"user_id": user_id}},
                                            {
                                                "bool": {
                                                    "must_not": [
                                                        {"exists": {"field": "document_type"}},
                                                    ]
                                                }
                                            },
                                        ]
                                    }
                                },
                            }
                        }
                    },
                }
                body_parts.append(json.dumps(header))
                body_parts.append(json.dumps(query))

            msearch_body = "\n".join(body_parts) + "\n"
            response = opensearch_client.msearch(body=msearch_body)

            for resp in response.get("responses", []):
                hits: list[dict] = []
                for hit in resp.get("hits", {}).get("hits", []):
                    source = hit.get("_source", {})
                    hits.append(
                        {
                            "speaker_uuid": source.get("speaker_uuid"),
                            "similarity": float(hit["_score"]),
                            "speaker_id": source.get("speaker_id"),
                        }
                    )
                all_results.append(hits)

        return all_results

    except Exception as e:
        logger.error(f"Error in msearch speaker similarities: {e}")
        return [[] for _ in speaker_data]


def iter_speaker_embeddings(
    user_id: int,
    speaker_uuids: list[str] | None = None,
    batch_size: int = 200,
) -> Generator[list[dict[str, Any]], None, None]:
    """Yield batches of speaker embeddings from the active index.

    If *speaker_uuids* is provided, only those speakers are fetched (via
    mget).  Otherwise all non-cluster speaker docs for *user_id* are
    scrolled.  Embeddings are never accumulated — each batch is yielded
    and can be discarded by the caller.

    Yields:
        Lists of dicts with keys: speaker_uuid, embedding, speaker_id,
        profile_id, display_name.
    """
    if not opensearch_client:
        return

    active_index = get_active_speaker_index()

    if speaker_uuids is not None:
        # Fetch specific speakers via mget in batches
        for i in range(0, len(speaker_uuids), batch_size):
            chunk = speaker_uuids[i : i + batch_size]
            try:
                response = opensearch_client.mget(
                    index=active_index,
                    body={"ids": chunk},
                )
                batch: list[dict[str, Any]] = []
                for doc in response.get("docs", []):
                    if doc.get("found") and "_source" in doc:
                        source = doc["_source"]
                        if "embedding" in source and "speaker_uuid" in source:
                            batch.append(
                                {
                                    "speaker_uuid": source["speaker_uuid"],
                                    "embedding": source["embedding"],
                                    "speaker_id": source.get("speaker_id"),
                                    "profile_id": source.get("profile_id"),
                                    "display_name": source.get("display_name"),
                                }
                            )
                if batch:
                    yield batch
            except Exception as e:
                logger.warning("mget batch failed: %s", e)
                continue
    else:
        # Scroll all speakers for user
        search_after = None
        while True:
            query: dict = {
                "size": batch_size,
                "query": {
                    "bool": {
                        "filter": [{"term": {"user_id": user_id}}],
                        "must_not": [{"exists": {"field": "document_type"}}],
                    }
                },
                "sort": [{"_id": "asc"}],
                "_source": [
                    "speaker_uuid",
                    "embedding",
                    "speaker_id",
                    "profile_id",
                    "display_name",
                ],
            }
            if search_after is not None:
                query["search_after"] = search_after

            try:
                response = opensearch_client.search(index=active_index, body=query)
            except Exception as e:
                logger.error("Scroll failed: %s", e)
                break

            hits = response["hits"]["hits"]
            if not hits:
                break

            batch = []
            for hit in hits:
                source = hit["_source"]
                if "embedding" in source and "speaker_uuid" in source:
                    batch.append(
                        {
                            "speaker_uuid": source["speaker_uuid"],
                            "embedding": source["embedding"],
                            "speaker_id": source.get("speaker_id"),
                            "profile_id": source.get("profile_id"),
                            "display_name": source.get("display_name"),
                        }
                    )
            if batch:
                yield batch

            search_after = hits[-1]["sort"]
            if len(hits) < batch_size:
                break


def get_all_speaker_embeddings(
    user_id: int,
    page_size: int = 500,
) -> list[dict]:
    """Fetch all speaker embeddings for a user from OpenSearch.

    Uses search_after pagination to handle arbitrarily large result sets
    instead of a hard limit.

    Args:
        user_id: Owner user ID.
        page_size: Number of documents per page (scroll batch size).

    Returns:
        List of dicts with speaker_uuid and embedding.
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return []

    try:
        active_index = get_active_speaker_index()
        results: list[dict] = []
        search_after = None

        while True:
            query: dict = {
                "size": page_size,
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"user_id": user_id}},
                        ],
                        "must_not": [
                            {"exists": {"field": "document_type"}},
                        ],
                    }
                },
                "sort": [{"_id": "asc"}],
                "_source": [
                    "speaker_uuid",
                    "embedding",
                    "speaker_id",
                    "profile_id",
                    "display_name",
                ],
            }

            if search_after is not None:
                query["search_after"] = search_after

            response = opensearch_client.search(index=active_index, body=query)

            hits = response["hits"]["hits"]
            if not hits:
                break

            for hit in hits:
                source = hit["_source"]
                if "embedding" in source and "speaker_uuid" in source:
                    results.append(
                        {
                            "speaker_uuid": source["speaker_uuid"],
                            "embedding": source["embedding"],
                            "speaker_id": source.get("speaker_id"),
                            "profile_id": source.get("profile_id"),
                            "display_name": source.get("display_name"),
                        }
                    )

            # Use the sort value of the last hit for search_after
            search_after = hits[-1]["sort"]

            # If we got fewer results than page_size, we're done
            if len(hits) < page_size:
                break

        logger.info(
            f"Fetched {len(results)} speaker embeddings for user {user_id} "
            f"from index '{active_index}'"
        )
        return results

    except Exception as e:
        logger.error(f"Error fetching speaker embeddings: {e}")
        return []


def remove_speaker_embedding(speaker_uuid: str) -> bool:
    """Remove a speaker embedding from all speaker indices (main + v4 staging).

    Cleans both the main speaker index (V3 or post-finalization V4) and the
    v4 staging index if it exists. This prevents orphaned entries when speakers
    are deleted or merged.

    Args:
        speaker_uuid: UUID of the speaker

    Returns:
        True if the main index deletion succeeded, False otherwise
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return False

    success = False
    try:
        opensearch_client.delete(index=settings.OPENSEARCH_SPEAKER_INDEX, id=str(speaker_uuid))
        logger.info(f"Removed speaker {speaker_uuid} from main speaker index")
        success = True
    except Exception as e:
        logger.warning(f"Error removing speaker embedding from main index (may not exist): {e}")

    # Also clean the v4 staging index if it exists (mid-migration cleanup)
    try:
        v4_index = f"{settings.OPENSEARCH_SPEAKER_INDEX}_v4"
        if opensearch_client.indices.exists(index=v4_index):
            opensearch_client.delete(index=v4_index, id=str(speaker_uuid))
            logger.debug(f"Removed speaker {speaker_uuid} from v4 staging index")
    except Exception:  # nosec B110
        pass  # Non-fatal: v4 may not have this speaker yet

    return success


def update_speaker_segment_count(speaker_uuid: str, segment_count: int) -> bool:
    """
    Update only the segment_count of a speaker in OpenSearch.

    Args:
        speaker_uuid: UUID of the speaker
        segment_count: New segment count value

    Returns:
        True if successful, False otherwise
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return False

    try:
        update_body = {
            "doc": {
                "segment_count": segment_count,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        }

        opensearch_client.update(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            id=str(speaker_uuid),
            body=update_body,
        )

        logger.info(f"Updated segment_count for speaker {speaker_uuid} to {segment_count}")
        return True

    except Exception as e:
        logger.warning(f"Error updating speaker segment count: {e}")
        return False


def update_speaker_display_name(speaker_uuid: str, display_name: str | None):
    """
    Update the display name of a speaker in OpenSearch

    Args:
        speaker_uuid: UUID of the speaker
        display_name: New display name (or None to clear)
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return

    try:
        # Update the speaker document with new display name using UUID
        update_body = {
            "doc": {
                "display_name": display_name,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        }

        response = opensearch_client.update(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            id=str(speaker_uuid),
            body=update_body,
            refresh="wait_for",
        )

        logger.info(f"Updated display name for speaker {speaker_uuid} to '{display_name}'")
        return response

    except Exception as e:
        logger.error(f"Error updating speaker display name: {e}")


def update_speaker_profile(
    speaker_uuid: str,
    profile_id: int | None,
    profile_uuid: str | None,
    verified: bool = False,
):
    """
    Update the profile assignment of a speaker in OpenSearch

    Args:
        speaker_uuid: UUID of the speaker
        profile_id: Profile ID to assign (or None to clear, for internal queries)
        profile_uuid: Profile UUID to assign (or None to clear)
        verified: Whether the speaker is verified
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return

    try:
        # Update the speaker document with new profile assignment using UUID
        update_body = {
            "doc": {
                "profile_id": profile_id,
                "profile_uuid": str(profile_uuid) if profile_uuid else None,
                "verified": verified,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        }

        response = opensearch_client.update(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            id=str(speaker_uuid),
            body=update_body,
        )

        logger.info(
            f"Updated profile assignment for speaker {speaker_uuid} to profile {profile_uuid}, verified={verified}"
        )
        return response

    except Exception as e:
        logger.error(f"Error updating speaker profile assignment: {e}")


def find_matching_profiles(
    embedding: list[float], user_id: int, threshold: float = 0.7, size: int = 5
) -> list[dict[str, Any]]:
    """
    Find matching speaker profiles using embedding similarity in OpenSearch.

    Args:
        embedding: Query embedding vector
        user_id: User ID to filter results
        threshold: Minimum similarity threshold
        size: Maximum number of results

    Returns:
        List of matching profiles with similarity scores
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return []

    try:
        # Ensure indices exist before searching
        ensure_indices_exist()

        # KNN search query for profile embeddings
        query = {
            "size": size,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": embedding,
                        "k": size,
                        "filter": {
                            "bool": {
                                "must": [
                                    {"term": {"user_id": user_id}},
                                    {"term": {"document_type": "profile"}},
                                ]
                            }
                        },
                    }
                }
            },
            "_source": ["profile_id", "profile_name", "embedding_count", "updated_at"],
        }

        response = opensearch_client.search(index=settings.OPENSEARCH_SPEAKER_INDEX, body=query)

        matches = []
        for hit in response["hits"]["hits"]:
            score = hit["_score"]
            if score >= threshold:
                source = hit["_source"]
                matches.append(
                    {
                        "profile_id": source["profile_id"],
                        "profile_name": source["profile_name"],
                        "similarity": score,
                        "embedding_count": source["embedding_count"],
                        "last_update": source.get("updated_at"),
                    }
                )

        logger.info(f"Found {len(matches)} profile matches above threshold {threshold}")
        return matches

    except Exception as e:
        logger.error(f"Error finding matching profiles: {e}")
        return []


def update_cluster_embedding(
    cluster_uuid: str,
    embedding: list[float],
    label: str | None = None,
) -> bool:
    """Update an existing cluster centroid embedding in OpenSearch.

    Re-indexes the full document (same as store) so that the embedding vector
    is replaced atomically.

    Args:
        cluster_uuid: UUID of the cluster.
        embedding: Updated centroid embedding vector.
        label: Optional updated label for the cluster.

    Returns:
        True if successful, False otherwise.
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return False

    try:
        ensure_indices_exist()
        active_index = get_active_speaker_index()

        # Fetch existing document to preserve user_id
        doc_id = f"cluster_{cluster_uuid}"
        try:
            existing = opensearch_client.get(index=active_index, id=doc_id)
            user_id = existing["_source"].get("user_id")
            existing_label = existing["_source"].get("label")
        except Exception:
            logger.error(f"Cannot update cluster {cluster_uuid}: document not found")
            return False

        doc = {
            "document_type": "cluster",
            "cluster_uuid": str(cluster_uuid),
            "user_id": user_id,
            "embedding": embedding,
            "label": label if label is not None else existing_label,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        opensearch_client.index(
            index=active_index,
            body=doc,
            id=doc_id,
            refresh="wait_for",
        )

        logger.info(f"Updated cluster {cluster_uuid} embedding in OpenSearch")
        return True

    except Exception as e:
        logger.error(f"Error updating cluster embedding for {cluster_uuid}: {e}")
        return False


def cleanup_orphaned_speaker_embeddings(user_id: int) -> int:
    """
    Remove speaker embeddings from OpenSearch for MediaFiles that no longer exist in PostgreSQL.

    Args:
        user_id: ID of the user to clean up orphaned documents for

    Returns:
        Number of orphaned documents removed
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return 0

    try:
        from app.db.session_utils import session_scope
        from app.models.media import MediaFile

        with session_scope() as db:
            # Get all existing MediaFile IDs for this user
            existing_media_file_ids = set(
                row[0] for row in db.query(MediaFile.id).filter(MediaFile.user_id == user_id).all()
            )
            logger.info(
                f"Found {len(existing_media_file_ids)} existing MediaFiles for user {user_id}: {existing_media_file_ids}"
            )

        # Query OpenSearch for all speaker documents for this user
        query = {
            "size": 1000,  # Adjust if needed
            "query": {
                "bool": {
                    "must": [
                        {"term": {"user_id": user_id}},
                        {
                            "bool": {"must_not": {"exists": {"field": "document_type"}}}
                        },  # Only speaker docs, not profiles
                    ]
                }
            },
            "_source": ["speaker_id", "speaker_uuid", "media_file_id"],
        }

        response = opensearch_client.search(index=settings.OPENSEARCH_SPEAKER_INDEX, body=query)

        orphaned_speaker_uuids = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            media_file_id = source.get("media_file_id")
            speaker_id = source.get("speaker_id")
            speaker_uuid = source.get("speaker_uuid")

            if media_file_id and media_file_id not in existing_media_file_ids:
                orphaned_speaker_uuids.append(speaker_uuid)
                logger.info(
                    f"Found orphaned speaker {speaker_uuid} (ID: {speaker_id}) referencing non-existent MediaFile {media_file_id}"
                )

        # Delete orphaned documents using UUIDs
        deleted_count = 0
        for speaker_uuid in orphaned_speaker_uuids:
            try:
                opensearch_client.delete(
                    index=settings.OPENSEARCH_SPEAKER_INDEX, id=str(speaker_uuid)
                )
                logger.info(f"Deleted orphaned speaker document for speaker {speaker_uuid}")
                deleted_count += 1
            except Exception as e:
                logger.error(f"Error deleting orphaned speaker {speaker_uuid}: {e}")

        logger.info(
            f"Cleanup completed: removed {deleted_count} orphaned speaker documents for user {user_id}"
        )
        return deleted_count

    except Exception as e:
        logger.error(f"Error during orphaned speaker cleanup: {e}")
        return 0
