import logging
import os
from pathlib import Path
from typing import Any
from typing import Optional

import numpy as np
import torch
from pyannote.audio import Inference
from pyannote.core import Segment

from app.core.config import settings
from app.utils.hardware_detection import detect_hardware

logger = logging.getLogger(__name__)


class SpeakerEmbeddingService:
    """Service for extracting speaker embeddings using pyannote."""

    def __init__(
        self, model_name: str = "pyannote/embedding", models_dir: Optional[str] = None
    ):
        """
        Initialize the speaker embedding service.

        Args:
            model_name: Name of the pyannote embedding model
            models_dir: Directory to cache models
        """
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
            # Check if we have a Hugging Face token
            hf_token = settings.HUGGINGFACE_TOKEN
            # Only warn about missing token if not in offline mode (models pre-downloaded)
            if not hf_token and os.getenv("HF_HUB_OFFLINE") != "1":
                logger.warning(
                    "No HUGGINGFACE_TOKEN found in settings. This may be required for gated models."
                )

            # Log VRAM before loading embedding model
            self.hardware_config.log_vram_usage("before embedding model load")

            # Initialize the embedding model with authentication if available
            if hf_token:
                logger.info("Initializing pyannote embedding model with authentication")
                self.inference = Inference(
                    self.model_name,
                    window="whole",
                    device=self.device,
                    use_auth_token=hf_token,
                )
            else:
                logger.info("Initializing pyannote embedding model without authentication")
                self.inference = Inference(self.model_name, window="whole", device=self.device)

            self.hardware_config.log_vram_usage("after embedding model loaded")
            logger.info(f"Initialized pyannote embedding model on {self.device}")
        except Exception as e:
            logger.error(f"Error initializing pyannote embedding model: {e}")
            raise

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
            if segment:
                # Extract embedding from a specific segment
                excerpt = Segment(segment["start"], segment["end"])
                embedding = self.inference.crop(audio_path, excerpt)
            else:
                # Extract embedding from the whole file
                embedding = self.inference(audio_path)

            return embedding

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
            Aggregated embedding (mean of all embeddings)
        """
        if not embeddings:
            raise ValueError("No embeddings to aggregate")

        if len(embeddings) == 1:
            return embeddings[0]

        # Stack all embeddings and compute mean
        stacked = np.vstack(embeddings)
        return np.mean(stacked, axis=0)

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
        return 512  # Pyannote embedding dimension (updated for newer models)

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
