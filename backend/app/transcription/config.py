"""Transcription pipeline configuration.

Builds configuration from environment variables and hardware detection,
with task-level overrides for per-file settings.
"""

import hashlib
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _parse_optional_float(value: str) -> float | None:
    """Parse a string to float, returning None for empty/whitespace."""
    if not value or not value.strip():
        return None
    return float(value.strip())


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
    enable_native_embeddings: bool = True
    enable_overlap_detection: bool = True
    overlap_min_duration: float = 0.25

    # VAD settings (Silero VAD used by faster-whisper BatchedInferencePipeline)
    vad_threshold: float = 0.5
    vad_min_silence_ms: int = 2000
    vad_min_speech_ms: int = 250
    vad_speech_pad_ms: int = 400

    # Accuracy settings
    hallucination_silence_threshold: float | None = None
    repetition_penalty: float = 1.0

    def config_hash(self) -> str:
        """Hash of model-loading-relevant config for cache invalidation."""
        key = f"{self.model_name}:{self.compute_type}:{self.device}:{self.device_index}"
        return hashlib.md5(key.encode()).hexdigest()[:12]  # noqa: S324  # nosec B324

    @classmethod
    def from_environment(cls, **overrides) -> "TranscriptionConfig":
        """Build config from env vars + hardware detection, with task-level overrides."""
        from app.utils.hardware_detection import detect_hardware

        hw = detect_hardware()
        whisperx_config = hw.get_whisperx_config()

        # Batch size: honor BATCH_SIZE env var, fall back to hardware-detected value
        batch_size_env = os.getenv("BATCH_SIZE", "auto")
        if batch_size_env != "auto":
            batch_size = int(batch_size_env)
        else:
            batch_size = whisperx_config["batch_size"]

        # Base config from environment and hardware detection
        config = cls(
            model_name=os.getenv("WHISPER_MODEL", "large-v3-turbo"),
            compute_type=os.getenv("WHISPER_COMPUTE_TYPE", whisperx_config["compute_type"]),
            beam_size=int(os.getenv("WHISPER_BEAM_SIZE", "5")),
            batch_size=batch_size,
            device=whisperx_config["device"],
            device_index=whisperx_config.get("device_index", 0),
            source_language=os.getenv("SOURCE_LANGUAGE", "auto"),
            translate_to_english=False,
            enable_dedup=os.getenv("ENABLE_SEGMENT_DEDUP", "true").lower() == "true",
            min_speakers=int(os.getenv("MIN_SPEAKERS", "1")),
            max_speakers=int(os.getenv("MAX_SPEAKERS", "20")),
            num_speakers=None,
            hf_token=os.getenv("HUGGINGFACE_TOKEN"),
            enable_native_embeddings=os.getenv("USE_NATIVE_SPEAKER_EMBEDDINGS", "true").lower()
            == "true",
            enable_overlap_detection=os.getenv("ENABLE_OVERLAP_DETECTION", "true").lower()
            == "true",
            overlap_min_duration=float(os.getenv("OVERLAP_MIN_DURATION", "0.25")),
            # VAD settings
            vad_threshold=float(os.getenv("VAD_THRESHOLD", "0.5")),
            vad_min_silence_ms=int(os.getenv("VAD_MIN_SILENCE_MS", "2000")),
            vad_min_speech_ms=int(os.getenv("VAD_MIN_SPEECH_MS", "250")),
            vad_speech_pad_ms=int(os.getenv("VAD_SPEECH_PAD_MS", "400")),
            # Accuracy settings
            hallucination_silence_threshold=_parse_optional_float(
                os.getenv("WHISPER_HALLUCINATION_THRESHOLD", "")
            ),
            repetition_penalty=float(os.getenv("WHISPER_REPETITION_PENALTY", "1.0")),
        )

        # Apply task-level overrides (all overrides are intentional, including None
        # values like hallucination_silence_threshold=None meaning "disabled")
        for key, value in overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

        logger.info(
            f"TranscriptionConfig: model={config.model_name}, device={config.device}, "
            f"compute_type={config.compute_type}, batch_size={config.batch_size}, "
            f"beam_size={config.beam_size}, language={config.source_language}, "
            f"translate={config.translate_to_english}"
        )

        return config
