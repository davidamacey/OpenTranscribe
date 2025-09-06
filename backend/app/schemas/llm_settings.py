"""
Pydantic schemas for user LLM settings
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel
from pydantic import field_validator


class LLMProvider(str, Enum):
    """Supported LLM providers"""
    OPENAI = "openai"
    VLLM = "vllm"
    OLLAMA = "ollama"
    CLAUDE = "claude"
    ANTHROPIC = "anthropic"  # Alias for claude
    OPENROUTER = "openrouter"
    CUSTOM = "custom"


class ConnectionStatus(str, Enum):
    """Connection test status"""
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    UNTESTED = "untested"


class UserLLMSettingsBase(BaseModel):
    """Base schema for user LLM settings"""
    provider: LLMProvider
    model_name: str
    base_url: Optional[str] = None
    max_tokens: int = 2000
    temperature: str = "0.3"  # Store as string to avoid float precision issues
    timeout: int = 60
    is_active: bool = True

    @field_validator('max_tokens')
    @classmethod
    def validate_max_tokens(cls, v):
        if v < 1 or v > 200000:  # Reasonable limits
            raise ValueError('max_tokens must be between 1 and 200000')
        return v

    @field_validator('temperature')
    @classmethod
    def validate_temperature(cls, v):
        try:
            temp_float = float(v)
            if temp_float < 0.0 or temp_float > 2.0:
                raise ValueError('temperature must be between 0.0 and 2.0')
        except ValueError:
            raise ValueError('temperature must be a valid number')
        return v

    @field_validator('timeout')
    @classmethod
    def validate_timeout(cls, v):
        if v < 5 or v > 600:  # 5 seconds to 10 minutes
            raise ValueError('timeout must be between 5 and 600 seconds')
        return v


class UserLLMSettingsCreate(UserLLMSettingsBase):
    """Schema for creating user LLM settings"""
    api_key: Optional[str] = None  # Will be encrypted before storage


class UserLLMSettingsUpdate(BaseModel):
    """Schema for updating user LLM settings"""
    provider: Optional[LLMProvider] = None
    model_name: Optional[str] = None
    api_key: Optional[str] = None  # Will be encrypted before storage
    base_url: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[str] = None
    timeout: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator('max_tokens')
    @classmethod
    def validate_max_tokens(cls, v):
        if v is not None and (v < 1 or v > 200000):
            raise ValueError('max_tokens must be between 1 and 200000')
        return v

    @field_validator('temperature')
    @classmethod
    def validate_temperature(cls, v):
        if v is not None:
            try:
                temp_float = float(v)
                if temp_float < 0.0 or temp_float > 2.0:
                    raise ValueError('temperature must be between 0.0 and 2.0')
            except ValueError:
                raise ValueError('temperature must be a valid number')
        return v

    @field_validator('timeout')
    @classmethod
    def validate_timeout(cls, v):
        if v is not None and (v < 5 or v > 600):
            raise ValueError('timeout must be between 5 and 600 seconds')
        return v


class UserLLMSettings(UserLLMSettingsBase):
    """Schema for returning user LLM settings"""
    id: int
    user_id: int
    last_tested: Optional[datetime] = None
    test_status: Optional[ConnectionStatus] = None
    test_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Note: api_key is never included in response for security
    model_config = {"from_attributes": True}


class UserLLMSettingsPublic(BaseModel):
    """Public schema that excludes sensitive information"""
    id: int
    user_id: int
    provider: LLMProvider
    model_name: str
    base_url: Optional[str] = None
    max_tokens: int
    temperature: str
    timeout: int
    is_active: bool
    last_tested: Optional[datetime] = None
    test_status: Optional[ConnectionStatus] = None
    test_message: Optional[str] = None
    has_api_key: bool = False  # Indicates whether an API key is stored
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConnectionTestRequest(BaseModel):
    """Schema for connection test requests"""
    provider: LLMProvider
    model_name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: Optional[int] = 30


class ConnectionTestResponse(BaseModel):
    """Schema for connection test results"""
    success: bool
    status: ConnectionStatus
    message: str
    response_time_ms: Optional[int] = None
    model_info: Optional[dict] = None


class ProviderDefaults(BaseModel):
    """Default configuration for a provider"""
    provider: LLMProvider
    default_model: str
    default_base_url: Optional[str] = None
    requires_api_key: bool = True
    supports_custom_url: bool = True
    max_context_length: Optional[int] = None
    description: str


class SupportedProvidersResponse(BaseModel):
    """Response containing all supported providers with their defaults"""
    providers: list[ProviderDefaults]


class LLMSettingsStatus(BaseModel):
    """Status information about user's LLM settings"""
    has_settings: bool = False
    provider: Optional[LLMProvider] = None
    model_name: Optional[str] = None
    test_status: Optional[ConnectionStatus] = None
    last_tested: Optional[datetime] = None
    is_active: bool = False
    using_system_default: bool = True
