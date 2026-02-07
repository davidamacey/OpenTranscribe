"""
Application-wide constants and configuration values.

This module contains commonly used constants across the application
to avoid magic numbers and improve maintainability.

Language Data Sources:
- Whisper language codes: Imported from faster_whisper.tokenizer._LANGUAGE_CODES (with fallback)
- Alignment languages: Imported from whisperx.alignment DEFAULT_ALIGN_MODELS_TORCH/HF
- Language names: From OpenAI whisper source (https://github.com/openai/whisper/blob/main/whisper/tokenizer.py)
  Title-cased for display purposes.
"""

import logging
import os as _os

_logger = logging.getLogger(__name__)

# =============================================================================
# Dynamic imports for language support
# =============================================================================

# Import alignment languages from whisperx (public API)
# Skip in test mode to avoid heavy torch import (~6s)

if _os.environ.get("SKIP_CELERY", "").lower() == "true":
    # Use fallback list in test mode - avoid loading torch/whisperx
    _logger.debug("Test mode: using fallback alignment language list")
    LANGUAGES_WITH_ALIGNMENT = None  # Will be set below in fallback
else:
    try:
        from whisperx.alignment import DEFAULT_ALIGN_MODELS_HF
        from whisperx.alignment import DEFAULT_ALIGN_MODELS_TORCH

        LANGUAGES_WITH_ALIGNMENT = set(DEFAULT_ALIGN_MODELS_TORCH.keys()) | set(
            DEFAULT_ALIGN_MODELS_HF.keys()
        )
    except ImportError:
        _logger.warning(
            "Could not import whisperx alignment models, using fallback alignment language list"
        )
        LANGUAGES_WITH_ALIGNMENT = None

if LANGUAGES_WITH_ALIGNMENT is None:
    # Fallback: known alignment languages as of whisperx 3.3.1
    LANGUAGES_WITH_ALIGNMENT = {
        "ar",
        "ca",
        "cs",
        "da",
        "de",
        "el",
        "en",
        "es",
        "eu",
        "fa",
        "fi",
        "fr",
        "gl",
        "he",
        "hi",
        "hr",
        "hu",
        "it",
        "ja",
        "ka",
        "ko",
        "lv",
        "ml",
        "nl",
        "nn",
        "no",
        "pl",
        "pt",
        "ro",
        "ru",
        "sk",
        "sl",
        "te",
        "tl",
        "tr",
        "uk",
        "ur",
        "vi",
        "zh",
    }

# Try to import language codes from faster_whisper for validation
# Skip in test mode to avoid heavy torch import
if _os.environ.get("SKIP_CELERY", "").lower() == "true":
    _logger.debug("Test mode: using None for WHISPER_LANGUAGE_CODES")
    WHISPER_LANGUAGE_CODES: set[str] | None = None
else:
    try:
        from faster_whisper.tokenizer import _LANGUAGE_CODES

        WHISPER_LANGUAGE_CODES = set(_LANGUAGE_CODES)
    except ImportError:
        _logger.warning("Could not import faster_whisper language codes for validation")
        WHISPER_LANGUAGE_CODES = None

# File upload constants
UPLOAD_CHUNK_SIZE = 10 * 1024 * 1024  # 10MB chunks for file uploads
MAX_FILENAME_LENGTH = 255
DEFAULT_FILE_NAME = "unnamed_file"

# Video processing constants (legacy - kept for backward compatibility)
THUMBNAIL_MAX_WIDTH = 320
THUMBNAIL_MAX_HEIGHT = 240
THUMBNAIL_QUALITY = 85

# Thumbnail settings (WebP optimized, preserves aspect ratio)
THUMBNAIL_MAX_DIMENSION = 1280  # Longest edge - Full HD for crisp display on any screen
THUMBNAIL_QUALITY_WEBP = 75  # WebP quality (replaces JPEG 85)
THUMBNAIL_QUALITY_JPEG = 70  # JPEG fallback quality
THUMBNAIL_FORMAT = "webp"  # Primary format

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

# Search & RAG constants
SEARCH_DEFAULT_PAGE_SIZE = 20
SEARCH_MAX_PAGE_SIZE = 100
SEARCH_MAX_SNIPPETS_PER_FILE = 100  # Return all occurrences for frontend navigation
SEARCH_MAX_SEMANTIC_SNIPPETS_PER_FILE = 2  # Display limit for card view (deprecated)
SEARCH_HYBRID_MIN_SCORE = 0.01
SEARCH_CACHE_TTL_SECONDS = 300
SEARCH_CACHE_MAX_SIZE = 256

# OpenSearch Native Neural Search Model Registry
# These models are registered and deployed directly in OpenSearch via ML Commons plugin
# Organized by quality tier (Fast → Balanced → Best) and language support (English / Multilingual)
OPENSEARCH_EMBEDDING_MODELS = {
    # === FAST TIER (384 dimensions) ===
    # Low latency, lower memory. Good for keyword-focused searches.
    "huggingface/sentence-transformers/all-MiniLM-L6-v2": {
        "name": "MiniLM - Fast (English Only)",
        "dimension": 384,
        "size_mb": 80,
        "languages": ["en"],
        "model_format": "TORCH_SCRIPT",
        "default": True,
        "requires_prefix": False,
        "tier": "fast",
        "language_type": "english",
        "description": "Fast, lightweight English model. Good baseline for keyword-heavy searches.",
    },
    "huggingface/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": {
        "name": "MiniLM - Fast (Multilingual, 50+ Languages)",
        "dimension": 384,
        "size_mb": 420,
        "languages": ["multilingual"],
        "model_format": "TORCH_SCRIPT",
        "default": False,
        "requires_prefix": False,
        "tier": "fast",
        "language_type": "multilingual",
        "description": "Fast multilingual model. 50+ languages with good quality.",
    },
    # === BALANCED TIER (768 dimensions) ===
    # Good balance of speed and semantic quality.
    "huggingface/sentence-transformers/all-mpnet-base-v2": {
        "name": "MPNet - Balanced (English Only)",
        "dimension": 768,
        "size_mb": 420,
        "languages": ["en"],
        "model_format": "TORCH_SCRIPT",
        "default": False,
        "requires_prefix": False,
        "tier": "balanced",
        "language_type": "english",
        "description": "Better semantic understanding. Good balance of speed and quality.",
    },
    "huggingface/sentence-transformers/paraphrase-multilingual-mpnet-base-v2": {
        "name": "MPNet - Balanced (Multilingual, 50+ Languages)",
        "dimension": 768,
        "size_mb": 1100,
        "languages": ["multilingual"],
        "model_format": "TORCH_SCRIPT",
        "default": False,
        "requires_prefix": False,
        "tier": "balanced",
        "language_type": "multilingual",
        "description": "Higher quality multilingual embeddings. Good semantic search.",
    },
    # === BEST QUALITY TIER ===
    # Highest retrieval quality, recommended for semantic-heavy searches.
    "huggingface/sentence-transformers/all-distilroberta-v1": {
        "name": "DistilRoBERTa - Best Quality (English Only)",
        "dimension": 768,
        "size_mb": 290,
        "languages": ["en"],
        "model_format": "TORCH_SCRIPT",
        "default": False,
        "requires_prefix": False,
        "tier": "best",
        "language_type": "english",
        "description": "Best retrieval quality for English. Excellent semantic understanding.",
    },
    "huggingface/sentence-transformers/distiluse-base-multilingual-cased-v1": {
        "name": "DistilUSE - Best Quality (Multilingual, 15 Languages)",
        "dimension": 512,
        "size_mb": 480,
        "languages": ["multilingual"],
        "model_format": "TORCH_SCRIPT",
        "default": False,
        "requires_prefix": False,
        "tier": "best",
        "language_type": "multilingual",
        "description": "Best quality for common languages. 15 languages with excellent accuracy.",
    },
}

# Default OpenSearch neural model for new installations
OPENSEARCH_DEFAULT_MODEL = "huggingface/sentence-transformers/all-MiniLM-L6-v2"

# Neural ingest pipeline name
OPENSEARCH_NEURAL_PIPELINE = "transcript-neural-ingest"

# WebSocket notification types for search
NOTIFICATION_TYPE_REINDEX_PROGRESS = "reindex_progress"
NOTIFICATION_TYPE_REINDEX_COMPLETE = "reindex_complete"

# WebSocket notification types for embedding migration
NOTIFICATION_TYPE_MIGRATION_PROGRESS = "migration_progress"
NOTIFICATION_TYPE_MIGRATION_COMPLETE = "migration_complete"

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
PYANNOTE_EMBEDDING_DIMENSION = 512  # Legacy v3 dimension (pyannote/embedding)

# Speaker embedding mode constants (PyAnnote v3/v4 compatibility)
# Typed as Literal for mypy compatibility with EmbeddingMode type
EMBEDDING_MODE_V3: str = "v3"  # pyannote/embedding, 512-dim
EMBEDDING_MODE_V4: str = "v4"  # WeSpeaker, 256-dim

# PyAnnote embedding dimensions by version
PYANNOTE_EMBEDDING_DIMENSION_V3 = 512  # pyannote/embedding model
PYANNOTE_EMBEDDING_DIMENSION_V4 = 256  # WeSpeaker ResNet34-LM model

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

# =============================================================================
# Language Settings (Multilingual Support)
# =============================================================================

# Default language settings
DEFAULT_SOURCE_LANGUAGE = "auto"
DEFAULT_TRANSLATE_TO_ENGLISH = False
DEFAULT_LLM_OUTPUT_LANGUAGE = "en"

# Human-readable language names from OpenAI whisper source
# Source: https://github.com/openai/whisper/blob/main/whisper/tokenizer.py
# Names are title-cased for display purposes
_WHISPER_LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "zh": "Chinese",
    "de": "German",
    "es": "Spanish",
    "ru": "Russian",
    "ko": "Korean",
    "fr": "French",
    "ja": "Japanese",
    "pt": "Portuguese",
    "tr": "Turkish",
    "pl": "Polish",
    "ca": "Catalan",
    "nl": "Dutch",
    "ar": "Arabic",
    "sv": "Swedish",
    "it": "Italian",
    "id": "Indonesian",
    "hi": "Hindi",
    "fi": "Finnish",
    "vi": "Vietnamese",
    "he": "Hebrew",
    "uk": "Ukrainian",
    "el": "Greek",
    "ms": "Malay",
    "cs": "Czech",
    "ro": "Romanian",
    "da": "Danish",
    "hu": "Hungarian",
    "ta": "Tamil",
    "no": "Norwegian",
    "th": "Thai",
    "ur": "Urdu",
    "hr": "Croatian",
    "bg": "Bulgarian",
    "lt": "Lithuanian",
    "la": "Latin",
    "mi": "Maori",
    "ml": "Malayalam",
    "cy": "Welsh",
    "sk": "Slovak",
    "te": "Telugu",
    "fa": "Persian",
    "lv": "Latvian",
    "bn": "Bengali",
    "sr": "Serbian",
    "az": "Azerbaijani",
    "sl": "Slovenian",
    "kn": "Kannada",
    "et": "Estonian",
    "mk": "Macedonian",
    "br": "Breton",
    "eu": "Basque",
    "is": "Icelandic",
    "hy": "Armenian",
    "ne": "Nepali",
    "mn": "Mongolian",
    "bs": "Bosnian",
    "kk": "Kazakh",
    "sq": "Albanian",
    "sw": "Swahili",
    "gl": "Galician",
    "mr": "Marathi",
    "pa": "Punjabi",
    "si": "Sinhala",
    "km": "Khmer",
    "sn": "Shona",
    "yo": "Yoruba",
    "so": "Somali",
    "af": "Afrikaans",
    "oc": "Occitan",
    "ka": "Georgian",
    "be": "Belarusian",
    "tg": "Tajik",
    "sd": "Sindhi",
    "gu": "Gujarati",
    "am": "Amharic",
    "yi": "Yiddish",
    "lo": "Lao",
    "uz": "Uzbek",
    "fo": "Faroese",
    "ht": "Haitian Creole",
    "ps": "Pashto",
    "tk": "Turkmen",
    "nn": "Nynorsk",
    "mt": "Maltese",
    "sa": "Sanskrit",
    "lb": "Luxembourgish",
    "my": "Myanmar",
    "bo": "Tibetan",
    "tl": "Tagalog",
    "mg": "Malagasy",
    "as": "Assamese",
    "tt": "Tatar",
    "haw": "Hawaiian",
    "ln": "Lingala",
    "ha": "Hausa",
    "ba": "Bashkir",
    "jw": "Javanese",
    "su": "Sundanese",
    "yue": "Cantonese",
}

# Build full WHISPER_LANGUAGES mapping with auto-detect option
WHISPER_LANGUAGES: dict[str, str] = {"auto": "Auto-detect"}
WHISPER_LANGUAGES.update(_WHISPER_LANGUAGE_NAMES)

# Validate against imported codes if available
if WHISPER_LANGUAGE_CODES is not None:
    _missing_names = WHISPER_LANGUAGE_CODES - set(_WHISPER_LANGUAGE_NAMES.keys())
    if _missing_names:
        _logger.warning(f"Missing language names for codes: {sorted(_missing_names)}")
    _extra_names = set(_WHISPER_LANGUAGE_NAMES.keys()) - WHISPER_LANGUAGE_CODES
    if _extra_names:
        _logger.warning(f"Extra language names not in faster_whisper: {sorted(_extra_names)}")

# Common languages shown at the top of dropdowns for convenience
COMMON_LANGUAGES = [
    "auto",
    "en",
    "es",
    "fr",
    "de",
    "it",
    "pt",
    "nl",
    "ru",
    "zh",
    "ja",
    "ko",
    "ar",
]

# Languages supported for LLM output (subset of common languages)
LLM_OUTPUT_LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "ru": "Russian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
}

# Note: LANGUAGES_WITH_ALIGNMENT is defined at the top of this file
# via dynamic import from whisperx.alignment module
