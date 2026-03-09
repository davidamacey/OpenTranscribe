"""
Service for detecting and managing speaker embedding mode (v3 vs v4).

This service handles the transition between PyAnnote v3 (512-dim) and v4 (256-dim)
speaker embeddings, ensuring backward compatibility for existing installations while
defaulting to v4 for new installations.
"""

import contextlib
import logging
from typing import TYPE_CHECKING
from typing import Literal

if TYPE_CHECKING:
    from opensearchpy import OpenSearch
from app.core.constants import PYANNOTE_EMBEDDING_DIMENSION_V3
from app.core.constants import PYANNOTE_EMBEDDING_DIMENSION_V4
from app.core.constants import get_speaker_index

logger = logging.getLogger(__name__)

EmbeddingMode = Literal["v3", "v4"]

# Define mode constants with proper Literal types for mypy
MODE_V3: EmbeddingMode = "v3"
MODE_V4: EmbeddingMode = "v4"


class EmbeddingModeService:
    """Service for detecting and managing speaker embedding mode (v3 vs v4).

    This service auto-detects the embedding mode by checking the OpenSearch speaker
    index dimension. For new installations, it defaults to v4 (256-dim WeSpeaker).
    For existing installations, it preserves the existing mode based on the stored
    embedding dimensions.

    Attributes:
        _cached_mode: Cached embedding mode to avoid repeated OpenSearch queries.

    Example:
        >>> mode = EmbeddingModeService.detect_mode()
        >>> dim = EmbeddingModeService.get_embedding_dimension()
        >>> if EmbeddingModeService.validate_embedding_dimension(embedding):
        ...     # Embedding is valid for current mode
    """

    _cached_mode: EmbeddingMode | None = None

    @classmethod
    def _dimension_to_mode(cls, dimension: int, source: str = "index") -> EmbeddingMode | None:
        """
        Convert an embedding dimension to the corresponding mode.

        Args:
            dimension: The embedding dimension to convert.
            source: Source of the dimension for logging ("index" or "documents").

        Returns:
            The corresponding mode, or None if unknown dimension.
        """
        if dimension == PYANNOTE_EMBEDDING_DIMENSION_V3:
            logger.info(f"Detected v3 embedding mode from {source} (dimension={dimension})")
            return MODE_V3
        elif dimension == PYANNOTE_EMBEDDING_DIMENSION_V4:
            logger.info(f"Detected v4 embedding mode from {source} (dimension={dimension})")
            return MODE_V4
        else:
            logger.warning(
                f"Unknown embedding dimension {dimension} in {source}, defaulting to v4 mode"
            )
            return None

    @classmethod
    def _get_dimension_from_mapping(cls, client: "OpenSearch", index_name: str) -> int | None:
        """
        Get the embedding dimension from the index mapping.

        Args:
            client: OpenSearch client instance.
            index_name: Name of the speaker index.

        Returns:
            The embedding dimension if found, None otherwise.
        """
        mapping = client.indices.get_mapping(index=index_name)
        if index_name not in mapping:
            return None

        properties = mapping[index_name].get("mappings", {}).get("properties", {})
        embedding_config = properties.get("embedding", {})
        dimension = embedding_config.get("dimension")
        return int(dimension) if dimension is not None else None

    @classmethod
    def detect_mode(cls, force_refresh: bool = False) -> EmbeddingMode:
        """
        Detect the current embedding mode from OpenSearch index.

        For new installs: Returns v4 (256-dim, WeSpeaker)
        For existing v3 installs: Returns v3 (512-dim, pyannote/embedding)
        For existing v4 installs: Returns v4 (256-dim, WeSpeaker)

        Args:
            force_refresh: If True, bypass cache and query OpenSearch directly.

        Returns:
            The detected embedding mode ("v3" or "v4").
        """
        # Return cached mode if available and not forcing refresh
        if cls._cached_mode is not None and not force_refresh:
            return cls._cached_mode

        # Import here to avoid circular imports and allow lazy initialization
        from app.services.opensearch_service import get_opensearch_client

        client = get_opensearch_client()
        if client is None:
            logger.warning("OpenSearch client not available, defaulting to v4 embedding mode")
            cls._cached_mode = MODE_V4
            return cls._cached_mode

        try:
            index_name = get_speaker_index()

            # If 'speakers' is an alias, resolve to the concrete index for mapping check
            resolved_index = index_name
            with contextlib.suppress(Exception):
                from app.services.opensearch_service import _get_alias_target

                target = _get_alias_target(index_name)
                if target:
                    resolved_index = target

            # Check if the speaker index exists
            if not client.indices.exists(index=resolved_index):
                logger.info(
                    f"Speaker index '{resolved_index}' does not exist, "
                    "new installation detected, using v4 mode"
                )
                cls._cached_mode = MODE_V4
                return cls._cached_mode

            # Try to get dimension from index mapping first
            dimension = cls._get_dimension_from_mapping(client, resolved_index)
            if dimension is not None:
                mode = cls._dimension_to_mode(dimension, "index mapping")
                cls._cached_mode = mode if mode is not None else MODE_V4
                return cls._cached_mode

            # Fall back to sampling existing documents
            logger.info("Could not determine dimension from mapping, checking existing documents")
            dimension = cls._detect_dimension_from_documents(client, index_name)
            if dimension is not None:
                mode = cls._dimension_to_mode(dimension, "documents")
                if mode is not None:
                    cls._cached_mode = mode
                    return cls._cached_mode

            # Default to v4 for new installations or if detection fails
            logger.info("No existing embeddings found, defaulting to v4 mode for new installation")
            cls._cached_mode = MODE_V4
            return cls._cached_mode

        except Exception as e:
            logger.error(
                f"Error detecting embedding mode from OpenSearch: {e}, defaulting to v4 mode"
            )
            cls._cached_mode = MODE_V4
            return cls._cached_mode

    @classmethod
    def _detect_dimension_from_documents(
        cls,
        client: "OpenSearch",
        index_name: str,
    ) -> int | None:
        """
        Detect embedding dimension by sampling existing documents.

        Args:
            client: OpenSearch client instance.
            index_name: Name of the speaker index.

        Returns:
            The embedding dimension if found, None otherwise.
        """
        try:
            # Query for a single document with an embedding
            response = client.search(
                index=index_name,
                body={
                    "size": 1,
                    "query": {"exists": {"field": "embedding"}},
                    "_source": ["embedding"],
                },
            )

            hits = response.get("hits", {}).get("hits", [])
            if hits:
                embedding = hits[0].get("_source", {}).get("embedding")
                if embedding and isinstance(embedding, list):
                    return len(embedding)

            return None

        except Exception as e:
            logger.warning(f"Error sampling documents for dimension detection: {e}")
            return None

    @classmethod
    def get_embedding_dimension(cls, mode: EmbeddingMode | None = None) -> int:
        """
        Get the embedding dimension for the given or current mode.

        Args:
            mode: Optional embedding mode. If None, uses the detected mode.

        Returns:
            The embedding dimension (512 for v3, 256 for v4).
        """
        if mode is None:
            mode = cls.detect_mode()

        if mode == MODE_V3:
            return PYANNOTE_EMBEDDING_DIMENSION_V3
        else:
            return PYANNOTE_EMBEDDING_DIMENSION_V4

    @classmethod
    def get_embedding_model_name(cls, mode: EmbeddingMode | None = None) -> str:
        """
        Get the embedding model name for the given or current mode.

        Args:
            mode: Optional embedding mode. If None, uses the detected mode.

        Returns:
            The model name string for the embedding model.
        """
        if mode is None:
            mode = cls.detect_mode()

        if mode == MODE_V3:
            return "pyannote/embedding"
        else:
            return "pyannote/wespeaker-voxceleb-resnet34-LM"

    @classmethod
    def validate_embedding_dimension(cls, embedding: list[float]) -> bool:
        """
        Validate that an embedding has the correct dimension for current mode.

        Args:
            embedding: The embedding vector to validate.

        Returns:
            True if the embedding dimension matches the current mode, False otherwise.
        """
        if not embedding:
            return False

        expected_dim = cls.get_embedding_dimension()
        actual_dim = len(embedding)

        if actual_dim != expected_dim:
            logger.warning(
                f"Embedding dimension mismatch: expected {expected_dim}, got {actual_dim}"
            )
            return False

        return True

    @classmethod
    def get_current_mode(cls) -> EmbeddingMode:
        """
        Get the current embedding mode (cached).

        This is a convenience method that returns the cached mode if available,
        otherwise detects and caches the mode.

        Returns:
            The current embedding mode.
        """
        return cls.detect_mode()

    @classmethod
    def clear_cache(cls) -> None:
        """
        Clear the cached embedding mode.

        This is useful when the OpenSearch index has been recreated or modified
        and the mode needs to be re-detected.
        """
        cls._cached_mode = None
        logger.info("Embedding mode cache cleared")

    @classmethod
    def is_v3_mode(cls) -> bool:
        """
        Check if the current mode is v3 (512-dim).

        Returns:
            True if using v3 mode, False otherwise.
        """
        return cls.detect_mode() == MODE_V3

    @classmethod
    def is_v4_mode(cls) -> bool:
        """
        Check if the current mode is v4 (256-dim).

        Returns:
            True if using v4 mode, False otherwise.
        """
        return cls.detect_mode() == MODE_V4

    @classmethod
    def get_mode_info(cls) -> dict[str, str | int]:
        """
        Get detailed information about the current embedding mode.

        Returns:
            Dictionary containing mode, dimension, and model name.
        """
        mode = cls.detect_mode()
        return {
            "mode": mode,
            "dimension": cls.get_embedding_dimension(mode),
            "model_name": cls.get_embedding_model_name(mode),
            "description": (
                "PyAnnote v3 (pyannote/embedding)"
                if mode == MODE_V3
                else "PyAnnote v4 (WeSpeaker ResNet34-LM)"
            ),
        }
