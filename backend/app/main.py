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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for startup and shutdown events.
    Handles database migrations, MinIO bucket creation, and task recovery.
    """
    # Startup
    logger.info("Starting application...")

    # Validate production secrets (Phase 7 code quality fix)
    _validate_production_secrets()

    # Run database migrations
    try:
        from app.db.migrations import run_migrations

        run_migrations()
    except Exception as e:
        logger.error(f"Migration error: {e}")
        # Continue startup - migrations might already be applied

    logger.info("Setting up MinIO and task recovery...")

    # Initialize MinIO bucket
    async def setup_minio():
        try:
            import json

            from minio import Minio

            # Get MinIO configuration from environment
            minio_host = os.getenv("MINIO_HOST", "minio")
            minio_port = os.getenv("MINIO_PORT", "9000")
            minio_user = os.getenv("MINIO_ROOT_USER", "minioadmin")
            minio_password = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
            bucket_name = os.getenv("MEDIA_BUCKET_NAME", "opentranscribe")

            # Initialize MinIO client
            client = Minio(
                f"{minio_host}:{minio_port}",
                access_key=minio_user,
                secret_key=minio_password,
                secure=False,
            )

            # Check if bucket exists, if not create it
            if not client.bucket_exists(bucket_name):
                client.make_bucket(bucket_name)
                logger.info(f"MinIO bucket '{bucket_name}' created successfully")

                # Set public read policy for the bucket
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"AWS": "*"},
                            "Action": ["s3:GetObject"],
                            "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
                        }
                    ],
                }

                client.set_bucket_policy(bucket_name, json.dumps(policy))
                logger.info(f"Public read policy set for bucket '{bucket_name}'")
            else:
                logger.info(f"MinIO bucket '{bucket_name}' already exists")

        except Exception as e:
            logger.error(f"Error setting up MinIO bucket: {e}")

    # Schedule startup recovery task
    async def run_startup_recovery():
        try:
            # Wait a bit for the app to fully start up
            await asyncio.sleep(10)

            # Import and run the startup recovery task
            from app.tasks.recovery import startup_recovery_task

            result = startup_recovery_task.delay()
            logger.info(f"Startup recovery task scheduled: {result.id}")
        except Exception as e:
            logger.error(f"Error scheduling startup recovery: {e}")

    # Run MinIO setup and recovery in background
    minio_task = asyncio.create_task(setup_minio())
    recovery_task = asyncio.create_task(run_startup_recovery())

    yield

    # Shutdown
    logger.info("Shutting down application...")
    # Cancel both tasks if they're still running
    for task in [minio_task, recovery_task]:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


# Create FastAPI app with lifespan and consistent routing configuration
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Audio transcription and analysis API",
    version="1.0.0",
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
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


# Health check endpoint
@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


# Static files are served by nginx in production, not by FastAPI
# Removed conflicting static file mounting to prevent nginx conflicts

# Run the application if executed directly
if __name__ == "__main__":
    import uvicorn

    # Binding to 0.0.0.0 is required for Docker containers
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)  # noqa: S104 # nosec B104
