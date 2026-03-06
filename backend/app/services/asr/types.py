"""Shared data types for ASR providers."""
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Any


@dataclass
class ASRConfig:
    """Configuration passed to each ASR provider."""

    language: str = "auto"
    min_speakers: int = 1
    max_speakers: int = 20
    num_speakers: int | None = None
    enable_diarization: bool = True
    translate_to_english: bool = False
    vocabulary: list[str] | None = None  # Custom vocabulary terms (hotwords)
    model_name: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    region: str | None = None
    compute_type: str | None = None
    device: str | None = None
    vad_threshold: float = 0.5
    hallucination_silence_threshold: float | None = None
    repetition_penalty: float = 1.0
    asr_config_uuid: str | None = None  # Track which config was used


@dataclass
class ASRWord:
    """A single word with timestamps from ASR output."""

    word: str
    start: float
    end: float
    confidence: float = 1.0


@dataclass
class ASRSegment:
    """A transcript segment from ASR output."""

    text: str
    start: float
    end: float
    speaker: str | None = None
    confidence: float | None = None
    words: list[ASRWord] = field(default_factory=list)


@dataclass
class ASRResult:
    """Full result from an ASR provider transcription."""

    segments: list[ASRSegment]
    language: str
    has_speakers: bool = False
    speaker_embeddings: dict[str, Any] | None = None
    overlap_info: dict | None = None
    provider_name: str = "local"
    model_name: str = ""
    metadata: dict = field(default_factory=dict)
