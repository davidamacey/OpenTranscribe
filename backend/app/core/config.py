from typing import List, Optional, Union
from pydantic import AnyHttpUrl, validator
from pydantic_settings import BaseSettings
import os
from pathlib import Path

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
    
    # Database settings
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "transcribe_app")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
    
    # MinIO / S3 settings
    MINIO_ROOT_USER: str = os.getenv("MINIO_ROOT_USER", "minioadmin")
    MINIO_ROOT_PASSWORD: str = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
    MINIO_HOST: str = os.getenv("MINIO_HOST", "localhost")
    MINIO_PORT: str = os.getenv("MINIO_PORT", "9000")
    MINIO_SECURE: bool = False  # Use HTTPS for MinIO
    MEDIA_BUCKET_NAME: str = os.getenv("MEDIA_BUCKET_NAME", "media")
    
    # Redis settings (for Celery)
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: str = os.getenv("REDIS_PORT", "6379")
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    REDIS_URL: str = os.getenv(
        "REDIS_URL", 
        f"redis://{':' + REDIS_PASSWORD + '@' if REDIS_PASSWORD else ''}{REDIS_HOST}:{REDIS_PORT}/0"
    )
    
    # OpenSearch settings
    OPENSEARCH_HOST: str = os.getenv("OPENSEARCH_HOST", "localhost")
    OPENSEARCH_PORT: str = os.getenv("OPENSEARCH_PORT", "9200")
    OPENSEARCH_USER: str = os.getenv("OPENSEARCH_USER", "admin")
    OPENSEARCH_PASSWORD: str = os.getenv("OPENSEARCH_PASSWORD", "admin")
    OPENSEARCH_VERIFY_CERTS: bool = False
    OPENSEARCH_TRANSCRIPT_INDEX: str = "transcripts"
    OPENSEARCH_SPEAKER_INDEX: str = "speakers"
    
    # Celery settings
    CELERY_BROKER_URL: str = REDIS_URL
    CELERY_RESULT_BACKEND: str = REDIS_URL
    
    # CORS settings
    CORS_ORIGINS: List[str] = ["*", "http://localhost:5173", "http://127.0.0.1:5173"]
    
    @validator("CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)
    
    # Hardware Detection Settings (auto-detected by default)
    TORCH_DEVICE: str = os.getenv("TORCH_DEVICE", "auto")  # auto, cuda, mps, cpu
    COMPUTE_TYPE: str = os.getenv("COMPUTE_TYPE", "auto")  # auto, float16, float32, int8
    USE_GPU: str = os.getenv("USE_GPU", "auto")  # auto, true, false
    GPU_DEVICE_ID: int = int(os.getenv("GPU_DEVICE_ID", "0"))
    BATCH_SIZE: str = os.getenv("BATCH_SIZE", "auto")  # auto or integer
    
    # AI Models settings
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "large-v2")
    PYANNOTE_MODEL: str = os.getenv("PYANNOTE_MODEL", "pyannote/speaker-diarization")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "mistral-7b-instruct-v0.2.Q4_K_M")  # For summarization
    HUGGINGFACE_TOKEN: str = os.getenv("HUGGINGFACE_TOKEN")
    
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
    
    # Storage paths
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "/mnt/nvm/repos/transcribe-app/data"))
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    MODEL_CACHE_DIR: Path = DATA_DIR / "model_cache"
    MODEL_BASE_DIR: Path = Path(os.getenv("MODELS_DIR", "/app/models"))
    
    # Initialization (CORS and directories)
    def __init__(self, **data):
        super().__init__(**data)
        # Ensure directories exist
        self.UPLOAD_DIR.mkdir(exist_ok=True, parents=True)
        self.MODEL_CACHE_DIR.mkdir(exist_ok=True, parents=True)
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
