"""
Pydantic schemas for organization context settings.

These schemas define the request/response models for user-level organization
context that is injected into LLM system prompts during summarization.
"""

from typing import Optional

from pydantic import BaseModel
from pydantic import Field

from app.core.constants import DEFAULT_ORG_CONTEXT_INCLUDE_CUSTOM_PROMPTS
from app.core.constants import DEFAULT_ORG_CONTEXT_INCLUDE_DEFAULT_PROMPTS
from app.core.constants import DEFAULT_ORG_CONTEXT_TEXT
from app.core.constants import ORG_CONTEXT_MAX_LENGTH


class OrganizationContextSettings(BaseModel):
    """
    Response schema for user organization context settings.

    Contains the organization context text and toggle preferences.
    """

    context_text: str = Field(
        default=DEFAULT_ORG_CONTEXT_TEXT,
        max_length=ORG_CONTEXT_MAX_LENGTH,
        description="Organization/project background context for LLM summaries",
    )
    include_in_default_prompts: bool = Field(
        default=DEFAULT_ORG_CONTEXT_INCLUDE_DEFAULT_PROMPTS,
        description="Include context when using system default summary prompts",
    )
    include_in_custom_prompts: bool = Field(
        default=DEFAULT_ORG_CONTEXT_INCLUDE_CUSTOM_PROMPTS,
        description="Include context when using user-created custom prompts",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "context_text": "Greenleaf Analytics is a healthcare data company building the Pulse platform...",
                "include_in_default_prompts": True,
                "include_in_custom_prompts": False,
            }
        }


class OrganizationContextUpdate(BaseModel):
    """
    Request schema for updating organization context settings.

    All fields are optional - only provided fields will be updated.
    """

    context_text: Optional[str] = Field(
        default=None,
        max_length=ORG_CONTEXT_MAX_LENGTH,
        description="Organization/project background context for LLM summaries",
    )
    include_in_default_prompts: Optional[bool] = Field(
        default=None,
        description="Include context when using system default summary prompts",
    )
    include_in_custom_prompts: Optional[bool] = Field(
        default=None,
        description="Include context when using user-created custom prompts",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "context_text": "Updated organization context...",
                "include_in_default_prompts": True,
                "include_in_custom_prompts": True,
            }
        }
