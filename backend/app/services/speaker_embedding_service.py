import logging
import os
from pathlib import Path
from typing import Any
from typing import Optional

import numpy as np
import torch
from pyannote.audio import Inference

from app.core.config import settings
from app.services.embedding_mode_service import EmbeddingMode
from app.services.embedding_mode_service import EmbeddingModeService
from app.utils.hardware_detection import detect_hardware

logger = logging.getLogger(__name__)


class SpeakerEmbeddingService:
    """Service for extracting speaker embeddings using pyannote."""

    def __init__(
        self,
        model_name: str | None = None,
        models_dir: Optional[str] = None,
        mode: EmbeddingMode | None = None,
    ):
        """
        Initialize the speaker embedding service.

        Args:
            model_name: Name of the embedding model (auto-detected if None)
            models_dir: Directory to cache models
            mode: Embedding mode ('v3' or 'v4', auto-detected if None)
        """
        # Detect embedding mode if not specified
        self.mode: EmbeddingMode = mode or EmbeddingModeService.detect_mode()

        # Select model based on mode if not explicitly provided
        if model_name is None:
            self.model_name = EmbeddingModeService.get_embedding_model_name(self.mode)
        else:
            self.model_name = model_name

        self.models_dir: Path = (
            Path(models_dir) if models_dir else Path(settings.MODEL_BASE_DIR) / "pyannote"
        )
        self.models_dir.mkdir(parents=True, exist_ok=True)

        # Hardware detection
        self.hardware_config = detect_hardware()
        pyannote_config = self.hardware_config.get_pyannote_config()
        self.device = torch.device(pyannote_config["device"])

        # Initialize the model
        self._initialize_model()

    def _initialize_model(self):
        """Initialize the pyannote embedding model."""
        try:
            from pyannote.audio import Model

            # Check if we have a Hugging Face token
            hf_token = settings.HUGGINGFACE_TOKEN
            # Only warn about missing token if not in offline mode (models pre-downloaded)
            if not hf_token and os.getenv("HF_HUB_OFFLINE") != "1":
                logger.warning(
                    "No HUGGINGFACE_TOKEN found in settings. This may be required for gated models."
                )

            # Log VRAM before loading embedding model
            self.hardware_config.log_vram_usage("before embedding model load")

            # Load the model first with authentication token
            logger.info(f"Loading pyannote embedding model: {self.model_name}")
            model = Model.from_pretrained(self.model_name, token=hf_token)
            if model is None:
                if os.getenv("HF_HUB_OFFLINE") == "1":
                    msg = (
                        f"PyAnnote model '{self.model_name}' returned None. "
                        "In offline mode, models must be pre-downloaded. "
                        "Ensure the model cache directory contains the PyAnnote models."
                    )
                else:
                    msg = (
                        f"PyAnnote model '{self.model_name}' returned None. "
                        "This usually means your HuggingFace token lacks access to this gated model. "
                        "Please verify your HUGGINGFACE_TOKEN and accept the model agreement on HuggingFace."
                    )
                raise PermissionError(msg)

            # Initialize inference with the loaded model
            logger.info("Initializing pyannote Inference for embeddings")
            self.inference = Inference(model, window="whole", device=self.device)

            self.hardware_config.log_vram_usage("after embedding model loaded")
            logger.info(f"Initialized pyannote embedding model on {self.device}")
        except Exception as e:
            logger.error(f"Error initializing pyannote embedding model: {e}")
            raise

    @staticmethod
    def _load_audio(audio_path: str, target_sr: int = 16000) -> tuple[torch.Tensor, int]:
        """Load audio file as a torch tensor with multi-backend fallback.

        Tries in order: FFmpeg (handles all formats), torchaudio, scipy.
        FFmpeg is preferred because torchaudio 2.8+ may have zero backends
        and scipy only handles WAV files.

        Returns:
            Tuple of (waveform tensor [1, samples], sample_rate).
        """
        # 1. FFmpeg: handles any audio format reliably
        try:
            import subprocess

            cmd = [
                "ffmpeg",
                "-i",
                audio_path,
                "-f",
                "f32le",
                "-acodec",
                "pcm_f32le",
                "-ac",
                "1",
                "-ar",
                str(target_sr),
                "-v",
                "quiet",
                "-",
            ]
            proc = subprocess.run(cmd, capture_output=True, timeout=120)  # noqa: S603  # nosec B603
            if proc.returncode == 0 and len(proc.stdout) > 0:
                audio = np.frombuffer(proc.stdout, dtype=np.float32)
                waveform = torch.from_numpy(audio).unsqueeze(0)  # [1, samples]
                return waveform, target_sr
            logger.debug(f"FFmpeg returned code {proc.returncode}, trying torchaudio")
        except FileNotFoundError:
            logger.debug("FFmpeg not found, trying torchaudio")
        except Exception as ffmpeg_err:
            logger.debug(f"FFmpeg failed ({ffmpeg_err}), trying torchaudio")

        # 2. torchaudio (when backends are available)
        try:
            import torchaudio

            waveform, sr = torchaudio.load(audio_path)
            return waveform, int(sr)
        except Exception as ta_err:
            if "backend" not in str(ta_err).lower() and "already_closed" not in str(ta_err).lower():
                raise
            logger.debug(f"torchaudio failed ({ta_err}), trying scipy")

        # 3. scipy (WAV files only)
        from scipy.io import wavfile

        sr, data = wavfile.read(audio_path)
        audio = data.astype(np.float32)
        if np.issubdtype(data.dtype, np.integer):
            audio = audio / np.float32(np.iinfo(data.dtype).max)
        audio = audio[np.newaxis, :] if audio.ndim == 1 else audio.T
        return torch.from_numpy(audio), sr

    def extract_embedding_from_file(
        self, audio_path: str, segment: Optional[dict[str, float]] = None
    ) -> Optional[np.ndarray]:
        """
        Extract speaker embedding from an audio file or segment.

        Args:
            audio_path: Path to the audio file
            segment: Optional segment dict with 'start' and 'end' times

        Returns:
            Numpy array of the embedding or None if failed
        """
        try:
            waveform, sample_rate = self._load_audio(audio_path)

            if segment:
                # Extract the specific segment
                start_sample = int(segment["start"] * sample_rate)
                end_sample = int(segment["end"] * sample_rate)
                waveform = waveform[:, start_sample:end_sample]

            # PyAnnote expects mono audio
            if waveform.shape[0] > 1:
                waveform = waveform.mean(dim=0, keepdim=True)

            # Pass as waveform dict to avoid torchcodec/AudioDecoder issues
            audio_input = {"waveform": waveform, "sample_rate": sample_rate}
            embedding = self.inference(audio_input)

            # L2 normalize for optimal cosine similarity in OpenSearch
            if embedding is not None:
                norm = np.linalg.norm(embedding)
                if norm > 0:
                    embedding = embedding / norm

            return embedding  # type: ignore[no-any-return]

        except Exception as e:
            logger.error(f"Error extracting embedding from {audio_path}: {e}")
            return None

    def extract_embeddings_for_segments(
        self,
        audio_path: str,
        segments: list[dict[str, Any]],
        speaker_mapping: dict[str, int],
    ) -> dict[int, list[np.ndarray]]:
        """
        Extract embeddings for all speaker segments in a transcription.

        Args:
            audio_path: Path to the audio file
            segments: List of transcript segments with speaker information
            speaker_mapping: Mapping of speaker labels to database IDs

        Returns:
            Dictionary mapping speaker IDs to lists of embeddings
        """
        speaker_embeddings: dict[int, list[np.ndarray]] = {}
        speaker_segments: dict[int, list[dict[str, Any]]] = {}  # Collect segments per speaker

        # First, collect all segments for each speaker
        for segment in segments:
            speaker_label = segment.get("speaker")
            if not speaker_label:
                continue

            speaker_id = speaker_mapping.get(speaker_label)
            if not speaker_id:
                continue

            # Only process segments that are long enough (minimum 0.5 seconds)
            duration = segment["end"] - segment["start"]
            if duration < 0.5:
                continue

            if speaker_id not in speaker_segments:
                speaker_segments[speaker_id] = []
            speaker_segments[speaker_id].append(segment)

        # Now extract embeddings for each speaker, using their longest segments
        for speaker_id, speaker_segs in speaker_segments.items():
            # Sort segments by duration (longest first)
            speaker_segs.sort(key=lambda x: x["end"] - x["start"], reverse=True)

            # Use up to 5 longest segments for this speaker (to avoid too much processing)
            selected_segments = speaker_segs[:5]

            embeddings = []
            for segment in selected_segments:
                embedding = self.extract_embedding_from_file(
                    audio_path, {"start": segment["start"], "end": segment["end"]}
                )

                if embedding is not None:
                    embeddings.append(embedding)

            if embeddings:
                speaker_embeddings[speaker_id] = embeddings
                logger.info(f"Extracted {len(embeddings)} embeddings for speaker {speaker_id}")

        return speaker_embeddings

    def aggregate_embeddings(self, embeddings: list[np.ndarray]) -> np.ndarray:
        """
        Aggregate multiple embeddings into a single representative embedding.

        Args:
            embeddings: List of numpy arrays

        Returns:
            Aggregated embedding (mean of all embeddings), L2 normalized
        """
        if not embeddings:
            raise ValueError("No embeddings to aggregate")

        if len(embeddings) == 1:
            embedding = embeddings[0]
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
            return embedding

        # Stack all embeddings and compute mean
        stacked = np.vstack(embeddings)
        aggregated = np.mean(stacked, axis=0)

        # L2 normalize the aggregated embedding
        norm = np.linalg.norm(aggregated)
        if norm > 0:
            aggregated = aggregated / norm

        return aggregated  # type: ignore[no-any-return]

    def compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compute cosine similarity between two embeddings.

        Delegates to the centralized SimilarityService for optimal performance.

        Args:
            embedding1: First embedding
            embedding2: Second embedding

        Returns:
            Cosine similarity score (0-1)
        """
        from app.services.similarity_service import SimilarityService

        result: float = SimilarityService.cosine_similarity(embedding1, embedding2)
        return result

    def extract_reference_embedding(self, audio_paths: list[str]) -> Optional[np.ndarray]:
        """
        Extract a reference embedding from multiple audio samples of the same speaker.

        Args:
            audio_paths: List of audio file paths containing the same speaker

        Returns:
            Aggregated reference embedding or None if failed
        """
        embeddings = []

        for audio_path in audio_paths:
            embedding = self.extract_embedding_from_file(audio_path)
            if embedding is not None:
                embeddings.append(embedding)

        if not embeddings:
            logger.error("Failed to extract any embeddings from reference audio")
            return None

        return self.aggregate_embeddings(embeddings)

    def get_embedding_dimension(self) -> int:
        """Get the dimension of the embeddings produced by the model."""
        return EmbeddingModeService.get_embedding_dimension(self.mode)

    def cleanup(self):
        """
        Explicitly cleanup the embedding model and free GPU memory.

        This should be called when the service is no longer needed to ensure
        proper GPU memory management, especially when multiple models are used
        in sequence during transcription processing.
        """
        self.hardware_config.log_vram_usage("before embedding model cleanup")

        if hasattr(self, "inference"):
            logger.info("Cleaning up PyAnnote embedding model")
            del self.inference

        # Force aggressive memory cleanup
        import gc

        gc.collect()

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

        self.hardware_config.log_vram_usage("after embedding model cleanup")
        logger.info("GPU memory cleaned up after embedding service")


# ============================================================================
# Warm Model Cache - keeps embedding model loaded between transcriptions
# ============================================================================

_cached_embedding_service: Optional[SpeakerEmbeddingService] = None
_cache_lock = None  # Lazy-initialized threading lock


def _get_cache_lock():
    """Get or create the cache lock (lazy initialization for fork safety)."""
    global _cache_lock
    if _cache_lock is None:
        import threading

        _cache_lock = threading.Lock()
    return _cache_lock


def get_cached_embedding_service(
    model_name: str | None = None,
    mode: EmbeddingMode | None = None,
) -> SpeakerEmbeddingService:
    """
    Get a cached SpeakerEmbeddingService instance.

    The model is loaded once and kept warm in GPU memory between transcriptions.
    Subsequent calls return the same instance, avoiding the 40-60 second model
    loading overhead.

    Args:
        model_name: Name of the embedding model (uses cached if matches)
        mode: Embedding mode ('v3' or 'v4', uses cached if matches)

    Returns:
        Cached or newly created SpeakerEmbeddingService
    """
    global _cached_embedding_service

    with _get_cache_lock():
        # Check if we have a valid cached service
        if _cached_embedding_service is not None:
            # Verify the cached service matches requested parameters
            requested_mode = mode or EmbeddingModeService.detect_mode()
            requested_model = model_name or EmbeddingModeService.get_embedding_model_name(
                requested_mode
            )

            if (
                _cached_embedding_service.mode == requested_mode
                and _cached_embedding_service.model_name == requested_model
            ):
                logger.info(
                    f"Using warm cached embedding service: {_cached_embedding_service.model_name} "
                    f"(mode: {_cached_embedding_service.mode})"
                )
                return _cached_embedding_service
            else:
                # Parameters changed, need to reload
                logger.info(
                    f"Embedding config changed, clearing cache. "
                    f"Old: {_cached_embedding_service.model_name}, New: {requested_model}"
                )
                clear_embedding_cache()

        # Create new service and cache it
        logger.info("Creating new embedding service (cold start)")
        _cached_embedding_service = SpeakerEmbeddingService(
            model_name=model_name,
            mode=mode,
        )
        logger.info(
            f"Embedding service cached and warm: {_cached_embedding_service.model_name} "
            f"(mode: {_cached_embedding_service.mode})"
        )
        return _cached_embedding_service


def clear_embedding_cache() -> None:
    """
    Clear the cached embedding service and free GPU memory.

    Call this when you need to free GPU memory for other models,
    or when shutting down the worker.
    """
    global _cached_embedding_service

    with _get_cache_lock():
        if _cached_embedding_service is not None:
            logger.info("Clearing cached embedding service")
            _cached_embedding_service.cleanup()
            _cached_embedding_service = None
            logger.info("Embedding cache cleared")
