"""PyAnnote v4 speaker diarization — no WhisperX wrapper.

Extracted from pyannote_compat.py's DiarizationPipelineV4 with direct
PyAnnote v4 API usage. No monkey-patching needed since we don't go
through WhisperX's diarization path.
"""

import logging
import time
from typing import NoReturn

import numpy as np
import pandas as pd
import torch

from app.transcription.config import TranscriptionConfig

logger = logging.getLogger(__name__)

PYANNOTE_V4_MODEL = "pyannote/speaker-diarization-community-1"
PYANNOTE_V3_FALLBACK = "pyannote/speaker-diarization-3.1"


class SpeakerDiarizer:
    """PyAnnote v4 speaker diarization."""

    def __init__(self, config: TranscriptionConfig):
        self.config = config
        self._pipeline = None
        self._model_name: str | None = None

    @property
    def is_loaded(self) -> bool:
        return self._pipeline is not None

    def load_model(self) -> None:
        """Load the PyAnnote diarization pipeline."""
        from pyannote.audio import Pipeline

        step_start = time.perf_counter()

        logger.info(f"Loading PyAnnote v4 pipeline: {PYANNOTE_V4_MODEL}")

        try:
            self._pipeline = Pipeline.from_pretrained(PYANNOTE_V4_MODEL, token=self.config.hf_token)
            if self._pipeline is None:
                import os

                if os.getenv("HF_HUB_OFFLINE") == "1":
                    msg = (
                        f"PyAnnote model '{PYANNOTE_V4_MODEL}' returned None. "
                        "In offline mode, models must be pre-downloaded. "
                        "Ensure the model cache directory contains the PyAnnote models."
                    )
                else:
                    msg = (
                        f"PyAnnote model '{PYANNOTE_V4_MODEL}' returned None. "
                        "This usually means your HuggingFace token lacks access to this gated model. "
                        "Please: 1) Create a token at https://huggingface.co/settings/tokens with Read permissions, "
                        "2) Accept the model agreement at https://huggingface.co/pyannote/speaker-diarization-3.1, "
                        "3) Set HUGGINGFACE_TOKEN in your .env file, and 4) Restart the containers."
                    )
                raise PermissionError(msg)
            self._model_name = PYANNOTE_V4_MODEL
            logger.info(f"Loaded PyAnnote v4 model: {PYANNOTE_V4_MODEL}")
        except Exception as e:
            logger.warning(
                f"Failed to load v4 model '{PYANNOTE_V4_MODEL}': {e}. "
                f"Trying fallback: {PYANNOTE_V3_FALLBACK}"
            )
            try:
                self._pipeline = Pipeline.from_pretrained(
                    PYANNOTE_V3_FALLBACK, token=self.config.hf_token
                )
                if self._pipeline is None:
                    import os

                    if os.getenv("HF_HUB_OFFLINE") == "1":
                        msg = (
                            f"PyAnnote fallback model '{PYANNOTE_V3_FALLBACK}' returned None. "
                            "In offline mode, models must be pre-downloaded. "
                            "Ensure the model cache directory contains the PyAnnote models."
                        )
                    else:
                        msg = (
                            f"PyAnnote fallback model '{PYANNOTE_V3_FALLBACK}' returned None. "
                            "This usually means your HuggingFace token lacks access to this gated model. "
                            "Please verify your HUGGINGFACE_TOKEN and accept the model agreement on HuggingFace."
                        )
                    raise PermissionError(msg)
                self._model_name = PYANNOTE_V3_FALLBACK
                logger.info(f"Loaded fallback model: {PYANNOTE_V3_FALLBACK}")
            except Exception as fallback_e:
                raise RuntimeError(
                    f"Could not load PyAnnote diarization model. "
                    f"Primary: {e}, Fallback: {fallback_e}"
                ) from e

        # Move to device
        device = torch.device(self.config.device)
        self._pipeline = self._pipeline.to(device)  # type: ignore[attr-defined]

        elapsed = time.perf_counter() - step_start
        logger.info(f"TIMING: diarizer model loaded in {elapsed:.3f}s on {device}")

    def diarize(self, audio: np.ndarray) -> tuple[pd.DataFrame, dict]:
        """Run speaker diarization on audio.

        Args:
            audio: Audio waveform as 16kHz mono float32 numpy array.

        Returns:
            Tuple of:
                diarize_df: DataFrame with columns [segment, label, speaker, start, end]
                    Has attrs: overlaps, overlap_count, overlap_duration
                overlap_info: Dict with count, duration, regions keys.

        Raises:
            RuntimeError: If model not loaded or diarization fails.
            PermissionError: If HuggingFace token lacks access.
        """
        if not self.is_loaded:
            raise RuntimeError("Diarizer model not loaded. Call load_model() first.")

        step_start = time.perf_counter()

        # Prepare audio input
        waveform = torch.from_numpy(audio)
        if waveform.ndim == 1:
            waveform = waveform.unsqueeze(0)
        audio_input = {"waveform": waveform, "sample_rate": 16000}

        # Build kwargs
        pipeline_kwargs = {}
        if self.config.num_speakers is not None:
            pipeline_kwargs["num_speakers"] = self.config.num_speakers
        else:
            pipeline_kwargs["min_speakers"] = self.config.min_speakers
            pipeline_kwargs["max_speakers"] = self.config.max_speakers

        logger.info(f"Running diarization with kwargs: {pipeline_kwargs}")

        try:
            assert self._pipeline is not None, "Pipeline not initialized"
            output = self._pipeline(audio_input, **pipeline_kwargs)  # type: ignore[misc]
        except Exception as e:
            self._handle_diarization_error(e)

        # Extract diarization results (handles v4 output format)
        exclusive = self._extract_diarization(output, prefer_exclusive=True)
        full = self._extract_diarization(output, prefer_exclusive=False)

        # Convert to DataFrame
        diarize_df = pd.DataFrame(
            exclusive.itertracks(yield_label=True),
            columns=["segment", "label", "speaker"],
        )
        diarize_df["start"] = diarize_df["segment"].apply(lambda x: x.start)
        diarize_df["end"] = diarize_df["segment"].apply(lambda x: x.end)

        # Extract overlap info
        overlaps = self._extract_overlaps(full)
        overlap_info = {"count": 0, "duration": 0.0, "regions": []}

        if overlaps:
            total_duration = sum(o["end"] - o["start"] for o in overlaps)
            overlap_info = {
                "count": len(overlaps),
                "duration": total_duration,
                "regions": overlaps,
            }
            diarize_df.attrs["overlaps"] = overlaps
            diarize_df.attrs["overlap_count"] = len(overlaps)
            diarize_df.attrs["overlap_duration"] = total_duration
            logger.info(
                f"Detected {len(overlaps)} overlapping regions (total: {total_duration:.2f}s)"
            )

        elapsed = time.perf_counter() - step_start
        num_speakers = diarize_df["speaker"].nunique()
        logger.info(
            f"TIMING: diarization completed in {elapsed:.3f}s - "
            f"{num_speakers} speakers, {len(diarize_df)} segments"
        )

        return diarize_df, overlap_info

    def unload_model(self) -> None:
        """Release model memory."""
        if self._pipeline is not None:
            del self._pipeline
            self._pipeline = None
        logger.info("Diarizer model unloaded")

    def _extract_diarization(self, output, prefer_exclusive: bool = True):
        """Extract diarization annotation from PyAnnote output."""
        if prefer_exclusive and hasattr(output, "exclusive_speaker_diarization"):
            return output.exclusive_speaker_diarization
        elif hasattr(output, "speaker_diarization"):
            return output.speaker_diarization
        elif hasattr(output, "exclusive_speaker_diarization"):
            return output.exclusive_speaker_diarization
        else:
            return output

    def _extract_overlaps(self, diarization) -> list[dict[str, float]]:
        """Extract overlapping speech regions from diarization."""
        overlaps: list[dict[str, float]] = []
        try:
            if hasattr(diarization, "get_overlap"):
                for segment in diarization.get_overlap():
                    overlaps.append(
                        {
                            "start": segment.start,
                            "end": segment.end,
                        }
                    )
        except Exception as e:
            logger.warning(f"Could not extract overlap regions: {e}")
        return overlaps

    def _handle_diarization_error(self, e: Exception) -> NoReturn:
        """Convert diarization errors to user-friendly messages."""
        error_msg = str(e)

        if "401" in error_msg or "unauthorized" in error_msg.lower():
            raise PermissionError(
                "Cannot access PyAnnote speaker diarization models. "
                "Your HuggingFace token does not have access to the required gated model. "
                "You must accept the model agreement on HuggingFace: "
                "pyannote/speaker-diarization-community-1 "
                "(https://huggingface.co/pyannote/speaker-diarization-community-1). "
                "After accepting, wait 1-2 minutes, restart containers, and retry."
            ) from e

        if "403" in error_msg or "forbidden" in error_msg.lower():
            raise PermissionError(
                "Access forbidden to PyAnnote models. "
                "Your HuggingFace token may not have Read permissions, "
                "or you have not accepted the gated model agreement. "
                "Please verify your token at https://huggingface.co/settings/tokens "
                "and accept: pyannote/speaker-diarization-community-1."
            ) from e

        if (
            "cannot find the requested files" in error_msg.lower()
            or "locate the file on the hub" in error_msg.lower()
        ):
            raise PermissionError(
                "Cannot download PyAnnote models from HuggingFace. "
                "Please accept the model agreement at "
                "https://huggingface.co/pyannote/speaker-diarization-community-1, "
                "wait 1-2 minutes, then restart and retry."
            ) from e

        if "libcudnn" in error_msg.lower():
            raise RuntimeError(
                "CUDA cuDNN library compatibility error detected during diarization. "
                f"Technical details: {error_msg}"
            ) from e

        if "cuda" in error_msg.lower() or "gpu" in error_msg.lower():
            raise RuntimeError(
                f"GPU processing error during speaker diarization: {error_msg}"
            ) from e

        raise RuntimeError(f"Speaker diarization failed: {error_msg}") from e
