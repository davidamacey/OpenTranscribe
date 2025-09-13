"""
Pydantic schemas for AI summarization functionality

Defines the request/response models for summary-related API endpoints.
"""

from datetime import datetime
from typing import Any
from typing import Literal
from typing import Optional
from typing import Union

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator


class SpeakerInfo(BaseModel):
    """Information about a speaker in the summary"""

    name: str = Field(..., description="Speaker name or label")
    talk_time_seconds: Union[int, float] = Field(..., description="Total talk time in seconds")
    percentage: float = Field(..., description="Percentage of total talk time")
    key_points: list[str] = Field(..., description="Key points or contributions from this speaker")

    @field_validator("talk_time_seconds")
    @classmethod
    def convert_talk_time_to_int(cls, v):
        """Convert float talk time to integer seconds"""
        if isinstance(v, float):
            return int(round(v))
        return v


class ContentSection(BaseModel):
    """A content section within the summary"""

    time_range: str = Field(..., description="Time range for this section (e.g., '00:05-00:15')")
    topic: str = Field(..., description="Topic or title of this section")
    key_points: list[str] = Field(..., description="Key discussion points in this section")


class ActionItem(BaseModel):
    """An action item extracted from the meeting"""

    text: str = Field(..., description="Description of the action item")
    assigned_to: Optional[str] = Field(None, description="Person assigned to this action")
    due_date: Optional[str] = Field(None, description="Due date in YYYY-MM-DD format")
    priority: Literal["high", "medium", "low"] = Field(..., description="Priority level")
    context: str = Field(..., description="Context about why this action is needed")
    status: Optional[Literal["pending", "completed", "cancelled"]] = Field(
        "pending", description="Current status"
    )


class SummaryMetadata(BaseModel):
    """Metadata about the summary generation process"""

    provider: str = Field(..., description="LLM provider used (vllm, openai, etc.)")
    model: str = Field(..., description="Model name used for generation")
    usage_tokens: Optional[int] = Field(None, description="Total tokens used")
    transcript_length: int = Field(..., description="Length of input transcript")
    processing_time_ms: Optional[int] = Field(None, description="Processing time in milliseconds")
    confidence_score: Optional[float] = Field(None, description="Overall confidence score")
    language: Optional[str] = Field(None, description="Detected language")
    error: Optional[str] = Field(None, description="Error message if generation failed")


class MajorTopic(BaseModel):
    """A major topic discussed in the content"""

    topic: str = Field(..., description="Topic title or subject")
    importance: Literal["high", "medium", "low"] = Field(
        ..., description="Importance level of this topic"
    )
    key_points: list[str] = Field(..., description="Key points discussed about this topic")
    participants: list[str] = Field(..., description="Speakers who contributed to this topic")


class SummaryData(BaseModel):
    """Complete structured summary data in BLUF format"""

    bluf: str = Field(..., description="Bottom Line Up Front - 2-3 sentence executive summary")
    brief_summary: str = Field(..., description="Comprehensive paragraph summary with context")
    major_topics: list[MajorTopic] = Field(..., description="Major topics and themes discussed")
    action_items: list[ActionItem] = Field(..., description="Extracted action items and tasks")
    key_decisions: list[str] = Field(..., description="Concrete decisions that were made")
    follow_up_items: list[str] = Field(..., description="Items requiring future attention")
    metadata: SummaryMetadata = Field(..., description="Generation metadata")


class SummaryResponse(BaseModel):
    """Response containing a file's summary"""

    file_id: int = Field(..., description="ID of the media file")
    summary_data: SummaryData = Field(..., description="The structured summary")
    source: Literal["opensearch", "postgresql"] = Field(..., description="Data source")
    document_id: Optional[str] = Field(None, description="OpenSearch document ID")
    created_at: Optional[datetime] = Field(None, description="When the summary was created")
    updated_at: Optional[datetime] = Field(None, description="When the summary was last updated")


class SummarySearchRequest(BaseModel):
    """Request for searching summaries"""

    query: Optional[str] = Field(None, description="Text to search for")
    speakers: Optional[list[str]] = Field(None, description="Filter by specific speakers")
    date_from: Optional[datetime] = Field(None, description="Start date filter")
    date_to: Optional[datetime] = Field(None, description="End date filter")
    has_pending_actions: Optional[bool] = Field(None, description="Filter by pending action items")
    size: int = Field(20, description="Number of results to return")
    offset: int = Field(0, description="Result offset for pagination")


class SummarySearchHit(BaseModel):
    """A single search result"""

    document_id: str = Field(..., description="OpenSearch document ID")
    score: float = Field(..., description="Relevance score")
    file_id: int = Field(..., description="Media file ID")
    bluf: str = Field(..., description="Executive summary")
    brief_summary: str = Field(..., description="Brief summary")
    created_at: str = Field(..., description="Creation timestamp")
    provider: str = Field(..., description="LLM provider used")
    model: str = Field(..., description="Model used")
    highlights: Optional[dict[str, list[str]]] = Field(
        None, description="Highlighted matching text"
    )


class SummarySearchResponse(BaseModel):
    """Response from summary search"""

    hits: list[SummarySearchHit] = Field(..., description="Search results")
    total: int = Field(..., description="Total number of matching documents")
    max_score: Optional[float] = Field(None, description="Highest relevance score")
    query: Optional[str] = Field(None, description="Original search query")
    filters: dict[str, Any] = Field(..., description="Applied filters")


class SummaryAnalyticsResponse(BaseModel):
    """Analytics data for user summaries"""

    total_summaries: int = Field(..., description="Total number of summaries")
    speaker_stats: list[dict[str, Any]] = Field(..., description="Speaker participation statistics")
    action_items_trend: list[dict[str, Any]] = Field(
        ..., description="Action item trends over time"
    )
    common_topics: list[dict[str, Any]] = Field(..., description="Most common discussion topics")
    summary_statistics: dict[str, Any] = Field(..., description="General summary statistics")
    provider_usage: list[dict[str, Any]] = Field(..., description="LLM provider usage statistics")


class SpeakerIdentificationResponse(BaseModel):
    """Response from speaker identification task"""

    message: str = Field(..., description="Status message")
    task_id: str = Field(..., description="Celery task ID")
    file_id: int = Field(..., description="Media file ID")
    speaker_count: int = Field(..., description="Number of speakers to identify")


class SummaryTaskRequest(BaseModel):
    """Request to trigger summarization task"""

    force_regenerate: bool = Field(False, description="Force regeneration of existing summary")


class SummaryTaskStatus(BaseModel):
    """Status of a summary generation task"""

    task_id: str = Field(..., description="Celery task ID")
    status: Literal["pending", "in_progress", "completed", "failed"] = Field(
        ..., description="Task status"
    )
    progress: Optional[float] = Field(None, description="Progress percentage (0-1)")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    result: Optional[dict[str, Any]] = Field(None, description="Task result if completed")
    created_at: datetime = Field(..., description="When the task was created")
    updated_at: datetime = Field(..., description="Last update time")
