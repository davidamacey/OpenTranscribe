"""
OpenSearch Summary Service

Handles indexing, searching, and analytics for AI-generated summaries
stored in OpenSearch for advanced search capabilities.
"""

import datetime
import logging
import uuid
from typing import Any
from typing import Optional

from opensearchpy.exceptions import NotFoundError

from app.core.config import settings
from app.services.opensearch_service import opensearch_client

logger = logging.getLogger(__name__)


class OpenSearchSummaryService:
    """Service for managing summaries in OpenSearch"""

    def __init__(self):
        self.client = opensearch_client
        self.index_name = getattr(
            settings, "OPENSEARCH_SUMMARY_INDEX", "transcript_summaries"
        )

        # Ensure the summary index exists
        self._ensure_summary_index_exists()

    def _ensure_summary_index_exists(self):
        """
        Create the summary index if it doesn't exist
        """
        if not self.client:
            logger.warning("OpenSearch client not initialized")
            return

        try:
            if not self.client.indices.exists(index=self.index_name):
                # Define the mapping for summary documents
                index_config = {
                    "settings": {
                        "index": {
                            "number_of_shards": 1,
                            "number_of_replicas": 0,
                            "max_result_window": 50000,  # Allow deeper pagination
                        },
                        "analysis": {
                            "analyzer": {
                                "summary_analyzer": {
                                    "type": "standard",
                                    "stopwords": ["_english_"],
                                }
                            }
                        },
                    },
                    "mappings": {
                        "properties": {
                            "file_id": {"type": "integer"},
                            "user_id": {"type": "integer"},
                            "summary_version": {"type": "integer"},
                            "provider": {"type": "keyword"},
                            "model": {"type": "keyword"},
                            "created_at": {"type": "date"},
                            "updated_at": {"type": "date"},
                            # Core summary content
                            "bluf": {"type": "text", "analyzer": "summary_analyzer"},
                            "brief_summary": {
                                "type": "text",
                                "analyzer": "summary_analyzer",
                            },
                            # Major topics (nested objects)
                            "major_topics": {
                                "type": "nested",
                                "properties": {
                                    "topic": {
                                        "type": "text",
                                        "analyzer": "summary_analyzer",
                                    },
                                    "importance": {"type": "keyword"},
                                    "key_points": {
                                        "type": "text",
                                        "analyzer": "summary_analyzer",
                                    },
                                    "participants": {"type": "keyword"},
                                },
                            },
                            # Action items (nested objects)
                            "action_items": {
                                "type": "nested",
                                "properties": {
                                    "text": {
                                        "type": "text",
                                        "analyzer": "summary_analyzer",
                                    },
                                    "assigned_to": {"type": "keyword"},
                                    "due_date": {
                                        "type": "date",
                                        "format": "yyyy-MM-dd||epoch_millis",
                                    },
                                    "priority": {"type": "keyword"},
                                    "context": {
                                        "type": "text",
                                        "analyzer": "summary_analyzer",
                                    },
                                    "status": {
                                        "type": "keyword"
                                    },  # pending, completed, cancelled
                                },
                            },
                            # Key decisions
                            "key_decisions": {
                                "type": "text",
                                "analyzer": "summary_analyzer",
                            },
                            # Follow-up items
                            "follow_up_items": {
                                "type": "text",
                                "analyzer": "summary_analyzer",
                            },
                            # Metadata
                            "metadata": {
                                "properties": {
                                    "transcript_length": {"type": "integer"},
                                    "processing_time_ms": {"type": "integer"},
                                    "confidence_score": {"type": "float"},
                                    "language": {"type": "keyword"},
                                    "usage_tokens": {"type": "integer"},
                                    "error": {"type": "text"},
                                }
                            },
                            # Full-text searchable combined content
                            "searchable_content": {
                                "type": "text",
                                "analyzer": "summary_analyzer",
                            },
                        }
                    },
                }

                self.client.indices.create(index=self.index_name, body=index_config)

                logger.info(f"Created summary index: {self.index_name}")

        except Exception as e:
            logger.error(f"Error creating summary index: {e}")

    async def index_summary(self, summary_data: dict[str, Any]) -> str:
        """
        Index a summary document in OpenSearch

        Args:
            summary_data: Summary data dictionary containing all summary information

        Returns:
            Document ID of the indexed summary
        """
        if not self.client:
            logger.warning("OpenSearch client not initialized")
            return None

        try:
            # Generate a unique document ID
            doc_id = str(uuid.uuid4())

            # Prepare the document for indexing
            doc = self._prepare_summary_document(summary_data)
            doc["created_at"] = datetime.datetime.now().isoformat()
            doc["updated_at"] = datetime.datetime.now().isoformat()

            # Index the document
            self.client.index(
                index=self.index_name,
                id=doc_id,
                body=doc,
                refresh=True,  # Make document immediately searchable
            )

            logger.info(
                f"Indexed summary for file {summary_data.get('file_id')}: {doc_id}"
            )
            return doc_id

        except Exception as e:
            logger.error(f"Error indexing summary: {e}")
            return None

    async def get_summary(self, document_id: str) -> Optional[dict[str, Any]]:
        """
        Retrieve a summary document by ID

        Args:
            document_id: OpenSearch document ID

        Returns:
            Summary document or None if not found
        """
        if not self.client:
            return None

        try:
            response = self.client.get(index=self.index_name, id=document_id)

            return response["_source"]

        except NotFoundError:
            logger.warning(f"Summary document not found: {document_id}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving summary: {e}")
            return None

    async def get_summary_by_file_id(
        self, file_id: int, user_id: int
    ) -> Optional[dict[str, Any]]:
        """
        Get the latest summary for a specific file

        Args:
            file_id: Media file ID
            user_id: User ID for security

        Returns:
            Latest summary document or None if not found
        """
        if not self.client:
            return None

        try:
            # Search for summaries for this file, get the latest version
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"file_id": file_id}},
                            {"term": {"user_id": user_id}},
                        ]
                    }
                },
                "sort": [{"summary_version": {"order": "desc"}}],
                "size": 1,
            }

            response = self.client.search(index=self.index_name, body=query)

            if response["hits"]["hits"]:
                hit = response["hits"]["hits"][0]
                summary_data = hit["_source"]

                # Ensure metadata has all required fields for backward compatibility
                if "metadata" in summary_data:
                    metadata = summary_data["metadata"]
                    # Add missing transcript_length if not present
                    if "transcript_length" not in metadata:
                        # Calculate from brief_summary if available
                        transcript_length = len(summary_data.get("brief_summary", ""))
                        metadata["transcript_length"] = transcript_length
                        logger.warning(
                            f"Added missing transcript_length ({transcript_length}) to summary metadata for file {file_id}"
                        )

                    # Ensure other required fields exist
                    if "usage_tokens" not in metadata:
                        metadata["usage_tokens"] = None
                    if "processing_time_ms" not in metadata:
                        metadata["processing_time_ms"] = None

                return {"document_id": hit["_id"], **summary_data}

            return None

        except Exception as e:
            logger.error(f"Error getting summary for file {file_id}: {e}")
            return None

    async def search_summaries(
        self, query: dict[str, Any], user_id: int, size: int = 20, from_: int = 0
    ) -> dict[str, Any]:
        """
        Search across all summaries with complex queries

        Args:
            query: Search query parameters
            user_id: User ID for security filtering
            size: Number of results to return
            from_: Offset for pagination

        Returns:
            Search results with metadata
        """
        if not self.client:
            return {"hits": [], "total": 0}

        try:
            # Base query - always filter by user
            search_body = {
                "query": {
                    "bool": {
                        "must": [{"term": {"user_id": user_id}}],
                        "should": [],
                        "filter": [],
                    }
                },
                "size": size,
                "from": from_,
                "sort": [{"created_at": {"order": "desc"}}],
                "highlight": {
                    "fields": {
                        "bluf": {},
                        "brief_summary": {},
                        "searchable_content": {"fragment_size": 200},
                    },
                    "pre_tags": ["<mark>"],
                    "post_tags": ["</mark>"],
                },
            }

            # Add text search if provided
            if query.get("text"):
                text_query = {
                    "multi_match": {
                        "query": query["text"],
                        "fields": [
                            "bluf^3",  # Boost BLUF content
                            "brief_summary^2",
                            "searchable_content",
                            "major_topics.topic^2",
                            "major_topics.key_points",
                            "action_items.text",
                            "key_decisions^2",
                        ],
                        "fuzziness": "AUTO",
                    }
                }
                search_body["query"]["bool"]["should"].append(text_query)
                search_body["query"]["bool"]["minimum_should_match"] = 1

            # Add date range filter
            if query.get("date_from") or query.get("date_to"):
                date_filter = {"range": {"created_at": {}}}
                if query.get("date_from"):
                    date_filter["range"]["created_at"]["gte"] = query["date_from"]
                if query.get("date_to"):
                    date_filter["range"]["created_at"]["lte"] = query["date_to"]
                search_body["query"]["bool"]["filter"].append(date_filter)

            # Add action item filter
            if query.get("has_pending_actions"):
                action_filter = {
                    "nested": {
                        "path": "action_items",
                        "query": {
                            "bool": {
                                "must_not": {
                                    "term": {"action_items.status": "completed"}
                                }
                            }
                        },
                    }
                }
                search_body["query"]["bool"]["filter"].append(action_filter)

            # Execute search
            response = self.client.search(index=self.index_name, body=search_body)

            # Process results
            hits = []
            for hit in response["hits"]["hits"]:
                source = hit["_source"]
                result = {
                    "document_id": hit["_id"],
                    "score": hit["_score"],
                    "file_id": source["file_id"],
                    "bluf": source.get("bluf", ""),
                    "brief_summary": source.get("brief_summary", ""),
                    "created_at": source.get("created_at"),
                    "provider": source.get("provider"),
                    "model": source.get("model"),
                }

                # Add highlights if available
                if "highlight" in hit:
                    result["highlights"] = hit["highlight"]

                hits.append(result)

            return {
                "hits": hits,
                "total": response["hits"]["total"]["value"],
                "max_score": response["hits"]["max_score"],
            }

        except Exception as e:
            logger.error(f"Error searching summaries: {e}")
            return {"hits": [], "total": 0}

    async def get_summary_analytics(
        self, user_id: int, filters: dict[str, Any] = None
    ) -> dict[str, Any]:
        """
        Get analytics and aggregations for summaries

        Args:
            user_id: User ID
            filters: Optional filters to apply

        Returns:
            Analytics data
        """
        if not self.client:
            return {}

        try:
            # Base query with user filter
            agg_query = {
                "size": 0,  # We only want aggregations
                "query": {"bool": {"must": [{"term": {"user_id": user_id}}]}},
                "aggs": {
                    # Action items over time
                    "action_items_trend": {
                        "date_histogram": {
                            "field": "created_at",
                            "calendar_interval": "week",
                        },
                        "aggs": {
                            "action_count": {
                                "nested": {"path": "action_items"},
                                "aggs": {
                                    "total": {
                                        "value_count": {
                                            "field": "action_items.text.keyword"
                                        }
                                    }
                                },
                            },
                            "pending_actions": {
                                "nested": {"path": "action_items"},
                                "aggs": {
                                    "pending": {
                                        "filter": {
                                            "bool": {
                                                "must_not": {
                                                    "term": {
                                                        "action_items.status": "completed"
                                                    }
                                                }
                                            }
                                        }
                                    }
                                },
                            },
                        },
                    },
                    # Most common topics
                    "common_topics": {
                        "nested": {"path": "major_topics"},
                        "aggs": {
                            "topics": {
                                "terms": {
                                    "field": "major_topics.topic.keyword",
                                    "size": 15,
                                }
                            }
                        },
                    },
                    # Summary statistics
                    "summary_stats": {"stats": {"field": "metadata.transcript_length"}},
                    # Provider usage
                    "provider_usage": {"terms": {"field": "provider", "size": 10}},
                },
            }

            # Apply date filter if provided
            if filters and filters.get("date_from"):
                date_filter = {"range": {"created_at": {"gte": filters["date_from"]}}}
                if filters.get("date_to"):
                    date_filter["range"]["created_at"]["lte"] = filters["date_to"]
                agg_query["query"]["bool"]["must"].append(date_filter)

            response = self.client.search(index=self.index_name, body=agg_query)

            # Process aggregations
            aggs = response["aggregations"]

            analytics = {
                "total_summaries": response["hits"]["total"]["value"],
                "speaker_stats": [],  # No longer tracking speaker stats
                "action_items_trend": self._process_trend_aggregation(
                    aggs["action_items_trend"]
                ),
                "common_topics": self._process_topics_aggregation(
                    aggs["common_topics"]
                ),
                "summary_statistics": aggs["summary_stats"],
                "provider_usage": self._process_terms_aggregation(
                    aggs["provider_usage"]
                ),
            }

            return analytics

        except Exception as e:
            logger.error(f"Error getting summary analytics: {e}")
            return {}

    async def update_summary(self, document_id: str, updates: dict[str, Any]) -> bool:
        """
        Update a summary document

        Args:
            document_id: OpenSearch document ID
            updates: Fields to update

        Returns:
            Success status
        """
        if not self.client:
            return False

        try:
            # Add updated timestamp
            updates["updated_at"] = datetime.datetime.now().isoformat()

            self.client.update(
                index=self.index_name,
                id=document_id,
                body={"doc": updates},
                refresh=True,
            )

            logger.info(f"Updated summary document: {document_id}")
            return True

        except Exception as e:
            logger.error(f"Error updating summary: {e}")
            return False

    async def delete_summary(self, document_id: str) -> bool:
        """
        Delete a summary document

        Args:
            document_id: OpenSearch document ID

        Returns:
            Success status
        """
        if not self.client:
            return False

        try:
            self.client.delete(index=self.index_name, id=document_id, refresh=True)

            logger.info(f"Deleted summary document: {document_id}")
            return True

        except NotFoundError:
            logger.warning(f"Summary document not found for deletion: {document_id}")
            return False
        except Exception as e:
            logger.error(f"Error deleting summary: {e}")
            return False

    def _prepare_summary_document(self, summary_data: dict[str, Any]) -> dict[str, Any]:
        """
        Prepare summary data for indexing

        Args:
            summary_data: Raw summary data

        Returns:
            Processed document ready for indexing
        """
        # Create searchable content by combining all text fields
        searchable_parts = [
            summary_data.get("bluf", ""),
            summary_data.get("brief_summary", ""),
        ]

        # Add major topics
        for topic in summary_data.get("major_topics", []):
            searchable_parts.append(topic.get("topic", ""))
            searchable_parts.extend(topic.get("key_points", []))

        # Add action items
        for item in summary_data.get("action_items", []):
            searchable_parts.extend([item.get("text", ""), item.get("context", "")])

        # Add decisions and follow-ups
        searchable_parts.extend(summary_data.get("key_decisions", []))
        searchable_parts.extend(summary_data.get("follow_up_items", []))

        # Create the document
        doc = {
            **summary_data,
            "searchable_content": " ".join(filter(None, searchable_parts)),
        }

        # Ensure action items have status field
        for item in doc.get("action_items", []):
            if "status" not in item:
                item["status"] = "pending"

        return doc

    def _process_trend_aggregation(self, agg: dict[str, Any]) -> list[dict[str, Any]]:
        """Process time-based trend aggregation"""
        trends = []
        for bucket in agg["buckets"]:
            trends.append(
                {
                    "date": bucket["key_as_string"],
                    "total_actions": bucket["action_count"]["total"]["value"],
                    "pending_actions": bucket["pending_actions"]["pending"][
                        "doc_count"
                    ],
                }
            )
        return trends

    def _process_topics_aggregation(self, agg: dict[str, Any]) -> list[dict[str, Any]]:
        """Process topics aggregation"""
        topics = []
        for bucket in agg["topics"]["buckets"]:
            topics.append({"topic": bucket["key"], "count": bucket["doc_count"]})
        return topics

    def _process_terms_aggregation(self, agg: dict[str, Any]) -> list[dict[str, Any]]:
        """Process simple terms aggregation"""
        terms = []
        for bucket in agg["buckets"]:
            terms.append({"term": bucket["key"], "count": bucket["doc_count"]})
        return terms
