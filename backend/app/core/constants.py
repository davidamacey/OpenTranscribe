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

_logger = logging.getLogger(__name__)

# =============================================================================
# Dynamic imports for language support
# =============================================================================

# Import alignment languages from whisperx (public API)
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
try:
    from faster_whisper.tokenizer import _LANGUAGE_CODES

    WHISPER_LANGUAGE_CODES: set[str] | None = set(_LANGUAGE_CODES)
except ImportError:
    _logger.warning("Could not import faster_whisper language codes for validation")
    WHISPER_LANGUAGE_CODES = None

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
