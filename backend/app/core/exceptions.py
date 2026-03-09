"""Application-specific exception hierarchy.

All domain exceptions inherit from ``OpenTranscribeError`` so they can
be caught by the global exception handler in ``main.py``.
"""


class OpenTranscribeError(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str, detail: str | None = None):
        self.message = message
        self.detail = detail
        super().__init__(message)


class TranscriptionError(OpenTranscribeError):
    """Errors during the transcription pipeline."""


class StorageError(OpenTranscribeError):
    """MinIO/S3 storage operation failures."""


class SearchIndexError(OpenTranscribeError):
    """OpenSearch indexing or query failures."""


class AuthenticationError(OpenTranscribeError):
    """Authentication or authorization failures."""


class LLMServiceError(OpenTranscribeError):
    """LLM provider communication failures."""


class MigrationError(OpenTranscribeError):
    """Data migration failures."""
