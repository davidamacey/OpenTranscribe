from fastapi import APIRouter, Request, Response
from fastapi.routing import APIRoute
from .endpoints import auth, files, search, speakers, comments, tags, users, tasks, admin, collections
from . import websockets
import logging

logger = logging.getLogger(__name__)

api_router = APIRouter()

# Custom route class that logs request details 
class LoggingRoute(APIRoute):
    def get_route_handler(self):
        original_route_handler = super().get_route_handler()
        
        async def custom_route_handler(request: Request):
            try:
                logger.debug(f"Processing route: {request.method} {request.url.path}")
                return await original_route_handler(request)
            except Exception as exc:
                logger.error(f"Error processing route {request.url.path}: {exc}")
                raise
        
        return custom_route_handler

# Function to include routers with proper route handling for consistent frontend-backend communication
def include_router_with_consistency(router, prefix, tags=None):
    """Include a router with consistent route handling that works both with and without trailing slashes
    
    This ensures consistent API behavior regardless of whether the frontend sends requests
    with or without trailing slashes, which is important for production with nginx.
    
    Args:
        router: The router to include
        prefix: The prefix for the router (e.g., '/users')
        tags: Tags for the router for API documentation
    """
    if tags is None:
        tags = [prefix.strip('/')]  # Default tag based on prefix
        
    # Ensure prefix starts with / but doesn't end with one
    normalized_prefix = '/' + prefix.strip('/')
    
    # Include the router with the normalized prefix
    api_router.include_router(router, prefix=normalized_prefix, tags=tags)

# Include routers from different endpoints with consistent path handling
include_router_with_consistency(auth.router, prefix="/auth", tags=["auth"])
include_router_with_consistency(files.router, prefix="/files", tags=["files"])
include_router_with_consistency(search.router, prefix="/search", tags=["search"])
include_router_with_consistency(speakers.router, prefix="/speakers", tags=["speakers"])
include_router_with_consistency(comments.router, prefix="/comments", tags=["comments"])
include_router_with_consistency(tags.router, prefix="/tags", tags=["tags"])
include_router_with_consistency(users.router, prefix="/users", tags=["users"])
include_router_with_consistency(tasks.router, prefix="/tasks", tags=["tasks"])
include_router_with_consistency(admin.router, prefix="/admin", tags=["admin"])
include_router_with_consistency(collections.router, prefix="/collections", tags=["collections"])

# Include WebSocket router without prefix since it handles its own paths
api_router.include_router(websockets.router, tags=["websockets"])
