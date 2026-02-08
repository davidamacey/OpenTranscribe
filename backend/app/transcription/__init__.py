"""Custom transcription pipeline using faster-whisper BatchedInferencePipeline.

Replaces the WhisperX transcription path with direct faster-whisper usage for
batched transcription with native word-level timestamps, combined with PyAnnote v4
diarization and fast speaker assignment.

Usage:
    from app.transcription import TranscriptionPipeline, TranscriptionConfig

    config = TranscriptionConfig.from_environment(min_speakers=2, max_speakers=10)
    pipeline = TranscriptionPipeline(config)
    result = pipeline.process("/path/to/audio.wav", progress_callback=my_callback)
"""

from app.transcription.config import TranscriptionConfig
from app.transcription.pipeline import TranscriptionPipeline

__all__ = ["TranscriptionConfig", "TranscriptionPipeline"]
