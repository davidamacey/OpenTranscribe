"""
Application-wide constants and configuration values.

This module contains commonly used constants across the application
to avoid magic numbers and improve maintainability.
"""

# File upload constants
UPLOAD_CHUNK_SIZE = 10 * 1024 * 1024  # 10MB chunks for file uploads
MAX_FILENAME_LENGTH = 255
DEFAULT_FILE_NAME = "unnamed_file"

# Video processing constants
THUMBNAIL_MAX_WIDTH = 320
THUMBNAIL_MAX_HEIGHT = 240
THUMBNAIL_QUALITY = 85

# Speaker matching confidence thresholds
SPEAKER_CONFIDENCE_HIGH = 0.75  # Auto-accept (green)
SPEAKER_CONFIDENCE_MEDIUM = 0.50  # Requires validation (yellow)
SPEAKER_CONFIDENCE_LOW = 0.0  # Requires user input (red)

# Cache control settings
CACHE_CONTROL_MEDIA_MAX_AGE = 86400  # 1 day for media files
CACHE_CONTROL_THUMBNAILS_MAX_AGE = 86400  # 1 day for thumbnails
CACHE_CONTROL_GENERIC_MAX_AGE = 3600  # 1 hour for other files

# Recording settings defaults
DEFAULT_RECORDING_MAX_DURATION = 120  # minutes (2 hours)
DEFAULT_RECORDING_QUALITY = "high"
DEFAULT_RECORDING_AUTO_STOP = True

# Valid recording durations (in minutes)
VALID_RECORDING_DURATIONS = [15, 30, 60, 120, 240, 480]

# Valid recording quality options
VALID_RECORDING_QUALITIES = ["standard", "high", "maximum"]

# LLM service settings
LLM_DEFAULT_MAX_TOKENS = 2000
LLM_DEFAULT_TEMPERATURE = 0.3
LLM_DEFAULT_TIMEOUT = 60

# OpenSearch settings
OPENSEARCH_DEFAULT_SIZE = 20
OPENSEARCH_MAX_RESULT_WINDOW = 50000

# Progress tracking intervals
PROGRESS_UPDATE_INTERVAL = 1000  # milliseconds
DOWNLOAD_CHECK_INTERVAL = 1000  # milliseconds
MAX_DOWNLOAD_CHECK_COUNT = 60  # seconds

# HTTP status codes (for readability)
HTTP_STATUS_PARTIAL_CONTENT = 206
HTTP_STATUS_RANGE_NOT_SATISFIABLE = 416

# File type patterns
AUDIO_CONTENT_TYPE_PREFIX = "audio/"
VIDEO_CONTENT_TYPE_PREFIX = "video/"
IMAGE_CONTENT_TYPE_PREFIX = "image/"

# WebSocket notification types
NOTIFICATION_TYPE_FILE_CREATED = "file_created"
NOTIFICATION_TYPE_TRANSCRIPTION_STATUS = "transcription_status"
NOTIFICATION_TYPE_SUMMARIZATION_STATUS = "summarization_status"
NOTIFICATION_TYPE_SPEAKER_MATCH = "speaker_match"

# Task statuses
TASK_STATUS_PENDING = "pending"
TASK_STATUS_PROCESSING = "processing"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_ERROR = "error"

# Embedding dimensions
SENTENCE_TRANSFORMER_DIMENSION = 384  # sentence-transformers/all-MiniLM-L6-v2
PYANNOTE_EMBEDDING_DIMENSION = 512  # PyAnnote embedding dimension

# Token estimation constants for LLM services
CHARS_PER_TOKEN_ESTIMATE = 4.0  # Average characters per token
SUBWORD_TOKENIZATION_FACTOR = 1.3  # Factor for subword tokenization
TOKEN_ESTIMATION_BUFFER = 1.1  # 10% buffer for safety

# Stream processing constants
DEFAULT_CHUNK_SIZE = 16384  # 16KB default chunk size
VIDEO_CHUNK_SIZE = 65536  # 64KB for video streaming
AUDIO_CHUNK_SIZE = 8192  # 8KB for audio streaming

# Transcription settings defaults
DEFAULT_TRANSCRIPTION_MIN_SPEAKERS = 1
DEFAULT_TRANSCRIPTION_MAX_SPEAKERS = 20
DEFAULT_SPEAKER_PROMPT_BEHAVIOR = "always_prompt"
DEFAULT_GARBAGE_CLEANUP_ENABLED = True
DEFAULT_GARBAGE_CLEANUP_THRESHOLD = 50

# Valid speaker prompt behaviors
VALID_SPEAKER_PROMPT_BEHAVIORS = ["always_prompt", "use_defaults", "use_custom"]
