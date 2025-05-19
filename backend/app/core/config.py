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
    
    # AI Models settings
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "large-v2")
    PYANNOTE_MODEL: str = os.getenv("PYANNOTE_MODEL", "pyannote/speaker-diarization")
    USE_GPU: bool = os.getenv("USE_GPU", "True").lower() == "true"  # Default to True as we have a powerful GPU
    LLM_MODEL: str = os.getenv("LLM_MODEL", "mistral-7b-instruct-v0.2.Q4_K_M")  # For summarization
    
    # Storage paths
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "/mnt/nvm/repos/transcribe-app/data"))
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    MODEL_CACHE_DIR: Path = DATA_DIR / "model_cache"
    
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
