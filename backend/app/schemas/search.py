"""Pydantic schemas for search API responses."""
from typing import Any

from pydantic import BaseModel
from pydantic import Field


class SearchOccurrenceSchema(BaseModel):
    """A single matching snippet within a file."""

    snippet: str = Field(..., description="Highlighted text snippet")
    speaker: str = Field("", description="Speaker name for this segment")
    start_time: float = Field(0.0, description="Start time in seconds")
    end_time: float = Field(0.0, description="End time in seconds")
    chunk_index: int = Field(0, description="Chunk index within the file")
    score: float = Field(0.0, description="Relevance score")
    match_type: str = Field("content", description="Match type: content, title, or speaker")
    has_keyword_match: bool = Field(True, description="False for semantic-only hits")
    highlight_type: str = Field("keyword", description="Highlight type: keyword or semantic")


class SearchHitSchema(BaseModel):
    """A file-level search result with multiple occurrences."""

    file_uuid: str = Field(..., description="File UUID")
    file_id: int = Field(..., description="File integer ID")
    title: str = Field("", description="File title")
    speakers: list[str] = Field(default_factory=list, description="All speakers in file")
    tags: list[str] = Field(default_factory=list, description="Tags on the file")
    upload_time: str = Field("", description="Upload timestamp ISO string")
    language: str = Field("", description="Language code")
    content_type: str = Field("", description="MIME content type (e.g. audio/mpeg, video/mp4)")
    relevance_score: float = Field(0.0, description="Best relevance score")
    occurrences: list[SearchOccurrenceSchema] = Field(
        default_factory=list, description="Matching snippets"
    )
    total_occurrences: int = Field(0, description="Total match count in file")
    title_highlighted: str = Field("", description="Title with highlight marks if matched")
    keyword_occurrences: int = Field(0, description="Count of keyword-matched occurrences")
    semantic_only: bool = Field(False, description="True if only semantic matches, no keywords")
    semantic_confidence: str = Field("", description="Semantic confidence: '', 'high', or 'low'")
    match_sources: list[str] = Field(
        default_factory=list, description="Match sources: content, title, speaker, semantic"
    )
    relevance_percent: int = Field(0, description="Relevance confidence 0-100 for display")


class SearchResponseSchema(BaseModel):
    """Complete search response."""

    query: str = Field(..., description="Original search query")
    results: list[SearchHitSchema] = Field(default_factory=list)
    total_results: int = Field(0, description="Total matching snippets")
    total_files: int = Field(0, description="Total matching files")
    page: int = Field(1, description="Current page number")
    page_size: int = Field(20, description="Results per page")
    total_pages: int = Field(0, description="Total number of pages")
    search_time_ms: float = Field(0.0, description="Search execution time in ms")
    filters_applied: dict[str, Any] = Field(default_factory=dict, description="Active filters")
    search_mode: str = Field("hybrid", description="Search mode: hybrid or keyword")


class SuggestionItemSchema(BaseModel):
    """Auto-complete suggestion item."""

    type: str = Field(..., description="Suggestion type: title, speaker, or content")
    text: str = Field(..., description="Suggestion text")
    file_uuid: str | None = Field(None, description="File UUID if type is title")
    count: int | None = Field(None, description="Match count if applicable")


class FilterOptionsSchema(BaseModel):
    """Available filter options for search."""

    speakers: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[dict[str, Any]] = Field(default_factory=list)
    date_range: dict[str, Any] = Field(default_factory=dict)


class ReindexRequestSchema(BaseModel):
    """Request to trigger re-indexing."""

    file_uuids: list[str] | None = Field(
        None, description="Specific file UUIDs to re-index (None = all)"
    )


class ReindexStatusSchema(BaseModel):
    """Re-indexing status response."""

    total_files: int = Field(0)
    indexed_files: int = Field(0)
    pending_files: int = Field(0)
    in_progress: bool = Field(False)
    current_model: str = Field("")
    current_dimension: int = Field(0)
    last_indexed_at: str | None = Field(None)


class EmbeddingModelSchema(BaseModel):
    """Embedding model info."""

    model_id: str
    name: str
    dimension: int
    description: str
    size_mb: int


class EmbeddingModelsResponseSchema(BaseModel):
    """Available embedding models response."""

    models: list[EmbeddingModelSchema]
    current_model_id: str
    current_dimension: int


class SetEmbeddingModelSchema(BaseModel):
    """Request to change embedding model."""

    model_id: str = Field(..., description="Model ID from the registry")
