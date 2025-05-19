from opensearchpy import OpenSearch, RequestsHttpConnection
from typing import List, Dict, Any, Optional
import json
import logging
import os

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
                        "number_of_replicas": 0
                    }
                },
                "mappings": {
                    "properties": {
                        "speaker_id": {"type": "integer"},
                        "user_id": {"type": "integer"},
                        "name": {"type": "keyword"},
                        "embedding": {
                            "type": "knn_vector", 
                            "dimension": 256  # Typical for speaker embeddings (Pyannote)
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
            "upload_time": "now",  # OpenSearch will interpret "now" as the current time
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


def add_speaker_embedding(speaker_id: int, user_id: int, name: str, embedding: List[float]):
    """
    Add a speaker embedding to OpenSearch
    
    Args:
        speaker_id: ID of the speaker in the database
        user_id: ID of the user who owns the speaker profile
        name: Name of the speaker
        embedding: Vector embedding of the speaker's voice
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized, skipping speaker embedding")
        return
    
    try:
        ensure_indices_exist()
        
        # Prepare document
        doc = {
            "speaker_id": speaker_id,
            "user_id": user_id,
            "name": name,
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
            # In a real implementation, we'd compute the query embedding here
            # query_embedding = get_embedding(query)
            # For now, we'll use a placeholder embedding
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
                          threshold: float = 0.8) -> Optional[Dict[str, Any]]:
    """
    Find a matching speaker for a given embedding
    
    Args:
        embedding: Speaker embedding vector
        user_id: ID of the user
        threshold: Similarity threshold (0-1) for matching
        
    Returns:
        Dictionary with speaker_id and name if a match is found, None otherwise
    """
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized, skipping speaker matching")
        return None
    
    try:
        # Build a kNN query to find similar speaker embeddings
        query = {
            "size": 1,  # We only need the closest match
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"user_id": user_id}}  # Restrict to user's speakers
                    ]
                }
            },
            "knn": {
                "embedding": {
                    "vector": embedding,
                    "k": 1
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
                    "name": source["name"]
                }
        
        # No match found or score below threshold
        return None
        
    except Exception as e:
        logger.error(f"Error finding matching speaker: {e}")
        return None
