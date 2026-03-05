"""Shared data types for ASR provider abstraction."""

from dataclasses import dataclass, field


@dataclass
class Word:
    """A single transcribed word with timing and confidence."""

    text: str
    start: float
    end: float
    confidence: float = 1.0
    speaker_label: str | None = None


@dataclass
class Segment:
    """A transcription segment (utterance) with speaker and timing."""

    text: str
    start: float
    end: float
    speaker_label: str | None = None
    confidence: float = 1.0
    words: list[Word] = field(default_factory=list)


@dataclass
class TranscriptionResult:
    """Unified result from any ASR provider."""

    segments: list[Segment]
    detected_language: str | None = None
    provider_name: str = ""
    provider_model: str = ""
    provider_metadata: dict = field(default_factory=dict)


@dataclass
class TranscriptionConfig:
    """Configuration passed to ASR providers."""

    source_language: str | None = None
    translate_to_english: bool = False
    min_speakers: int = 1
    max_speakers: int = 20
    num_speakers: int | None = None
    keyterms: list[str] = field(default_factory=list)
