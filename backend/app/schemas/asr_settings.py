"""
Pydantic schemas for user ASR settings
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.schemas.base import UUIDBaseSchema


class ASRProvider(str, Enum):
    """Supported ASR providers"""

    DEEPGRAM = "deepgram"
    WHISPERX = "whisperx"


class ConnectionStatus(str, Enum):
    """Connection test status"""

    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    UNTESTED = "untested"


class UserASRSettingsBase(BaseModel):
    """Base schema for user ASR settings"""

    name: str
    provider: ASRProvider
    model_name: str
    is_active: bool = True


class UserASRSettingsCreate(UserASRSettingsBase):
    """Schema for creating user ASR settings"""

    api_key: Optional[str] = None


class UserASRSettingsUpdate(BaseModel):
    """Schema for updating user ASR settings"""

    name: Optional[str] = None
    provider: Optional[ASRProvider] = None
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    is_active: Optional[bool] = None


class UserASRSettings(UserASRSettingsBase, UUIDBaseSchema):
    """Schema for returning user ASR settings with UUID"""

    user_id: UUID
    last_tested: Optional[datetime] = None
    test_status: Optional[ConnectionStatus] = None
    test_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class UserASRSettingsPublic(UUIDBaseSchema):
    """Public schema that excludes sensitive information"""

    user_id: UUID
    name: str
    provider: ASRProvider
    model_name: str
    is_active: bool
    last_tested: Optional[datetime] = None
    test_status: Optional[ConnectionStatus] = None
    test_message: Optional[str] = None
    has_api_key: bool = False
    created_at: datetime
    updated_at: datetime


class ASRConnectionTestRequest(BaseModel):
    """Schema for ASR connection test requests"""

    provider: ASRProvider
    model_name: str
    api_key: Optional[str] = None
    config_id: Optional[UUID] = None  # For edit mode - uses stored API key


class ASRConnectionTestResponse(BaseModel):
    """Schema for ASR connection test results"""

    success: bool
    status: ConnectionStatus
    message: str
    response_time_ms: Optional[int] = None


class ASRProviderDefaults(BaseModel):
    """Default configuration for an ASR provider"""

    provider: ASRProvider
    default_model: str
    requires_api_key: bool = True
    description: str


class SupportedASRProvidersResponse(BaseModel):
    """Response containing all supported ASR providers with their defaults"""

    providers: list[ASRProviderDefaults]


class UserASRConfigurationsList(BaseModel):
    """Response containing all user's ASR configurations"""

    configurations: list[UserASRSettingsPublic]
    active_configuration_id: Optional[UUID] = None
    total: int


class SetActiveASRConfigRequest(BaseModel):
    """Request to set active ASR configuration"""

    configuration_id: UUID


class ASRSettingsStatus(BaseModel):
    """Status information about user's ASR settings"""

    has_settings: bool = False
    active_configuration: Optional[UserASRSettingsPublic] = None
    total_configurations: int = 0
    using_env_default: bool = True
