"""
Pydantic schemas for OpenTranscribe API.

This package contains validation schemas for request/response models.
"""

from .auth_config import AuthConfigAuditResponse
from .auth_config import AuthConfigBase
from .auth_config import AuthConfigCategoryResponse
from .auth_config import AuthConfigCreate
from .auth_config import AuthConfigResponse
from .auth_config import AuthConfigStatusResponse
from .auth_config import AuthConfigUpdate
from .auth_config import AuthMethodTestRequest
from .auth_config import AuthMethodTestResponse
from .auth_config import BulkConfigUpdate
from .auth_config import KeycloakConfig
from .auth_config import LDAPConfig
from .auth_config import LoginBannerConfig
from .auth_config import MFAConfig
from .auth_config import PasswordPolicyConfig
from .auth_config import PKIConfig
from .auth_config import SessionConfig
from .download_settings import DownloadSettings
from .download_settings import DownloadSettingsUpdate
from .download_settings import DownloadSystemDefaults
from .llm_settings import ConnectionStatus
from .llm_settings import ConnectionTestRequest
from .llm_settings import ConnectionTestResponse
from .llm_settings import LLMProvider
from .llm_settings import LLMSettingsStatus
from .llm_settings import ProviderDefaults
from .llm_settings import SetActiveConfigRequest
from .llm_settings import SupportedProvidersResponse
from .llm_settings import UserLLMConfigurationsList
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
from .prompt import LinkedCollection
from .prompt import SummaryPrompt
from .prompt import SummaryPromptBase
from .prompt import SummaryPromptCreate
from .prompt import SummaryPromptList
from .prompt import SummaryPromptUpdate
from .prompt import SummaryPromptWithCollections
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
from .transcription_settings import TranscriptionSettings
from .transcription_settings import TranscriptionSettingsUpdate
from .transcription_settings import TranscriptionSystemDefaults
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
    "SummaryPromptWithCollections",
    "LinkedCollection",
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
    "UserLLMConfigurationsList",
    "SetActiveConfigRequest",
    "ConnectionTestRequest",
    "ConnectionTestResponse",
    "ProviderDefaults",
    "SupportedProvidersResponse",
    "LLMSettingsStatus",
    "TranscriptionSettings",
    "TranscriptionSettingsUpdate",
    "TranscriptionSystemDefaults",
    # Auth config schemas
    "AuthConfigBase",
    "AuthConfigCreate",
    "AuthConfigUpdate",
    "AuthConfigResponse",
    "AuthConfigAuditResponse",
    "AuthConfigCategoryResponse",
    "AuthConfigStatusResponse",
    "AuthMethodTestRequest",
    "AuthMethodTestResponse",
    "BulkConfigUpdate",
    "LDAPConfig",
    "KeycloakConfig",
    "PKIConfig",
    "PasswordPolicyConfig",
    "MFAConfig",
    "SessionConfig",
    "LoginBannerConfig",
    # Download settings schemas
    "DownloadSettings",
    "DownloadSettingsUpdate",
    "DownloadSystemDefaults",
]
