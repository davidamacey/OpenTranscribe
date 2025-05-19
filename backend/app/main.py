from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import logging

from app.api.router import api_router
from app.core.config import settings
from app.middleware.route_fixer import RouteFixerMiddleware

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app with consistent routing configuration
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Audio transcription and analysis API",
    version="1.0.0",
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    docs_url=f"{settings.API_PREFIX}/docs",
    redoc_url=f"{settings.API_PREFIX}/redoc",
    # Enable built-in support for routes with or without trailing slashes
    # This ensures consistent behavior regardless of how frontend makes requests
    redirect_slashes=True
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# Mount static files (for production deployment)
if os.path.exists("../frontend/dist") and settings.ENVIRONMENT != "development":
    app.mount("/", StaticFiles(directory="../frontend/dist", html=True), name="static")

# Run the application if executed directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
