from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.base import Base

# Enum for file status
class FileStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class MediaFile(Base):
    __tablename__ = "media_file"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    filename = Column(String, index=True)
    storage_path = Column(String, nullable=False)  # Path in MinIO/S3
    upload_time = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)  # When processing completed
    duration = Column(Float, nullable=True)  # Duration in seconds
    file_size = Column(Integer, nullable=False)  # Size in bytes
    content_type = Column(String, nullable=False)  # MIME type
    is_public = Column(Boolean, default=False)  # Whether file is publicly accessible
    language = Column(String, nullable=True)  # Detected language code
    status = Column(Enum(FileStatus), default=FileStatus.PENDING)
    summary = Column(Text, nullable=True)
    translated_text = Column(Text, nullable=True)  # For non-English transcripts
    
    # Detailed metadata fields
    metadata_raw = Column(JSON, nullable=True)  # Complete raw metadata from extraction
    metadata_important = Column(JSON, nullable=True)  # Important metadata for display
    
    # Media technical specs
    media_format = Column(String, nullable=True)  # Container format (MP4, MOV, etc.)
    codec = Column(String, nullable=True)  # Codec used (H.264, AAC, etc.)
    frame_rate = Column(Float, nullable=True)  # Frames per second for video
    frame_count = Column(Integer, nullable=True)  # Total frames for video
    resolution_width = Column(Integer, nullable=True)  # Video width in pixels
    resolution_height = Column(Integer, nullable=True)  # Video height in pixels
    aspect_ratio = Column(String, nullable=True)  # Aspect ratio (16:9, etc.)
    
    # Audio specs
    audio_channels = Column(Integer, nullable=True)  # Number of audio channels
    audio_sample_rate = Column(Integer, nullable=True)  # Audio sample rate (Hz)
    audio_bit_depth = Column(Integer, nullable=True)  # Audio bit depth
    
    # Creation information
    creation_date = Column(DateTime(timezone=True), nullable=True)  # Original creation date
    last_modified_date = Column(DateTime(timezone=True), nullable=True)  # Last modified date
    
    # Device information
    device_make = Column(String, nullable=True)  # Device manufacturer
    device_model = Column(String, nullable=True)  # Device model
    
    # Content information
    title = Column(String, nullable=True)  # Content title from metadata
    author = Column(String, nullable=True)  # Content author/artist
    description = Column(Text, nullable=True)  # Content description
    
    # Relationships
    user = relationship("User", back_populates="media_files")
    transcript_segments = relationship("TranscriptSegment", back_populates="media_file", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="media_file", cascade="all, delete-orphan")
    file_tags = relationship("FileTag", back_populates="media_file", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="media_file", cascade="all, delete-orphan")
    analytics = relationship("Analytics", back_populates="media_file", uselist=False, cascade="all, delete-orphan")


class TranscriptSegment(Base):
    __tablename__ = "transcript_segment"

    id = Column(Integer, primary_key=True, index=True)
    media_file_id = Column(Integer, ForeignKey("media_file.id"), nullable=False)
    speaker_id = Column(Integer, ForeignKey("speaker.id"), nullable=True)
    start_time = Column(Float, nullable=False)  # Start time in seconds
    end_time = Column(Float, nullable=False)  # End time in seconds
    text = Column(Text, nullable=False)
    
    # Relationships
    media_file = relationship("MediaFile", back_populates="transcript_segments")
    speaker = relationship("Speaker", back_populates="transcript_segments")


class Speaker(Base):
    __tablename__ = "speaker"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    name = Column(String, nullable=False)  # Original name from diarization (e.g., "SPEAKER_01")
    display_name = Column(String, nullable=True)  # User-assigned name (e.g., "John Doe")
    uuid = Column(String, nullable=False, index=True)  # Unique identifier for the speaker
    embedding_vector = Column(JSON, nullable=True)  # Speaker embedding as JSON array
    verified = Column(Boolean, default=False)  # Flag to indicate if the speaker has been verified by a user
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="speakers")
    transcript_segments = relationship("TranscriptSegment", back_populates="speaker")


class Comment(Base):
    __tablename__ = "comment"

    id = Column(Integer, primary_key=True, index=True)
    media_file_id = Column(Integer, ForeignKey("media_file.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    text = Column(Text, nullable=False)
    timestamp = Column(Float, nullable=True)  # Timestamp in seconds, null for general comments
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    media_file = relationship("MediaFile", back_populates="comments")
    user = relationship("User", back_populates="comments")


class Tag(Base):
    __tablename__ = "tag"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)


class FileTag(Base):
    __tablename__ = "file_tag"

    media_file_id = Column(Integer, ForeignKey("media_file.id"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tag.id"), primary_key=True)
    
    # Relationships
    media_file = relationship("MediaFile", back_populates="file_tags")
    tag = relationship("Tag")


class Task(Base):
    __tablename__ = "task"

    id = Column(String, primary_key=True)  # Celery task ID
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    media_file_id = Column(Integer, ForeignKey("media_file.id"), nullable=True)
    task_type = Column(String, nullable=False)  # E.g., "transcription", "summarization"
    status = Column(String, nullable=False)  # "pending", "in_progress", "completed", "failed"
    progress = Column(Float, default=0.0)  # Progress as percentage
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Relationships
    user = relationship("User")
    media_file = relationship("MediaFile", back_populates="tasks")


class Analytics(Base):
    __tablename__ = "analytics"

    id = Column(Integer, primary_key=True, index=True)
    media_file_id = Column(Integer, ForeignKey("media_file.id"), unique=True)
    speaker_stats = Column(JSON, nullable=True)  # Speaker talk times and stats
    sentiment = Column(JSON, nullable=True)  # Overall or per-speaker sentiment
    keywords = Column(JSON, nullable=True)  # Extracted keywords/topics
    
    # Relationships
    media_file = relationship("MediaFile", back_populates="analytics")
