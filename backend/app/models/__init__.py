"""
SQLAlchemy ORM models for OpenTranscribe.

This package contains database models for all entities in the system.
"""

from .auth_config import AuthConfig
from .auth_config import AuthConfigAudit
from .group import UserGroup
from .group import UserGroupMember
from .media import Analytics
from .media import Collection
from .media import CollectionMember
from .media import Comment
from .media import FileStatus
from .media import FileTag
from .media import MediaFile
from .media import Speaker
from .media import SpeakerCluster
from .media import SpeakerClusterMember
from .media import SpeakerCollection
from .media import SpeakerCollectionMember
from .media import SpeakerMatch
from .media import SpeakerProfile
from .media import Tag
from .media import Task
from .media import TranscriptSegment
from .password_history import PasswordHistory
from .prompt import SummaryPrompt
from .prompt import UserSetting
from .refresh_token import RefreshToken
from .sharing import CollectionShare
from .topic import TopicSuggestion
from .user import User
from .user_llm_settings import UserLLMSettings
from .user_mfa import UserMFA

__all__ = [
    "User",
    "MediaFile",
    "TranscriptSegment",
    "FileTag",
    "Tag",
    "Speaker",
    "SpeakerProfile",
    "Comment",
    "Task",
    "FileStatus",
    "Analytics",
    "Collection",
    "CollectionMember",
    "SpeakerCluster",
    "SpeakerClusterMember",
    "SpeakerMatch",
    "SpeakerCollection",
    "SpeakerCollectionMember",
    "SummaryPrompt",
    "UserSetting",
    "UserLLMSettings",
    "TopicSuggestion",
    "RefreshToken",
    "UserMFA",
    "PasswordHistory",
    "AuthConfig",
    "AuthConfigAudit",
    "UserGroup",
    "UserGroupMember",
    "CollectionShare",
]
