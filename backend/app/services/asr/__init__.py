"""ASR provider abstraction layer — 10 providers (1 local + 9 cloud)."""

from .factory import ASRProviderFactory
from .types import ASRConfig
from .types import ASRResult
from .types import ASRSegment
from .types import ASRWord

__all__ = ["ASRProviderFactory", "ASRConfig", "ASRResult", "ASRSegment", "ASRWord"]
