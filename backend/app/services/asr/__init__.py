"""ASR (Automatic Speech Recognition) provider abstraction layer.

Supports multiple ASR engines through a unified interface.
Currently implemented: Deepgram Nova-3 Medical.
"""

from .base import ASRProvider
from .factory import get_asr_provider
from .types import Segment
from .types import TranscriptionConfig
from .types import TranscriptionResult
from .types import Word

__all__ = [
    "ASRProvider",
    "TranscriptionConfig",
    "TranscriptionResult",
    "Segment",
    "Word",
    "get_asr_provider",
]
