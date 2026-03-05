"""Abstract base class for ASR providers."""

from abc import ABC, abstractmethod
from typing import Callable

from .types import TranscriptionConfig, TranscriptionResult


class ASRProvider(ABC):
    """Abstract base class that all ASR providers must implement."""

    @abstractmethod
    async def transcribe(
        self,
        audio_path: str,
        config: TranscriptionConfig,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> TranscriptionResult:
        """Transcribe an audio file and return a unified result.

        Args:
            audio_path: Path to the audio file (WAV preferred).
            config: Transcription configuration (language, speakers, keyterms).
            progress_callback: Optional callback(progress_float, message_str).

        Returns:
            TranscriptionResult with segments, words, and metadata.
        """

    @abstractmethod
    def supports_diarization(self) -> bool:
        """Whether this provider handles speaker diarization internally."""

    @abstractmethod
    def supports_keyterms(self) -> bool:
        """Whether this provider supports custom vocabulary/keyterms."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Short identifier for this provider (e.g., 'deepgram', 'whisperx')."""
