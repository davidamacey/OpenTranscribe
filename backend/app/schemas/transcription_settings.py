"""
Pydantic schemas for user transcription settings.

These schemas define the request/response models for user-level transcription
preferences including speaker detection, prompt behavior, and garbage cleanup settings.
"""

from typing import Literal
from typing import Optional

from pydantic import BaseModel
from pydantic import Field

from app.core.constants import DEFAULT_GARBAGE_CLEANUP_ENABLED
from app.core.constants import DEFAULT_GARBAGE_CLEANUP_THRESHOLD
from app.core.constants import DEFAULT_SPEAKER_PROMPT_BEHAVIOR
from app.core.constants import DEFAULT_TRANSCRIPTION_MAX_SPEAKERS
from app.core.constants import DEFAULT_TRANSCRIPTION_MIN_SPEAKERS
from app.core.constants import VALID_SPEAKER_PROMPT_BEHAVIORS

# Type alias for speaker prompt behavior
SpeakerPromptBehavior = Literal["always_prompt", "use_defaults", "use_custom"]


class TranscriptionSettings(BaseModel):
    """
    Response schema for user transcription settings.

    Contains all transcription-related user preferences with their current values.
    """

    min_speakers: int = Field(
        default=DEFAULT_TRANSCRIPTION_MIN_SPEAKERS,
        ge=1,
        le=100,
        description="Minimum number of speakers to detect during diarization",
    )
    max_speakers: int = Field(
        default=DEFAULT_TRANSCRIPTION_MAX_SPEAKERS,
        ge=1,
        le=100,
        description="Maximum number of speakers to detect during diarization",
    )
    speaker_prompt_behavior: SpeakerPromptBehavior = Field(
        default=DEFAULT_SPEAKER_PROMPT_BEHAVIOR,
        description="How to handle speaker count prompts: always_prompt, use_defaults, or use_custom",
    )
    garbage_cleanup_enabled: bool = Field(
        default=DEFAULT_GARBAGE_CLEANUP_ENABLED,
        description="Whether automatic garbage segment cleanup is enabled",
    )
    garbage_cleanup_threshold: int = Field(
        default=DEFAULT_GARBAGE_CLEANUP_THRESHOLD,
        ge=0,
        le=100,
        description="Confidence threshold (0-100) below which segments are flagged as garbage",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "min_speakers": 1,
                "max_speakers": 20,
                "speaker_prompt_behavior": "always_prompt",
                "garbage_cleanup_enabled": True,
                "garbage_cleanup_threshold": 50,
            }
        }


class TranscriptionSettingsUpdate(BaseModel):
    """
    Request schema for updating user transcription settings.

    All fields are optional - only provided fields will be updated.
    """

    min_speakers: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Minimum number of speakers to detect during diarization",
    )
    max_speakers: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Maximum number of speakers to detect during diarization",
    )
    speaker_prompt_behavior: Optional[SpeakerPromptBehavior] = Field(
        default=None,
        description="How to handle speaker count prompts: always_prompt, use_defaults, or use_custom",
    )
    garbage_cleanup_enabled: Optional[bool] = Field(
        default=None,
        description="Whether automatic garbage segment cleanup is enabled",
    )
    garbage_cleanup_threshold: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Confidence threshold (0-100) below which segments are flagged as garbage",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "min_speakers": 2,
                "max_speakers": 10,
                "speaker_prompt_behavior": "use_custom",
                "garbage_cleanup_enabled": True,
                "garbage_cleanup_threshold": 40,
            }
        }


class TranscriptionSystemDefaults(BaseModel):
    """
    Response schema for system-level transcription defaults.

    Contains the system-wide default values from environment configuration.
    """

    min_speakers: int = Field(
        description="System default minimum speakers (from MIN_SPEAKERS env var)"
    )
    max_speakers: int = Field(
        description="System default maximum speakers (from MAX_SPEAKERS env var)"
    )
    garbage_cleanup_enabled: bool = Field(
        default=DEFAULT_GARBAGE_CLEANUP_ENABLED,
        description="System default for garbage cleanup enabled",
    )
    garbage_cleanup_threshold: int = Field(
        default=DEFAULT_GARBAGE_CLEANUP_THRESHOLD,
        description="System default garbage cleanup threshold",
    )
    valid_speaker_prompt_behaviors: list[str] = Field(
        default=list(VALID_SPEAKER_PROMPT_BEHAVIORS),
        description="List of valid speaker prompt behavior options",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "min_speakers": 1,
                "max_speakers": 20,
                "garbage_cleanup_enabled": True,
                "garbage_cleanup_threshold": 50,
                "valid_speaker_prompt_behaviors": [
                    "always_prompt",
                    "use_defaults",
                    "use_custom",
                ],
            }
        }
