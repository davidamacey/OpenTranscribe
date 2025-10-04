"""
Pydantic schemas for AI summarization functionality
"""

from datetime import datetime
from typing import Any
from typing import Literal
from typing import Optional
from typing import Union
from uuid import UUID

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator


class SpeakerInfo(BaseModel):
    name: str = Field(..., description="Speaker name or label")
    talk_time_seconds: Union[int, float] = Field(..., description="Total talk time in seconds")
    percentage: float = Field(..., description="Percentage of total talk time")
    key_points: list[str] = Field(..., description="Key points from this speaker")

    @field_validator("talk_time_seconds")
    @classmethod
    def convert_talk_time_to_int(cls, v):
        if isinstance(v, float):
            return int(round(v))
        return v


class ContentSection(BaseModel):
    time_range: str = Field(..., description="Time range for this section")
    topic: str = Field(..., description="Topic or title")
    key_points: list[str] = Field(..., description="Key discussion points")


class ActionItem(BaseModel):
    text: str = Field(..., description="Action item description")
    assigned_to: Optional[str] = Field(None, description="Person assigned")
    due_date: Optional[str] = Field(None, description="Due date in YYYY-MM-DD format")
    priority: Literal["high", "medium", "low"] = Field(..., description="Priority level")
    context: str = Field(..., description="Context about why this action is needed")
    status: Optional[Literal["pending", "completed", "cancelled"]] = Field("pending")


class SummaryMetadata(BaseModel):
    provider: str = Field(..., description="LLM provider used")
    model: str = Field(..., description="Model name")
    usage_tokens: Optional[int] = None
    transcript_length: int
    processing_time_ms: Optional[int] = None
    confidence_score: Optional[float] = None
    language: Optional[str] = None
    error: Optional[str] = None


class MajorTopic(BaseModel):
    topic: str
    importance: Literal["high", "medium", "low"]
    key_points: list[str]
    participants: list[str]


class SummaryData(BaseModel):
    bluf: str
    brief_summary: str
    major_topics: list[MajorTopic]
    action_items: list[ActionItem]
    key_decisions: list[str]
    follow_up_items: list[str]
    metadata: SummaryMetadata


class SummaryResponse(BaseModel):
    file_id: UUID  # Changed from int to UUID
    summary_data: SummaryData
    source: Literal["opensearch", "postgresql"]
    document_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SummarySearchRequest(BaseModel):
    query: Optional[str] = None
    speakers: Optional[list[str]] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    has_pending_actions: Optional[bool] = None
    size: int = 20
    offset: int = 0


class SummarySearchHit(BaseModel):
    document_id: str
    score: float
    file_id: UUID  # Changed from int to UUID
    bluf: str
    brief_summary: str
    created_at: str
    provider: str
    model: str
    highlights: Optional[dict[str, list[str]]] = None


class SummarySearchResponse(BaseModel):
    hits: list[SummarySearchHit]
    total: int
    max_score: Optional[float] = None
    query: Optional[str] = None
    filters: dict[str, Any]


class SummaryAnalyticsResponse(BaseModel):
    total_summaries: int
    speaker_stats: list[dict[str, Any]]
    action_items_trend: list[dict[str, Any]]
    common_topics: list[dict[str, Any]]
    summary_statistics: dict[str, Any]
    provider_usage: list[dict[str, Any]]


class SpeakerIdentificationResponse(BaseModel):
    message: str
    task_id: str
    file_id: UUID  # Changed from int to UUID
    speaker_count: int


class SummaryTaskRequest(BaseModel):
    force_regenerate: bool = False


class SummaryTaskStatus(BaseModel):
    task_id: str
    status: Literal["pending", "in_progress", "completed", "failed"]
    progress: Optional[float] = None
    error_message: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
