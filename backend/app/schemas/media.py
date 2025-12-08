from datetime import datetime
from enum import Enum
from typing import Any
from typing import Optional
from uuid import UUID

from pydantic import BaseModel
from pydantic import Field

from app.schemas.base import UUIDBaseSchema


class FileStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    ORPHANED = "orphaned"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ReprocessRequest(BaseModel):
    """Request schema for reprocessing a file with optional speaker diarization settings.

    Attributes:
        min_speakers: Optional minimum number of speakers for diarization
        max_speakers: Optional maximum number of speakers for diarization
        num_speakers: Optional fixed number of speakers for diarization (overrides min/max)
    """

    min_speakers: Optional[int] = Field(
        None, description="Minimum number of speakers for diarization (positive integer)"
    )
    max_speakers: Optional[int] = Field(
        None, description="Maximum number of speakers for diarization (positive integer)"
    )
    num_speakers: Optional[int] = Field(
        None, description="Fixed number of speakers for diarization (overrides min/max when set)"
    )


class PrepareUploadRequest(BaseModel):
    """Request schema for preparing a file upload.

    This schema is used to create a file record before the actual upload starts.

    Attributes:
        filename: Name of the file to be uploaded
        file_size: Size of the file in bytes
        content_type: MIME type of the file
        file_hash: SHA-256 hash of the file for duplicate detection
        extracted_from_video: Optional metadata from original video file (if audio was extracted client-side)
        min_speakers: Optional minimum number of speakers for diarization
        max_speakers: Optional maximum number of speakers for diarization
        num_speakers: Optional fixed number of speakers for diarization (overrides min/max)
    """

    filename: str = Field(..., description="Name of the file to be uploaded")
    file_size: int = Field(..., description="Size of the file in bytes")
    content_type: str = Field(..., description="MIME type of the file")
    file_hash: Optional[str] = Field(
        None, description="SHA-256 hash of the file for duplicate detection"
    )
    extracted_from_video: Optional[dict[str, Any]] = Field(
        None, description="Metadata from original video file if audio was extracted client-side"
    )
    min_speakers: Optional[int] = Field(
        None, description="Minimum number of speakers for diarization (positive integer)"
    )
    max_speakers: Optional[int] = Field(
        None, description="Maximum number of speakers for diarization (positive integer)"
    )
    num_speakers: Optional[int] = Field(
        None, description="Fixed number of speakers for diarization (overrides min/max when set)"
    )


class SpeakerBase(BaseModel):
    name: str
    display_name: Optional[str] = None
    suggested_name: Optional[str] = None
    verified: bool = False


class SpeakerCreate(SpeakerBase):
    embedding_vector: Optional[list[float]] = None


class SpeakerUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    suggested_name: Optional[str] = None
    verified: Optional[bool] = None
    embedding_vector: Optional[list[float]] = None
    profile_action: Optional[str] = None  # 'update_profile' or 'create_new_profile'


class Speaker(SpeakerBase, UUIDBaseSchema):
    """Speaker with UUID as public identifier"""

    user_id: UUID
    media_file_id: UUID
    profile_id: Optional[UUID] = None
    confidence: Optional[float] = None
    created_at: datetime

    # Computed status fields from SpeakerStatusService
    computed_status: Optional[str] = None  # "verified", "suggested", "unverified"
    status_text: Optional[str] = None  # Human-readable status text
    status_color: Optional[str] = None  # CSS color for status display
    resolved_display_name: Optional[str] = None  # Best available display name


# Speaker Profile schemas
class SpeakerProfileBase(BaseModel):
    name: str
    description: Optional[str] = None


class SpeakerProfileCreate(SpeakerProfileBase):
    pass


class SpeakerProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class SpeakerProfile(SpeakerProfileBase, UUIDBaseSchema):
    """Speaker profile with UUID as public identifier"""

    user_id: UUID
    created_at: datetime
    updated_at: datetime


# Speaker Collection schemas
class SpeakerCollectionBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_public: bool = False


class SpeakerCollectionCreate(SpeakerCollectionBase):
    pass


class SpeakerCollectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None


class SpeakerCollection(SpeakerCollectionBase, UUIDBaseSchema):
    """Speaker collection with UUID as public identifier"""

    user_id: UUID
    created_at: datetime
    updated_at: datetime


class TranscriptSegmentBase(BaseModel):
    start_time: float
    end_time: float
    text: str
    speaker_id: Optional[UUID] = None


class TranscriptSegmentCreate(TranscriptSegmentBase):
    pass  # media_file_id will be from URL path


class TranscriptSegmentUpdate(BaseModel):
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    text: Optional[str] = None
    speaker_id: Optional[UUID] = None


class TranscriptSegment(TranscriptSegmentBase, UUIDBaseSchema):
    """Transcript segment with UUID as public identifier"""

    media_file_id: UUID
    speaker: Optional[Speaker] = None

    # Formatted fields for frontend display
    formatted_timestamp: Optional[str] = None  # e.g., "0:45.2"
    display_timestamp: Optional[str] = None  # e.g., "0:45.2" for transcript UI
    speaker_label: Optional[
        str
    ] = None  # ALWAYS original speaker ID (e.g., "SPEAKER_01") for color consistency
    resolved_speaker_name: Optional[str] = None  # Display name (user label or original ID)


class MediaFileBase(BaseModel):
    filename: str


class MediaFileCreate(MediaFileBase):
    storage_path: str
    duration: Optional[float] = None
    language: Optional[str] = None
    file_hash: Optional[str] = None
    thumbnail_path: Optional[str] = None


class MediaFileUpdate(BaseModel):
    filename: Optional[str] = None
    title: Optional[str] = None
    status: Optional[FileStatus] = None
    summary_data: Optional[dict[str, Any]] = None
    translated_text: Optional[str] = None
    duration: Optional[float] = None
    language: Optional[str] = None
    file_hash: Optional[str] = None
    thumbnail_path: Optional[str] = None


class MediaFile(MediaFileBase, UUIDBaseSchema):
    """Media file with UUID as public identifier"""

    user_id: UUID
    storage_path: str
    upload_time: datetime
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    duration: Optional[float] = None
    language: Optional[str] = None
    status: FileStatus
    summary_data: Optional[dict[str, Any]] = None
    translated_text: Optional[str] = None
    download_url: Optional[str] = None
    preview_url: Optional[str] = None
    file_hash: Optional[str] = None
    thumbnail_path: Optional[str] = None
    thumbnail_url: Optional[str] = None

    # Technical metadata
    media_format: Optional[str] = None
    codec: Optional[str] = None
    resolution_width: Optional[int] = None
    resolution_height: Optional[int] = None
    frame_rate: Optional[float] = None
    frame_count: Optional[int] = None
    aspect_ratio: Optional[str] = None

    # Audio specs
    audio_channels: Optional[int] = None
    audio_sample_rate: Optional[int] = None
    audio_bit_depth: Optional[int] = None

    # Creation and device information
    creation_date: Optional[datetime] = None
    last_modified_date: Optional[datetime] = None
    device_make: Optional[str] = None
    device_model: Optional[str] = None

    # Content information
    title: Optional[str] = None
    author: Optional[str] = None
    description: Optional[str] = None
    source_url: Optional[str] = None

    # Formatted fields for frontend display
    formatted_duration: Optional[str] = None  # e.g., "5:23"
    formatted_upload_date: Optional[str] = None  # e.g., "Oct 15, 2024"
    formatted_file_age: Optional[str] = None  # e.g., "2 hours ago"
    formatted_file_size: Optional[str] = None  # e.g., "2.5 MB"
    display_status: Optional[str] = None  # User-friendly status text
    status_badge_class: Optional[str] = None  # CSS class for status styling

    # Error handling fields
    error_category: Optional[str] = None  # Error category for user-friendly handling
    error_suggestions: Optional[list[str]] = None  # User-friendly error suggestions
    is_retryable: Optional[bool] = None  # Whether the error is retryable


class MediaFileDetail(MediaFile):
    transcript_segments: list[TranscriptSegment] = []
    tags: list[str] = []
    collections: list["Collection"] = []
    analytics: Optional["Analytics"] = None
    speakers: list[Speaker] = []

    # Additional formatted fields for detail view
    speaker_summary: Optional[dict[str, Any]] = None  # Speaker count and primary speakers

    # Transcript pagination metadata
    total_segments: Optional[int] = None  # Total number of transcript segments
    segment_limit: Optional[int] = None  # Max segments returned (None = all)
    segment_offset: Optional[int] = None  # Offset for pagination


class TagBase(BaseModel):
    name: str


class Tag(TagBase, UUIDBaseSchema):
    """Tag with UUID as public identifier"""


class TagWithCount(Tag):
    """Tag with usage count for filtering UI"""

    usage_count: int = 0


class CommentBase(BaseModel):
    text: str
    timestamp: Optional[float] = None


class CommentCreate(CommentBase):
    pass  # media_file_id will be from URL path


class CommentUpdate(BaseModel):
    text: Optional[str] = None
    timestamp: Optional[float] = None


class Comment(CommentBase, UUIDBaseSchema):
    """Comment with UUID as public identifier"""

    media_file_id: UUID
    user_id: UUID
    created_at: datetime


class MediaFileInfo(BaseModel):
    """Schema for simplified media file information that gets included in tasks"""

    id: UUID
    filename: str
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    duration: Optional[float] = None
    language: Optional[str] = None
    format: Optional[str] = None
    media_format: Optional[str] = None
    codec: Optional[str] = None
    upload_time: Optional[datetime] = None


class TaskBase(BaseModel):
    task_type: str
    status: str
    media_file_id: Optional[UUID] = None


class TaskCreate(TaskBase):
    id: str  # Celery task ID (string, not UUID)
    user_id: UUID


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    progress: Optional[float] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class Task(TaskBase):
    """Task schema - uses Celery task ID (string), not UUID"""

    id: str  # Celery task ID
    user_id: UUID
    progress: float
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    media_file: Optional[MediaFileInfo] = None

    # Computed fields for frontend display
    age_category: Optional[str] = None  # "today", "week", "month", "older"
    formatted_duration: Optional[str] = None  # e.g., "5m", "1h 23m"
    status_display: Optional[str] = None  # Human-readable status

    model_config = {"from_attributes": True}


# Analytics-related schemas
class SpeakerTimeStats(BaseModel):
    by_speaker: dict[str, float] = {}
    total: float = 0.0


class InterruptionStats(BaseModel):
    by_speaker: dict[str, int] = {}
    total: int = 0


class TurnTakingStats(BaseModel):
    by_speaker: dict[str, int] = {}
    total_turns: int = 0


class QuestionStats(BaseModel):
    by_speaker: dict[str, int] = {}
    total: int = 0


class OverallAnalytics(BaseModel):
    word_count: int = 0
    duration_seconds: float = 0.0
    talk_time: SpeakerTimeStats = SpeakerTimeStats()
    interruptions: InterruptionStats = InterruptionStats()
    turn_taking: TurnTakingStats = TurnTakingStats()
    questions: QuestionStats = QuestionStats()
    speaking_pace: Optional[float] = None  # words per minute
    silence_ratio: Optional[float] = None  # ratio of silence


class AnalyticsBase(BaseModel):
    overall_analytics: Optional[OverallAnalytics] = None


class AnalyticsCreate(AnalyticsBase):
    pass  # media_file_id will be from context


class Analytics(AnalyticsBase, UUIDBaseSchema):
    """Analytics with UUID as public identifier"""

    media_file_id: UUID
    computed_at: Optional[datetime] = None
    version: Optional[str] = None


# Collection schemas
class CollectionBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_public: bool = False


class CollectionCreate(CollectionBase):
    pass


class CollectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None


class Collection(CollectionBase, UUIDBaseSchema):
    """Collection with UUID as public identifier"""

    user_id: UUID
    created_at: datetime
    updated_at: datetime


class CollectionWithCount(Collection):
    media_count: int = 0


class CollectionResponse(Collection):
    media_files: Optional[list[MediaFile]] = []


class CollectionMemberAdd(BaseModel):
    media_file_ids: list[UUID]  # Changed from int to UUID


class CollectionMemberRemove(BaseModel):
    media_file_ids: list[UUID]  # Changed from int to UUID


# Subtitle-related schemas
class SubtitleFormat(str, Enum):
    SRT = "srt"
    WEBVTT = "webvtt"
    MOV_TEXT = "mov_text"


class VideoFormat(str, Enum):
    MP4 = "mp4"
    MKV = "mkv"
    WEBM = "webm"


class SubtitleRequest(BaseModel):
    """Request schema for generating subtitles."""

    include_speakers: bool = Field(True, description="Include speaker labels in subtitles")
    format: SubtitleFormat = Field(SubtitleFormat.SRT, description="Subtitle format")


class VideoWithSubtitlesRequest(BaseModel):
    """Request schema for video with embedded subtitles."""

    output_format: Optional[VideoFormat] = Field(
        None, description="Output video format (auto-detect if not specified)"
    )
    include_speakers: bool = Field(True, description="Include speaker labels in subtitles")
    force_regenerate: bool = Field(
        False, description="Force regeneration even if cached version exists"
    )


class VideoWithSubtitlesResponse(BaseModel):
    """Response schema for video with embedded subtitles."""

    download_url: str = Field(..., description="URL to download the video with embedded subtitles")
    format: str = Field(..., description="Video format")
    cache_key: str = Field(..., description="Cache key for the processed video")
    expires_at: datetime = Field(..., description="When the download URL expires")
    file_size: Optional[int] = Field(None, description="Size of the processed video file")


class SubtitleValidationResult(BaseModel):
    """Result of subtitle validation."""

    is_valid: bool = Field(..., description="Whether subtitles are valid")
    issues: list[str] = Field(default_factory=list, description="List of validation issues found")
    total_segments: int = Field(..., description="Total number of subtitle segments")
    total_duration: float = Field(..., description="Total duration of subtitles in seconds")
