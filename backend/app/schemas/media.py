from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class FileStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class SpeakerBase(BaseModel):
    name: str


class SpeakerCreate(SpeakerBase):
    user_id: int
    embedding_vector: Optional[List[float]] = None


class SpeakerUpdate(BaseModel):
    name: Optional[str] = None
    embedding_vector: Optional[List[float]] = None


class Speaker(SpeakerBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


class MediaFileBase(BaseModel):
    filename: str
    user_id: int


class MediaFileCreate(MediaFileBase):
    storage_path: str
    duration: Optional[float] = None
    language: Optional[str] = None


class MediaFileUpdate(BaseModel):
    filename: Optional[str] = None
    status: Optional[FileStatus] = None
    summary: Optional[str] = None
    translated_text: Optional[str] = None
    duration: Optional[float] = None
    language: Optional[str] = None


class MediaFile(MediaFileBase):
    id: int
    storage_path: str
    upload_time: datetime
    duration: Optional[float] = None
    language: Optional[str] = None
    status: FileStatus
    summary: Optional[str] = None
    translated_text: Optional[str] = None
    download_url: Optional[str] = None
    preview_url: Optional[str] = None
    
    class Config:
        from_attributes = True


class MediaFileDetail(MediaFile):
    transcript_segments: List[TranscriptSegment] = []
    tags: List[str] = []

    class Config:
        from_attributes = True


class TagBase(BaseModel):
    name: str


class Tag(TagBase):
    id: int

    class Config:
        from_attributes = True


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
    # Add fields for user information
    user: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


class AnalyticsBase(BaseModel):
    speaker_stats: Optional[Dict[str, Any]] = None
    sentiment: Optional[Dict[str, Any]] = None
    keywords: Optional[List[str]] = None


class AnalyticsCreate(AnalyticsBase):
    media_file_id: int


class Analytics(AnalyticsBase):
    id: int
    media_file_id: int

    class Config:
        from_attributes = True
