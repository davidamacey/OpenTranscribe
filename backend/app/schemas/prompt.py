"""
Pydantic schemas for AI summarization prompt management
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from pydantic import Field
from pydantic import validator


class SummaryPromptBase(BaseModel):
    """Base schema for summary prompts"""
    name: str = Field(..., max_length=255, description="User-friendly name for the prompt")
    description: Optional[str] = Field(None, description="Optional description of what this prompt is for")
    prompt_text: str = Field(..., description="The actual prompt content")
    content_type: Optional[str] = Field(None, description="Content type: meeting, interview, podcast, documentary, general")
    is_active: bool = Field(True, description="Whether the prompt is available for use")

    @validator('content_type')
    def validate_content_type(self, v):
        if v is not None:
            valid_types = {'meeting', 'interview', 'podcast', 'documentary', 'general'}
            if v not in valid_types:
                raise ValueError(f'content_type must be one of: {valid_types}')
        return v


class SummaryPromptCreate(SummaryPromptBase):
    """Schema for creating a new summary prompt"""


class SummaryPromptUpdate(BaseModel):
    """Schema for updating an existing summary prompt"""
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    prompt_text: Optional[str] = None
    content_type: Optional[str] = None
    is_active: Optional[bool] = None

    @validator('content_type')
    def validate_content_type(self, v):
        if v is not None:
            valid_types = {'meeting', 'interview', 'podcast', 'documentary', 'general'}
            if v not in valid_types:
                raise ValueError(f'content_type must be one of: {valid_types}')
        return v


class SummaryPrompt(SummaryPromptBase):
    """Schema for summary prompt responses"""
    id: int
    user_id: Optional[int] = Field(None, description="User ID for custom prompts, null for system prompts")
    is_system_default: bool = Field(False, description="Whether this is a system-provided prompt")
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class SummaryPromptList(BaseModel):
    """Schema for paginated summary prompt lists"""
    prompts: list[SummaryPrompt]
    total: int
    page: int
    size: int
    has_next: bool
    has_prev: bool


# User Settings Schemas
class UserSettingBase(BaseModel):
    """Base schema for user settings"""
    setting_key: str = Field(..., max_length=100, description="Setting key")
    setting_value: Optional[str] = Field(None, description="Setting value (JSON or simple value)")


class UserSettingCreate(UserSettingBase):
    """Schema for creating a new user setting"""


class UserSettingUpdate(BaseModel):
    """Schema for updating an existing user setting"""
    setting_value: Optional[str] = None


class UserSetting(UserSettingBase):
    """Schema for user setting responses"""
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class UserSettingsList(BaseModel):
    """Schema for user settings list"""
    settings: list[UserSetting]


# Summary prompt selection schemas
class ActivePromptSelection(BaseModel):
    """Schema for selecting an active summary prompt"""
    prompt_id: int = Field(..., description="ID of the summary prompt to use")


class ActivePromptResponse(BaseModel):
    """Schema for active prompt response"""
    active_prompt_id: Optional[int] = Field(None, description="Currently active prompt ID")
    active_prompt: Optional[SummaryPrompt] = Field(None, description="Currently active prompt details")


# Content type specific prompt schemas
class ContentTypePromptsResponse(BaseModel):
    """Schema for getting prompts by content type"""
    content_type: str
    system_prompts: list[SummaryPrompt]
    user_prompts: list[SummaryPrompt]
    active_prompt_id: Optional[int] = None
