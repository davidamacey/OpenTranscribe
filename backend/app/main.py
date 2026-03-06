import asyncio
import logging
import os
from contextlib import asynccontextmanager
from contextlib import suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.api.router import api_router
from app.auth.rate_limit import limiter
from app.auth.rate_limit import rate_limit_exceeded_handler
from app.core.config import settings
from app.core.version import APP_VERSION
from app.middleware.audit import AuditMiddleware

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _validate_production_secrets():
    """Validate that production secrets are properly configured."""
    is_production = settings.ENVIRONMENT.lower() in ("production", "prod")

    # Check JWT secret key
    insecure_jwt_secrets = (
        "this_should_be_changed_in_production",
        "changeme",
        "secret",
        "your-secret-key",
    )
    if is_production and settings.JWT_SECRET_KEY.lower() in insecure_jwt_secrets:
        logger.error(
            "SECURITY ERROR: JWT_SECRET_KEY is using an insecure default value in production! "
            "Set a strong, unique secret key via the JWT_SECRET_KEY environment variable."
        )
        raise ValueError("Insecure JWT_SECRET_KEY in production environment")

    # Check encryption key
    if is_production and "this_should_be_changed" in settings.ENCRYPTION_KEY.lower():
        logger.error(
            "SECURITY ERROR: ENCRYPTION_KEY is using an insecure default value in production! "
            "Set a strong, unique encryption key via the ENCRYPTION_KEY environment variable."
        )
        raise ValueError("Insecure ENCRYPTION_KEY in production environment")

    # Warn about Keycloak audience validation disabled in production
    if is_production and settings.KEYCLOAK_ENABLED and not settings.KEYCLOAK_VERIFY_AUDIENCE:
        logger.warning(
            "SECURITY WARNING: KEYCLOAK_VERIFY_AUDIENCE is disabled in production! "
            "This allows tokens intended for other clients to be accepted. "
            "Set KEYCLOAK_VERIFY_AUDIENCE=true and configure KEYCLOAK_AUDIENCE for proper token validation."
        )

    # Warn about PKI enabled without trusted proxies
    if settings.PKI_ENABLED and not settings.PKI_TRUSTED_PROXIES:
        logger.warning(
            "SECURITY WARNING: PKI_ENABLED=true but PKI_TRUSTED_PROXIES is empty! "
            "This allows any client to inject PKI certificate headers. "
            "Configure PKI_TRUSTED_PROXIES with your reverse proxy IP addresses "
            "(e.g., '127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16')."
        )

    if is_production:
        logger.info("Production security validation passed")


async def _setup_minio():
    """Initialize MinIO bucket on startup.

    Creates the media bucket if it doesn't exist and ensures the bucket
    policy is private (no anonymous/public access). All file access goes
    through presigned URLs, so public read is unnecessary and a security risk.
    """
    try:
        import json

        from minio import Minio

        minio_host = os.getenv("MINIO_HOST", "minio")
        minio_port = os.getenv("MINIO_PORT", "9000")
        minio_user = os.getenv("MINIO_ROOT_USER", "minioadmin")
        minio_password = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
        bucket_name = os.getenv("MEDIA_BUCKET_NAME", "opentranscribe")

        client = Minio(
            f"{minio_host}:{minio_port}",
            access_key=minio_user,
            secret_key=minio_password,
            secure=False,
        )

        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            logger.info(f"MinIO bucket '{bucket_name}' created successfully")
        else:
            logger.info(f"MinIO bucket '{bucket_name}' already exists")

        # Security: ensure bucket has no public access policy.
        # Previous versions set a public read policy ("Principal": {"AWS": "*"})
        # which allowed anonymous access to all stored files. Since all file
        # access goes through presigned URLs, public read is unnecessary.
        # Remove any existing public policy to lock down the bucket.
        try:
            existing_policy = client.get_bucket_policy(bucket_name)
            if existing_policy:
                policy_data = json.loads(existing_policy)
                has_public_access = any(
                    stmt.get("Principal") in ({"AWS": "*"}, "*", {"AWS": ["*"]})
                    for stmt in policy_data.get("Statement", [])
                )
                if has_public_access:
                    client.delete_bucket_policy(bucket_name)
                    logger.warning(
                        f"SECURITY FIX: Removed public access policy from bucket '{bucket_name}'. "
                        "All file access now requires authentication via presigned URLs."
                    )
        except Exception:  # noqa: S110
            # No policy set (expected for new buckets) — this is the secure default
            logger.debug("No bucket policy set for '%s' (secure default)", bucket_name)

    except Exception as e:
        logger.error(f"Error setting up MinIO bucket: {e}")


async def _run_startup_recovery():
    """Schedule startup recovery task after a delay."""
    try:
        await asyncio.sleep(10)
        from app.tasks.recovery import startup_recovery_task

        result = startup_recovery_task.delay()
        logger.info(f"Startup recovery task scheduled: {result.id}")
    except Exception as e:
        logger.error(f"Error scheduling startup recovery: {e}")


async def _run_search_maintenance():
    """Schedule search index maintenance after a delay."""
    try:
        await asyncio.sleep(30)
        from app.tasks.search_maintenance_task import search_index_maintenance_task

        result = search_index_maintenance_task.delay()
        logger.info(f"Search index maintenance task scheduled: {result.id}")
    except Exception as e:
        logger.error(f"Error scheduling search maintenance: {e}")


async def _run_thumbnail_migration():
    """Schedule thumbnail migration from JPEG to WebP after a delay."""
    try:
        await asyncio.sleep(45)  # Wait for other startup tasks
        from app.tasks.thumbnail_migration import migrate_thumbnails_to_webp

        result = migrate_thumbnails_to_webp.delay(batch_size=20)
        logger.info(f"Thumbnail migration task scheduled: {result.id}")
    except Exception as e:
        logger.error(f"Error scheduling thumbnail migration: {e}")


async def _run_one_time_embedding_normalization():
    """One-time migration: normalize legacy embeddings for users upgrading.

    Checks a DB flag first — if already done, returns immediately.
    After successful normalization, sets the flag so it never runs again.
    """
    try:
        await asyncio.sleep(60)

        from app.db.base import SessionLocal
        from app.models.system_settings import SystemSettings

        db = SessionLocal()
        try:
            flag = (
                db.query(SystemSettings)
                .filter(SystemSettings.key == "embedding_normalization_done")
                .first()
            )
            if flag and flag.value == "true":
                logger.info("Embedding normalization already completed — skipping")
                return
        finally:
            db.close()

        from app.tasks.speaker_embedding_migration import normalize_speaker_embeddings_task

        result = normalize_speaker_embeddings_task.apply(throw=False)
        if result and result.result and result.result.get("normalized", 0) == 0:
            # All vectors already normalized — set flag
            db = SessionLocal()
            try:
                setting = (
                    db.query(SystemSettings)
                    .filter(SystemSettings.key == "embedding_normalization_done")
                    .first()
                )
                if not setting:
                    setting = SystemSettings(
                        key="embedding_normalization_done",
                        value="true",
                        description="One-time embedding L2 normalization migration completed",
                    )
                    db.add(setting)
                else:
                    setting.value = "true"
                db.commit()
                logger.info("Embedding normalization flag set — will not run again")
            finally:
                db.close()
        elif result and result.result:
            stats = result.result
            logger.info(
                "Embedding normalization migrated %d vectors (checked %d)",
                stats.get("normalized", 0),
                stats.get("total_found", 0),
            )
            # Set flag after successful migration
            db = SessionLocal()
            try:
                setting = SystemSettings(
                    key="embedding_normalization_done",
                    value="true",
                    description="One-time embedding L2 normalization migration completed",
                )
                db.merge(setting)
                db.commit()
            finally:
                db.close()
    except Exception as e:
        logger.error(f"Embedding normalization migration error: {e}")


# NOTE: Search settings (model ID, dimension) are now managed by OpenSearch
# neural search via ml_model_service.py and persisted in system_settings table.
# No need to load them into runtime config - they're read directly from DB when needed.


async def _initialize_neural_search():
    """Initialize OpenSearch neural search models on startup.

    This function:
    1. Configures ML Commons cluster settings
    2. Checks for local models (offline deployment support)
    3. Auto-downloads default model if missing and internet available
    4. Ensures the default model is registered and deployed
    5. Creates/updates the neural ingest pipeline

    Runs after a delay to allow OpenSearch to fully start.
    For offline/air-gapped deployments, models are loaded from
    pre-downloaded local files (mounted at /ml-models in OpenSearch container).
    """
    if not settings.OPENSEARCH_NEURAL_SEARCH_ENABLED:
        logger.info("Neural search disabled, skipping initialization")
        return

    try:
        # Wait for OpenSearch to be ready
        await asyncio.sleep(15)

        from app.services.search.ml_model_service import get_ml_model_service

        ml_service = get_ml_model_service()

        # Configure ML Commons settings
        if not ml_service.configure_ml_settings():
            logger.warning("Could not configure ML Commons settings")
            return

        # Check for available local models (offline deployment support)
        local_models = ml_service.get_available_local_models()
        if local_models:
            model_names = [m["short_name"] for m in local_models]
            logger.info(f"Found {len(local_models)} local models for offline use: {model_names}")
        else:
            logger.warning("No local models found - attempting automatic download")

            # Try to download default model if internet is available
            from app.services.search.model_downloader import check_internet_connectivity
            from app.services.search.model_downloader import ensure_model_downloaded

            default_model = settings.OPENSEARCH_NEURAL_MODEL

            if check_internet_connectivity():
                logger.info(f"Internet available - downloading default model: {default_model}")
                model_path = ensure_model_downloaded(default_model)

                if model_path:
                    logger.info(f"Model downloaded successfully: {model_path}")
                    # Re-check local models after download
                    local_models = ml_service.get_available_local_models()
                    if local_models:
                        logger.info("Models now available for offline use")
                else:
                    logger.warning("Model download failed - will use remote registration")
            else:
                logger.warning("No internet connection - cannot download models")
                logger.warning("Will use remote registration (requires OpenSearch to download)")

        # Check if we have an active model
        active_model_id = ml_service.get_active_model_id()

        if active_model_id:
            logger.info(f"Neural search already has active model: {active_model_id}")
        else:
            # Try to register and deploy the default model
            default_model = settings.OPENSEARCH_NEURAL_MODEL
            logger.info(f"No active model, attempting to setup default: {default_model}")

            # Check if default model is available locally
            local_path = ml_service.get_local_model_path(default_model)
            if local_path:
                logger.info(f"Default model available locally: {local_path}")
            else:
                logger.info("Default model not found locally, will download from remote")

            model_id = ml_service.ensure_model_deployed(default_model)
            if model_id:
                ml_service.set_active_model_id(model_id)
                logger.info(f"Default neural model deployed: {default_model} -> {model_id}")
            else:
                logger.warning(f"Could not deploy default model {default_model}")
                return

        # Ensure neural ingest pipeline is configured
        from app.services.search.indexing_service import ensure_neural_ingest_pipeline

        if ensure_neural_ingest_pipeline():
            logger.info("Neural ingest pipeline configured successfully")
        else:
            logger.warning("Could not configure neural ingest pipeline")

    except Exception as e:
        logger.error(f"Error initializing neural search: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown events."""
    if os.environ.get("TESTING", "").lower() == "true":
        logger.info("Test mode: skipping startup tasks")
        yield
        return

    logger.info("Starting application...")
    _validate_production_secrets()

    from app.db.migrations import run_migrations

    try:
        run_migrations()
    except Exception as e:
        logger.critical(f"Database migration failed — aborting startup: {e}")
        raise SystemExit(1) from e

    # Seed initial data (admin user, default tags, system prompts)
    try:
        from app.db.base import SessionLocal
        from app.initial_data import init_db

        db = SessionLocal()
        try:
            init_db(db)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Initial data seeding failed (non-fatal): {e}")

    # Check OpenSearch index health (auto-repair corrupted shards from unclean shutdowns)
    try:
        from app.services.opensearch_service import check_and_repair_indices
        from app.services.opensearch_service import ensure_indices_exist
        from app.services.opensearch_service import ensure_v4_index_exists

        ensure_indices_exist()
        ensure_v4_index_exists()
        check_and_repair_indices()
    except Exception as e:
        logger.warning(f"OpenSearch startup health check failed (non-fatal): {e}")

    logger.info("Setting up MinIO and task recovery...")
    minio_task = asyncio.create_task(_setup_minio())
    recovery_task = asyncio.create_task(_run_startup_recovery())
    search_maintenance = asyncio.create_task(_run_search_maintenance())
    thumbnail_migration = asyncio.create_task(_run_thumbnail_migration())
    neural_search_task = asyncio.create_task(_initialize_neural_search())
    embedding_migration = asyncio.create_task(_run_one_time_embedding_normalization())

    yield

    logger.info("Shutting down application...")
    for task in [
        minio_task,
        recovery_task,
        search_maintenance,
        thumbnail_migration,
        neural_search_task,
        embedding_migration,
    ]:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


# Create FastAPI app with lifespan and consistent routing configuration
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Audio transcription and analysis API",
    version=APP_VERSION,
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    docs_url=f"{settings.API_PREFIX}/docs",
    redoc_url=f"{settings.API_PREFIX}/redoc",
    lifespan=lifespan,
    # Disable redirect_slashes to prevent 307 redirects that expose Docker internal hostnames
    # Routes should be defined with "" (not "/") to match paths without trailing slash
    redirect_slashes=False,
    # Increase default timeout to 1 hour for large file uploads
    default_timeout=3600,
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure maximum upload size (50GB)
app.router.default_max_upload_size = 50 * 1024 * 1024 * 1024  # type: ignore[attr-defined]  # 50GB

# Add Audit Middleware for request ID tracking (FedRAMP AU-2/AU-3)
app.add_middleware(AuditMiddleware)

# Include the API router
app.include_router(api_router, prefix=settings.API_PREFIX)

# Set up rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]


# Health check endpoint
@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": APP_VERSION}


# Static files are served by nginx in production, not by FastAPI
# Removed conflicting static file mounting to prevent nginx conflicts

# Run the application if executed directly
if __name__ == "__main__":
    import uvicorn

    # Binding to 0.0.0.0 is required for Docker containers
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)  # noqa: S104 # nosec B104
