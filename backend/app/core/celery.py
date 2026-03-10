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
from celery.signals import worker_ready  # noqa: E402

from app.core.config import settings  # noqa: E402

# Initialize Celery
celery_app = Celery(
    "transcribe_app",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.transcription",
        "app.tasks.transcription.preprocess",
        "app.tasks.transcription.postprocess",
        "app.tasks.transcription.dispatch",
        "app.tasks.waveform",
        "app.tasks.waveform_generation",
        "app.tasks.summarization",
        "app.tasks.analytics",
        "app.tasks.cleanup",
        "app.tasks.utility",
        "app.tasks.recovery",
        "app.tasks.youtube_processing",
        "app.tasks.speaker_tasks",
        "app.tasks.speaker_identification_task",
        "app.tasks.speaker_update_task",
        "app.tasks.speaker_embedding_task",
        "app.tasks.speaker_attribute_task",
        "app.tasks.topic_extraction",
        "app.tasks.reindex_task",
        "app.tasks.search_maintenance_task",
        "app.tasks.opensearch_integrity_task",
        "app.tasks.search_indexing_task",
        "app.tasks.thumbnail",
        "app.tasks.thumbnail_migration",
        "app.tasks.embedding_migration_v4",
        "app.tasks.speaker_embedding_migration",
        "app.tasks.baseline_export",
        "app.tasks.rediarize_task",
        "app.tasks.speaker_clustering",
        "app.tasks.auto_labeling",
        "app.tasks.speaker_attribute_migration_task",
        "app.tasks.combined_speaker_analysis_task",
        "app.tasks.speaker_embedding_consistency",
        "app.tasks.embedding_consistency_repair",
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
    # Enable Redis priority queues: lower number = higher priority (runs first).
    # Priorities are PER-QUEUE — GPUPriority.X is independent of CPUPriority.X.
    # Named constants defined in app.core.constants: GPUPriority, CPUPriority, etc.
    # GPU queue:  0=speaker-reassign  1=embed-extract  3=transcription  4=rediarize
    #             5=recluster  7=admin-migration-batches
    # CPU queue:  2=pipeline-critical  4=user-triggered  5=system  6=admin  8=maintenance
    # NLP queue:  3=user-triggered  5=auto-pipeline  7=admin-batch  9=background
    # Download:   3=single-url  6=playlist
    # Embedding:  2=pipeline-critical
    # Utility:    1=emergency  3=operational  5=routine  7=background  9=dev-tools
    broker_transport_options={
        "priority_steps": list(range(10)),
        "queue_order_strategy": "priority",
    },
    task_routes={
        # GPU Queue - GPU-intensive AI tasks (concurrency=1, requires GPU)
        # See priority comment above for priority scheme
        "transcription.process_file": {"queue": "gpu"},
        # Pipeline chain tasks (3-stage: CPU preprocess → GPU transcribe → CPU postprocess)
        # NOTE: "transcription.gpu_transcribe" is intentionally NOT listed here so
        # dispatch.py can route it to either "gpu" or "cloud-asr" at call time.
        "transcription.preprocess": {"queue": "cpu"},
        "transcription.postprocess": {"queue": "cpu"},
        "transcription.pipeline_error": {"queue": "utility"},
        "rediarize": {"queue": "gpu"},
        "update_speaker_embedding_on_reassignment": {"queue": "gpu"},
        "extract_v4_embeddings": {"queue": "gpu"},
        "extract_v4_embeddings_batch": {"queue": "gpu"},
        "app.tasks.speaker_clustering.recluster_all_speakers": {"queue": "gpu"},
        "app.tasks.speaker_clustering.cluster_speakers_for_file": {"queue": "cpu"},
        # NOTE: "transcribe_audio" is intentionally NOT listed here so that
        # apply_async(queue=task_queue) in upload.py / reprocess.py can route it
        # to either "gpu" (local) or "cloud-asr" (cloud provider) at call time.
        # A static task_routes entry would override the per-call queue argument.
        # Download Queue - Network I/O tasks (concurrency=3, no GPU)
        "download.media_url": {"queue": "download"},
        "download.media_playlist": {"queue": "download"},
        # CPU Queue - CPU-intensive parallel tasks (concurrency=8, no GPU)
        "media.generate_waveform": {"queue": "cpu"},
        "media.generate_waveform_data": {"queue": "cpu"},
        "analytics.analyze_transcript": {"queue": "cpu"},
        "detect_speaker_attributes": {"queue": "cpu"},
        "migrate_speaker_attributes": {"queue": "cpu"},
        "detect_speaker_attributes_batch": {"queue": "gpu"},
        "analyze_speakers_combined_batch": {"queue": "gpu"},
        "migrate_speakers_combined": {"queue": "cpu"},
        "system.update_gpu_stats": {"queue": "cpu"},
        "migrate_speaker_embeddings_to_v4": {"queue": "cpu"},
        "migration.normalize_embeddings": {"queue": "cpu"},
        "generate_thumbnail": {"queue": "cpu"},
        "migrate_thumbnails_to_webp": {"queue": "cpu"},
        "reindex_transcripts": {"queue": "cpu"},
        "reindex_batch": {"queue": "cpu"},
        "search_index_maintenance": {"queue": "cpu"},
        "opensearch_orphan_cleanup": {"queue": "cpu"},
        "speaker_embedding_consistency_check": {"queue": "cpu"},
        "speaker_embedding_consistency_repair_batch": {"queue": "gpu"},
        # NLP Queue - LLM API calls (concurrency=4, no GPU needed)
        "ai.generate_summary": {"queue": "nlp"},
        "ai.identify_speakers": {"queue": "nlp"},
        "process_speaker_update_background": {"queue": "cpu"},
        "extract_speaker_embeddings": {"queue": "gpu"},
        "ai.extract_topics": {"queue": "nlp"},
        "ai.extract_topics_batch": {"queue": "nlp"},
        "ai.group_batch_files": {"queue": "nlp"},
        "ai.retroactive_auto_label": {"queue": "nlp"},
        "ai.auto_label_batch": {"queue": "nlp"},
        # Embedding Queue - Search indexing with embedding model (concurrency=1)
        "index_transcript_search": {"queue": "embedding"},
        # Access index updates are lightweight OpenSearch writes (no GPU/embedding needed)
        "update_file_access_index": {"queue": "utility"},
        # Utility Queue - Lightweight maintenance tasks (concurrency=8)
        "system.startup_recovery": {"queue": "utility"},
        "system.recover_user_files": {"queue": "utility"},
        "system.health_check": {"queue": "utility"},
        "cleanup_expired_files": {"queue": "utility"},
        "cleanup.run_periodic_cleanup": {"queue": "utility"},
        "cleanup.deep_cleanup": {"queue": "utility"},
        "cleanup.health_check": {"queue": "utility"},
        "cleanup.emergency_recovery": {"queue": "utility"},
        "check_migration_status": {"queue": "utility"},
        "finalize_v4_migration": {"queue": "utility"},
        "export_transcript_baseline": {"queue": "utility"},
        "compare_transcript_baseline": {"queue": "utility"},
    },
    # Configure beat schedule for periodic tasks
    beat_schedule={
        "periodic-health-check": {
            "task": "system.health_check",
            "schedule": crontab(minute="*/10"),  # Run every 10 minutes
            "options": {"queue": "utility", "priority": 3},  # UtilityPriority.OPERATIONAL
        },
        "search-index-maintenance": {
            "task": "search_index_maintenance",
            "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours
            "options": {"queue": "cpu", "priority": 8},  # CPUPriority.MAINTENANCE
        },
        "opensearch-orphan-cleanup": {
            "task": "opensearch_orphan_cleanup",
            "schedule": crontab(minute=0, hour="3,9,15,21"),  # Every 6h, offset from maintenance
            "options": {"queue": "cpu", "priority": 8},  # CPUPriority.MAINTENANCE
        },
        "embedding-consistency-check": {
            "task": "speaker_embedding_consistency_check",
            "schedule": crontab(minute="*/10"),  # Every 10 minutes
            "options": {"queue": "cpu", "priority": 8},  # CPUPriority.MAINTENANCE
        },
        "gpu-stats-update": {
            "task": "system.update_gpu_stats",
            "schedule": crontab(minute="*/5"),  # Run every 5 minutes
            "options": {"queue": "cpu", "priority": 5},  # CPUPriority.SYSTEM
        },
        "cleanup-expired-files": {
            "task": "cleanup_expired_files",
            "schedule": crontab(minute=0),  # Every hour on the hour
            "options": {"queue": "utility", "priority": 5},  # UtilityPriority.ROUTINE
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


@worker_ready.connect
def preload_gpu_models(**kwargs):
    """Preload GPU models for concurrent thread pool workers.

    worker_ready fires for all pool types (including threads) after the
    worker is fully initialized, unlike worker_process_init which only
    fires for prefork child processes.
    """
    try:
        from app.transcription.config import TranscriptionConfig

        config = TranscriptionConfig.from_environment()
        if config.concurrent_requests > 1 and config.device == "cuda":
            from app.transcription.model_manager import ModelManager

            ModelManager.get_instance().ensure_models_loaded(config)
            logger.info(
                "GPU models preloaded for concurrent mode "
                f"(concurrent_requests={config.concurrent_requests})"
            )
    except Exception as e:
        logger.debug(f"Model preloading skipped (not a GPU worker or error): {e}")


@task_postrun.connect
def close_session_after_task(**kwargs):
    """Close database connections after each task to prevent stale connections."""
    from app.db.base import engine

    engine.dispose()
