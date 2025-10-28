from celery import Celery
from celery.schedules import crontab
from celery.signals import task_postrun
from celery.signals import worker_process_init

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
        "app.tasks.topic_extraction",
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
        # GPU Queue - GPU-intensive AI tasks ONLY (concurrency=1, requires GPU)
        # WhisperX transcription + PyAnnote diarization - runs continuously without blocking
        "app.tasks.transcription.*": {"queue": "gpu"},
        "transcribe_audio": {"queue": "gpu"},
        # Download Queue - Network I/O tasks (concurrency=3, no GPU)
        # YouTube downloads in parallel, immediately dispatch to GPU when complete
        "process_youtube_url_task": {"queue": "download"},
        "process_youtube_playlist_task": {"queue": "download"},
        # CPU Queue - CPU-intensive parallel tasks (concurrency=8, no GPU)
        # Audio/video processing that doesn't need GPU - modern CPUs have 8+ cores
        "generate_waveform_data": {"queue": "cpu"},
        "extract_audio": {"queue": "cpu"},
        "analyze_transcript": {"queue": "cpu"},
        # NLP Queue - LLM API calls (concurrency=4, no GPU needed)
        # These are I/O-bound API calls to external LLM services (vLLM, OpenAI, etc.)
        # Moderate concurrency to avoid overwhelming LLM APIs and maintain stability
        # Run AFTER transcription, don't block next transcription from starting
        "app.tasks.summarization.*": {"queue": "nlp"},
        "summarize_transcript": {"queue": "nlp"},
        "app.tasks.analytics.*": {"queue": "nlp"},
        "app.tasks.speaker_tasks.*": {"queue": "nlp"},
        "identify_speakers_llm": {"queue": "nlp"},
        "app.tasks.topic_extraction.*": {"queue": "nlp"},
        "extract_topics_from_transcript": {"queue": "nlp"},
        # Utility Queue - Lightweight maintenance tasks (concurrency=2)
        "app.tasks.utility.*": {"queue": "utility"},
        "app.tasks.recovery.*": {"queue": "utility"},
        "check_tasks_health": {"queue": "utility"},
        "update_gpu_stats": {"queue": "utility"},
        "startup_recovery": {"queue": "utility"},
        "recover_user_files": {"queue": "utility"},
        "periodic_health_check": {"queue": "utility"},
    },
    # Configure beat schedule for periodic tasks
    beat_schedule={
        "periodic-health-check": {
            "task": "periodic_health_check",
            "schedule": crontab(minute="*/10"),  # Run every 10 minutes
            "options": {"queue": "utility"},
        },
        "update-gpu-stats": {
            "task": "update_gpu_stats",
            "schedule": 30.0,  # Run every 30 seconds
            "options": {"queue": "gpu"},  # Run on GPU worker
        },
    },
)


# Signal handlers for proper database connection management
@worker_process_init.connect
def init_worker_process(**kwargs):
    """Initialize worker process - dispose of any existing connections."""
    from app.db.base import engine

    engine.dispose()


@task_postrun.connect
def close_session_after_task(**kwargs):
    """Close database connections after each task to prevent stale connections."""
    from app.db.base import engine

    engine.dispose()
