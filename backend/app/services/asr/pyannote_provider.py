"""pyannote.ai STT Orchestration ASR provider (stub — Phase A).

pyannote.ai offers premium diarization bundled with transcription (Nvidia Parakeet
or whisper-large-v3-turbo) via their STT Orchestration API.  This stub implements
only ``validate_connection()`` so the provider can be configured and tested.
Full ``transcribe()`` will follow in Phase B.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from .base import ASRProvider
from .types import ASRConfig
from .types import ASRResult

logger = logging.getLogger(__name__)


class PyAnnoteProvider(ASRProvider):
    """pyannote.ai STT Orchestration provider.

    Phase A: connection validation only.  ``transcribe()`` raises
    NotImplementedError until Phase B.
    """

    def __init__(self, api_key: str, model_name: str = "parakeet"):
        self._api_key = api_key
        self._model_name = model_name

    @property
    def provider_name(self) -> str:
        return "pyannote"

    def supports_diarization(self) -> bool:
        return True

    def supports_vocabulary(self) -> bool:
        return False

    def supports_translation(self) -> bool:
        return False

    def validate_connection(self) -> tuple[bool, str, float]:
        """Validate the API key by calling the pyannote.ai /v1/info endpoint."""
        start = time.time()

        if not self._api_key:
            ms = (time.time() - start) * 1000
            return False, "API key is required for pyannote.ai", ms

        try:
            import httpx

            resp = httpx.get(
                "https://api.pyannote.ai/v1/info",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=15.0,
            )
            ms = (time.time() - start) * 1000
            if resp.status_code == 200:
                return True, "Connected to pyannote.ai", ms
            if resp.status_code == 401:
                return False, "Invalid API key", ms
            return False, f"pyannote.ai returned HTTP {resp.status_code}", ms
        except ImportError:
            ms = (time.time() - start) * 1000
            return False, "httpx package not installed (required for pyannote.ai)", ms
        except Exception as exc:
            ms = (time.time() - start) * 1000
            sanitized = self._sanitize_error(str(exc), self._api_key)
            return False, f"Connection failed: {sanitized}", ms

    def transcribe(
        self,
        audio_path: str,
        config: ASRConfig,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> ASRResult:
        """Not yet implemented — Phase B will add full STT Orchestration support."""
        raise NotImplementedError(
            "PyAnnoteProvider.transcribe() is not yet implemented. "
            "Phase B will add STT Orchestration (transcription + diarization)."
        )
