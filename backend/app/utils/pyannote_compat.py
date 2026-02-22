"""
PyAnnote v4 Compatibility Layer for WhisperX

This module provides a compatibility layer that allows WhisperX to work with
PyAnnote Audio v4, which has significant API changes from v3.

Key differences in PyAnnote v4:
- Model: pyannote/speaker-diarization-community-1 (CC-BY-4.0, single gate)
- Uses VBx clustering for better accuracy
- Uses `token=` parameter instead of `use_auth_token=`
- Output has `.speaker_diarization` and `.exclusive_speaker_diarization` properties
- WeSpeaker embeddings (256-dim) vs pyannote/embedding (512-dim)

Usage:
    from app.utils.pyannote_compat import apply_pyannote_v4_patch
    apply_pyannote_v4_patch()

    # Now WhisperX diarization will use PyAnnote v4
    import whisperx
    diarize_model = whisperx.DiarizationPipeline(...)
"""

import functools
import logging
from typing import TYPE_CHECKING
from typing import Optional
from typing import Union

import numpy as np
import torch

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)

# Track whether patch has been applied
_patch_applied = False

# PyAnnote v4 model identifier
PYANNOTE_V4_MODEL = "pyannote/speaker-diarization-community-1"


def build_native_embeddings(
    diarization,
    centroids: np.ndarray | None,
) -> dict[str, np.ndarray]:
    """Build speaker label -> L2-normalized centroid mapping from PyAnnote output.

    Shared between the native engine (Diarizer) and WhisperX engine
    (DiarizationPipelineV4) to avoid code duplication.

    Uses vectorized numpy L2-normalization for efficiency.

    Args:
        diarization: PyAnnote Annotation (exclusive diarization).
        centroids: ndarray of shape (num_speakers, embedding_dim) from PyAnnote,
            or None if OracleClustering was used.

    Returns:
        Dict mapping speaker labels to L2-normalized centroid vectors.
        Empty dict on any failure.
    """
    if centroids is None:
        logger.debug("No centroids returned by pipeline (OracleClustering?)")
        return {}

    try:
        labels = diarization.labels()
        if not labels:
            logger.warning("Diarization produced no speaker labels for centroid mapping")
            return {}

        # Truncate to available rows if labels exceed centroid rows
        n_usable = min(len(labels), centroids.shape[0])
        if n_usable < len(labels):
            dropped_labels = labels[n_usable:]
            logger.warning(
                f"Only {n_usable} centroid rows for {len(labels)} labels, "
                f"dropping speakers without centroids: {dropped_labels}"
            )

        # Vectorized L2-normalization of all centroids at once
        usable = centroids[:n_usable]
        norms = np.linalg.norm(usable, axis=1, keepdims=True)
        # Mask out near-zero vectors to avoid division by zero
        # Use [:, 0] instead of squeeze() to always produce 1-d array
        # (squeeze() on shape (1,1) gives 0-dim scalar, breaking indexing)
        valid_mask = norms[:, 0] > 1e-8
        normalized = np.where(norms > 1e-8, usable / norms, 0.0)

        embeddings = {labels[i]: normalized[i] for i in range(n_usable) if valid_mask[i]}

        skipped_labels = [labels[i] for i in range(n_usable) if not valid_mask[i]]
        if skipped_labels:
            logger.warning(
                f"Skipped {len(skipped_labels)} speakers with zero-norm centroids: {skipped_labels}"
            )

        logger.info(
            f"Built {len(embeddings)} native speaker embeddings "
            f"(dim={centroids.shape[1]}) from {len(labels)} labels"
        )
        return embeddings

    except Exception as e:
        logger.warning(f"Failed to build native embeddings: {e}")
        return {}


def extract_overlap_regions(
    diarization,
    min_duration: float = 0.25,
) -> list[dict[str, float]]:
    """Extract overlapping speech regions from a PyAnnote diarization annotation.

    Shared between the native engine (Diarizer) and WhisperX engine
    (DiarizationPipelineV4) to avoid code duplication.

    Args:
        diarization: PyAnnote Annotation object with full diarization.
        min_duration: Minimum overlap region duration in seconds.
            Regions shorter than this are filtered as noise.

    Returns:
        List of overlap regions as dicts with 'start' and 'end' keys.
    """
    if not hasattr(diarization, "get_overlap"):
        return []

    try:
        # Build regions via list comprehension
        all_regions = [{"start": seg.start, "end": seg.end} for seg in diarization.get_overlap()]

        # Filter by minimum duration in a single pass
        if min_duration > 0:
            overlaps = [o for o in all_regions if (o["end"] - o["start"]) >= min_duration]
            filtered = len(all_regions) - len(overlaps)
            if filtered > 0:
                logger.debug(f"Filtered {filtered} overlap regions below {min_duration}s threshold")
            return overlaps

        return all_regions
    except Exception as e:
        logger.warning(f"Could not extract overlap regions: {e}")
        return []


class DiarizationPipelineV4:
    """
    PyAnnote v4 compatible diarization pipeline for WhisperX.

    This class wraps PyAnnote's Pipeline for speaker-diarization-community-1
    and provides the same interface as whisperx.diarize.DiarizationPipeline.

    Key API changes handled:
    - Uses `token=` instead of `use_auth_token=`
    - Handles v4 output format with `output.speaker_diarization`
    - Supports exclusive diarization via `output.exclusive_speaker_diarization`
    """

    def __init__(
        self,
        model_name: str = PYANNOTE_V4_MODEL,
        use_auth_token: Optional[str] = None,
        token: Optional[str] = None,
        device: Optional[Union[str, torch.device]] = None,
        enable_overlap_detection: bool = True,
        overlap_min_duration: float = 0.25,
    ):
        """
        Initialize the PyAnnote v4 diarization pipeline.

        Args:
            model_name: The PyAnnote model to use. Defaults to v4 community model.
            use_auth_token: HuggingFace authentication token (legacy parameter).
            token: HuggingFace authentication token (PyAnnote v4 parameter).
            device: The device to run inference on (cpu, cuda, etc.)
            enable_overlap_detection: Whether to extract overlap regions.
            overlap_min_duration: Minimum duration (seconds) for overlap regions.
        """
        from pyannote.audio import Pipeline

        self.model_name = model_name
        self.device = device
        self.enable_overlap_detection = enable_overlap_detection
        self.overlap_min_duration = overlap_min_duration

        # Accept both token and use_auth_token for compatibility
        # Prefer token if both are provided
        auth_token = token or use_auth_token

        logger.info(f"Initializing PyAnnote v4 pipeline with model: {model_name}")

        try:
            # Try loading the v4 community model first
            self.model = Pipeline.from_pretrained(
                model_name,
                token=auth_token,
            )
            logger.info(f"Successfully loaded PyAnnote v4 model: {model_name}")
        except Exception as e:
            logger.warning(
                f"Failed to load PyAnnote v4 model '{model_name}': {e}. "
                "Attempting fallback to pyannote/speaker-diarization-3.1"
            )
            # Fall back to v3.1 model if v4 community model isn't available
            try:
                self.model = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    token=auth_token,
                )
                self.model_name = "pyannote/speaker-diarization-3.1"
                logger.info("Successfully loaded fallback model: pyannote/speaker-diarization-3.1")
            except Exception as fallback_e:
                logger.error(f"Failed to load fallback model: {fallback_e}")
                raise RuntimeError(
                    f"Could not load PyAnnote diarization model. "
                    f"Primary error: {e}, Fallback error: {fallback_e}"
                ) from e

        # Move model to specified device
        if device is not None:
            self.model = self.model.to(torch.device(device))

    def __call__(
        self,
        audio: Union[str, np.ndarray],
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
        num_speakers: Optional[int] = None,
    ) -> "pd.DataFrame":
        """
        Run speaker diarization on audio.

        Args:
            audio: Path to audio file or audio waveform as numpy array.
                   If numpy array, should be shape (samples,) or (channels, samples).
            min_speakers: Minimum number of speakers (optional hint).
            max_speakers: Maximum number of speakers (optional hint).
            num_speakers: Exact number of speakers if known (overrides min/max).

        Returns:
            Dictionary with diarization segments in WhisperX format:
            {
                "segments": [
                    {"start": float, "end": float, "speaker": str},
                    ...
                ]
            }
        """
        # Prepare audio input
        audio_input: str | dict[str, object]
        if isinstance(audio, np.ndarray):
            # Convert numpy array to format expected by PyAnnote
            # PyAnnote expects {"waveform": tensor, "sample_rate": int}
            waveform = torch.from_numpy(audio)
            if waveform.ndim == 1:
                waveform = waveform.unsqueeze(0)  # Add channel dimension
            audio_input = {"waveform": waveform, "sample_rate": 16000}
        else:
            # Assume it's a file path
            audio_input = audio

        # Build kwargs for pipeline
        pipeline_kwargs = {}
        if num_speakers is not None:
            pipeline_kwargs["num_speakers"] = num_speakers
        else:
            if min_speakers is not None:
                pipeline_kwargs["min_speakers"] = min_speakers
            if max_speakers is not None:
                pipeline_kwargs["max_speakers"] = max_speakers

        # Run diarization
        logger.debug(f"Running diarization with kwargs: {pipeline_kwargs}")

        raw_output = self.model(audio_input, **pipeline_kwargs)

        # PyAnnote v4 returns DiarizeOutput dataclass with speaker_embeddings attribute
        # (centroids are always computed internally, no need for return_embeddings kwarg)
        centroids = getattr(raw_output, "speaker_embeddings", None)
        output = raw_output

        # Handle v4 output format
        # In v4, output may have .speaker_diarization and .exclusive_speaker_diarization
        exclusive_diarization = self._extract_diarization(output, prefer_exclusive=True)
        full_diarization = self._extract_diarization(output, prefer_exclusive=False)

        # Convert to pandas DataFrame (WhisperX format)
        # This matches the original DiarizationPipeline return format
        import pandas as pd

        diarize_df = pd.DataFrame(
            exclusive_diarization.itertracks(yield_label=True),
            columns=["segment", "label", "speaker"],
        )
        diarize_df["start"] = diarize_df["segment"].apply(lambda x: x.start)
        diarize_df["end"] = diarize_df["segment"].apply(lambda x: x.end)

        # Build native speaker embeddings from PyAnnote centroids (shared utility)
        native_embeddings = build_native_embeddings(exclusive_diarization, centroids)

        # Extract overlap information from full diarization (gated by config)
        overlaps = (
            extract_overlap_regions(full_diarization, self.overlap_min_duration)
            if self.enable_overlap_detection
            else []
        )

        # Store overlap info as DataFrame attributes for compatibility
        if overlaps:
            total_overlap_duration = sum(o["end"] - o["start"] for o in overlaps)
            logger.info(
                f"Detected {len(overlaps)} overlapping regions "
                f"(total: {total_overlap_duration:.2f}s)"
            )
            # Store as attributes on the DataFrame for our code to access
            diarize_df.attrs["overlaps"] = overlaps
            diarize_df.attrs["overlap_count"] = len(overlaps)
            diarize_df.attrs["overlap_duration"] = total_overlap_duration
            diarize_df.attrs["_raw_diarization"] = full_diarization

        # Store native embeddings for upstream extraction
        if native_embeddings:
            diarize_df.attrs["native_embeddings"] = native_embeddings

        return diarize_df

    def _extract_diarization(self, output, prefer_exclusive: bool = True):
        """
        Extract diarization annotation from PyAnnote output.

        In PyAnnote v4, the output structure may differ:
        - output.speaker_diarization: Regular diarization with overlaps
        - output.exclusive_speaker_diarization: No overlaps (single speaker per segment)

        Args:
            output: PyAnnote pipeline output
            prefer_exclusive: If True, prefer exclusive diarization (no overlaps).
                            If False, prefer regular diarization (with overlaps).

        Returns:
            PyAnnote Annotation object
        """
        # Check for v4-style output attributes
        if prefer_exclusive and hasattr(output, "exclusive_speaker_diarization"):
            logger.debug("Using exclusive_speaker_diarization from v4 output")
            return output.exclusive_speaker_diarization
        elif hasattr(output, "speaker_diarization"):
            logger.debug("Using speaker_diarization from v4 output")
            return output.speaker_diarization
        elif hasattr(output, "exclusive_speaker_diarization"):
            logger.debug("Using exclusive_speaker_diarization from v4 output (fallback)")
            return output.exclusive_speaker_diarization
        else:
            # v3 style - output is the annotation directly
            logger.debug("Using direct annotation output (v3 style)")
            return output


def _patch_pyannote_inference() -> bool:
    """
    Patch PyAnnote's Inference class to accept use_auth_token as alias for token.

    This handles the API change where PyAnnote v4 uses `token` instead of
    `use_auth_token`, but WhisperX still passes `use_auth_token`.

    Returns:
        True if patch was applied successfully, False otherwise.
    """
    try:
        from pyannote.audio import Inference as OriginalInference

        # Check if already patched
        if hasattr(OriginalInference, "_patched_for_v4"):
            logger.debug("PyAnnote Inference already patched")
            return True

        original_init = OriginalInference.__init__

        def patched_init(self, *args, use_auth_token=None, **kwargs):
            # Convert use_auth_token to token if provided
            if use_auth_token is not None and "token" not in kwargs:
                kwargs["token"] = use_auth_token
            return original_init(self, *args, **kwargs)

        OriginalInference.__init__ = patched_init
        OriginalInference._patched_for_v4 = True

        logger.info("Patched PyAnnote Inference to accept use_auth_token parameter")
        return True

    except Exception as e:
        logger.warning(f"Could not patch PyAnnote Inference: {e}")
        return False


def _patch_pyannote_vad() -> bool:
    """
    Patch PyAnnote's VoiceActivityDetection to accept use_auth_token as alias for token.

    Returns:
        True if patch was applied successfully, False otherwise.
    """
    try:
        from pyannote.audio.pipelines import VoiceActivityDetection

        # Check if already patched
        if hasattr(VoiceActivityDetection, "_patched_for_v4"):
            logger.debug("PyAnnote VoiceActivityDetection already patched")
            return True

        original_init = VoiceActivityDetection.__init__

        def patched_init(self, *args, use_auth_token=None, **kwargs):
            # Convert use_auth_token to token if provided
            if use_auth_token is not None and "token" not in kwargs:
                kwargs["token"] = use_auth_token
            return original_init(self, *args, **kwargs)

        VoiceActivityDetection.__init__ = patched_init
        VoiceActivityDetection._patched_for_v4 = True

        logger.info("Patched PyAnnote VoiceActivityDetection to accept use_auth_token parameter")
        return True

    except Exception as e:
        logger.warning(f"Could not patch PyAnnote VoiceActivityDetection: {e}")
        return False


def _patch_whisperx_vad() -> bool:
    """
    Patch WhisperX VAD to use PyAnnote v4's token parameter.

    WhisperX's VoiceActivitySegmentation class passes `use_auth_token` to
    PyAnnote's VoiceActivityDetection, but PyAnnote v4 expects `token`.

    Returns:
        True if patch was applied successfully, False otherwise.
    """
    # First, patch the underlying PyAnnote classes
    _patch_pyannote_inference()
    _patch_pyannote_vad()

    try:
        import whisperx.vads.pyannote as vad_module

        # Store reference to original class
        vas_class = vad_module.VoiceActivitySegmentation

        # Check if already patched
        if hasattr(vas_class, "_patched_for_v4"):
            logger.debug("WhisperX VoiceActivitySegmentation already patched")
            return True

        original_init = vas_class.__init__

        def patched_init(self, *args, use_auth_token=None, **kwargs):
            # Convert use_auth_token to token for the parent class
            if use_auth_token is not None and "token" not in kwargs:
                kwargs["token"] = use_auth_token
            return original_init(self, *args, **kwargs)

        vas_class.__init__ = patched_init
        vas_class._patched_for_v4 = True

        logger.info("Patched WhisperX VoiceActivitySegmentation for PyAnnote v4 compatibility")
        return True

    except Exception as e:
        logger.warning(f"Could not patch WhisperX VAD: {e}")
        return False


def _patch_hf_hub_download() -> bool:
    """
    Patch huggingface_hub.hf_hub_download to accept use_auth_token as alias for token.

    WhisperX 3.7.0 passes the removed `use_auth_token` parameter to newer
    versions of huggingface_hub which only accept `token`.
    """
    try:
        import huggingface_hub

        if hasattr(huggingface_hub, "_hf_hub_download_patched"):
            logger.debug("hf_hub_download already patched")
            return True

        original_fn = huggingface_hub.hf_hub_download

        @functools.wraps(original_fn)
        def patched_hf_hub_download(*args, use_auth_token=None, **kwargs):
            if use_auth_token is not None and "token" not in kwargs:
                kwargs["token"] = use_auth_token
            return original_fn(*args, **kwargs)

        huggingface_hub.hf_hub_download = patched_hf_hub_download
        huggingface_hub._hf_hub_download_patched = True

        logger.info("Patched hf_hub_download to accept use_auth_token parameter")
        return True
    except Exception as e:
        logger.warning(f"Could not patch hf_hub_download: {e}")
        return False


def apply_pyannote_v4_patch() -> bool:
    """
    Apply the PyAnnote v4 compatibility patch to WhisperX.

    This function replaces whisperx.diarize.DiarizationPipeline with our
    v4-compatible DiarizationPipelineV4 class, and patches the VAD module.

    The patch is idempotent - calling it multiple times has no additional effect.

    Returns:
        True if the patch was applied (or was already applied), False if failed.
    """
    global _patch_applied

    if _patch_applied:
        logger.debug("PyAnnote v4 patch already applied, skipping")
        return True

    try:
        import whisperx.diarize

        # Store original for potential restoration
        if not hasattr(whisperx.diarize, "_OriginalDiarizationPipeline"):
            whisperx.diarize._OriginalDiarizationPipeline = whisperx.diarize.DiarizationPipeline

        # Apply the patch
        whisperx.diarize.DiarizationPipeline = DiarizationPipelineV4

        # Also patch at the whisperx module level if it's exposed there
        if hasattr(whisperx, "DiarizationPipeline"):
            whisperx.DiarizationPipeline = DiarizationPipelineV4

        # Patch the VAD module for PyAnnote v4 compatibility
        _patch_whisperx_vad()

        # Patch hf_hub_download for use_auth_token compatibility
        _patch_hf_hub_download()

        _patch_applied = True
        logger.info(
            "Successfully applied PyAnnote v4 compatibility patch to WhisperX. "
            f"Using model: {PYANNOTE_V4_MODEL}"
        )
        return True

    except ImportError as e:
        logger.warning(f"Could not import whisperx.diarize for patching: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to apply PyAnnote v4 patch: {e}")
        return False


def restore_original_pipeline() -> bool:
    """
    Restore the original WhisperX DiarizationPipeline.

    Useful for testing or if you need to switch back to the original behavior.

    Returns:
        True if restored successfully, False otherwise.
    """
    global _patch_applied

    if not _patch_applied:
        logger.debug("PyAnnote v4 patch was not applied, nothing to restore")
        return True

    try:
        import whisperx.diarize

        if hasattr(whisperx.diarize, "_OriginalDiarizationPipeline"):
            whisperx.diarize.DiarizationPipeline = whisperx.diarize._OriginalDiarizationPipeline

            if hasattr(whisperx, "DiarizationPipeline"):
                whisperx.DiarizationPipeline = whisperx.diarize._OriginalDiarizationPipeline

            _patch_applied = False
            logger.info("Restored original WhisperX DiarizationPipeline")
            return True
        else:
            logger.warning("Original DiarizationPipeline not found, cannot restore")
            return False

    except Exception as e:
        logger.error(f"Failed to restore original pipeline: {e}")
        return False


def is_patch_applied() -> bool:
    """Check if the PyAnnote v4 patch is currently applied."""
    return _patch_applied
