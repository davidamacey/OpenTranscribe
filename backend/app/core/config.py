import os
from pathlib import Path
from typing import Optional
from typing import Union

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API configuration
    API_PREFIX: str = "/api"
    PROJECT_NAME: str = "Transcription App"

    # Environment configuration
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = ENVIRONMENT == "development"

    # JWT Token settings
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "this_should_be_changed_in_production")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Encryption settings for sensitive data (API keys, etc.)
    ENCRYPTION_KEY: str = os.getenv(
        "ENCRYPTION_KEY", "this_should_be_changed_in_production_for_api_key_encryption"
    )

    # Database settings
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "transcribe_app")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}",
    )

    # MinIO / S3 settings
    MINIO_ROOT_USER: str = os.getenv("MINIO_ROOT_USER", "minioadmin")
    MINIO_ROOT_PASSWORD: str = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
    MINIO_HOST: str = os.getenv("MINIO_HOST", "localhost")
    MINIO_PORT: str = os.getenv("MINIO_PORT", "9000")
    MINIO_SECURE: bool = False  # Use HTTPS for MinIO
    MEDIA_BUCKET_NAME: str = os.getenv("MEDIA_BUCKET_NAME", "opentranscribe")

    # Redis settings (for Celery)
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: str = os.getenv("REDIS_PORT", "6379")
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    REDIS_URL: str = os.getenv(
        "REDIS_URL",
        f"redis://{':' + REDIS_PASSWORD + '@' if REDIS_PASSWORD else ''}{REDIS_HOST}:{REDIS_PORT}/0",
    )

    # OpenSearch settings
    OPENSEARCH_HOST: str = os.getenv("OPENSEARCH_HOST", "localhost")
    OPENSEARCH_PORT: str = os.getenv("OPENSEARCH_PORT", "9200")
    OPENSEARCH_USER: str = os.getenv("OPENSEARCH_USER", "admin")
    OPENSEARCH_PASSWORD: str = os.getenv("OPENSEARCH_PASSWORD", "admin")
    OPENSEARCH_VERIFY_CERTS: bool = False
    OPENSEARCH_TRANSCRIPT_INDEX: str = "transcripts"
    OPENSEARCH_SPEAKER_INDEX: str = "speakers"
    OPENSEARCH_SUMMARY_INDEX: str = "transcript_summaries"
    OPENSEARCH_TOPIC_SUGGESTIONS_INDEX: str = "topic_suggestions"
    OPENSEARCH_TOPIC_VECTORS_INDEX: str = "topic_vectors"

    # Celery settings
    CELERY_BROKER_URL: str = REDIS_URL
    CELERY_RESULT_BACKEND: str = REDIS_URL

    # CORS settings
    CORS_ORIGINS: list[str] = ["*", "http://localhost:5173", "http://127.0.0.1:5173"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, list[str]]) -> Union[list[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # Hardware Detection Settings (auto-detected by default)
    TORCH_DEVICE: str = os.getenv("TORCH_DEVICE", "auto")  # auto, cuda, mps, cpu
    COMPUTE_TYPE: str = os.getenv("COMPUTE_TYPE", "auto")  # auto, float16, float32, int8
    USE_GPU: str = os.getenv("USE_GPU", "auto")  # auto, true, false
    GPU_DEVICE_ID: int = int(
        os.getenv("GPU_DEVICE_ID", "0")
    )  # Host GPU index (Docker maps to device 0)
    BATCH_SIZE: str = os.getenv("BATCH_SIZE", "auto")  # auto or integer

    # AI Models settings
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "large-v2")
    PYANNOTE_MODEL: str = os.getenv("PYANNOTE_MODEL", "pyannote/speaker-diarization")
    HUGGINGFACE_TOKEN: Optional[str] = os.getenv("HUGGINGFACE_TOKEN", None)

    # Speaker diarization settings
    MIN_SPEAKERS: int = int(os.getenv("MIN_SPEAKERS", "1"))
    MAX_SPEAKERS: int = int(os.getenv("MAX_SPEAKERS", "20"))
    # NUM_SPEAKERS forces exact speaker count (overrides min/max if set)
    NUM_SPEAKERS: Optional[int] = int(os.getenv("NUM_SPEAKERS")) if os.getenv("NUM_SPEAKERS") else None

    # LLM Configuration - Users configure through web UI, stored in database
    # These are system fallbacks for quick access when no user settings exist
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "")

    # Quick access defaults for common providers
    VLLM_BASE_URL: str = os.getenv("VLLM_BASE_URL", "http://localhost:8012/v1")
    VLLM_MODEL_NAME: str = os.getenv("VLLM_MODEL_NAME", "gpt-oss")
    VLLM_API_KEY: str = os.getenv("VLLM_API_KEY", "")

    OPENAI_MODEL_NAME: str = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL_NAME: str = os.getenv("OLLAMA_MODEL_NAME", "llama2:7b-chat")

    ANTHROPIC_MODEL_NAME: str = os.getenv("ANTHROPIC_MODEL_NAME", "claude-3-haiku-20240307")
    ANTHROPIC_BASE_URL: str = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    OPENROUTER_MODEL_NAME: str = os.getenv("OPENROUTER_MODEL_NAME", "anthropic/claude-3-haiku")
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")

    # Performance optimization properties
    @property
    def effective_use_gpu(self) -> bool:
        """Determine if GPU should be used based on hardware detection."""
        if self.USE_GPU.lower() == "auto":
            try:
                from app.utils.hardware_detection import detect_hardware

                config = detect_hardware()
                return config.device in ["cuda", "mps"]
            except ImportError:
                return False
        return self.USE_GPU.lower() == "true"

    @property
    def effective_torch_device(self) -> str:
        """Get the effective torch device."""
        if self.TORCH_DEVICE.lower() == "auto":
            try:
                from app.utils.hardware_detection import detect_hardware

                config = detect_hardware()
                return config.device
            except ImportError:
                return "cpu"
        return self.TORCH_DEVICE.lower()

    @property
    def effective_compute_type(self) -> str:
        """Get the effective compute type."""
        if self.COMPUTE_TYPE.lower() == "auto":
            try:
                from app.utils.hardware_detection import detect_hardware

                config = detect_hardware()
                return config.compute_type
            except ImportError:
                return "int8"
        return self.COMPUTE_TYPE.lower()

    @property
    def effective_batch_size(self) -> int:
        """Get the effective batch size."""
        if self.BATCH_SIZE.lower() == "auto":
            try:
                from app.utils.hardware_detection import detect_hardware

                config = detect_hardware()
                return config.batch_size
            except ImportError:
                return 1
        return int(self.BATCH_SIZE)

    # Storage paths (container paths, mounted from host via docker-compose volumes)
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "/app/data"))
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    MODEL_BASE_DIR: Path = Path(os.getenv("MODELS_DIR", "/app/models"))
    TEMP_DIR: Path = Path(os.getenv("TEMP_DIR", "/app/temp"))

    # Initialization (CORS and directories)
    def __init__(self, **data):
        super().__init__(**data)
        # Ensure directories exist
        self.UPLOAD_DIR.mkdir(exist_ok=True, parents=True)
        self.TEMP_DIR.mkdir(exist_ok=True, parents=True)

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
