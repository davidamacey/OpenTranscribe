from celery import Celery
from app.core.config import settings

# Initialize Celery
celery_app = Celery(
    "transcribe_app",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.transcription", "app.tasks.summarization", "app.tasks.analytics"]
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,  # One task at a time for GPU tasks
    task_routes={
        "app.tasks.transcription.*": {"queue": "transcription"},
        "app.tasks.summarization.*": {"queue": "nlp"},
        "app.tasks.analytics.*": {"queue": "nlp"},
        "app.tasks.utility.*": {"queue": "utility"}
    }
)
