"""ASR provider factory."""

import logging
import os

from .base import ASRProvider

logger = logging.getLogger(__name__)


def get_asr_provider(provider_name: str | None = None) -> ASRProvider:
    """Create and return an ASR provider instance.

    Args:
        provider_name: Provider name ('deepgram' or 'whisperx').
            Falls back to ASR_PROVIDER env var, then defaults to 'deepgram'.

    Returns:
        Configured ASRProvider instance.

    Raises:
        ValueError: If provider is unknown or misconfigured.
    """
    name = (provider_name or os.getenv("ASR_PROVIDER", "deepgram")).lower().strip()

    if name == "deepgram":
        from .deepgram_provider import DeepgramProvider

        api_key = os.getenv("DEEPGRAM_API_KEY", "")
        model = os.getenv("DEEPGRAM_MODEL", "nova-3-medical")
        return DeepgramProvider(api_key=api_key, model=model)

    if name == "whisperx":
        from .whisperx_provider import WhisperXProvider

        return WhisperXProvider(
            model_name=os.getenv("WHISPER_MODEL", "large-v2"),
            models_dir=os.getenv("MODELS_DIR", "/app/models"),
        )

    raise ValueError(
        f"Unknown ASR provider: '{name}'. Supported: 'deepgram', 'whisperx'"
    )
