"""
Pydantic schemas for admin settings
"""

from typing import Optional

from pydantic import BaseModel
from pydantic import field_validator


class RetryConfig(BaseModel):
    """Response schema for retry configuration"""

    max_retries: int
    retry_limit_enabled: bool


class RetryConfigUpdate(BaseModel):
    """Schema for updating retry configuration"""

    max_retries: Optional[int] = None
    retry_limit_enabled: Optional[bool] = None

    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, v):
        if v is not None and (v < 0 or v > 99):
            raise ValueError("max_retries must be between 0 and 99 (0 = unlimited)")
        return v


class SystemSettingResponse(BaseModel):
    """Response schema for a single system setting"""

    key: str
    value: Optional[str]
    description: Optional[str]
    updated_at: Optional[str]


class AllSettingsResponse(BaseModel):
    """Response schema for all system settings"""

    settings: dict[str, dict]


class GarbageCleanupConfig(BaseModel):
    """Response schema for garbage cleanup configuration"""

    garbage_cleanup_enabled: bool
    max_word_length: int


class GarbageCleanupConfigUpdate(BaseModel):
    """Schema for updating garbage cleanup configuration"""

    garbage_cleanup_enabled: Optional[bool] = None
    max_word_length: Optional[int] = None

    @field_validator("max_word_length")
    @classmethod
    def validate_max_word_length(cls, v):
        if v is not None and (v < 20 or v > 200):
            raise ValueError("max_word_length must be between 20 and 200")
        return v
