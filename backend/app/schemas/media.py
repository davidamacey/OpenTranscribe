from datetime import datetime
from enum import Enum
from typing import Any
from typing import Optional

from pydantic import BaseModel
from pydantic import Field


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


class PrepareUploadRequest(BaseModel):
    """Request schema for preparing a file upload.

    This schema is used to create a file record before the actual upload starts.

    Attributes:
        filename: Name of the file to be uploaded
        file_size: Size of the file in bytes
        content_type: MIME type of the file
        file_hash: SHA-256 hash of the file for duplicate detection
    """

    filename: str = Field(..., description="Name of the file to be uploaded")
    file_size: int = Field(..., description="Size of the file in bytes")
    content_type: str = Field(..., description="MIME type of the file")
    file_hash: Optional[str] = Field(
        None, description="SHA-256 hash of the file for duplicate detection"
    )


class SpeakerBase(BaseModel):
    name: str
    display_name: Optional[str] = None
    suggested_name: Optional[str] = None
    uuid: str  # Non-optional to match database NOT NULL constraint
    verified: bool = False


class SpeakerCreate(SpeakerBase):
    user_id: int
    media_file_id: int
    embedding_vector: Optional[list[float]] = None


class SpeakerUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    suggested_name: Optional[str] = None
    verified: Optional[bool] = None
    embedding_vector: Optional[list[float]] = None


class Speaker(SpeakerBase):
    id: int
    user_id: int
    media_file_id: int
    profile_id: Optional[int] = None
    confidence: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# Speaker Profile schemas
class SpeakerProfileBase(BaseModel):
    name: str
    description: Optional[str] = None


class SpeakerProfileCreate(SpeakerProfileBase):
    pass


class SpeakerProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class SpeakerProfile(SpeakerProfileBase):
    id: int
    user_id: int
    uuid: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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


class SpeakerCollection(SpeakerCollectionBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TranscriptSegmentBase(BaseModel):
    start_time: float
    end_time: float
    text: str
    speaker_id: Optional[int] = None


class TranscriptSegmentCreate(TranscriptSegmentBase):
    media_file_id: int


class TranscriptSegmentUpdate(BaseModel):
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    text: Optional[str] = None
    speaker_id: Optional[int] = None


class TranscriptSegment(TranscriptSegmentBase):
    id: int
    media_file_id: int
    speaker: Optional[Speaker] = None

    model_config = {"from_attributes": True}


class MediaFileBase(BaseModel):
    filename: str
    user_id: int


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
    summary: Optional[str] = None
    translated_text: Optional[str] = None
    duration: Optional[float] = None
    language: Optional[str] = None
    file_hash: Optional[str] = None
    thumbnail_path: Optional[str] = None


class MediaFile(MediaFileBase):
    id: int
    storage_path: str
    upload_time: datetime
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    duration: Optional[float] = None
    language: Optional[str] = None
    status: FileStatus
    summary: Optional[str] = None
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

    model_config = {"from_attributes": True}


class MediaFileDetail(MediaFile):
    transcript_segments: list[TranscriptSegment] = []
    tags: list[str] = []
    collections: list["Collection"] = []

    model_config = {"from_attributes": True}


class TagBase(BaseModel):
    name: str


class Tag(TagBase):
    id: int

    model_config = {"from_attributes": True}


class CommentBase(BaseModel):
    text: str
    timestamp: Optional[float] = None


class CommentCreate(CommentBase):
    media_file_id: int
    user_id: Optional[int] = None


class CommentUpdate(BaseModel):
    text: Optional[str] = None
    timestamp: Optional[float] = None


class Comment(CommentBase):
    id: int
    media_file_id: int
    user_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class MediaFileInfo(BaseModel):
    """Schema for simplified media file information that gets included in tasks"""

    id: int
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
    media_file_id: Optional[int] = None


class TaskCreate(TaskBase):
    id: str  # Celery task ID
    user_id: int


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    progress: Optional[float] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class Task(TaskBase):
    id: str
    user_id: int
    progress: float
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    media_file: Optional[MediaFileInfo] = None

    model_config = {"from_attributes": True}


class AnalyticsBase(BaseModel):
    speaker_stats: Optional[dict[str, Any]] = None
    sentiment: Optional[dict[str, Any]] = None
    keywords: Optional[list[str]] = None


class AnalyticsCreate(AnalyticsBase):
    media_file_id: int


class Analytics(AnalyticsBase):
    id: int
    media_file_id: int

    model_config = {"from_attributes": True}


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


class Collection(CollectionBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CollectionWithCount(Collection):
    media_count: int = 0


class CollectionResponse(Collection):
    media_files: Optional[list[MediaFile]] = []


class CollectionMemberAdd(BaseModel):
    media_file_ids: list[int]


class CollectionMemberRemove(BaseModel):
    media_file_ids: list[int]


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
