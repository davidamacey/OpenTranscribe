"""
API endpoints for user settings management

This module provides REST endpoints for managing user-specific settings
that need to persist across sessions and devices. Supports:
- Recording settings (duration, quality, auto-stop)
- Audio extraction settings
- Transcription settings (speaker detection, garbage cleanup)
"""

from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app.api.endpoints.auth import get_current_active_user
from app.core.config import settings as app_settings
from app.core.constants import COMMON_LANGUAGES
from app.core.constants import DEFAULT_GARBAGE_CLEANUP_ENABLED
from app.core.constants import DEFAULT_GARBAGE_CLEANUP_THRESHOLD
from app.core.constants import DEFAULT_LLM_OUTPUT_LANGUAGE
from app.core.constants import DEFAULT_RECORDING_AUTO_STOP
from app.core.constants import DEFAULT_RECORDING_MAX_DURATION
from app.core.constants import DEFAULT_RECORDING_QUALITY
from app.core.constants import DEFAULT_SOURCE_LANGUAGE
from app.core.constants import DEFAULT_SPEAKER_PROMPT_BEHAVIOR
from app.core.constants import DEFAULT_TRANSCRIPTION_MAX_SPEAKERS
from app.core.constants import DEFAULT_TRANSCRIPTION_MIN_SPEAKERS
from app.core.constants import DEFAULT_TRANSLATE_TO_ENGLISH
from app.core.constants import LANGUAGES_WITH_ALIGNMENT
from app.core.constants import LLM_OUTPUT_LANGUAGES
from app.core.constants import VALID_RECORDING_DURATIONS
from app.core.constants import VALID_RECORDING_QUALITIES
from app.core.constants import VALID_SPEAKER_PROMPT_BEHAVIORS
from app.core.constants import WHISPER_LANGUAGES
from app.db.base import get_db
from app.schemas.transcription_settings import TranscriptionSettings
from app.schemas.transcription_settings import TranscriptionSettingsUpdate
from app.schemas.transcription_settings import TranscriptionSystemDefaults

router = APIRouter()


# Default values for recording settings (when user hasn't set custom values)
DEFAULT_RECORDING_SETTINGS = {
    "max_recording_duration": DEFAULT_RECORDING_MAX_DURATION,
    "recording_quality": DEFAULT_RECORDING_QUALITY,
    "auto_stop_enabled": DEFAULT_RECORDING_AUTO_STOP,
}

# Default values for audio extraction settings
DEFAULT_AUDIO_EXTRACTION_SETTINGS = {
    "auto_extract_enabled": True,  # Automatically extract audio from large videos
    "extraction_threshold_mb": 100,  # Minimum file size (in MB) to trigger extraction prompt
    "remember_choice": False,  # Remember user's last choice (extract vs upload full)
    "show_modal": True,  # Show extraction modal (false to auto-extract without asking)
}

# Default values for transcription settings
DEFAULT_TRANSCRIPTION_SETTINGS = {
    "min_speakers": DEFAULT_TRANSCRIPTION_MIN_SPEAKERS,
    "max_speakers": DEFAULT_TRANSCRIPTION_MAX_SPEAKERS,
    "speaker_prompt_behavior": DEFAULT_SPEAKER_PROMPT_BEHAVIOR,
    "garbage_cleanup_enabled": DEFAULT_GARBAGE_CLEANUP_ENABLED,
    "garbage_cleanup_threshold": DEFAULT_GARBAGE_CLEANUP_THRESHOLD,
    "source_language": DEFAULT_SOURCE_LANGUAGE,
    "translate_to_english": DEFAULT_TRANSLATE_TO_ENGLISH,
    "llm_output_language": DEFAULT_LLM_OUTPUT_LANGUAGE,
}


@router.get("/recording", response_model=dict[str, Any])
def get_recording_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Get user's recording settings.

    Returns settings with defaults for any values not customized by the user.
    Maps database keys to frontend-friendly keys.

    Returns:
        Dict containing max_recording_duration, recording_quality, and auto_stop_enabled
    """
    # Get all recording-related settings for the user
    recording_settings = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == current_user.id,
            models.UserSetting.setting_key.in_(
                ["recording_max_duration", "recording_quality", "recording_auto_stop"]
            ),
        )
        .all()
    )

    # Build settings map from database results
    settings_map = {setting.setting_key: setting.setting_value for setting in recording_settings}

    # Map database keys to frontend keys and provide defaults for missing values
    settings = {
        "max_recording_duration": int(
            settings_map.get(
                "recording_max_duration",
                DEFAULT_RECORDING_SETTINGS["max_recording_duration"],
            )
        ),
        "recording_quality": settings_map.get(
            "recording_quality", DEFAULT_RECORDING_SETTINGS["recording_quality"]
        ),
        "auto_stop_enabled": settings_map.get("recording_auto_stop", "true").lower() == "true",
    }

    return settings


@router.put("/recording", response_model=dict[str, Any])
def update_recording_settings(
    *,
    db: Session = Depends(get_db),
    settings_data: dict[str, Any],
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Update user's recording settings.

    Validates input data and updates only the provided settings.
    Creates new settings if they don't exist, updates existing ones otherwise.

    Args:
        settings_data: Dict with optional keys: max_recording_duration,
                      recording_quality, auto_stop_enabled

    Returns:
        Updated settings dict with all current values

    Raises:
        HTTPException: If validation fails for any setting
    """
    # Validate incoming data
    valid_keys = {"max_recording_duration", "recording_quality", "auto_stop_enabled"}
    if not all(key in valid_keys for key in settings_data):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid setting keys. Valid keys are: {valid_keys}",
        )

    # Validate specific values
    if "max_recording_duration" in settings_data:
        duration = settings_data["max_recording_duration"]
        if not isinstance(duration, int) or duration not in VALID_RECORDING_DURATIONS:
            valid_durations = ", ".join(map(str, VALID_RECORDING_DURATIONS))
            raise HTTPException(
                status_code=400,
                detail=f"max_recording_duration must be one of: {valid_durations} (minutes)",
            )

    if "recording_quality" in settings_data:
        quality = settings_data["recording_quality"]
        if quality not in VALID_RECORDING_QUALITIES:
            valid_qualities = ", ".join(VALID_RECORDING_QUALITIES)
            raise HTTPException(
                status_code=400,
                detail=f"recording_quality must be one of: {valid_qualities}",
            )

    if "auto_stop_enabled" in settings_data:
        auto_stop = settings_data["auto_stop_enabled"]
        if not isinstance(auto_stop, bool):
            raise HTTPException(status_code=400, detail="auto_stop_enabled must be a boolean")

    # Map frontend keys to database keys
    setting_mappings = {
        "max_recording_duration": "recording_max_duration",
        "recording_quality": "recording_quality",
        "auto_stop_enabled": "recording_auto_stop",
    }

    for frontend_key, value in settings_data.items():
        db_key = setting_mappings[frontend_key]

        # Convert value to string for database storage
        db_value = ("true" if value else "false") if isinstance(value, bool) else str(value)

        # Check if setting already exists
        existing_setting = (
            db.query(models.UserSetting)
            .filter(
                models.UserSetting.user_id == current_user.id,
                models.UserSetting.setting_key == db_key,
            )
            .first()
        )

        if existing_setting:
            existing_setting.setting_value = db_value
            db.add(existing_setting)
        else:
            new_setting = models.UserSetting(
                user_id=current_user.id, setting_key=db_key, setting_value=db_value
            )
            db.add(new_setting)

    db.commit()

    # Return updated settings
    return get_recording_settings(db=db, current_user=current_user)


@router.delete("/recording")
def reset_recording_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Reset user's recording settings to defaults (delete from database)
    """
    deleted_count = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == current_user.id,
            models.UserSetting.setting_key.in_(
                ["recording_max_duration", "recording_quality", "recording_auto_stop"]
            ),
        )
        .delete(synchronize_session=False)
    )

    db.commit()

    return {
        "message": f"Recording settings reset to defaults. Removed {deleted_count} custom settings.",
        "default_settings": DEFAULT_RECORDING_SETTINGS,
    }


@router.get("/audio-extraction", response_model=dict[str, Any])
def get_audio_extraction_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Get user's audio extraction settings.

    Returns settings with defaults for any values not customized by the user.

    Returns:
        Dict containing auto_extract_enabled, extraction_threshold_mb, remember_choice, show_modal
    """
    # Get all audio extraction-related settings for the user
    extraction_settings = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == current_user.id,
            models.UserSetting.setting_key.in_(
                [
                    "audio_extraction_auto_extract",
                    "audio_extraction_threshold_mb",
                    "audio_extraction_remember_choice",
                    "audio_extraction_show_modal",
                ]
            ),
        )
        .all()
    )

    # Build settings map from database results
    settings_map = {setting.setting_key: setting.setting_value for setting in extraction_settings}

    # Map database keys to frontend keys and provide defaults for missing values
    settings = {
        "auto_extract_enabled": settings_map.get("audio_extraction_auto_extract", "true").lower()
        == "true",
        "extraction_threshold_mb": int(
            settings_map.get(
                "audio_extraction_threshold_mb",
                DEFAULT_AUDIO_EXTRACTION_SETTINGS["extraction_threshold_mb"],
            )
        ),
        "remember_choice": settings_map.get("audio_extraction_remember_choice", "false").lower()
        == "true",
        "show_modal": settings_map.get("audio_extraction_show_modal", "true").lower() == "true",
    }

    return settings


@router.put("/audio-extraction", response_model=dict[str, Any])
def update_audio_extraction_settings(
    *,
    db: Session = Depends(get_db),
    settings_data: dict[str, Any],
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Update user's audio extraction settings.

    Validates input data and updates only the provided settings.
    Creates new settings if they don't exist, updates existing ones otherwise.

    Args:
        settings_data: Dict with optional keys: auto_extract_enabled,
                      extraction_threshold_mb, remember_choice, show_modal

    Returns:
        Updated settings dict with all current values

    Raises:
        HTTPException: If validation fails for any setting
    """
    # Validate incoming data
    valid_keys = {
        "auto_extract_enabled",
        "extraction_threshold_mb",
        "remember_choice",
        "show_modal",
    }
    if not all(key in valid_keys for key in settings_data):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid setting keys. Valid keys are: {valid_keys}",
        )

    # Validate specific values
    if "extraction_threshold_mb" in settings_data:
        threshold = settings_data["extraction_threshold_mb"]
        if not isinstance(threshold, int) or threshold < 1 or threshold > 10000:
            raise HTTPException(
                status_code=400,
                detail="extraction_threshold_mb must be an integer between 1 and 10000",
            )

    for key in ["auto_extract_enabled", "remember_choice", "show_modal"]:
        if key in settings_data and not isinstance(settings_data[key], bool):
            raise HTTPException(status_code=400, detail=f"{key} must be a boolean")

    # Map frontend keys to database keys
    setting_mappings = {
        "auto_extract_enabled": "audio_extraction_auto_extract",
        "extraction_threshold_mb": "audio_extraction_threshold_mb",
        "remember_choice": "audio_extraction_remember_choice",
        "show_modal": "audio_extraction_show_modal",
    }

    for frontend_key, value in settings_data.items():
        db_key = setting_mappings[frontend_key]

        # Convert value to string for database storage
        db_value = ("true" if value else "false") if isinstance(value, bool) else str(value)

        # Check if setting already exists
        existing_setting = (
            db.query(models.UserSetting)
            .filter(
                models.UserSetting.user_id == current_user.id,
                models.UserSetting.setting_key == db_key,
            )
            .first()
        )

        if existing_setting:
            existing_setting.setting_value = db_value
            db.add(existing_setting)
        else:
            new_setting = models.UserSetting(
                user_id=current_user.id, setting_key=db_key, setting_value=db_value
            )
            db.add(new_setting)

    db.commit()

    # Return updated settings
    return get_audio_extraction_settings(db=db, current_user=current_user)


@router.get("/all", response_model=dict[str, Any])
def get_all_user_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Get all user settings (for debugging/admin purposes)
    """
    user_settings = (
        db.query(models.UserSetting).filter(models.UserSetting.user_id == current_user.id).all()
    )

    return {setting.setting_key: setting.setting_value for setting in user_settings}


# =============================================================================
# Transcription Settings Endpoints
# =============================================================================


def _validate_speaker_range(
    update_data: dict[str, Any],
    current_settings: TranscriptionSettings | None,
) -> None:
    """
    Validate that min_speakers <= max_speakers.

    Args:
        update_data: Dictionary of settings being updated
        current_settings: Current TranscriptionSettings (None if both min and max in update_data)

    Raises:
        HTTPException: If min_speakers > max_speakers
    """
    min_val = update_data.get("min_speakers")
    max_val = update_data.get("max_speakers")

    # Both provided in update
    if min_val is not None and max_val is not None:
        if min_val > max_val:
            raise HTTPException(
                status_code=400,
                detail="min_speakers cannot be greater than max_speakers",
            )
        return

    # Only min_speakers provided - check against current max
    if min_val is not None and current_settings is not None:
        if min_val > current_settings.max_speakers:
            raise HTTPException(
                status_code=400,
                detail=f"min_speakers ({min_val}) cannot be greater than current max_speakers ({current_settings.max_speakers})",
            )
        return

    # Only max_speakers provided - check against current min
    if (
        max_val is not None
        and current_settings is not None
        and max_val < current_settings.min_speakers
    ):
        raise HTTPException(
            status_code=400,
            detail=f"max_speakers ({max_val}) cannot be less than current min_speakers ({current_settings.min_speakers})",
        )


def _validate_speaker_prompt_behavior(behavior: str | None) -> None:
    """
    Validate speaker_prompt_behavior value.

    Args:
        behavior: The behavior value to validate (or None to skip)

    Raises:
        HTTPException: If behavior is not in VALID_SPEAKER_PROMPT_BEHAVIORS
    """
    if behavior is not None and behavior not in VALID_SPEAKER_PROMPT_BEHAVIORS:
        raise HTTPException(
            status_code=400,
            detail=f"speaker_prompt_behavior must be one of: {VALID_SPEAKER_PROMPT_BEHAVIORS}",
        )


def _validate_source_language(language: str | None) -> None:
    """
    Validate source_language value against supported Whisper languages.

    Args:
        language: The language code to validate (or None to skip)

    Raises:
        HTTPException: If language is not in WHISPER_LANGUAGES
    """
    if language is not None and language not in WHISPER_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail="source_language must be a valid ISO 639-1 code or 'auto'. See available_source_languages in system defaults.",
        )


def _validate_llm_output_language(language: str | None) -> None:
    """
    Validate llm_output_language value against supported LLM output languages.

    Args:
        language: The language code to validate (or None to skip)

    Raises:
        HTTPException: If language is not in LLM_OUTPUT_LANGUAGES
    """
    if language is not None and language not in LLM_OUTPUT_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"llm_output_language must be one of: {list(LLM_OUTPUT_LANGUAGES.keys())}",
        )


def _upsert_user_setting(
    db: Session,
    user_id: int,
    setting_key: str,
    setting_value: Any,
) -> None:
    """
    Insert or update a user setting in the database.

    Args:
        db: Database session
        user_id: ID of the user
        setting_key: The database key for the setting
        setting_value: The value to store (will be converted to string)
    """
    # Convert value to string for database storage
    if isinstance(setting_value, bool):
        db_value = "true" if setting_value else "false"
    else:
        db_value = str(setting_value)

    existing_setting = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == user_id,
            models.UserSetting.setting_key == setting_key,
        )
        .first()
    )

    if existing_setting:
        existing_setting.setting_value = db_value
        db.add(existing_setting)
    else:
        new_setting = models.UserSetting(
            user_id=user_id, setting_key=setting_key, setting_value=db_value
        )
        db.add(new_setting)


@router.get("/transcription", response_model=TranscriptionSettings)
def get_transcription_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> TranscriptionSettings:
    """
    Get user's transcription settings.

    Returns settings with defaults for any values not customized by the user.
    Defaults fall back to system-level settings from environment variables
    for speaker counts, and application constants for other settings.

    Returns:
        TranscriptionSettings containing min_speakers, max_speakers,
        speaker_prompt_behavior, garbage_cleanup_enabled, garbage_cleanup_threshold,
        source_language, translate_to_english, and llm_output_language
    """
    # Get all transcription-related settings for the user
    transcription_settings = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == current_user.id,
            models.UserSetting.setting_key.in_(
                [
                    "transcription_min_speakers",
                    "transcription_max_speakers",
                    "transcription_speaker_prompt_behavior",
                    "transcription_garbage_cleanup_enabled",
                    "transcription_garbage_cleanup_threshold",
                    "transcription_source_language",
                    "transcription_translate_to_english",
                    "transcription_llm_output_language",
                ]
            ),
        )
        .all()
    )

    # Build settings map from database results
    settings_map = {
        setting.setting_key: setting.setting_value for setting in transcription_settings
    }

    # Get system defaults from environment (via app_settings)
    system_min_speakers = app_settings.MIN_SPEAKERS
    system_max_speakers = app_settings.MAX_SPEAKERS

    # Build response with user values or defaults
    return TranscriptionSettings(
        min_speakers=int(settings_map.get("transcription_min_speakers", system_min_speakers)),
        max_speakers=int(settings_map.get("transcription_max_speakers", system_max_speakers)),
        speaker_prompt_behavior=settings_map.get(
            "transcription_speaker_prompt_behavior",
            DEFAULT_TRANSCRIPTION_SETTINGS["speaker_prompt_behavior"],
        ),
        garbage_cleanup_enabled=settings_map.get(
            "transcription_garbage_cleanup_enabled", "true"
        ).lower()
        == "true",
        garbage_cleanup_threshold=int(
            settings_map.get(
                "transcription_garbage_cleanup_threshold",
                DEFAULT_TRANSCRIPTION_SETTINGS["garbage_cleanup_threshold"],
            )
        ),
        source_language=settings_map.get(
            "transcription_source_language",
            DEFAULT_TRANSCRIPTION_SETTINGS["source_language"],
        ),
        translate_to_english=settings_map.get("transcription_translate_to_english", "false").lower()
        == "true",
        llm_output_language=settings_map.get(
            "transcription_llm_output_language",
            DEFAULT_TRANSCRIPTION_SETTINGS["llm_output_language"],
        ),
    )


@router.put("/transcription", response_model=TranscriptionSettings)
def update_transcription_settings(
    *,
    db: Session = Depends(get_db),
    settings_data: TranscriptionSettingsUpdate,
    current_user: models.User = Depends(get_current_active_user),
) -> TranscriptionSettings:
    """
    Update user's transcription settings.

    Validates input data and updates only the provided settings.
    Creates new settings if they don't exist, updates existing ones otherwise.

    Args:
        settings_data: TranscriptionSettingsUpdate with optional fields:
            min_speakers, max_speakers, speaker_prompt_behavior,
            garbage_cleanup_enabled, garbage_cleanup_threshold,
            source_language, translate_to_english, llm_output_language

    Returns:
        Updated TranscriptionSettings with all current values

    Raises:
        HTTPException: If validation fails for any setting
    """
    # Convert Pydantic model to dict, excluding None values
    update_data = settings_data.model_dump(exclude_none=True)

    if not update_data:
        return get_transcription_settings(db=db, current_user=current_user)

    # Get current settings only if needed for validation
    needs_current = ("min_speakers" in update_data) != ("max_speakers" in update_data)
    current_settings = (
        get_transcription_settings(db=db, current_user=current_user) if needs_current else None
    )

    # Validate speaker range and prompt behavior
    _validate_speaker_range(update_data, current_settings)
    _validate_speaker_prompt_behavior(update_data.get("speaker_prompt_behavior"))

    # Validate language settings
    _validate_source_language(update_data.get("source_language"))
    _validate_llm_output_language(update_data.get("llm_output_language"))

    # Map frontend keys to database keys
    setting_mappings = {
        "min_speakers": "transcription_min_speakers",
        "max_speakers": "transcription_max_speakers",
        "speaker_prompt_behavior": "transcription_speaker_prompt_behavior",
        "garbage_cleanup_enabled": "transcription_garbage_cleanup_enabled",
        "garbage_cleanup_threshold": "transcription_garbage_cleanup_threshold",
        "source_language": "transcription_source_language",
        "translate_to_english": "transcription_translate_to_english",
        "llm_output_language": "transcription_llm_output_language",
    }

    # Update each setting in the database
    for frontend_key, value in update_data.items():
        _upsert_user_setting(db, current_user.id, setting_mappings[frontend_key], value)

    db.commit()

    return get_transcription_settings(db=db, current_user=current_user)


@router.delete("/transcription")
def reset_transcription_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Reset user's transcription settings to defaults.

    Deletes all user-specific transcription settings from the database,
    causing the system to fall back to default values.

    Returns:
        Message confirming reset and the default settings that will now apply
    """
    deleted_count = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == current_user.id,
            models.UserSetting.setting_key.in_(
                [
                    "transcription_min_speakers",
                    "transcription_max_speakers",
                    "transcription_speaker_prompt_behavior",
                    "transcription_garbage_cleanup_enabled",
                    "transcription_garbage_cleanup_threshold",
                    "transcription_source_language",
                    "transcription_translate_to_english",
                    "transcription_llm_output_language",
                ]
            ),
        )
        .delete(synchronize_session=False)
    )

    db.commit()

    # Return defaults including system-level speaker settings
    default_settings = {
        "min_speakers": app_settings.MIN_SPEAKERS,
        "max_speakers": app_settings.MAX_SPEAKERS,
        "speaker_prompt_behavior": DEFAULT_TRANSCRIPTION_SETTINGS["speaker_prompt_behavior"],
        "garbage_cleanup_enabled": DEFAULT_TRANSCRIPTION_SETTINGS["garbage_cleanup_enabled"],
        "garbage_cleanup_threshold": DEFAULT_TRANSCRIPTION_SETTINGS["garbage_cleanup_threshold"],
        "source_language": DEFAULT_TRANSCRIPTION_SETTINGS["source_language"],
        "translate_to_english": DEFAULT_TRANSCRIPTION_SETTINGS["translate_to_english"],
        "llm_output_language": DEFAULT_TRANSCRIPTION_SETTINGS["llm_output_language"],
    }

    return {
        "message": f"Transcription settings reset to defaults. Removed {deleted_count} custom settings.",
        "default_settings": default_settings,
    }


@router.get("/transcription/system-defaults", response_model=TranscriptionSystemDefaults)
def get_transcription_system_defaults() -> TranscriptionSystemDefaults:
    """
    Get system-level transcription defaults.

    Returns the system-wide default values from environment configuration
    (MIN_SPEAKERS, MAX_SPEAKERS from .env) and application constants.
    This endpoint is useful for showing users what the default values are
    before they customize their settings.

    Note: This endpoint does not require authentication as it returns
    only system configuration, not user-specific data.

    Returns:
        TranscriptionSystemDefaults containing system min/max speakers,
        garbage cleanup defaults, valid behavior options, and language options
    """
    return TranscriptionSystemDefaults(
        min_speakers=app_settings.MIN_SPEAKERS,
        max_speakers=app_settings.MAX_SPEAKERS,
        garbage_cleanup_enabled=DEFAULT_GARBAGE_CLEANUP_ENABLED,
        garbage_cleanup_threshold=DEFAULT_GARBAGE_CLEANUP_THRESHOLD,
        valid_speaker_prompt_behaviors=list(VALID_SPEAKER_PROMPT_BEHAVIORS),
        available_source_languages=WHISPER_LANGUAGES,
        available_llm_output_languages=LLM_OUTPUT_LANGUAGES,
        common_languages=COMMON_LANGUAGES,
        languages_with_alignment=sorted(list(LANGUAGES_WITH_ALIGNMENT)),
    )
