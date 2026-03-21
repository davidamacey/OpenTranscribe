"""
Utility functions for AI summary enable/disable settings.

Centralizes all summary-enable checks to avoid scattered DB queries.
Implements a three-tier control model:
  1. System-level (admin): system_settings key 'ai.summary_enabled'
  2. User-level: user_setting key 'ai_summary_enabled'
  3. Per-file: media_file.summary_status == 'disabled'
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.constants import DEFAULT_AI_SUMMARY_ENABLED

logger = logging.getLogger(__name__)


def is_summary_enabled_system(db: Session) -> bool:
    """Check system_settings key 'ai.summary_enabled'.

    Args:
        db: Database session.

    Returns:
        True if system-wide AI summaries are enabled (default: True).
    """
    from app.services.system_settings_service import get_setting_bool

    return get_setting_bool(db, "ai.summary_enabled", default=DEFAULT_AI_SUMMARY_ENABLED)


def is_summary_enabled_for_user(db: Session, user_id: int) -> bool:
    """Check user_setting key 'ai_summary_enabled' for a user.

    Args:
        db: Database session.
        user_id: ID of the user to check.

    Returns:
        True if the user has auto-summary enabled (default: True).
    """
    from app.models.prompt import UserSetting

    setting = (
        db.query(UserSetting)
        .filter(
            UserSetting.user_id == user_id,
            UserSetting.setting_key == "ai_summary_enabled",
        )
        .first()
    )
    if not setting:
        return DEFAULT_AI_SUMMARY_ENABLED
    return str(setting.setting_value).lower() != "false"


def get_summary_disable_reason(db: Session, user_id: int) -> str | None:
    """Return human-readable reason why summary is disabled, or None if enabled.

    Checks system-level first (highest precedence), then user-level.

    Args:
        db: Database session.
        user_id: ID of the file owner.

    Returns:
        ``"system"`` if system-wide disabled,
        ``"user"`` if user preference disabled,
        ``None`` if enabled at all levels.
    """
    if not is_summary_enabled_system(db):
        return "system"
    if not is_summary_enabled_for_user(db, user_id):
        return "user"
    return None
