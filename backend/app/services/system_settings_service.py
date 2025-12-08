"""
Service for managing system-wide settings.

Provides a clean interface for getting and setting system configuration
with type conversion and caching support.
"""

import logging
from typing import Any
from typing import Optional

from sqlalchemy.orm import Session

from app.models.system_settings import SystemSettings

logger = logging.getLogger(__name__)


def get_setting(db: Session, key: str, default: Any = None) -> Optional[str]:
    """
    Get a system setting by key.

    Args:
        db: Database session
        key: Setting key (e.g., 'transcription.max_retries')
        default: Default value if setting doesn't exist

    Returns:
        Setting value as string, or default if not found
    """
    setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    if setting is None:
        return default
    return setting.value


def get_setting_int(db: Session, key: str, default: int = 0) -> int:
    """
    Get a system setting as an integer.

    Args:
        db: Database session
        key: Setting key
        default: Default value if setting doesn't exist or can't be converted

    Returns:
        Setting value as integer
    """
    value = get_setting(db, key)
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning(
            f"Could not convert setting '{key}' value '{value}' to int, using default {default}"
        )
        return default


def get_setting_bool(db: Session, key: str, default: bool = False) -> bool:
    """
    Get a system setting as a boolean.

    Args:
        db: Database session
        key: Setting key
        default: Default value if setting doesn't exist

    Returns:
        Setting value as boolean
    """
    value = get_setting(db, key)
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


def set_setting(
    db: Session, key: str, value: Any, description: Optional[str] = None
) -> SystemSettings:
    """
    Set a system setting.

    Args:
        db: Database session
        key: Setting key
        value: Setting value (will be converted to string)
        description: Optional description for the setting

    Returns:
        Updated or created SystemSettings object
    """
    setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()

    str_value = str(value).lower() if isinstance(value, bool) else str(value)

    if setting is None:
        setting = SystemSettings(key=key, value=str_value, description=description)
        db.add(setting)
    else:
        setting.value = str_value
        if description is not None:
            setting.description = description

    db.commit()
    db.refresh(setting)
    return setting


def get_all_settings(db: Session) -> dict[str, dict]:
    """
    Get all system settings.

    Returns:
        Dictionary of all settings with their values and descriptions
    """
    settings = db.query(SystemSettings).all()
    return {
        s.key: {
            "value": s.value,
            "description": s.description,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in settings
    }


def get_retry_config(db: Session) -> dict:
    """
    Get retry configuration as a structured dict.

    Returns:
        Dictionary with retry configuration:
        - max_retries: int (0 = unlimited)
        - retry_limit_enabled: bool
    """
    return {
        "max_retries": get_setting_int(db, "transcription.max_retries", 3),
        "retry_limit_enabled": get_setting_bool(db, "transcription.retry_limit_enabled", True),
    }


def should_retry_file(db: Session, retry_count: int) -> bool:
    """
    Check if a file should be retried based on system settings.

    Args:
        db: Database session
        retry_count: Current retry count for the file

    Returns:
        True if the file should be retried, False otherwise
    """
    config = get_retry_config(db)

    # If retry limit is disabled, always allow retries
    if not config["retry_limit_enabled"]:
        return True

    # Check against the system-wide max retries
    max_retries = config["max_retries"]
    return retry_count < max_retries


def update_retry_config(
    db: Session, max_retries: Optional[int] = None, retry_limit_enabled: Optional[bool] = None
) -> dict:
    """
    Update retry configuration.

    Args:
        db: Database session
        max_retries: New max retries value (None to keep current)
        retry_limit_enabled: New enabled state (None to keep current)

    Returns:
        Updated retry configuration
    """
    if max_retries is not None:
        set_setting(
            db,
            "transcription.max_retries",
            max_retries,
            "Maximum number of retry attempts for failed transcriptions (0 = unlimited)",
        )

    if retry_limit_enabled is not None:
        set_setting(
            db,
            "transcription.retry_limit_enabled",
            retry_limit_enabled,
            "Whether to enforce retry limits on transcription processing",
        )

    return get_retry_config(db)


def get_garbage_cleanup_config(db: Session) -> dict:
    """
    Get garbage cleanup configuration as a structured dict.

    Returns:
        Dictionary with garbage cleanup configuration:
        - garbage_cleanup_enabled: bool
        - max_word_length: int (default: 50)
    """
    return {
        "garbage_cleanup_enabled": get_setting_bool(
            db, "transcription.garbage_cleanup_enabled", True
        ),
        "max_word_length": get_setting_int(db, "transcription.max_word_length", 50),
    }


def update_garbage_cleanup_config(
    db: Session,
    garbage_cleanup_enabled: Optional[bool] = None,
    max_word_length: Optional[int] = None,
) -> dict:
    """
    Update garbage cleanup configuration.

    Args:
        db: Database session
        garbage_cleanup_enabled: New enabled state (None to keep current)
        max_word_length: New max word length threshold (None to keep current)

    Returns:
        Updated garbage cleanup configuration
    """
    if garbage_cleanup_enabled is not None:
        set_setting(
            db,
            "transcription.garbage_cleanup_enabled",
            garbage_cleanup_enabled,
            "Whether to clean up garbage words (very long words with no spaces) during transcription",
        )

    if max_word_length is not None:
        set_setting(
            db,
            "transcription.max_word_length",
            max_word_length,
            "Maximum word length threshold for garbage detection (words longer than this with no spaces are replaced)",
        )

    return get_garbage_cleanup_config(db)
