"""ASR provider factory."""

import logging
import os
from typing import TYPE_CHECKING

from .base import ASRProvider

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _load_user_asr_config(user_id: int, db: "Session") -> dict | None:
    """Load the active ASR configuration for a user from the database.

    Returns a dict with provider, model_name, api_key (decrypted) or None.
    """
    try:
        from app.models import UserASRSettings, UserSetting
        from app.utils.encryption import decrypt_api_key

        active_setting = (
            db.query(UserSetting)
            .filter(
                UserSetting.user_id == user_id,
                UserSetting.setting_key == "active_asr_config_id",
            )
            .first()
        )

        if not active_setting or not active_setting.setting_value:
            return None

        config_id = int(active_setting.setting_value)
        config = (
            db.query(UserASRSettings)
            .filter(
                UserASRSettings.id == config_id,
                UserASRSettings.user_id == user_id,
                UserASRSettings.is_active.is_(True),
            )
            .first()
        )

        if not config:
            return None

        api_key = None
        if config.api_key:
            api_key = decrypt_api_key(str(config.api_key))

        return {
            "provider": config.provider,
            "model_name": config.model_name,
            "api_key": api_key,
        }
    except Exception as e:
        logger.warning(f"Failed to load user ASR config: {e}")
        return None


def get_asr_provider(
    provider_name: str | None = None,
    user_id: int | None = None,
    db: "Session | None" = None,
) -> ASRProvider:
    """Create and return an ASR provider instance.

    If user_id and db are provided, attempts to load the user's active ASR
    configuration from the database first. Falls back to env vars.

    Args:
        provider_name: Provider name ('deepgram' or 'whisperx').
            Falls back to user DB config, then ASR_PROVIDER env var, then 'deepgram'.
        user_id: Optional user ID to look up per-user ASR settings.
        db: Optional database session (required if user_id is provided).

    Returns:
        Configured ASRProvider instance.

    Raises:
        ValueError: If provider is unknown or misconfigured.
    """
    # Try to load user-specific config from DB
    user_config = None
    if user_id is not None and db is not None:
        user_config = _load_user_asr_config(user_id, db)

    if user_config:
        name = user_config["provider"]
        api_key = user_config.get("api_key", "")
        model = user_config.get("model_name", "")
    else:
        name = (provider_name or os.getenv("ASR_PROVIDER", "deepgram")).lower().strip()
        api_key = os.getenv("DEEPGRAM_API_KEY", "")
        model = os.getenv("DEEPGRAM_MODEL", "nova-3-medical")

    if name == "deepgram":
        from .deepgram_provider import DeepgramProvider

        return DeepgramProvider(api_key=api_key or "", model=model or "nova-3-medical")

    if name == "whisperx":
        from .whisperx_provider import WhisperXProvider

        return WhisperXProvider(
            model_name=model or os.getenv("WHISPER_MODEL", "large-v2"),
            models_dir=os.getenv("MODELS_DIR", "/app/models"),
        )

    raise ValueError(
        f"Unknown ASR provider: '{name}'. Supported: 'deepgram', 'whisperx'"
    )
