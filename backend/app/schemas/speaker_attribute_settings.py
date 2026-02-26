"""Pydantic schemas for speaker attribute detection settings."""

from typing import Optional

from pydantic import BaseModel


class SpeakerAttributeSettings(BaseModel):
    """User-level speaker attribute settings."""

    detection_enabled: bool = True
    gender_detection_enabled: bool = True
    age_detection_enabled: bool = True
    show_attributes_on_cards: bool = True


class SpeakerAttributeSettingsUpdate(BaseModel):
    """Partial update for speaker attribute settings."""

    detection_enabled: Optional[bool] = None
    gender_detection_enabled: Optional[bool] = None
    age_detection_enabled: Optional[bool] = None
    show_attributes_on_cards: Optional[bool] = None


class SpeakerAttributeSystemDefaults(BaseModel):
    """System-level defaults for speaker attribute settings."""

    detection_enabled: bool
    gender_detection_enabled: bool
    age_detection_enabled: bool
    show_attributes_on_cards: bool
