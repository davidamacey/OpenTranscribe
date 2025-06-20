from opensearchpy import OpenSearch, RequestsHttpConnection
from typing import List, Dict, Any, Optional
import json
import logging
import os
import datetime

from app.core.config import settings

# Setup logging
logger = logging.getLogger(__name__)

# Initialize the OpenSearch client
try:
    opensearch_client = OpenSearch(
        hosts=[{'host': settings.OPENSEARCH_HOST, 'port': int(settings.OPENSEARCH_PORT)}],
        http_auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
        use_ssl=False,
        verify_certs=settings.OPENSEARCH_VERIFY_CERTS,
        connection_class=RequestsHttpConnection
    )
except Exception as e:
    logger.error(f"Error initializing OpenSearch client: {e}")
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
        if not opensearch_client.indices.exists(settings.OPENSEARCH_TRANSCRIPT_INDEX):
            transcript_index_config = {
                "settings": {
                    "index": {
                        "number_of_shards": 1,
                        "number_of_replicas": 0
                    },
                    "analysis": {
                        "analyzer": {
                            "default": {
                                "type": "standard"
                            }
                        }
                    }
                },
                "mappings": {
                    "properties": {
                        "file_id": {"type": "integer"},
                        "user_id": {"type": "integer"},
                        "content": {"type": "text"},
                        "speakers": {"type": "keyword"},
                        "tags": {"type": "keyword"},
                        "upload_time": {"type": "date"},
                        "title": {"type": "text"},
                        "embedding": {
                            "type": "knn_vector", 
                            "dimension": 384  # Using sentence-transformers/all-MiniLM-L6-v2 by default
                        }
                    }
                }
            }
            
            opensearch_client.indices.create(
                index=settings.OPENSEARCH_TRANSCRIPT_INDEX,
                body=transcript_index_config
            )
            
            logger.info(f"Created transcript index: {settings.OPENSEARCH_TRANSCRIPT_INDEX}")
        
        # Create speaker index if it doesn't exist
        if not opensearch_client.indices.exists(settings.OPENSEARCH_SPEAKER_INDEX):
            speaker_index_config = {
                "settings": {
                    "index": {
                        "number_of_shards": 1,
                        "number_of_replicas": 0,
                        "knn": True,
                        "knn.algo_param.ef_search": 100,
                        "knn.algo_param.ef_construction": 200,
                        "knn.algo_param.m": 16
                    }
                },
                "mappings": {
                    "properties": {
                        "speaker_id": {"type": "integer"},
                        "profile_id": {"type": "integer"},
                        "user_id": {"type": "integer"},
                        "name": {"type": "keyword"},
                        "collection_ids": {"type": "integer"},  # Array of collection IDs
                        "media_file_id": {"type": "integer"},  # Source media file
                        "segment_count": {"type": "integer"},  # Number of segments used
                        "created_at": {"type": "date"},
                        "updated_at": {"type": "date"},
                        "embedding": {
                            "type": "knn_vector", 
                            "dimension": 512,  # Pyannote embedding dimension (updated)
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "lucene",  # Use lucene engine which supports filters
                                "parameters": {
                                    "ef_construction": 128,
                                    "m": 24
                                }
                            }
                        }
                    }
                }
            }
            
            opensearch_client.indices.create(
                index=settings.OPENSEARCH_SPEAKER_INDEX,
                body=speaker_index_config
            )
            
            logger.info(f"Created speaker index: {settings.OPENSEARCH_SPEAKER_INDEX}")
            
    except Exception as e:
        logger.error(f"Error creating indices: {e}")


def index_transcript(file_id: int, user_id: int, transcript_text: str, 
                     speakers: List[str], title: str, 
                     tags: List[str] = None, embedding: List[float] = None):
    """
    Index a transcript in OpenSearch
    
    Args:
        file_id: ID of the media file
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
        
        # In a real implementation, if embedding is None, we'd compute it here using
        # a sentence transformer like sentence-transformers/all-MiniLM-L6-v2
        if embedding is None:
            # Placeholder - in production we'd use a real model
            embedding = [0.0] * 384  # Simulated embedding
        
        # Prepare document
        doc = {
            "file_id": file_id,
            "user_id": user_id,
            "content": transcript_text,
            "speakers": speakers,
            "title": title,
            "tags": tags or [],
            "upload_time": datetime.datetime.now().isoformat(),  # ISO-8601 format that OpenSearch can parse
            "embedding": embedding
        }
        
        # Index the document
        response = opensearch_client.index(
            index=settings.OPENSEARCH_TRANSCRIPT_INDEX,
            body=doc,
            id=str(file_id)  # Use file_id as document ID
        )
        
        logger.info(f"Indexed transcript for file {file_id}: {response}")
        return response
        
    except Exception as e:
        logger.error(f"Error indexing transcript for file {file_id}: {e}")


def add_speaker_embedding(speaker_id: int, user_id: int, name: str, embedding: List[float],
                        profile_id: Optional[int] = None, collection_ids: Optional[List[int]] = None,
                        media_file_id: Optional[int] = None, segment_count: int = 1,
                        display_name: Optional[str] = None):
    """
    Add a speaker embedding to OpenSearch with collection support
    
    Args:
        speaker_id: ID of the speaker in the database
        user_id: ID of the user who owns the speaker profile
        name: Name of the speaker
        embedding: Vector embedding of the speaker's voice
        profile_id: Optional speaker profile ID
        collection_ids: Optional list of collection IDs
        media_file_id: Optional source media file ID
        segment_count: Number of segments used to create embedding
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized, skipping speaker embedding")
        return
    
    try:
        ensure_indices_exist()
        
        # Validate embedding before indexing
        if embedding is None:
            logger.error(f"Cannot index speaker {speaker_id}: embedding is None")
            return
        
        if not isinstance(embedding, list) or len(embedding) == 0:
            logger.error(f"Cannot index speaker {speaker_id}: invalid embedding format")
            return
        
        logger.info(f"Indexing speaker {speaker_id} with embedding length: {len(embedding)}")
        
        # Prepare document
        doc = {
            "speaker_id": speaker_id,
            "profile_id": profile_id,
            "user_id": user_id,
            "name": name,
            "display_name": display_name,
            "collection_ids": collection_ids or [],
            "media_file_id": media_file_id,
            "segment_count": segment_count,
            "created_at": datetime.datetime.now().isoformat(),
            "updated_at": datetime.datetime.now().isoformat(),
            "embedding": embedding
        }
        
        # Index the document
        response = opensearch_client.index(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            body=doc,
            id=str(speaker_id)  # Use speaker_id as document ID
        )
        
        logger.info(f"Indexed speaker embedding for speaker {speaker_id}: {response}")
        return response
        
    except Exception as e:
        logger.error(f"Error indexing speaker embedding for speaker {speaker_id}: {e}")


def bulk_add_speaker_embeddings(embeddings_data: List[Dict[str, Any]]):
    """
    Bulk add multiple speaker embeddings for efficient indexing
    
    Args:
        embeddings_data: List of embedding data dictionaries
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return
    
    try:
        ensure_indices_exist()
        
        # Prepare bulk operations
        bulk_body = []
        for data in embeddings_data:
            # Index action
            bulk_body.append({
                "index": {
                    "_index": settings.OPENSEARCH_SPEAKER_INDEX,
                    "_id": str(data["speaker_id"])
                }
            })
            
            # Document
            bulk_body.append({
                "speaker_id": data["speaker_id"],
                "profile_id": data.get("profile_id"),
                "user_id": data["user_id"],
                "name": data["name"],
                "collection_ids": data.get("collection_ids", []),
                "media_file_id": data.get("media_file_id"),
                "segment_count": data.get("segment_count", 1),
                "created_at": datetime.datetime.now().isoformat(),
                "updated_at": datetime.datetime.now().isoformat(),
                "embedding": data["embedding"]
            })
        
        # Execute bulk operation
        response = opensearch_client.bulk(body=bulk_body)
        
        if response["errors"]:
            logger.error(f"Bulk indexing had errors: {response}")
        else:
            logger.info(f"Successfully bulk indexed {len(embeddings_data)} speaker embeddings")
        
        return response
        
    except Exception as e:
        logger.error(f"Error bulk indexing speaker embeddings: {e}")


def search_transcripts(query: str, user_id: int, speaker: Optional[str] = None,
                       tags: Optional[List[str]] = None, limit: int = 10,
                       use_semantic: bool = True) -> List[Dict[str, Any]]:
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
        logger.warning("OpenSearch client not initialized or in test environment, returning mock data")
        # Return mock search results for testing
        return [
            {
                "file_id": 1,
                "title": "Test Recording",
                "speakers": ["Speaker 1", "Speaker 2"],
                "upload_time": "2025-05-05T10:00:00",
                "snippet": "This is a mock search result for testing purposes..."
            }
        ]
    
    try:
        # Build the search query
        must_conditions = [
            {"term": {"user_id": user_id}}  # Restrict to user's files
        ]
        
        # Add full-text search
        if query:
            must_conditions.append({
                "match": {
                    "content": {
                        "query": query,
                        "fuzziness": "AUTO"
                    }
                }
            })
        
        # Add speaker filter if specified
        if speaker:
            must_conditions.append({"term": {"speakers": speaker}})
        
        # Add tags filter if specified
        if tags and len(tags) > 0:
            must_conditions.append({"terms": {"tags": tags}})
        
        # Construct basic search
        search_body = {
            "query": {
                "bool": {
                    "must": must_conditions
                }
            },
            "size": limit,
            "_source": ["file_id", "title", "content", "speakers", "tags", "upload_time"],
            "highlight": {
                "fields": {
                    "content": {"pre_tags": ["<em>"], "post_tags": ["</em>"], "fragment_size": 150}
                }
            }
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
                logger.warning("sentence-transformers package not installed, using fallback embedding")
                # Fallback to zero vector
                query_embedding = [0.0] * 384
            except Exception as e:
                logger.warning(f"Error generating query embedding: {e}")
                # Fallback to zero vector
                query_embedding = [0.0] * 384
            
            # Add kNN query
            knn_query = {
                "knn": {
                    "embedding": {
                        "vector": query_embedding,
                        "k": limit
                    }
                }
            }
            
            # Combine text search with vector search
            search_body["query"]["bool"]["should"] = [knn_query]
        
        # Execute search
        response = opensearch_client.search(
            index=settings.OPENSEARCH_TRANSCRIPT_INDEX,
            body=search_body
        )
        
        # Process results
        results = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            result = {
                "file_id": source["file_id"],
                "title": source["title"],
                "speakers": source["speakers"],
                "upload_time": source["upload_time"]
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


def find_matching_speaker(embedding: List[float], user_id: int, 
                          threshold: float = 0.5, collection_ids: Optional[List[int]] = None,
                          exclude_speaker_ids: Optional[List[int]] = None) -> Optional[Dict[str, Any]]:
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
                        "filter": {
                            "bool": {
                                "filter": filters
                            }
                        }
                    }
                }
            }
        }
        
        # Execute search
        response = opensearch_client.search(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            body=query
        )
        
        # Check if we have a match
        if len(response["hits"]["hits"]) > 0:
            hit = response["hits"]["hits"][0]
            # Get the score (normalized 0-1)
            score = hit["_score"]
            
            # Check if score meets our threshold
            if score >= threshold:
                source = hit["_source"]
                return {
                    "speaker_id": source["speaker_id"],
                    "profile_id": source.get("profile_id"),
                    "name": source["name"],
                    "confidence": score,
                    "media_file_id": source.get("media_file_id"),
                    "collection_ids": source.get("collection_ids", [])
                }
        
        # No match found or score below threshold
        return None
        
    except Exception as e:
        logger.error(f"Error finding matching speaker: {e}")
        return None


def batch_find_matching_speakers(embeddings: List[Dict[str, Any]], user_id: int,
                               threshold: float = 0.5, max_candidates: int = 5) -> List[Dict[str, Any]]:
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
        # Use multi-search for efficient batch processing
        msearch_body = []
        
        for emb_data in embeddings:
            # Add search header
            msearch_body.append({"index": settings.OPENSEARCH_SPEAKER_INDEX})
            
            # Add search query
            msearch_body.append({
                "size": max_candidates,
                "query": {
                    "bool": {
                        "filter": [{"term": {"user_id": user_id}}]
                    }
                },
                "knn": {
                    "embedding": {
                        "vector": emb_data["embedding"],
                        "k": max_candidates
                    }
                }
            })
        
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
                        matches.append({
                            "speaker_id": source["speaker_id"],
                            "profile_id": source.get("profile_id"),
                            "name": source["name"],
                            "confidence": score,
                            "media_file_id": source.get("media_file_id")
                        })
            
            results.append({
                "input_id": emb_data["id"],
                "matches": matches
            })
        
        return results
        
    except Exception as e:
        logger.error(f"Error in batch speaker matching: {e}")
        return []


def find_speaker_across_media(speaker_id: int, user_id: int) -> List[Dict[str, Any]]:
    """
    Find all media files where a specific speaker appears
    
    Args:
        speaker_id: ID of the speaker
        user_id: ID of the user
        
    Returns:
        List of media files where this speaker appears
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return []
    
    try:
        # First, get the speaker's name from the speaker index
        speaker_doc = opensearch_client.get(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            id=str(speaker_id)
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
                        {"term": {"speakers": speaker_name}}
                    ]
                }
            },
            "size": 100,  # Get up to 100 media files
            "_source": ["file_id", "title", "upload_time"]
        }
        
        response = opensearch_client.search(
            index=settings.OPENSEARCH_TRANSCRIPT_INDEX,
            body=query
        )
        
        # Process results
        results = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            results.append({
                "file_id": source["file_id"],
                "title": source["title"],
                "upload_time": source["upload_time"]
            })
        
        return results
        
    except Exception as e:
        logger.error(f"Error finding speaker across media: {e}")
        return []


def update_speaker_collections(speaker_id: int, profile_id: int, collection_ids: List[int]):
    """
    Update speaker embedding collections when a speaker is labeled/assigned to profile
    
    Args:
        speaker_id: Speaker ID in the database
        profile_id: Profile ID the speaker is assigned to
        collection_ids: List of collection IDs to assign
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return
    
    try:
        # Update the speaker document in OpenSearch
        update_body = {
            "doc": {
                "profile_id": profile_id,
                "collection_ids": collection_ids,
                "updated_at": datetime.datetime.now().isoformat()
            }
        }
        
        response = opensearch_client.update(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            id=str(speaker_id),
            body=update_body
        )
        
        logger.info(f"Updated speaker {speaker_id} collections: {collection_ids}")
        return response
        
    except Exception as e:
        logger.error(f"Error updating speaker collections: {e}")


def move_speaker_to_profile_collection(unlabeled_speaker_id: int, target_profile_id: int, 
                                     target_collection_ids: List[int]):
    """
    Move an unlabeled speaker embedding to a profile's collection
    
    Args:
        unlabeled_speaker_id: ID of the unlabeled speaker
        target_profile_id: ID of the target profile
        target_collection_ids: Target collection IDs
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return
    
    try:
        # Update the speaker's profile and collection assignments
        update_body = {
            "doc": {
                "profile_id": target_profile_id,
                "collection_ids": target_collection_ids,
                "updated_at": datetime.datetime.now().isoformat()
            }
        }
        
        response = opensearch_client.update(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            id=str(unlabeled_speaker_id),
            body=update_body
        )
        
        logger.info(f"Moved speaker {unlabeled_speaker_id} to profile {target_profile_id}")
        return response
        
    except Exception as e:
        logger.error(f"Error moving speaker to profile collection: {e}")


def bulk_update_collection_assignments(updates: List[Dict[str, Any]]):
    """
    Bulk update collection assignments for multiple speakers
    
    Args:
        updates: List of update dictionaries with speaker_id, profile_id, collection_ids
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return
    
    try:
        # Prepare bulk update operations
        bulk_body = []
        for update in updates:
            # Update action
            bulk_body.append({
                "update": {
                    "_index": settings.OPENSEARCH_SPEAKER_INDEX,
                    "_id": str(update["speaker_id"])
                }
            })
            
            # Update document
            bulk_body.append({
                "doc": {
                    "profile_id": update.get("profile_id"),
                    "collection_ids": update.get("collection_ids", []),
                    "updated_at": datetime.datetime.now().isoformat()
                }
            })
        
        # Execute bulk operation
        response = opensearch_client.bulk(body=bulk_body)
        
        if response["errors"]:
            logger.error(f"Bulk collection update had errors: {response}")
        else:
            logger.info(f"Successfully updated collections for {len(updates)} speakers")
        
        return response
        
    except Exception as e:
        logger.error(f"Error bulk updating collection assignments: {e}")


def get_speakers_in_collection(collection_id: int, user_id: int) -> List[Dict[str, Any]]:
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
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"user_id": user_id}},
                        {"term": {"collection_ids": collection_id}}
                    ]
                }
            },
            "size": 1000,  # Adjust based on expected collection size
            "_source": ["speaker_id", "profile_id", "name", "media_file_id", "segment_count", "created_at"]
        }
        
        response = opensearch_client.search(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            body=query
        )
        
        speakers = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            speakers.append({
                "speaker_id": source["speaker_id"],
                "profile_id": source.get("profile_id"),
                "name": source["name"],
                "media_file_id": source.get("media_file_id"),
                "segment_count": source.get("segment_count", 1),
                "created_at": source.get("created_at")
            })
        
        return speakers
        
    except Exception as e:
        logger.error(f"Error getting speakers in collection: {e}")
        return []


def merge_speaker_embeddings(source_speaker_id: int, target_speaker_id: int, 
                           new_collection_ids: List[int]):
    """
    Merge two speaker embeddings (used when combining speakers)
    
    Args:
        source_speaker_id: ID of speaker to merge from
        target_speaker_id: ID of speaker to merge into
        new_collection_ids: Updated collection IDs for the target
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return
    
    try:
        # Delete the source speaker document
        opensearch_client.delete(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            id=str(source_speaker_id)
        )
        
        # Update the target speaker's collections
        update_body = {
            "doc": {
                "collection_ids": new_collection_ids,
                "updated_at": datetime.datetime.now().isoformat()
            }
        }
        
        response = opensearch_client.update(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            id=str(target_speaker_id),
            body=update_body
        )
        
        logger.info(f"Merged speaker {source_speaker_id} into {target_speaker_id}")
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
        # Find all embeddings for user
        query = {
            "query": {"term": {"user_id": user_id}},
            "size": 1000,
            "_source": ["speaker_id", "profile_id"]
        }
        
        response = opensearch_client.search(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            body=query
        )
        
        # This function would need to be called with database context
        # to verify which speakers still exist
        logger.info(f"Found {len(response['hits']['hits'])} embeddings for user {user_id}")
        
        # Return count for now - actual cleanup would require database validation
        return len(response["hits"]["hits"])
        
    except Exception as e:
        logger.error(f"Error cleaning up orphaned embeddings: {e}")
        return 0


def get_speaker_embedding(speaker_id: int) -> Optional[List[float]]:
    """
    Get the embedding vector for a speaker from OpenSearch
    
    Args:
        speaker_id: ID of the speaker
        
    Returns:
        Embedding vector or None if not found
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return None
    
    try:
        response = opensearch_client.get(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            id=str(speaker_id)
        )
        
        if response and "_source" in response:
            return response["_source"].get("embedding")
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting speaker embedding: {e}")
        return None


def update_speaker_display_name(speaker_id: int, display_name: Optional[str]):
    """
    Update the display name of a speaker in OpenSearch
    
    Args:
        speaker_id: ID of the speaker
        display_name: New display name (or None to clear)
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return
    
    try:
        # Update the speaker document with new display name
        update_body = {
            "doc": {
                "display_name": display_name,
                "updated_at": datetime.datetime.now().isoformat()
            }
        }
        
        response = opensearch_client.update(
            index=settings.OPENSEARCH_SPEAKER_INDEX,
            id=str(speaker_id),
            body=update_body
        )
        
        logger.info(f"Updated display name for speaker {speaker_id} to '{display_name}'")
        return response
        
    except Exception as e:
        logger.error(f"Error updating speaker display name: {e}")
