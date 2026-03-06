"""Speechmatics batch ASR provider.

Targets speechmatics-python >= 1.11.0 (BatchClient v2 API).
Supports 55+ languages, 3 diarization modes (speaker / channel / none),
and additional vocabulary hints.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable

from .base import ASRProvider
from .types import ASRConfig
from .types import ASRResult
from .types import ASRSegment
from .types import ASRWord

logger = logging.getLogger(__name__)

# Polling limits (2-hour hard cap, consistent with other cloud providers).
_MAX_POLL = 720  # iterations — 720 × 10 s = 7 200 s
_POLL_INTERVAL = 10  # seconds per poll


class SpeechmaticsProvider(ASRProvider):
    def __init__(self, api_key: str, model_name: str = "standard"):
        self._api_key = api_key
        self._model_name = model_name

    @property
    def provider_name(self) -> str:
        return "speechmatics"

    def supports_diarization(self) -> bool:
        return True

    def supports_vocabulary(self) -> bool:
        return True

    def supports_translation(self) -> bool:
        return False

    def validate_connection(self) -> tuple[bool, str, float]:
        """Test credentials with a lightweight list-jobs call (limit=1)."""
        start = time.time()
        try:
            import speechmatics  # noqa: F401
        except ImportError:
            return (
                False,
                "speechmatics-python not installed. Run: pip install 'speechmatics-python>=1.11.0'",
                0.0,
            )
        try:
            import requests as _requests

            resp = _requests.get(
                "https://asr.api.speechmatics.com/v2/jobs",
                headers={"Authorization": f"Bearer {self._api_key}"},
                params={"limit": 1},
                timeout=10,
            )
            ms = (time.time() - start) * 1000
            if resp.status_code == 401:
                return (
                    False,
                    self._sanitize_error(
                        "Invalid Speechmatics API key (401 Unauthorized)", self._api_key
                    ),
                    ms,
                )
            return True, "Speechmatics connection successful", ms
        except Exception as e:
            ms = (time.time() - start) * 1000
            return False, self._sanitize_error(str(e), self._api_key), ms

    def transcribe(  # noqa: C901
        self,
        audio_path: str,
        config: ASRConfig,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> ASRResult:
        try:
            from speechmatics.batch_client import BatchClient
            from speechmatics.models import AudioSettings
            from speechmatics.models import BatchTranscriptionConfig
            from speechmatics.models import ConnectionSettings
            from speechmatics.models import TranscriptionConfig
        except ImportError as err:
            raise RuntimeError(
                "speechmatics-python not installed. Run: pip install 'speechmatics-python>=1.11.0'"
            ) from err

        # Validate the file exists before attempting network I/O.
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        filename = os.path.basename(audio_path)
        t_start = time.time()
        logger.info(
            "Speechmatics transcribe start: file=%s model=%s diarize=%s lang=%s",
            filename,
            self._model_name,
            config.enable_diarization,
            config.language,
        )

        if progress_callback:
            progress_callback(0.1, "Uploading to Speechmatics…")

        conn = ConnectionSettings(
            url="https://asr.api.speechmatics.com/v2", auth_token=self._api_key
        )
        lang = config.language if config.language != "auto" else "en"

        tc = TranscriptionConfig(
            language=lang,
            diarization="speaker" if config.enable_diarization else None,
            additional_vocab=[{"content": t} for t in (config.vocabulary or [])],
        )
        job_cfg = BatchTranscriptionConfig(
            transcription_config=tc,
            audio_settings=AudioSettings(),
        )

        if progress_callback:
            progress_callback(0.2, "Transcribing with Speechmatics…")

        try:
            with BatchClient(conn) as client:
                with open(audio_path, "rb") as f:
                    job_id = client.submit_job(audio=(audio_path, f), transcription_config=job_cfg)
                for _attempt in range(_MAX_POLL):
                    job = client.get_job(job_id)
                    st = job["job"]["status"]
                    if st == "done":
                        break
                    if st == "rejected":
                        raise RuntimeError(f"Speechmatics job rejected: {job}")
                    time.sleep(_POLL_INTERVAL)
                    if progress_callback:
                        progress_callback(
                            0.3 + min(_attempt / _MAX_POLL, 0.5), "Speechmatics processing…"
                        )
                else:
                    raise RuntimeError(
                        f"Speechmatics transcription timed out after {_MAX_POLL * _POLL_INTERVAL} seconds"
                    )
                result = client.get_job_result(job_id)
        except RuntimeError:
            raise
        except Exception as exc:
            sanitized = self._sanitize_error(str(exc), self._api_key)
            logger.error("Speechmatics transcription failed for file=%s: %s", filename, sanitized)
            raise RuntimeError(f"Speechmatics transcription failed: {sanitized}") from exc

        elapsed_ms = (time.time() - t_start) * 1000
        logger.info(
            "Speechmatics transcribe complete: file=%s duration_ms=%.0f", filename, elapsed_ms
        )

        if progress_callback:
            progress_callback(0.85, "Parsing Speechmatics response…")

        segments: list[ASRSegment] = []
        cur_spk: str | None = None
        cur_words: list[ASRWord] = []
        cur_start = 0.0

        for item in result.get("results", []):
            if item.get("type") != "word":
                continue
            alts = item.get("alternatives", [{}])
            if not alts:
                continue
            word = alts[0].get("content", "")
            start = item.get("start_time", 0.0)
            end = item.get("end_time", 0.0)
            conf = alts[0].get("confidence", 1.0)
            # Speechmatics places the speaker label inside alternatives[0], e.g. "S1", "S2",
            # or "UU" when the speaker cannot be identified.  Treat "UU" as no speaker.
            raw_spk = alts[0].get("speaker")  # "S1" | "S2" | "UU" | None
            spk = None if (raw_spk is None or raw_spk == "UU") else raw_spk

            if spk != cur_spk:
                if cur_words:
                    avg_conf = sum(w.confidence for w in cur_words) / len(cur_words)
                    segments.append(
                        ASRSegment(
                            text=" ".join(w.word for w in cur_words),
                            start=cur_start,
                            end=cur_words[-1].end,
                            speaker=self._normalize_speaker_label(cur_spk)
                            if cur_spk is not None
                            else None,
                            confidence=avg_conf,
                            words=cur_words,
                        )
                    )
                cur_spk, cur_words, cur_start = spk, [], start

            cur_words.append(ASRWord(word, start, end, conf))

        if cur_words:
            avg_conf = sum(w.confidence for w in cur_words) / len(cur_words)
            segments.append(
                ASRSegment(
                    text=" ".join(w.word for w in cur_words),
                    start=cur_start,
                    end=cur_words[-1].end,
                    speaker=self._normalize_speaker_label(cur_spk) if cur_spk is not None else None,
                    confidence=avg_conf,
                    words=cur_words,
                )
            )

        if progress_callback:
            progress_callback(1.0, "Speechmatics transcription complete")

        # has_speakers is True only when we actually received speaker labels in the output,
        # not merely because diarization was requested (the API may not return labels
        # for short or silent audio even when the feature was enabled).
        actual_has_speakers = config.enable_diarization and any(s.speaker for s in segments)

        return ASRResult(
            segments=segments,
            language=lang,
            has_speakers=actual_has_speakers,
            provider_name="speechmatics",
            model_name=self._model_name,
        )
