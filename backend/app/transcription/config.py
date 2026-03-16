"""Transcription pipeline configuration.

Builds configuration from environment variables and hardware detection,
with task-level overrides for per-file settings.
"""

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import ClassVar

logger = logging.getLogger(__name__)


def _parse_optional_float(value: str) -> float | None:
    """Parse a string to float, returning None for empty/whitespace."""
    if not value or not value.strip():
        return None
    return float(value.strip())


@dataclass
class TranscriptionConfig:
    """Configuration for the transcription pipeline."""

    # Class-level pin: set once at worker startup, used for all subsequent tasks.
    # Prevents mid-flight model swaps when admin changes the DB setting.
    _pinned_model_name: ClassVar[str | None] = None

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

    # Concurrent GPU model sharing (Phase 2)
    concurrent_requests: int = 1

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
            model_name=cls._resolve_model_name(),
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
            concurrent_requests=cls._resolve_concurrent_requests(),
        )

        # Divide batch sizes by concurrent_requests to share GPU bandwidth
        if config.concurrent_requests > 1:
            config.batch_size = max(4, config.batch_size // config.concurrent_requests)

        # Apply task-level overrides (all overrides are intentional, including None
        # values like hallucination_silence_threshold=None meaning "disabled")
        for key, value in overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

        logger.info(
            f"TranscriptionConfig: model={config.model_name}, device={config.device}, "
            f"compute_type={config.compute_type}, batch_size={config.batch_size}, "
            f"beam_size={config.beam_size}, language={config.source_language}, "
            f"translate={config.translate_to_english}, "
            f"concurrent_requests={config.concurrent_requests}"
        )

        return config

    @classmethod
    def pin_model(cls, model_name: str) -> None:
        """Pin the model name after preloading at worker startup.

        Once pinned, all subsequent ``from_environment()`` calls use this value
        instead of re-reading the DB.  This prevents mid-flight model swaps when
        the admin changes the DB setting before restarting the worker — running
        tasks always use the model that's actually loaded in VRAM.

        The pin is reset on process restart (new worker reads fresh from DB).
        """
        cls._pinned_model_name = model_name
        logger.info("Model name pinned to '%s' for this worker process", model_name)

    @classmethod
    def _resolve_model_name(cls) -> str:
        """Resolve the Whisper model name: pinned value -> DB -> env -> default.

        Resolution order:
        1. Pinned value (set at worker startup after model preload)
        2. SystemSettings DB key ``asr.local_model`` (admin-set)
        3. WHISPER_MODEL environment variable
        4. Hardcoded default ``large-v3-turbo``
        """
        # Fast path: use pinned value from worker startup (no DB hit)
        if cls._pinned_model_name is not None:
            return cls._pinned_model_name

        # Startup path: read from DB (first call before pin_model is called)
        try:
            from app.db.session_utils import session_scope
            from app.models.system_settings import SystemSettings

            with session_scope() as db:
                setting = (
                    db.query(SystemSettings).filter(SystemSettings.key == "asr.local_model").first()
                )
                if setting and setting.value:
                    return str(setting.value)
        except Exception:  # noqa: S110  # nosec B110
            # DB not available (e.g., during testing, worker startup race) — fall back to env
            logger.debug("Could not read asr.local_model from DB, using env var")
        return os.getenv("WHISPER_MODEL", "large-v3-turbo")

    @staticmethod
    def _resolve_concurrent_requests() -> int:
        """Resolve GPU_CONCURRENT_REQUESTS from env, with auto-detection."""
        raw = os.getenv("GPU_CONCURRENT_REQUESTS", "1").strip().lower()
        if raw == "auto":
            return TranscriptionConfig._auto_concurrent()
        try:
            return max(1, int(raw))
        except ValueError:
            logger.warning(f"Invalid GPU_CONCURRENT_REQUESTS='{raw}', defaulting to 1")
            return 1

    @staticmethod
    def _auto_concurrent() -> int:
        """Calculate max concurrent tasks from available VRAM.

        Profiled model sizes (large-v3-turbo + PyAnnote v4):
          - Shared model weights: ~6GB (CTranslate2 whisper + PyAnnote)
          - Per-task inference overhead: ~1GB (activations, batch buffers)
        Formula: (total_vram - 6000MB for models) // 1000MB per task, capped at 4.
        """
        try:
            import torch

            if torch.cuda.is_available():
                total_mb = torch.cuda.get_device_properties(0).total_memory / (1024**2)
                concurrent = int((total_mb - 6000) // 1000)
                return max(1, min(concurrent, 4))
        except Exception as e:
            logger.debug(f"Auto-concurrent VRAM detection failed: {e}")
        return 1
