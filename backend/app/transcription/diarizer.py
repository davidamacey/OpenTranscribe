"""PyAnnote v4 speaker diarization.

Direct PyAnnote v4 API usage for speaker diarization with configurable
speaker count parameters.
"""

import gc
import logging
import os
import time
from typing import NoReturn

import numpy as np
import pandas as pd
import torch

from app.transcription.config import TranscriptionConfig
from app.utils.pyannote_utils import build_native_embeddings
from app.utils.pyannote_utils import extract_overlap_regions

logger = logging.getLogger(__name__)

# Retry sequence for segmentation batch_size on OOM
_BATCH_SIZE_RETRY_SEQUENCE = [16, 8, 4, 2, 1]

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
                        "2) Accept the model agreement at https://huggingface.co/pyannote/speaker-diarization-community-1, "
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

        # Phase C: plumb the VRAM-budget policy into the fork. Settings come
        # from DIARIZATION_VRAM_BUDGET_MB / DIARIZATION_MIXED_PRECISION in
        # app.core.config. None budget -> fork queries live free VRAM.
        self._apply_vram_policy()

        # Configure segmentation batch_size based on GPU VRAM or env override.
        # PyAnnote defaults to 32 which causes OOM on GPUs with ≤12GB VRAM.
        self._configure_segmentation_batch_size()

        # Configure embedding batch_size for speaker embedding extraction.
        # PyAnnote defaults to 1, causing ~850K individual GPU forward passes for
        # long audio. Batch size 32 reduces kernel launches 32x with identical results.
        # See docs/GPU_OPTIMIZATION_PATCHES.md for benchmarks and evidence.
        self._configure_embedding_batch_size()

        elapsed = time.perf_counter() - step_start
        logger.info(f"TIMING: diarizer model loaded in {elapsed:.3f}s on {device}")

    def _apply_vram_policy(self) -> None:
        """Wire Phase C settings into the pyannote fork pipeline.

        Reads DIARIZATION_VRAM_BUDGET_MB and DIARIZATION_MIXED_PRECISION from
        app.core.config.settings and pushes them onto the loaded fork
        pipeline. Safe no-op on stock upstream pyannote.
        """
        if self._pipeline is None:
            return
        try:
            from app.core.config import settings
        except Exception:
            return
        budget = getattr(settings, "DIARIZATION_VRAM_BUDGET_MB", None)
        mp_embed = getattr(settings, "DIARIZATION_MIXED_PRECISION", False)
        if hasattr(self._pipeline, "vram_budget_mb"):
            self._pipeline.vram_budget_mb = budget
        if hasattr(self._pipeline, "embedding_mixed_precision"):
            self._pipeline.embedding_mixed_precision = bool(mp_embed)
        logger.info(f"Diarization VRAM policy: budget_mb={budget} mixed_precision={mp_embed}")

    def _configure_segmentation_batch_size(self) -> None:
        """Set PyAnnote's segmentation batch_size based on GPU VRAM or env override.

        PyAnnote's pretrained pipeline defaults to batch_size=32 for the internal
        segmentation model. This causes OOM on GPUs with limited VRAM, especially
        when the WhisperX model is still resident in memory.
        """
        if self._pipeline is None:
            return

        # Check env override first
        env_batch = os.getenv("DIARIZATION_BATCH_SIZE")
        if env_batch is not None:
            try:
                batch_size = int(env_batch)
                self._pipeline.segmentation_batch_size = batch_size
                logger.info(f"Diarization segmentation batch_size set to {batch_size} (from env)")
                return
            except ValueError:
                logger.warning(
                    f"Invalid DIARIZATION_BATCH_SIZE='{env_batch}', using auto-detection"
                )

        # Auto-detect based on GPU VRAM
        if self.config.device == "cuda" and torch.cuda.is_available():
            total_memory = torch.cuda.get_device_properties(0).total_memory
            memory_gb = total_memory / (1024**3)

            if memory_gb >= 40:
                batch_size = 32  # A6000/A100 — keep default
            elif memory_gb >= 24:
                batch_size = 24
            elif memory_gb >= 16:
                batch_size = 16
            elif memory_gb >= 12:
                batch_size = 8  # RTX 3080 Ti — conservative, WhisperX still in memory
            else:
                batch_size = 4
        elif self.config.device == "mps":
            batch_size = 8
        else:
            batch_size = 4  # CPU

        current = self._pipeline.segmentation_batch_size
        if batch_size != current:
            self._pipeline.segmentation_batch_size = batch_size
            logger.info(
                f"Diarization segmentation batch_size: {current} → {batch_size} "
                f"(auto-detected for {self.config.device})"
            )
        else:
            logger.info(f"Diarization segmentation batch_size: {batch_size} (default OK)")

    def _configure_embedding_batch_size(self) -> None:
        """Set PyAnnote's embedding batch_size for speaker embedding extraction.

        The optimized PyAnnote fork auto-selects batch size (64-256) based on
        free GPU VRAM when embedding_batch_size <= 32. We set 32 here as a
        baseline that triggers the fork's auto-selection. With stock PyAnnote,
        32 is still a major improvement over the default of 1.

        Env override: DIARIZATION_EMBEDDING_BATCH_SIZE (bypasses auto-selection)
        Evidence: docs/GPU_OPTIMIZATION_RESULTS.md
        """
        if self._pipeline is None:
            return

        # Allow env override (bypasses auto-selection in optimized fork)
        env_batch = os.getenv("DIARIZATION_EMBEDDING_BATCH_SIZE")
        if env_batch is not None:
            try:
                batch_size = int(env_batch)
                self._pipeline.embedding_batch_size = batch_size
                logger.info(f"Diarization embedding batch_size set to {batch_size} (from env)")
                return
            except ValueError:
                logger.warning(
                    f"Invalid DIARIZATION_EMBEDDING_BATCH_SIZE='{env_batch}', using default 32"
                )

        # Set 32 as baseline. The optimized PyAnnote fork auto-elevates
        # batch_size to 64-256 based on free VRAM when it sees <= 32.
        # With stock PyAnnote, 32 is still 32x better than the default of 1.
        batch_size = 32

        current = getattr(self._pipeline, "embedding_batch_size", 1)
        if batch_size != current:
            self._pipeline.embedding_batch_size = batch_size
            logger.info(f"Diarization embedding batch_size: {current} → {batch_size}")
        else:
            logger.info(f"Diarization embedding batch_size: {batch_size} (already set)")

    def diarize(self, audio: np.ndarray) -> tuple[pd.DataFrame, dict, dict[str, np.ndarray] | None]:
        """Run speaker diarization on audio.

        Args:
            audio: Audio waveform as 16kHz mono float32 numpy array.

        Returns:
            Tuple of:
                diarize_df: DataFrame with columns [segment, label, speaker, start, end]
                    Has attrs: overlaps, overlap_count, overlap_duration
                overlap_info: Dict with count, duration, regions keys.
                native_embeddings: Dict mapping speaker labels to L2-normalized
                    centroid vectors, or None if disabled/unavailable.

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

        # Sub-stage timing via hook callback
        stage_timing: dict[str, dict[str, float]] = {}

        def timing_hook(step_name, step_artefact, **kwargs):
            now = time.perf_counter()
            if step_name not in stage_timing:
                stage_timing[step_name] = {"start": now, "last": now}
            else:
                stage_timing[step_name]["last"] = now

        raw_output = self._run_pipeline_with_oom_retry(
            audio_input, pipeline_kwargs, hook=timing_hook
        )

        centroids = getattr(raw_output, "speaker_embeddings", None)
        output = raw_output

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

        # Extract overlap info (gated by config, shared utility)
        overlaps = (
            extract_overlap_regions(full, self.config.overlap_min_duration)
            if self.config.enable_overlap_detection
            else []
        )
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

        # Build native embeddings from PyAnnote centroids (shared utility)
        native_embeddings = (
            build_native_embeddings(exclusive, centroids)
            if self.config.enable_native_embeddings
            else {}
        )

        # Log per-stage breakdown
        if stage_timing:
            stages = sorted(stage_timing.items(), key=lambda x: x[1].get("start", 0))
            breakdown = []
            for name, times in stages:
                duration = times["last"] - times["start"]
                breakdown.append(f"{name}={duration:.1f}s")
            logger.info(f"TIMING: diarization stages: {', '.join(breakdown)}")
            overlap_info["stage_timing"] = {
                name: round(times["last"] - times["start"], 3) for name, times in stages
            }

        elapsed = time.perf_counter() - step_start
        num_speakers = diarize_df["speaker"].nunique()
        logger.info(
            f"TIMING: diarization completed in {elapsed:.3f}s - "
            f"{num_speakers} speakers, {len(diarize_df)} segments"
        )

        return diarize_df, overlap_info, native_embeddings

    def _run_pipeline_with_oom_retry(self, audio_input: dict, pipeline_kwargs: dict, hook=None):
        """Run the diarization pipeline with automatic batch_size reduction on OOM.

        If the segmentation model hits an OOM error due to batch_size being too
        large, this method halves the batch_size and retries, down to batch_size=1.
        """
        assert self._pipeline is not None, "Pipeline not initialized"

        current_batch = self._pipeline.segmentation_batch_size

        # Build retry sequence: current value, then smaller values from the predefined list
        retry_sizes = [current_batch] + [s for s in _BATCH_SIZE_RETRY_SEQUENCE if s < current_batch]

        last_error: Exception | None = None
        for batch_size in retry_sizes:
            try:
                self._pipeline.segmentation_batch_size = batch_size
                call_kwargs = dict(pipeline_kwargs)
                if hook is not None:
                    call_kwargs["hook"] = hook
                raw_output = self._pipeline(audio_input, **call_kwargs)  # type: ignore[misc]
                if batch_size != current_batch:
                    logger.info(
                        f"Diarization succeeded with reduced batch_size={batch_size} "
                        f"(original: {current_batch})"
                    )
                return raw_output
            except Exception as e:
                if self._is_oom_error(e):
                    last_error = e
                    logger.warning(
                        f"Diarization OOM with batch_size={batch_size}, reducing and retrying..."
                    )
                    # Free GPU memory before retry
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    continue
                # Non-OOM error — don't retry
                self._handle_diarization_error(e)

        # All retries exhausted
        assert last_error is not None
        self._handle_diarization_error(last_error)

    @staticmethod
    def _is_oom_error(e: Exception) -> bool:
        """Check if an exception is a GPU out-of-memory error."""
        error_msg = str(e).lower()
        return (
            ("batch_size" in error_msg and "too large" in error_msg)
            or "out of memory" in error_msg
            or isinstance(e, torch.cuda.OutOfMemoryError)
        )

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

    def _handle_diarization_error(self, e: Exception) -> NoReturn:
        """Convert diarization errors to user-friendly messages."""
        error_msg = str(e)

        if self._is_oom_error(e):
            raise RuntimeError(
                "Speaker diarization ran out of GPU memory even at minimum batch size. "
                "This audio file may be too long for the available VRAM. "
                "Try setting DIARIZATION_BATCH_SIZE=1 in .env, or process shorter audio."
            ) from e

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
