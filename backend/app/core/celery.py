# PyTorch 2.6+ compatibility fix - MUST be done BEFORE any ML library imports
# Patch torch.load to default to weights_only=False for trusted HuggingFace models
# This must be at the TOP of celery.py because Celery's include= imports task modules
# which import pyannote/whisperx that cache torch.load at import time
import torch

_original_torch_load = torch.load


def _patched_torch_load(*args, **kwargs):
    # Handle both missing weights_only AND weights_only=None (which PyTorch 2.8 treats as True)
    if kwargs.get("weights_only") is None:
        kwargs["weights_only"] = False
    return _original_torch_load(*args, **kwargs)


torch.load = _patched_torch_load

# WhisperX 3.7.0 passes deprecated use_auth_token to newer huggingface_hub
# which no longer accepts it. Patch hf_hub_download to convert the parameter.
import huggingface_hub
from huggingface_hub import hf_hub_download as _original_hf_hub_download


def _patched_hf_hub_download(*args, **kwargs):
    if "use_auth_token" in kwargs:
        kwargs["token"] = kwargs.pop("use_auth_token")
    return _original_hf_hub_download(*args, **kwargs)


huggingface_hub.hf_hub_download = _patched_hf_hub_download

# Imports must come after patches to prevent caching issues
from celery import Celery  # noqa: E402
from celery.schedules import crontab  # noqa: E402
from celery.signals import task_postrun  # noqa: E402
from celery.signals import worker_process_init  # noqa: E402

from app.core.config import settings  # noqa: E402

# Initialize Celery
celery_app = Celery(
    "transcribe_app",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.transcription",
        "app.tasks.waveform",
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
        "generate_waveform_task": {"queue": "cpu"},
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
        "update_gpu_stats": {"queue": "gpu"},
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
    },
)


# Signal handlers for proper database connection management
@worker_process_init.connect
def init_worker_process(**kwargs):
    """Initialize worker process - dispose of any existing connections and set auth tokens."""
    import os

    from app.db.base import engine

    # Register HF token so pyannote/whisperx can access gated models
    if settings.HUGGINGFACE_TOKEN:
        os.environ["HF_TOKEN"] = settings.HUGGINGFACE_TOKEN
        try:
            from huggingface_hub import login

            login(token=settings.HUGGINGFACE_TOKEN, add_to_git_credential=False)
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"HuggingFace login failed: {e}")

    engine.dispose()


@task_postrun.connect
def close_session_after_task(**kwargs):
    """Close database connections after each task to prevent stale connections."""
    from app.db.base import engine

    engine.dispose()
