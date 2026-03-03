# Skip heavy AI imports during testing - speeds up test startup significantly
import logging
import os

logger = logging.getLogger(__name__)

_SKIP_CELERY = os.environ.get("SKIP_CELERY", "").lower() == "true"

if not _SKIP_CELERY:
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

    # Note: WhisperX 3.8.1 has native PyAnnote v4 support — no patches needed

# Imports must come after torch.load patch to prevent caching issues
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
        "app.tasks.waveform_generation",
        "app.tasks.summarization",
        "app.tasks.analytics",
        "app.tasks.cleanup",
        "app.tasks.utility",
        "app.tasks.recovery",
        "app.tasks.youtube_processing",
        "app.tasks.speaker_tasks",
        "app.tasks.speaker_attribute_task",
        "app.tasks.topic_extraction",
        "app.tasks.reindex_task",
        "app.tasks.search_maintenance_task",
        "app.tasks.search_indexing_task",
        "app.tasks.thumbnail_migration",
        "app.tasks.embedding_migration_v4",
        "app.tasks.speaker_embedding_migration",
        "app.tasks.baseline_export",
        "app.tasks.cleanup",
        "app.tasks.rediarize_task",
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
    worker_send_task_events=True,  # Enable real-time task events for Flower
    task_send_sent_event=True,  # Fire event when task is dispatched to queue
    result_expires=86400,  # Expire results after 24h (prevent Redis bloat)
    task_routes={
        # GPU Queue - GPU-intensive AI tasks ONLY (concurrency=1, requires GPU)
        "app.tasks.transcription.*": {"queue": "gpu"},
        "transcription.process_file": {"queue": "gpu"},
        "transcription.rediarize_speakers": {"queue": "gpu"},
        "speaker.update_embeddings_gpu": {"queue": "gpu"},
        "migration.extract_embeddings_v4": {"queue": "gpu"},
        "migration.extract_embeddings_v4_batch": {"queue": "gpu"},
        # Download Queue - Network I/O tasks (concurrency=3, no GPU)
        "download.media_url": {"queue": "download"},
        "download.media_playlist": {"queue": "download"},
        # CPU Queue - CPU-intensive parallel tasks (concurrency=8, no GPU)
        # Audio/video processing that doesn't need GPU - modern CPUs have 8+ cores
        "media.generate_waveform": {"queue": "cpu"},
        "media.generate_waveform_data": {"queue": "cpu"},
        "analytics.analyze_transcript": {"queue": "cpu"},
        "speaker.detect_attributes": {"queue": "cpu"},
        "system.update_gpu_stats": {"queue": "cpu"},
        "migration.speaker_embeddings_v4": {"queue": "cpu"},
        "migration.normalize_embeddings": {"queue": "cpu"},
        "migration.thumbnails_to_webp": {"queue": "cpu"},
        "search.reindex_all": {"queue": "cpu"},
        # NLP Queue - LLM API calls (concurrency=4, no GPU needed)
        "app.tasks.summarization.*": {"queue": "nlp"},
        "ai.generate_summary": {"queue": "nlp"},
        "app.tasks.analytics.*": {"queue": "nlp"},
        # Speaker embedding reassignment needs GPU for PyAnnote model
        "update_speaker_embedding_on_reassignment": {"queue": "gpu"},
        "app.tasks.speaker_tasks.*": {"queue": "nlp"},
        "ai.identify_speakers": {"queue": "nlp"},
        "speaker.process_update": {"queue": "nlp"},
        "speaker.extract_embeddings": {"queue": "nlp"},
        "app.tasks.topic_extraction.*": {"queue": "nlp"},
        "ai.extract_topics": {"queue": "nlp"},
        "ai.extract_topics_batch": {"queue": "nlp"},
        # Embedding Queue - Search indexing with embedding model (concurrency=1)
        # Dedicated worker keeps the embedding model loaded and processes one at a time.
        # Same pattern as GPU queue: sequential execution, model stays warm in memory.
        "app.tasks.reindex_task.*": {"queue": "embedding"},
        "app.tasks.search_indexing_task.*": {"queue": "embedding"},
        "search.index_transcript": {"queue": "embedding"},
        "search.index_maintenance": {"queue": "embedding"},
        # Utility Queue - Lightweight maintenance tasks (concurrency=8)
        "app.tasks.utility.*": {"queue": "utility"},
        "app.tasks.recovery.*": {"queue": "utility"},
        # GPU stats runs on the cpu worker so it fires independently of long-running
        # GPU transcription tasks (gpu worker concurrency=1 would block for 30+ min).
        # The cpu worker is given 'count: all' NVIDIA device access in gpu.yml so it
        # can call nvidia-smi for any device.  The task selects the correct device ID
        # via GPU_SCALE_ENABLED + GPU_SCALE_DEVICE_ID vs GPU_DEVICE_ID from .env.
        "app.tasks.cleanup.*": {"queue": "utility"},
        "system.startup_recovery": {"queue": "utility"},
        "system.recover_user_files": {"queue": "utility"},
        "system.health_check": {"queue": "utility"},
        "system.check_tasks_health": {"queue": "utility"},
        "system.cleanup_expired_files": {"queue": "utility"},
        "cleanup.run_periodic_cleanup": {"queue": "utility"},
        "cleanup.deep_cleanup": {"queue": "utility"},
        "cleanup.health_check": {"queue": "utility"},
        "cleanup.emergency_recovery": {"queue": "utility"},
        "migration.check_status": {"queue": "utility"},
        "migration.finalize_v4": {"queue": "utility"},
        "quality.export_baseline": {"queue": "utility"},
        "quality.compare_baseline": {"queue": "utility"},
    },
    # Configure beat schedule for periodic tasks
    beat_schedule={
        "periodic-health-check": {
            "task": "system.health_check",
            "schedule": crontab(minute="*/10"),  # Run every 10 minutes
            "options": {"queue": "utility"},
        },
        "search-index-maintenance": {
            "task": "search.index_maintenance",
            "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours
            "options": {"queue": "embedding"},
        },
        "gpu-stats-update": {
            "task": "system.update_gpu_stats",
            "schedule": crontab(minute="*/5"),  # Run every 5 minutes
            "options": {"queue": "cpu"},
        },
        "cleanup-expired-files": {
            "task": "system.cleanup_expired_files",
            "schedule": crontab(minute=0),  # Every hour on the hour
            "options": {"queue": "utility"},
        },
    },
)


# Signal handlers for proper database connection management
@worker_process_init.connect
def init_worker_process(**kwargs):
    """Initialize worker process - register HF token and dispose connections."""
    import os

    # Register HuggingFace token for gated model access (e.g., pyannote)
    # Skip in offline mode — models are pre-downloaded and no network is available
    hf_token = os.getenv("HUGGINGFACE_TOKEN")
    if hf_token and os.getenv("HF_HUB_OFFLINE") != "1":
        try:
            from huggingface_hub import login

            login(token=hf_token, add_to_git_credential=False)
            logger.info("HuggingFace token registered for gated model access")
        except Exception as e:
            logger.warning(f"Failed to register HuggingFace token: {e}")

    from app.db.base import engine

    engine.dispose()


@task_postrun.connect
def close_session_after_task(**kwargs):
    """Close database connections after each task to prevent stale connections."""
    from app.db.base import engine

    engine.dispose()
