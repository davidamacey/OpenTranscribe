"""Singleton embedding service for search vector generation."""
import logging
import threading

from app.core.config import settings

logger = logging.getLogger(__name__)

# Model-specific instruction prefixes for optimal embedding quality.
# E5 models require "query: " and "passage: " prefixes per their training.
# BGE-M3 handles instructions internally via SentenceTransformer's encode().
_QUERY_PREFIXES: dict[str, str] = {
    "intfloat/e5-base-v2": "query: ",
}
_DOCUMENT_PREFIXES: dict[str, str] = {
    "intfloat/e5-base-v2": "passage: ",
}


class SearchEmbeddingService:
    """Singleton embedding service with cached model.

    Uses sentence-transformers to generate embeddings for search indexing
    and query encoding. Thread-safe singleton ensures model is loaded once.
    """

    _instance = None
    _model = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "SearchEmbeddingService":
        """Get or create the singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (used when switching models)."""
        with cls._lock:
            cls._model = None
            cls._instance = None
            logger.info("SearchEmbeddingService reset")

    def __init__(self):
        if SearchEmbeddingService._model is None:
            self._load_model()

    def _load_model(self) -> None:
        """Load the sentence transformer model."""
        model_name = settings.SEARCH_EMBEDDING_MODEL
        logger.info(f"Loading search embedding model: {model_name}")
        try:
            from sentence_transformers import SentenceTransformer

            device = settings.SEARCH_EMBEDDING_DEVICE
            SearchEmbeddingService._model = SentenceTransformer(model_name, device=device)
            logger.info(f"Search embedding model loaded: {model_name} on device={device}")
        except Exception as e:
            logger.error(f"Failed to load search embedding model {model_name}: {e}")
            raise

    def embed_texts(self, texts: list[str], batch_size: int = 256) -> list[list[float]]:
        """Batch embed document texts.

        Runs on the device configured by SEARCH_EMBEDDING_DEVICE (default: cpu).
        Applies model-specific instruction prefixes for optimal quality.

        Args:
            texts: List of text strings to embed.
            batch_size: Batch size for encoding.

        Returns:
            List of embedding vectors as float lists.
        """
        if not texts:
            return []

        # Apply model-specific document prefix
        model_name = settings.SEARCH_EMBEDDING_MODEL
        prefix = _DOCUMENT_PREFIXES.get(model_name, "")
        if prefix:
            texts = [prefix + t for t in texts]

        # Scale batch size by model dimension to avoid OOM on large models
        dimension = settings.SEARCH_EMBEDDING_DIMENSION
        effective_batch = min(batch_size, max(32, 65536 // dimension))

        if self._model is None:
            raise RuntimeError("Embedding model not loaded")

        embeddings = self._model.encode(
            texts,
            batch_size=effective_batch,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        result: list[list[float]] = embeddings.tolist()
        return result

    def embed_query(self, query: str) -> list[float]:
        """Embed a single search query.

        Applies model-specific query prefix for optimal quality.

        Args:
            query: Search query text.

        Returns:
            Embedding vector as float list.
        """
        # Apply model-specific query prefix
        model_name = settings.SEARCH_EMBEDDING_MODEL
        prefix = _QUERY_PREFIXES.get(model_name, "")
        text = prefix + query if prefix else query

        if self._model is None:
            raise RuntimeError("Embedding model not loaded")

        result: list[float] = self._model.encode(text, normalize_embeddings=True).tolist()
        return result

    @property
    def model_name(self) -> str:
        """Return the currently loaded model name."""
        return settings.SEARCH_EMBEDDING_MODEL

    @property
    def dimension(self) -> int:
        """Return the embedding dimension."""
        return settings.SEARCH_EMBEDDING_DIMENSION

    def find_similar_words(
        self, query: str, text: str, threshold: float = 0.3, max_words: int = 20
    ) -> list[str]:
        """Find words in text that are semantically similar to the query.

        Uses embedding similarity to identify words/phrases that are conceptually
        related to the search query, even if they don't share common stems.

        Args:
            query: The search query.
            text: The text passage to search for similar words.
            threshold: Minimum cosine similarity score (0-1) to consider a match.
            max_words: Maximum number of similar words to return.

        Returns:
            List of words from the text that are semantically similar to the query.
        """
        import re

        import numpy as np

        if not query or not text:
            return []

        # Extract unique words from text (3+ characters, alphabetic)
        words = list(set(re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())))
        if not words:
            return []

        # Limit words to process for efficiency
        words = words[:100]

        try:
            # Get query embedding
            query_embedding = np.array(self.embed_query(query))

            # Get embeddings for all words in batch
            word_embeddings = np.array(self.embed_texts(words))

            if len(word_embeddings) == 0:
                return []

            # Compute cosine similarities (embeddings are already normalized)
            similarities = np.dot(word_embeddings, query_embedding)

            # Find words above threshold
            similar_indices = np.where(similarities >= threshold)[0]

            # Sort by similarity (highest first) and take top max_words
            sorted_indices = similar_indices[np.argsort(similarities[similar_indices])[::-1]]
            top_indices = sorted_indices[:max_words]

            # Return the similar words
            similar_words = [words[i] for i in top_indices]

            logger.debug(
                f"Found {len(similar_words)} similar words for query '{query}': {similar_words[:5]}"
            )
            return similar_words

        except Exception as e:
            logger.warning(f"Error finding similar words: {e}")
            return []
