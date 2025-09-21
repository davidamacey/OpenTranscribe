"""
Transcription module for OpenTranscribe.

This module contains the refactored transcription pipeline split into modular components:
- core.py: Main transcription task orchestrator
- metadata_extractor.py: Media metadata extraction utilities
- audio_processor.py: Audio file processing and conversion
- whisperx_service.py: WhisperX transcription service
- speaker_processor.py: Speaker diarization and management
- storage.py: Database storage utilities
- notifications.py: WebSocket notification utilities
"""

from .core import transcribe_audio_task

__all__ = ["transcribe_audio_task"]
