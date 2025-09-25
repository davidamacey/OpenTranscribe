from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

# Initialize Celery
celery_app = Celery(
    "transcribe_app",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.transcription",
        "app.tasks.summarization",
        "app.tasks.analytics",
        "app.tasks.utility",
        "app.tasks.recovery",
        "app.tasks.youtube_processing",
        "app.tasks.speaker_tasks",
    ],
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
        "app.tasks.transcription.*": {"queue": "gpu"},
        "transcribe_audio": {"queue": "gpu"},  # Explicit routing for transcription task
        "process_youtube_url_task": {"queue": "gpu"},  # Explicit routing for YouTube task
        "generate_waveform_data": {"queue": "utility"},  # Waveform generation is CPU-bound
        "app.tasks.summarization.*": {"queue": "nlp"},
        "app.tasks.analytics.*": {"queue": "nlp"},
        "app.tasks.utility.*": {"queue": "utility"},
        "app.tasks.recovery.*": {"queue": "utility"},
        "app.tasks.youtube_processing.*": {"queue": "gpu"},  # GPU queue for video processing
        "app.tasks.speaker_tasks.*": {"queue": "nlp"},  # Speaker tasks use NLP queue
        "identify_speakers_llm": {"queue": "nlp"},  # Explicit routing for speaker identification
    },
    # Configure beat schedule for periodic tasks
    beat_schedule={
        "periodic-health-check": {
            "task": "periodic_health_check",
            "schedule": crontab(minute="*/10"),  # Run every 10 minutes
            "options": {"queue": "utility"},
        }
    },
)
