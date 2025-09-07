"""
Pydantic schemas for OpenTranscribe API.

This package contains validation schemas for request/response models.
"""

from .llm_settings import ConnectionStatus
from .llm_settings import ConnectionTestRequest
from .llm_settings import ConnectionTestResponse
from .llm_settings import LLMProvider
from .llm_settings import LLMSettingsStatus
from .llm_settings import ProviderDefaults
from .llm_settings import SupportedProvidersResponse
from .llm_settings import UserLLMSettings
from .llm_settings import UserLLMSettingsCreate
from .llm_settings import UserLLMSettingsPublic
from .llm_settings import UserLLMSettingsUpdate
from .media import Comment
from .media import CommentCreate
from .media import CommentUpdate
from .media import MediaFile
from .media import MediaFileDetail
from .media import MediaFileUpdate
from .media import Speaker
from .media import SpeakerUpdate
from .media import Tag
from .media import TagBase
from .media import TranscriptSegment
from .media import TranscriptSegmentUpdate
from .prompt import ActivePromptResponse
from .prompt import ActivePromptSelection
from .prompt import ContentTypePromptsResponse
from .prompt import SummaryPrompt
from .prompt import SummaryPromptBase
from .prompt import SummaryPromptCreate
from .prompt import SummaryPromptList
from .prompt import SummaryPromptUpdate
from .prompt import UserSetting
from .prompt import UserSettingBase
from .prompt import UserSettingCreate
from .prompt import UserSettingsList
from .prompt import UserSettingUpdate
from .summary import ActionItem
from .summary import MajorTopic
from .summary import SummaryData
from .summary import SummaryResponse
from .summary import SummarySearchHit
from .summary import SummarySearchResponse
from .summary import SummaryTaskStatus
from .user import User as UserSchema
from .user import UserCreate
from .user import UserUpdate

__all__ = [
    "UserCreate",
    "UserUpdate",
    "UserSchema",
    "MediaFile",
    "MediaFileDetail",
    "MediaFileUpdate",
    "TranscriptSegment",
    "TranscriptSegmentUpdate",
    "Speaker",
    "SpeakerUpdate",
    "Comment",
    "CommentCreate",
    "CommentUpdate",
    "Tag",
    "TagBase",
    "SummaryData",
    "SummaryResponse",
    "MajorTopic",
    "ActionItem",
    "SummarySearchHit",
    "SummarySearchResponse",
    "SummaryTaskStatus",
    "SummaryPromptBase",
    "SummaryPromptCreate",
    "SummaryPromptUpdate",
    "SummaryPrompt",
    "SummaryPromptList",
    "UserSettingBase",
    "UserSettingCreate",
    "UserSettingUpdate",
    "UserSetting",
    "UserSettingsList",
    "ActivePromptSelection",
    "ActivePromptResponse",
    "ContentTypePromptsResponse",
    "LLMProvider",
    "ConnectionStatus",
    "UserLLMSettings",
    "UserLLMSettingsCreate",
    "UserLLMSettingsUpdate",
    "UserLLMSettingsPublic",
    "ConnectionTestRequest",
    "ConnectionTestResponse",
    "ProviderDefaults",
    "SupportedProvidersResponse",
    "LLMSettingsStatus",
]
