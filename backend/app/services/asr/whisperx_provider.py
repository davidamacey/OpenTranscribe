"""WhisperX ASR provider (requires local GPU).

This is a thin wrapper around the existing WhisperXService to conform
to the ASRProvider interface. Requires GPU hardware and PyAnnote for diarization.

NOTE: This provider is currently deferred — Deepgram is the primary provider.
It exists as a reference implementation for future GPU-based deployments.
"""

import logging
import os
from typing import Callable

from .base import ASRProvider
from .types import Segment, TranscriptionConfig, TranscriptionResult, Word

logger = logging.getLogger(__name__)


class WhisperXProvider(ASRProvider):
    """WhisperX ASR provider wrapping the existing WhisperXService."""

    def __init__(
        self,
        model_name: str = "large-v2",
        models_dir: str = "/app/models",
        huggingface_token: str | None = None,
    ):
        self._model_name = model_name
        self._models_dir = models_dir
        self._huggingface_token = huggingface_token or os.getenv("HUGGINGFACE_TOKEN")

    @property
    def provider_name(self) -> str:
        return "whisperx"

    def supports_diarization(self) -> bool:
        return True  # Via PyAnnote

    def supports_keyterms(self) -> bool:
        return False

    async def transcribe(
        self,
        audio_path: str,
        config: TranscriptionConfig,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio using WhisperX + PyAnnote pipeline."""
        from app.tasks.transcription.whisperx_service import WhisperXService

        whisperx_service = WhisperXService(
            model_name=self._model_name,
            models_dir=self._models_dir,
            source_language=config.source_language,
            translate_to_english=config.translate_to_english,
        )

        result = whisperx_service.process_full_pipeline(
            audio_path,
            self._huggingface_token,
            progress_callback=progress_callback,
            min_speakers=config.min_speakers,
            max_speakers=config.max_speakers,
            num_speakers=config.num_speakers,
        )

        return self._convert_result(result)

    def _convert_result(self, whisperx_result: dict) -> TranscriptionResult:
        """Convert WhisperX dict result to unified TranscriptionResult."""
        segments = []
        for seg in whisperx_result.get("segments", []):
            words = []
            for w in seg.get("words", []):
                if "start" in w and "end" in w:
                    words.append(
                        Word(
                            text=w.get("word", ""),
                            start=w.get("start", 0.0),
                            end=w.get("end", 0.0),
                            confidence=w.get("score", 1.0),
                            speaker_label=w.get("speaker"),
                        )
                    )

            speaker = seg.get("speaker")
            avg_confidence = sum(w.confidence for w in words) / len(words) if words else 1.0

            segments.append(
                Segment(
                    text=seg.get("text", ""),
                    start=seg.get("start", 0.0),
                    end=seg.get("end", 0.0),
                    speaker_label=speaker,
                    confidence=avg_confidence,
                    words=words,
                )
            )

        return TranscriptionResult(
            segments=segments,
            detected_language=whisperx_result.get("language"),
            provider_name="whisperx",
            provider_model=self._model_name,
        )
