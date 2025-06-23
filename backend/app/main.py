from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os
import logging
import asyncio

from app.api.router import api_router
from app.core.config import settings
from app.middleware.route_fixer import RouteFixerMiddleware

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for startup and shutdown events.
    Handles MinIO bucket creation, task recovery on startup and cleanup on shutdown.
    """
    # Startup
    logger.info("Starting application with MinIO setup and task recovery...")
    
    # Initialize MinIO bucket
    async def setup_minio():
        try:
            from minio import Minio
            from minio.error import S3Error
            import json
            
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
                secure=False
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
                            "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
                        }
                    ]
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
            try:
                await task
            except asyncio.CancelledError:
                pass


# Create FastAPI app with lifespan and consistent routing configuration
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Audio transcription and analysis API",
    version="1.0.0",
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    docs_url=f"{settings.API_PREFIX}/docs",
    redoc_url=f"{settings.API_PREFIX}/redoc",
    lifespan=lifespan,
    # Enable built-in support for routes with or without trailing slashes
    # This ensures consistent behavior regardless of how frontend makes requests
    redirect_slashes=True,
    # Increase default timeout to 1 hour for large file uploads
    default_timeout=3600
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
app.router.default_max_upload_size = 50 * 1024 * 1024 * 1024  # 50GB

# Add Route Fixer Middleware to handle inconsistent frontend/backend API calls
app.add_middleware(
    RouteFixerMiddleware,
    api_prefix=settings.API_PREFIX
)

# Include the API router
app.include_router(api_router, prefix=settings.API_PREFIX)

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
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
