import datetime
import logging
import os
from typing import Any
from typing import Optional

from opensearchpy import OpenSearch
from opensearchpy import RequestsHttpConnection

from app.core.config import settings
from app.core.constants import PYANNOTE_EMBEDDING_DIMENSION
from app.core.constants import SENTENCE_TRANSFORMER_DIMENSION

# Setup logging
logger = logging.getLogger(__name__)

# Initialize the OpenSearch client
try:
    opensearch_client = OpenSearch(
        hosts=[{"host": settings.OPENSEARCH_HOST, "port": int(settings.OPENSEARCH_PORT)}],
        http_auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
        use_ssl=False,
        verify_certs=settings.OPENSEARCH_VERIFY_CERTS,
        connection_class=RequestsHttpConnection,
    )
    logger.info("OpenSearch client initialized successfully")
except (ConnectionError, ValueError) as e:
    logger.error(f"Configuration error initializing OpenSearch client: {e}")
    opensearch_client = None
except Exception as e:
    logger.error(f"Unexpected error initializing OpenSearch client: {e}")
    opensearch_client = None


def ensure_indices_exist():
    """
    Ensure the transcript and speaker indices exist, creating them if necessary
    """
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
                        "knn.algo_param.ef_search": 100,
                        "knn.algo_param.ef_construction": 200,
                        "knn.algo_param.m": 16,
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
                            "dimension": PYANNOTE_EMBEDDING_DIMENSION,
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


def index_transcript(
    file_id: int,
    file_uuid: str,
    user_id: int,
    transcript_text: str,
    speakers: list[str],
    title: str,
    tags: list[str] = None,
    embedding: list[float] = None,
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
            "upload_time": datetime.datetime.now().isoformat(),  # ISO-8601 format
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
    profile_id: Optional[int] = None,
    profile_uuid: Optional[str] = None,
    collection_ids: Optional[list[int]] = None,
    media_file_id: Optional[int] = None,
    segment_count: int = 1,
    display_name: Optional[str] = None,
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
            "created_at": datetime.datetime.now().isoformat(),
            "updated_at": datetime.datetime.now().isoformat(),
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
            bulk_body.append(
                {
                    "speaker_id": data["speaker_id"],
                    "speaker_uuid": str(data["speaker_uuid"]),
                    "profile_id": data.get("profile_id"),
                    "profile_uuid": str(data.get("profile_uuid"))
                    if data.get("profile_uuid")
                    else None,
                    "user_id": data["user_id"],
                    "name": data["name"],
                    "collection_ids": data.get("collection_ids", []),
                    "media_file_id": data.get("media_file_id"),
                    "segment_count": data.get("segment_count", 1),
                    "created_at": datetime.datetime.now().isoformat(),
                    "updated_at": datetime.datetime.now().isoformat(),
                    "embedding": data["embedding"],
                }
            )

        # Execute bulk operation
        response = opensearch_client.bulk(body=bulk_body)

        if response["errors"]:
            logger.error(f"Bulk indexing had errors: {response}")
        else:
            logger.info(f"Successfully bulk indexed {len(embeddings_data)} speaker embeddings")

        return response

    except Exception as e:
        logger.error(f"Error bulk indexing speaker embeddings: {e}")


def search_transcripts(
    query: str,
    user_id: int,
    speaker: Optional[str] = None,
    tags: Optional[list[str]] = None,
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
    # Return mock data in test environment
    if os.environ.get("SKIP_OPENSEARCH") or not opensearch_client:
        logger.warning(
            "OpenSearch client not initialized or in test environment, returning mock data"
        )
        # Return mock search results for testing
        return [
            {
                "file_id": 1,
                "title": "Test Recording",
                "speakers": ["Speaker 1", "Speaker 2"],
                "upload_time": "2025-05-05T10:00:00",
                "snippet": "This is a mock search result for testing purposes...",
            }
        ]

    try:
        # Build the search query
        must_conditions = [
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
                from sentence_transformers import SentenceTransformer

                # Check if model exists locally or download it
                model_path = os.path.join(settings.MODELS_DIRECTORY, "sentence-transformers")
                os.makedirs(model_path, exist_ok=True)

                # Load the model (will download if not present)
                embedding_model = SentenceTransformer("all-MiniLM-L6-v2", cache_folder=model_path)

                # Generate embedding for the query
                query_embedding = embedding_model.encode(query).tolist()
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
            knn_query = {"knn": {"embedding": {"vector": query_embedding, "k": limit}}}

            # Combine text search with vector search
            search_body["query"]["bool"]["should"] = [knn_query]

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
    collection_ids: Optional[list[int]] = None,
    exclude_speaker_ids: Optional[list[int]] = None,
) -> Optional[dict[str, Any]]:
    """
    Find a matching speaker for a given embedding with confidence score

    Args:
        embedding: Speaker embedding vector
        user_id: ID of the user
        threshold: Minimum similarity threshold (0-1) for matching
        collection_ids: Optional list of collection IDs to search within
        exclude_speaker_ids: Optional list of speaker IDs to exclude

    Returns:
        Dictionary with speaker info and confidence if a match is found, None otherwise
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized, skipping speaker matching")
        return None

    try:
        # Ensure indices exist before searching
        ensure_indices_exist()

        # Build filter conditions
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
        msearch_body = []

        for emb_data in embeddings:
            # Add search header
            msearch_body.append({"index": settings.OPENSEARCH_SPEAKER_INDEX})

            # Add search query with self-exclusion
            msearch_body.append(
                {
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
            )

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
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"user_id": user_id}},
                        {"term": {"speakers": speaker_name}},
                    ]
                }
            },
            "size": 100,  # Get up to 100 media files
            "_source": ["file_id", "file_uuid", "title", "upload_time"],
        }

        response = opensearch_client.search(index=settings.OPENSEARCH_TRANSCRIPT_INDEX, body=query)

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
                "updated_at": datetime.datetime.now().isoformat(),
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
                "updated_at": datetime.datetime.now().isoformat(),
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
        bulk_body = []
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
            bulk_body.append(
                {
                    "doc": {
                        "profile_id": update.get("profile_id"),
                        "profile_uuid": str(update.get("profile_uuid"))
                        if update.get("profile_uuid")
                        else None,
                        "collection_ids": update.get("collection_ids", []),
                        "updated_at": datetime.datetime.now().isoformat(),
                    }
                }
            )

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

        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"user_id": user_id}},
                        {"term": {"collection_ids": collection_id}},
                    ]
                }
            },
            "size": 1000,  # Adjust based on expected collection size
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
        # Delete the source speaker document using UUID
        opensearch_client.delete(
            index=settings.OPENSEARCH_SPEAKER_INDEX, id=str(source_speaker_uuid)
        )

        # Update the target speaker's collections using UUID
        update_body = {
            "doc": {
                "collection_ids": new_collection_ids,
                "updated_at": datetime.datetime.now().isoformat(),
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


def cleanup_orphaned_embeddings(user_id: int) -> int:
    """
    Clean up embeddings that are no longer associated with valid speakers

    Args:
        user_id: User ID to clean up for

    Returns:
        Number of cleaned up embeddings
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return 0

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

        # This function would need to be called with database context
        # to verify which speakers still exist
        logger.info(f"Found {len(response['hits']['hits'])} embeddings for user {user_id}")

        # Return count for now - actual cleanup would require database validation
        return len(response["hits"]["hits"])

    except Exception as e:
        logger.error(f"Error cleaning up orphaned embeddings: {e}")
        return 0


def get_speaker_embedding(speaker_uuid: str) -> Optional[list[float]]:
    """
    Get the embedding vector for a speaker from OpenSearch

    Args:
        speaker_uuid: UUID of the speaker

    Returns:
        Embedding vector or None if not found
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return None

    try:
        # Ensure indices exist before searching
        ensure_indices_exist()

        response = opensearch_client.get(
            index=settings.OPENSEARCH_SPEAKER_INDEX, id=str(speaker_uuid)
        )

        if response and "_source" in response:
            return response["_source"].get("embedding")

        return None

    except Exception as e:
        logger.error(f"Error getting speaker embedding: {e}")
        return None


def get_profile_embedding(profile_uuid: str) -> Optional[list[float]]:
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
            return response["_source"].get("embedding")

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
            "updated_at": datetime.datetime.now().isoformat(),
        }

        # Use UUID-based prefixed ID to avoid conflicts with speaker documents
        opensearch_client.index(
            index=settings.OPENSEARCH_SPEAKER_INDEX, body=doc, id=f"profile_{profile_uuid}"
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
            "updated_at": datetime.datetime.now().isoformat(),
        }

        # Use UUID-based prefixed ID
        opensearch_client.index(
            index=settings.OPENSEARCH_SPEAKER_INDEX, id=f"profile_{profile_uuid}", body=doc
        )

        logger.info(f"Updated profile {profile_uuid} embedding in OpenSearch")
        return True

    except Exception as e:
        logger.error(f"Error updating profile embedding: {e}")
        return False


def remove_profile_embedding(profile_uuid: str) -> bool:
    """
    Remove a profile embedding from OpenSearch

    Args:
        profile_uuid: UUID of the speaker profile

    Returns:
        True if successful, False otherwise
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return False

    try:
        # Use UUID-based prefixed ID
        opensearch_client.delete(
            index=settings.OPENSEARCH_SPEAKER_INDEX, id=f"profile_{profile_uuid}"
        )

        logger.info(f"Removed profile {profile_uuid} embedding from OpenSearch")
        return True

    except Exception as e:
        logger.warning(f"Error removing profile embedding (may not exist): {e}")
        return False


def update_speaker_display_name(speaker_uuid: str, display_name: Optional[str]):
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
                "updated_at": datetime.datetime.now().isoformat(),
            }
        }

        response = opensearch_client.update(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            id=str(speaker_uuid),
            body=update_body,
        )

        logger.info(f"Updated display name for speaker {speaker_uuid} to '{display_name}'")
        return response

    except Exception as e:
        logger.error(f"Error updating speaker display name: {e}")


def update_speaker_profile(
    speaker_uuid: str,
    profile_id: Optional[int],
    profile_uuid: Optional[str],
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
                "updated_at": datetime.datetime.now().isoformat(),
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
                        "filter": {"term": {"user_id": user_id}},
                    }
                }
            },
            "_source": ["profile_id", "profile_name", "embedding_count", "updated_at"],
        }

        response = opensearch_client.search(
            index=f"{settings.OPENSEARCH_SPEAKER_INDEX}_profiles", body=query
        )

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
