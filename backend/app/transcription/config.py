"""Transcription pipeline configuration.

Builds configuration from environment variables and hardware detection,
with task-level overrides for per-file settings.
"""

import hashlib
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionConfig:
    """Configuration for the transcription pipeline."""

    model_name: str = "large-v3-turbo"
    compute_type: str = "float16"
    beam_size: int = 5
    batch_size: int = 16
    device: str = "cuda"
    device_index: int = 0
    source_language: str = "auto"
    translate_to_english: bool = False
    enable_dedup: bool = True
    min_speakers: int = 1
    max_speakers: int = 20
    num_speakers: int | None = None
    hf_token: str | None = None

    def config_hash(self) -> str:
        """Hash of model-loading-relevant config for cache invalidation."""
        key = f"{self.model_name}:{self.compute_type}:{self.device}:{self.device_index}"
        return hashlib.md5(key.encode()).hexdigest()[:12]  # noqa: S324

    @classmethod
    def from_environment(cls, **overrides) -> "TranscriptionConfig":
        """Build config from env vars + hardware detection, with task-level overrides."""
        from app.utils.hardware_detection import detect_hardware

        hw = detect_hardware()
        whisperx_config = hw.get_whisperx_config()

        # Base config from environment and hardware detection
        config = cls(
            model_name=os.getenv("WHISPER_MODEL", "large-v3-turbo"),
            compute_type=os.getenv("WHISPER_COMPUTE_TYPE", whisperx_config["compute_type"]),
            beam_size=int(os.getenv("WHISPER_BEAM_SIZE", "5")),
            batch_size=whisperx_config["batch_size"],
            device=whisperx_config["device"],
            device_index=whisperx_config.get("device_index", 0),
            source_language=os.getenv("SOURCE_LANGUAGE", "auto"),
            translate_to_english=False,
            enable_dedup=os.getenv("ENABLE_SEGMENT_DEDUP", "true").lower() == "true",
            min_speakers=int(os.getenv("MIN_SPEAKERS", "1")),
            max_speakers=int(os.getenv("MAX_SPEAKERS", "20")),
            num_speakers=None,
            hf_token=os.getenv("HUGGINGFACE_TOKEN"),
        )

        # Apply task-level overrides
        for key, value in overrides.items():
            if value is not None and hasattr(config, key):
                setattr(config, key, value)

        logger.info(
            f"TranscriptionConfig: model={config.model_name}, device={config.device}, "
            f"compute_type={config.compute_type}, batch_size={config.batch_size}, "
            f"beam_size={config.beam_size}, language={config.source_language}, "
            f"translate={config.translate_to_english}"
        )

        return config
