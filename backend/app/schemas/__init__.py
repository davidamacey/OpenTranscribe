"""
Pydantic schemas for OpenTranscribe API.

This package contains validation schemas for request/response models.
"""

from .user import UserCreate, UserUpdate, User as UserSchema
from .media import (
    MediaFile, MediaFileDetail, MediaFileUpdate, 
    TranscriptSegment, TranscriptSegmentUpdate,
    Speaker, SpeakerUpdate,
    Comment, CommentCreate, CommentUpdate,
    Tag, TagBase
)

__all__ = [
    "UserCreate", "UserUpdate", "UserSchema",
    "MediaFile", "MediaFileDetail", "MediaFileUpdate",
    "TranscriptSegment", "TranscriptSegmentUpdate", 
    "Speaker", "SpeakerUpdate",
    "Comment", "CommentCreate", "CommentUpdate",
    "Tag", "TagBase"
]