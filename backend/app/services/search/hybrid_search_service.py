"""Hybrid BM25 + vector search service using OpenSearch 3.4 native features."""

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from app.core.config import settings
from app.core.constants import SEARCH_CACHE_MAX_SIZE
from app.core.constants import SEARCH_CACHE_TTL_SECONDS
from app.core.constants import SEARCH_DEFAULT_PAGE_SIZE
from app.core.constants import SEARCH_MAX_PAGE_SIZE
from app.core.constants import SEARCH_MAX_SNIPPETS_PER_FILE
from app.services.opensearch_service import get_opensearch_client
from app.services.opensearch_service import opensearch_client
from app.services.search.embedding_service import SearchEmbeddingService
from app.services.search.indexing_service import ensure_chunks_index_exists
from app.services.search.indexing_service import ensure_search_pipeline_exists

logger = logging.getLogger(__name__)

# Module-level caches for index/pipeline existence checks
_index_verified = False
_pipeline_verified = False


def _sanitize_html(text: str) -> str:
    """Strip all HTML tags except <mark> and </mark> to prevent XSS.

    OpenSearch highlights wrap matched terms in <mark> tags, but the surrounding
    content from indexed transcripts could contain injected HTML/JS.
    """
    if not text:
        return text
    # Temporarily replace allowed <mark> tags with placeholders
    text = text.replace('<mark class="semantic">', "\x00MARK_SEM_OPEN\x00")
    text = text.replace("<mark>", "\x00MARK_OPEN\x00")
    text = text.replace("</mark>", "\x00MARK_CLOSE\x00")
    # Strip all remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Escape HTML entities in the remaining text
    text = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
    # Restore allowed <mark> tags
    text = text.replace("\x00MARK_SEM_OPEN\x00", '<mark class="semantic">')
    text = text.replace("\x00MARK_OPEN\x00", "<mark>")
    text = text.replace("\x00MARK_CLOSE\x00", "</mark>")
    return text


def _add_semantic_highlights(snippet: str, query: str) -> str:
    """Highlight query words in semantic snippet using <mark class='semantic'>.

    For semantic-only hits, OpenSearch returns no <mark> tags. This function
    adds indigo-styled highlights for query words that appear in the snippet text.

    Args:
        snippet: The snippet text (may contain HTML entities but no <mark> tags).
        query: The original search query string.

    Returns:
        Snippet with query words wrapped in <mark class="semantic"> tags.
    """
    query_words = query.lower().split()
    if not query_words:
        return snippet
    # Only match words with 3+ characters to avoid highlighting articles/prepositions
    patterns = [re.escape(w) for w in query_words if len(w) >= 3]
    if not patterns:
        return snippet
    regex = re.compile(r"\b(" + "|".join(patterns) + r")\b", re.IGNORECASE)
    return regex.sub(r'<mark class="semantic">\g<0></mark>', snippet)


def _parse_query_operators(raw_query: str) -> tuple[str, dict[str, str]]:
    """Parse inline operators from query string.

    Supports: speaker:"Name" or speaker:Name
    Returns: (clean_query, operators_dict)

    Examples:
        'speaker:"Joe Rogan" china' -> ('china', {'speaker': 'Joe Rogan'})
        'speaker:SPEAKER_00 warp' -> ('warp', {'speaker': 'SPEAKER_00'})
        'just plain text' -> ('just plain text', {})
    """
    operators: dict[str, str] = {}
    # Match speaker:"quoted name" or speaker:single_word
    pattern = r'speaker:(?:"([^"]+)"|(\S+))'
    match = re.search(pattern, raw_query, re.IGNORECASE)
    if match:
        speaker_name = match.group(1) or match.group(2)
        operators["speaker"] = speaker_name
        # Remove the operator from query text
        clean = re.sub(pattern, "", raw_query, count=1, flags=re.IGNORECASE).strip()
        # Collapse multiple spaces
        clean = re.sub(r"\s+", " ", clean).strip()
        logger.info(f"PARSE: raw='{raw_query}' -> clean='{clean}', speaker='{speaker_name}'")
    else:
        clean = raw_query
    return clean, operators


def _extract_snippet_and_match_type(
    source: dict[str, Any],
    highlight: dict[str, Any],
) -> tuple[str, str]:
    """Extract the display snippet and match type from a search hit.

    Args:
        source: The _source dict from the OpenSearch hit.
        highlight: The highlight dict from the OpenSearch hit.

    Returns:
        Tuple of (sanitized snippet text, match type string).
    """
    if "content" in highlight or "content.exact" in highlight:
        content_highlights = highlight.get("content") or highlight.get("content.exact", [])
        snippet = " ... ".join(content_highlights)
        match_type = "content"
    elif "title" in highlight:
        snippet = source.get("content", "")[:200]
        match_type = "title"
    elif "speaker" in highlight:
        snippet = source.get("content", "")[:200]
        match_type = "speaker"
    else:
        snippet = source.get("content", "")[:200]
        match_type = "content"
    return _sanitize_html(snippet), match_type


def _extract_highlighted_field(
    highlight: dict[str, Any],
    field: str,
) -> str:
    """Extract and sanitize a highlighted field value.

    Args:
        highlight: The highlight dict from the OpenSearch hit.
        field: Field name to extract (e.g., "title", "speaker").

    Returns:
        Sanitized highlighted string, or empty string if not present.
    """
    if field in highlight:
        return _sanitize_html(" ".join(highlight[field]))
    return ""


@dataclass
class SearchOccurrence:
    """A single matching snippet within a file."""

    snippet: str
    speaker: str
    start_time: float
    end_time: float
    chunk_index: int
    score: float
    match_type: str = "content"  # "content", "title", or "speaker"
    speaker_highlighted: str = ""  # Speaker name with <mark> tags if matched
    has_keyword_match: bool = True  # False for semantic-only hits (no highlights)
    highlight_type: str = "keyword"  # "keyword" or "semantic"


@dataclass
class SearchHit:
    """A file-level search result with multiple occurrences."""

    file_uuid: str
    file_id: int
    title: str
    speakers: list[str]
    tags: list[str]
    upload_time: str
    language: str
    content_type: str = ""
    relevance_score: float = 0.0
    occurrences: list[SearchOccurrence] = field(default_factory=list)
    total_occurrences: int = 0
    title_highlighted: str = ""  # Title with <mark> tags if matched
    keyword_occurrences: int = 0  # Count of hits with actual keyword highlights
    semantic_only: bool = False  # True if no keyword matches, only semantic
    semantic_confidence: str = ""  # "", "high", or "low" for semantic-only hits
    match_sources: list[str] = field(
        default_factory=list
    )  # e.g. ["content", "title", "speaker", "semantic"]
    relevance_percent: int = 0  # 0-100 relevance confidence for display


@dataclass
class SearchResponse:
    """Complete search response."""

    query: str
    results: list[SearchHit]
    total_results: int
    total_files: int
    page: int
    page_size: int
    total_pages: int
    search_time_ms: float
    filters_applied: dict[str, Any] = field(default_factory=dict)
    search_mode: str = "hybrid"


# Module-level search cache
_search_cache: dict[str, tuple[float, SearchResponse]] = {}
_search_cache_lock = threading.Lock()


def _make_cache_key(**kwargs) -> str:
    """Create a deterministic cache key from search params."""
    serializable = {k: v for k, v in sorted(kwargs.items()) if v is not None}
    raw = json.dumps(serializable, sort_keys=True, default=str)
    return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()


def _get_cached_response(cache_key: str) -> SearchResponse | None:
    """Get a cached response if it exists and hasn't expired."""
    with _search_cache_lock:
        if cache_key in _search_cache:
            cached_time, cached_response = _search_cache[cache_key]
            if (time.time() - cached_time) < SEARCH_CACHE_TTL_SECONDS:
                return cached_response
            else:
                del _search_cache[cache_key]
    return None


def _set_cached_response(cache_key: str, response: SearchResponse) -> None:
    """Cache a search response with TTL."""
    with _search_cache_lock:
        # Evict oldest entries if cache is full
        if len(_search_cache) >= SEARCH_CACHE_MAX_SIZE:
            oldest_key = min(_search_cache, key=lambda k: _search_cache[k][0])
            del _search_cache[oldest_key]
        _search_cache[cache_key] = (time.time(), response)


def clear_search_cache() -> None:
    """Clear the entire search cache. Called after reindex or model switch."""
    with _search_cache_lock:
        _search_cache.clear()
    logger.info("Search cache cleared")


def _append_range_filter(
    filters: list[dict[str, Any]],
    field: str,
    gte_value: Any | None,
    lte_value: Any | None,
) -> None:
    """Append a range filter clause if at least one bound is provided.

    Args:
        filters: List of filter clauses to append to.
        field: OpenSearch field name for the range.
        gte_value: Lower bound (inclusive), or None.
        lte_value: Upper bound (inclusive), or None.
    """
    if gte_value is None and lte_value is None:
        return
    range_clause: dict[str, Any] = {}
    if gte_value is not None:
        range_clause["gte"] = gte_value
    if lte_value is not None:
        range_clause["lte"] = lte_value
    filters.append({"range": {field: range_clause}})


def _ensure_infrastructure() -> None:
    """Ensure the OpenSearch index and search pipeline exist (checked once)."""
    global _index_verified, _pipeline_verified
    if not _index_verified:
        ensure_chunks_index_exists()
        _index_verified = True
    if not _pipeline_verified:
        ensure_search_pipeline_exists()
        _pipeline_verified = True


def _collect_filters_applied(
    speakers: list[str] | None = None,
    tags: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    file_type: list[str] | None = None,
    collection_id: int | None = None,
    language: str | None = None,
    title_filter: str | None = None,
) -> dict[str, Any]:
    """Build a dict of non-None filter values for the response metadata."""
    candidates: list[tuple[str, Any]] = [
        ("speakers", speakers),
        ("tags", tags),
        ("date_from", date_from),
        ("date_to", date_to),
        ("file_type", file_type),
        ("collection_id", collection_id),
        ("language", language),
        ("title_filter", title_filter),
    ]
    return {key: value for key, value in candidates if value}


class HybridSearchService:
    """Executes hybrid BM25 + vector search with RRF via OpenSearch 3.4 native pipeline."""

    def search(
        self,
        query: str,
        user_id: int,
        page: int = 1,
        page_size: int = SEARCH_DEFAULT_PAGE_SIZE,
        speakers: list[str] | None = None,
        tags: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sort_by: str = "relevance",
        search_mode: str = "hybrid",
        file_type: list[str] | None = None,
        collection_id: int | None = None,
        min_duration: float | None = None,
        max_duration: float | None = None,
        min_file_size: int | None = None,
        max_file_size: int | None = None,
        language: str | None = None,
        title_filter: str | None = None,
    ) -> SearchResponse:
        """Execute hybrid search and return grouped results.

        Args:
            query: Search query text.
            user_id: Current user ID for filtering.
            page: Page number (1-indexed).
            page_size: Results per page.
            speakers: Optional speaker filter list.
            tags: Optional tag filter list.
            date_from: Optional start date filter (ISO format).
            date_to: Optional end date filter (ISO format).
            sort_by: Sort order - relevance, date, or match_count.
            title_filter: Optional filename/title substring filter.

        Returns:
            SearchResponse with grouped results.
        """
        client = get_opensearch_client()
        if not client:
            logger.warning("OpenSearch client not initialized")
            return self._empty_response(query, page, page_size)

        start_time = time.time()
        page_size = min(page_size, SEARCH_MAX_PAGE_SIZE)

        # Check cache
        cache_key = _make_cache_key(
            query=query,
            user_id=user_id,
            page=page,
            page_size=page_size,
            speakers=speakers,
            tags=tags,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
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
        cached = _get_cached_response(cache_key)
        if cached:
            return cached

        _ensure_infrastructure()

        # Parse inline query operators (e.g., speaker:"Joe Rogan" china)
        clean_query, operators = _parse_query_operators(query)
        if "speaker" in operators:
            speakers = list(speakers or []) + [operators["speaker"]]
        search_query = clean_query.strip() if clean_query else ""

        # Debug logging
        logger.info(
            f"SEARCH: original='{query}', clean='{clean_query}', search_query='{search_query}', speakers={speakers}"
        )

        # Build filters
        filters = self._build_filters(
            user_id,
            speakers,
            tags,
            date_from,
            date_to,
            file_type=file_type,
            collection_id=collection_id,
            min_duration=min_duration,
            max_duration=max_duration,
            min_file_size=min_file_size,
            max_file_size=max_file_size,
            language=language,
            title_filter=title_filter,
        )
        filters_applied = _collect_filters_applied(
            speakers=speakers,
            tags=tags,
            date_from=date_from,
            date_to=date_to,
            file_type=file_type,
            collection_id=collection_id,
            language=language,
            title_filter=title_filter,
        )

        # Generate query embedding and execute search
        query_embedding, use_hybrid = self._generate_query_embedding(search_query, search_mode)
        has_speaker_filter = bool(speakers)
        response = self._execute_search(
            search_query, query_embedding, filters, page_size, use_hybrid, has_speaker_filter
        )
        if response is None:
            return self._empty_response(query, page, page_size)

        # Group, sort, paginate, and build response
        grouped = self._group_results_by_file(response, query=query)

        # Filter weakest semantic-only results (intra-semantic comparison)
        semantic_hits = [h for h in grouped if h.semantic_only]
        if semantic_hits:
            best_semantic = max(h.relevance_score for h in semantic_hits)
            min_semantic = settings.SEARCH_HYBRID_MIN_SCORE
            semantic_range = best_semantic - min_semantic
            if semantic_range > 0:
                # Keep semantic results scoring >= SUPPRESS_RATIO of the
                # best semantic score (measured within the semantic range)
                threshold = min_semantic + semantic_range * settings.SEARCH_SEMANTIC_SUPPRESS_RATIO
                grouped = [
                    h for h in grouped if not h.semantic_only or h.relevance_score >= threshold
                ]

        result = self._sort_and_paginate(
            query,
            grouped,
            sort_by,
            search_mode,
            page,
            page_size,
            filters_applied,
            start_time,
        )

        # Cache the response
        _set_cached_response(cache_key, result)

        return result

    def _generate_query_embedding(
        self,
        query: str,
        search_mode: str,
    ) -> tuple[list[float] | None, bool]:
        """Generate query embedding vector for semantic search.

        Args:
            query: Search query text.
            search_mode: Search mode - "keyword" skips embedding.

        Returns:
            Tuple of (embedding vector or None, whether hybrid mode is active).
        """
        if search_mode == "keyword":
            return None, False
        try:
            embedding_service = SearchEmbeddingService.get_instance()
            query_embedding = embedding_service.embed_query(query)
            return query_embedding, True
        except Exception as e:
            logger.warning(f"Embedding failed, falling back to BM25-only: {e}")
            return None, False

    def _execute_search(
        self,
        query: str,
        query_embedding: list[float] | None,
        filters: list[dict[str, Any]],
        page_size: int,
        use_hybrid: bool,
        has_speaker_filter: bool = False,
    ) -> dict[str, Any] | None:
        """Execute the OpenSearch query with fallback to BM25-only.

        Args:
            query: Search query text.
            query_embedding: Optional embedding vector.
            filters: OpenSearch filter clauses.
            page_size: Results per page.
            use_hybrid: Whether to use hybrid search pipeline.
            has_speaker_filter: Whether a speaker filter is active.

        Returns:
            OpenSearch response dict, or None if all attempts fail.
        """
        if not opensearch_client:
            return None
        try:
            search_body = self._build_search_body(
                query, query_embedding, filters, page_size, use_hybrid, has_speaker_filter
            )
            search_params: dict[str, Any] = {}
            if use_hybrid:
                search_params["search_pipeline"] = settings.OPENSEARCH_SEARCH_PIPELINE
            result: dict[str, Any] = opensearch_client.search(
                index=settings.OPENSEARCH_CHUNKS_INDEX,
                body=search_body,
                params=search_params,
            )
            return result
        except Exception as e:
            logger.error(f"Search query failed: {e}")

        # Fall back to BM25-only without pipeline
        try:
            search_body = self._build_bm25_only_body(query, filters, page_size, has_speaker_filter)
            fallback: dict[str, Any] = opensearch_client.search(
                index=settings.OPENSEARCH_CHUNKS_INDEX,
                body=search_body,
            )
            return fallback
        except Exception as e2:
            logger.error(f"BM25 fallback also failed: {e2}")
            return None

    def _sort_and_paginate(
        self,
        query: str,
        grouped: list[SearchHit],
        sort_by: str,
        search_mode: str,
        page: int,
        page_size: int,
        filters_applied: dict[str, Any],
        start_time: float,
    ) -> SearchResponse:
        """Sort grouped results, paginate, and build SearchResponse.

        Keyword-matched files always appear before semantic-only files.
        """
        if sort_by == "date":
            grouped.sort(key=lambda h: (h.semantic_only, h.upload_time), reverse=False)
            # We want: keyword first (semantic_only=False=0), then semantic (True=1)
            # Within each group, sort by date descending
            grouped.sort(key=lambda h: h.upload_time, reverse=True)
            grouped.sort(key=lambda h: h.semantic_only)
        elif sort_by == "match_count":
            grouped.sort(key=lambda h: (-int(not h.semantic_only), -h.keyword_occurrences))
        else:
            # Relevance: keyword matches first, then by score
            grouped.sort(key=lambda h: (-int(not h.semantic_only), -h.relevance_score))

        total_files = len(grouped)
        total_pages = max(1, (total_files + page_size - 1) // page_size)
        start_idx = (page - 1) * page_size
        page_results = grouped[start_idx : start_idx + page_size]

        # Total results uses keyword_occurrences for files with keyword matches,
        # total_occurrences for semantic-only files
        total_results = sum(
            h.keyword_occurrences if h.keyword_occurrences > 0 else h.total_occurrences
            for h in grouped
        )
        elapsed_ms = round((time.time() - start_time) * 1000, 1)

        return SearchResponse(
            query=query,
            results=page_results,
            total_results=total_results,
            total_files=total_files,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            search_time_ms=elapsed_ms,
            filters_applied=filters_applied,
            search_mode=search_mode,
        )

    def get_suggestions(
        self,
        prefix: str,
        user_id: int,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        """Get auto-complete suggestions.

        Args:
            prefix: Search prefix text.
            user_id: Current user ID.
            limit: Maximum number of suggestions.

        Returns:
            List of suggestion dicts with type, text, and optional metadata.
        """
        if not opensearch_client:
            return []

        index_name = settings.OPENSEARCH_CHUNKS_INDEX

        global _index_verified
        if not _index_verified:
            try:
                if not opensearch_client.indices.exists(index=index_name):
                    return []
                _index_verified = True
            except Exception:
                return []

        suggestions = []

        try:
            # Multi-search for title and speaker suggestions
            msearch_body = [
                # Title matches
                {"index": index_name},
                {
                    "size": 4,
                    "query": {
                        "bool": {
                            "must": [{"match_phrase_prefix": {"title": prefix}}],
                            "filter": [{"term": {"user_id": user_id}}],
                        }
                    },
                    "_source": ["title", "file_uuid"],
                    "collapse": {"field": "file_uuid"},
                },
                # Speaker matches
                {"index": index_name},
                {
                    "size": 0,
                    "query": {
                        "bool": {
                            "must": [{"prefix": {"speaker": {"value": prefix.lower()}}}],
                            "filter": [{"term": {"user_id": user_id}}],
                        }
                    },
                    "aggs": {"speakers": {"terms": {"field": "speaker", "size": 4}}},
                },
            ]

            response = opensearch_client.msearch(body=msearch_body)

            # Process title matches
            if len(response.get("responses", [])) > 0:
                title_resp = response["responses"][0]
                for hit in title_resp.get("hits", {}).get("hits", []):
                    source = hit["_source"]
                    suggestions.append(
                        {
                            "type": "title",
                            "text": source["title"],
                            "file_uuid": source.get("file_uuid"),
                        }
                    )

            # Process speaker matches
            if len(response.get("responses", [])) > 1:
                speaker_resp = response["responses"][1]
                buckets = (
                    speaker_resp.get("aggregations", {}).get("speakers", {}).get("buckets", [])
                )
                for bucket in buckets:
                    suggestions.append(
                        {
                            "type": "speaker",
                            "text": bucket["key"],
                            "count": bucket["doc_count"],
                        }
                    )

        except Exception as e:
            logger.error(f"Error getting suggestions: {e}")

        return suggestions[:limit]

    def get_available_filters(self, user_id: int) -> dict[str, Any]:
        """Return available filter options for the current user.

        Args:
            user_id: Current user ID.

        Returns:
            Dict with speakers, tags, and date_range.
        """
        if not opensearch_client:
            return {"speakers": [], "tags": [], "date_range": {}}

        index_name = settings.OPENSEARCH_CHUNKS_INDEX

        global _index_verified
        if not _index_verified:
            try:
                if not opensearch_client.indices.exists(index=index_name):
                    return {"speakers": [], "tags": [], "date_range": {}}
                _index_verified = True
            except Exception:
                return {"speakers": [], "tags": [], "date_range": {}}

        try:
            response = opensearch_client.search(
                index=index_name,
                body={
                    "size": 0,
                    "query": {"term": {"user_id": user_id}},
                    "aggs": {
                        "speakers": {"terms": {"field": "speaker", "size": 100}},
                        "tags": {"terms": {"field": "tags", "size": 100}},
                        "date_range": {"stats": {"field": "upload_time"}},
                    },
                },
            )

            aggs = response.get("aggregations", {})
            speakers = [
                {"name": b["key"], "count": b["doc_count"]}
                for b in aggs.get("speakers", {}).get("buckets", [])
            ]
            tags = [
                {"name": b["key"], "count": b["doc_count"]}
                for b in aggs.get("tags", {}).get("buckets", [])
            ]
            date_stats = aggs.get("date_range", {})

            return {
                "speakers": speakers,
                "tags": tags,
                "date_range": {
                    "min": date_stats.get("min_as_string"),
                    "max": date_stats.get("max_as_string"),
                },
            }
        except Exception as e:
            logger.error(f"Error getting filters: {e}")
            return {"speakers": [], "tags": [], "date_range": {}}

    def _build_filters(
        self,
        user_id: int,
        speakers: list[str] | None,
        tags: list[str] | None,
        date_from: str | None,
        date_to: str | None,
        file_type: list[str] | None = None,
        collection_id: int | None = None,
        min_duration: float | None = None,
        max_duration: float | None = None,
        min_file_size: int | None = None,
        max_file_size: int | None = None,
        language: str | None = None,
        title_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Build OpenSearch filter clauses."""
        filters: list[dict[str, Any]] = [{"term": {"user_id": user_id}}]

        if speakers:
            filters.append({"terms": {"speaker": speakers}})
        if tags:
            filters.append({"terms": {"tags": tags}})
        if file_type:
            filters.append({"terms": {"content_type": file_type}})
        if collection_id is not None:
            filters.append({"term": {"collection_ids": collection_id}})
        if language:
            filters.append({"term": {"language": language}})
        if title_filter:
            filters.append(
                {
                    "wildcard": {
                        "title": {"value": f"*{title_filter.lower()}*", "case_insensitive": True}
                    }
                }
            )

        # Range filters for date, duration, and file size
        _append_range_filter(filters, "upload_time", date_from, date_to)
        _append_range_filter(filters, "duration", min_duration, max_duration)
        _append_range_filter(filters, "file_size", min_file_size, max_file_size)

        return filters

    def _build_search_body(
        self,
        query: str,
        query_embedding: list[float] | None,
        filters: list[dict[str, Any]],
        page_size: int,
        use_hybrid: bool,
        has_speaker_filter: bool = False,
    ) -> dict[str, Any]:
        """Build the hybrid search query body."""
        # Over-fetch for grouping by file
        fetch_size = page_size * 5

        # Dynamically set search fields based on speaker filter
        if has_speaker_filter:
            search_fields = [
                "content^3",
                "content.exact^2",
                "title^2",
            ]
        else:
            search_fields = [
                "content^3",
                "content.exact^2",
                "title^2",
                "speaker^3",
            ]

        # Build the text query clause (multi_match or match_all if no query)
        if query and query.strip():
            text_query_clause = {
                "multi_match": {
                    "query": query,
                    "fields": search_fields,
                    "type": "best_fields",
                }
            }
            logger.info(
                f"BUILD_BODY: using multi_match with query='{query}', has_speaker_filter={has_speaker_filter}, fields={search_fields}"
            )
        else:
            # Empty query - use match_all (will only filter by speaker/tags/etc)
            text_query_clause = {"match_all": {}}
            logger.info(
                f"BUILD_BODY: using match_all (empty query), has_speaker_filter={has_speaker_filter}"
            )

        # Build highlight fields (exclude speaker when using speaker filter)
        highlight_fields = {
            "content": {
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
                "fragment_size": 200,
                "number_of_fragments": 3,
            },
            "title": {
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
                "number_of_fragments": 0,
            },
        }
        if not has_speaker_filter:
            highlight_fields["speaker"] = {
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
                "number_of_fragments": 0,
            }

        if use_hybrid and query_embedding:
            search_body: dict[str, Any] = {
                "size": fetch_size,
                "query": {
                    "hybrid": {
                        "queries": [
                            # BM25 leg
                            {
                                "bool": {
                                    "must": [text_query_clause],
                                    "filter": filters,
                                }
                            },
                            # Vector leg
                            {
                                "knn": {
                                    "embedding": {
                                        "vector": query_embedding,
                                        "k": settings.SEARCH_RRF_WINDOW_SIZE,
                                        "filter": {"bool": {"filter": filters}},
                                    }
                                }
                            },
                        ]
                    }
                },
                "highlight": {"fields": highlight_fields},
                "_source": [
                    "file_uuid",
                    "file_id",
                    "title",
                    "speaker",
                    "speakers",
                    "tags",
                    "start_time",
                    "end_time",
                    "chunk_index",
                    "upload_time",
                    "language",
                    "content",
                    "content_type",
                ],
            }
        else:
            search_body = self._build_bm25_only_body(query, filters, page_size, has_speaker_filter)

        return search_body

    def _build_bm25_only_body(
        self,
        query: str,
        filters: list[dict[str, Any]],
        page_size: int,
        has_speaker_filter: bool = False,
    ) -> dict[str, Any]:
        """Build a BM25-only search body for exact/keyword mode.

        Uses the content.exact subfield (standard analyzer, no stemming)
        for truly exact matching. No fuzziness.
        """
        fetch_size = page_size * 5

        # Dynamically set search fields based on speaker filter
        if has_speaker_filter:
            search_fields = [
                "content.exact^3",
                "title^2",
            ]
        else:
            search_fields = [
                "content.exact^3",
                "title^2",
                "speaker^3",
            ]

        # Build the text query clause (multi_match or match_all if no query)
        if query and query.strip():
            text_query_clause = {
                "multi_match": {
                    "query": query,
                    "fields": search_fields,
                    "type": "best_fields",
                }
            }
        else:
            # Empty query - use match_all (will only filter by speaker/tags/etc)
            text_query_clause = {"match_all": {}}

        # Build highlight fields (exclude speaker when using speaker filter)
        highlight_fields_bm25 = {
            "content.exact": {
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
                "fragment_size": 200,
                "number_of_fragments": 3,
            },
            "title": {
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
                "number_of_fragments": 0,
            },
        }
        if not has_speaker_filter:
            highlight_fields_bm25["speaker"] = {
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
                "number_of_fragments": 0,
            }

        return {
            "size": fetch_size,
            "query": {
                "bool": {
                    "must": [text_query_clause],
                    "filter": filters,
                }
            },
            "highlight": {"fields": highlight_fields_bm25},
            "_source": [
                "file_uuid",
                "file_id",
                "title",
                "speaker",
                "speakers",
                "tags",
                "start_time",
                "end_time",
                "chunk_index",
                "upload_time",
                "language",
                "content",
                "content_type",
            ],
        }

    def _group_results_by_file(  # noqa: C901
        self,
        response: dict[str, Any],
        query: str = "",
    ) -> list[SearchHit]:
        """Group OpenSearch hits by file_uuid into SearchHit objects."""
        hits_by_file: dict[str, SearchHit] = {}

        for hit in response.get("hits", {}).get("hits", []):
            score = hit.get("_score", 0.0) or 0.0
            if score < settings.SEARCH_HYBRID_MIN_SCORE:
                continue

            source = hit["_source"]
            file_uuid = source["file_uuid"]
            highlight = hit.get("highlight", {})

            snippet, match_type = _extract_snippet_and_match_type(source, highlight)
            title_highlighted = _extract_highlighted_field(highlight, "title")
            speaker_highlighted = _extract_highlighted_field(highlight, "speaker")

            # Classify: keyword match if highlight dict has any entries
            has_keyword_match = bool(highlight)

            # For semantic-only hits, highlight query words in snippet
            if not has_keyword_match and query:
                snippet = _add_semantic_highlights(snippet, query)

            occurrence = SearchOccurrence(
                snippet=snippet,
                speaker=source.get("speaker", ""),
                start_time=source.get("start_time", 0.0),
                end_time=source.get("end_time", 0.0),
                chunk_index=source.get("chunk_index", 0),
                score=score,
                match_type=match_type,
                speaker_highlighted=speaker_highlighted,
                has_keyword_match=has_keyword_match,
                highlight_type="keyword" if has_keyword_match else "semantic",
            )

            if file_uuid not in hits_by_file:
                hits_by_file[file_uuid] = SearchHit(
                    file_uuid=file_uuid,
                    file_id=source.get("file_id", 0),
                    title=source.get("title", ""),
                    speakers=source.get("speakers", []),
                    tags=source.get("tags", []),
                    upload_time=source.get("upload_time", ""),
                    language=source.get("language", ""),
                    content_type=source.get("content_type", ""),
                    relevance_score=score,
                    title_highlighted=title_highlighted,
                )

            file_hit = hits_by_file[file_uuid]

            if title_highlighted and not file_hit.title_highlighted:
                file_hit.title_highlighted = title_highlighted
            if len(file_hit.occurrences) < SEARCH_MAX_SNIPPETS_PER_FILE:
                file_hit.occurrences.append(occurrence)
            file_hit.total_occurrences += 1
            if has_keyword_match:
                file_hit.keyword_occurrences += 1
            if score > file_hit.relevance_score:
                file_hit.relevance_score = score

            # Track match sources from highlights
            if (
                "content" in highlight or "content.exact" in highlight
            ) and "content" not in file_hit.match_sources:
                file_hit.match_sources.append("content")
            if "title" in highlight and "title" not in file_hit.match_sources:
                file_hit.match_sources.append("title")
            if "speaker" in highlight and "speaker" not in file_hit.match_sources:
                file_hit.match_sources.append("speaker")

        # Post-process: sort occurrences so keyword matches surface first,
        # classify semantic-only files, and detect metadata speakers.
        for file_hit in hits_by_file.values():
            file_hit.occurrences.sort(
                key=lambda o: (not o.has_keyword_match, -o.score),
            )

        semantic_high_threshold = getattr(settings, "SEARCH_SEMANTIC_HIGH_CONFIDENCE", 0.015)
        query_lower = query.lower().strip() if query else ""
        for file_hit in hits_by_file.values():
            if file_hit.keyword_occurrences == 0:
                file_hit.semantic_only = True
                if "semantic" not in file_hit.match_sources:
                    file_hit.match_sources.append("semantic")
                if file_hit.relevance_score >= semantic_high_threshold:
                    file_hit.semantic_confidence = "high"
                else:
                    file_hit.semantic_confidence = "low"

            # Detect if query matches a speaker in this file (metadata match)
            if query_lower:
                for speaker_name in file_hit.speakers:
                    speaker_lower = speaker_name.lower()
                    if query_lower in speaker_lower or speaker_lower in query_lower:
                        if "metadata_speaker" not in file_hit.match_sources:
                            file_hit.match_sources.append("metadata_speaker")
                        break

        # Compute relevance_percent using observed score ranges for better spread.
        # Keyword and semantic results are scored on different RRF scales, so we
        # normalize each group independently against the scores actually present.
        all_hits = list(hits_by_file.values())
        kw_hits = [h for h in all_hits if not h.semantic_only]
        sem_hits = [h for h in all_hits if h.semantic_only]

        if kw_hits:
            kw_scores = [h.relevance_score for h in kw_hits]
            kw_min, kw_max = min(kw_scores), max(kw_scores)
            kw_range = kw_max - kw_min
            for h in kw_hits:
                if kw_range > 0:
                    # Map to 30-99%: even the weakest keyword match shows decent relevance
                    pct = (h.relevance_score - kw_min) / kw_range
                    h.relevance_percent = int(30 + pct * 69)
                else:
                    # Single keyword file or all same score
                    h.relevance_percent = 85

        if sem_hits:
            sem_scores = [h.relevance_score for h in sem_hits]
            sem_min, sem_max = min(sem_scores), max(sem_scores)
            sem_range = sem_max - sem_min
            for h in sem_hits:
                if sem_range > 0:
                    # Map to 15-80%: semantic matches cap below keyword range
                    pct = (h.relevance_score - sem_min) / sem_range
                    h.relevance_percent = int(15 + pct * 65)
                else:
                    h.relevance_percent = 50

        return list(hits_by_file.values())

    def _empty_response(self, query: str, page: int, page_size: int) -> SearchResponse:
        """Return an empty search response."""
        return SearchResponse(
            query=query,
            results=[],
            total_results=0,
            total_files=0,
            page=page,
            page_size=page_size,
            total_pages=0,
            search_time_ms=0.0,
        )
