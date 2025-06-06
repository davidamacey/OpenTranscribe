from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, List, Optional
import json
import logging
import asyncio
import redis.asyncio as redis
from ..core.security import get_token_from_cookie, verify_token
from ..core.config import settings
from ..db.base import get_db
from sqlalchemy.orm import Session
from ..models.user import User

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

# Connection manager to handle WebSocket connections
class ConnectionManager:
    def __init__(self):
        # user_id -> List[WebSocket]
        self.active_connections: Dict[int, List[WebSocket]] = {}
        
    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"User {user_id} connected. Total connections: {len(self.active_connections)}")
        
    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
            logger.info(f"User {user_id} disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_personal_message(self, user_id: int, message: dict):
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_text(json.dumps(message))
                except Exception as e:
                    logger.error(f"Error sending message to user {user_id}: {str(e)}")
    
    async def broadcast(self, message: dict):
        for user_id in self.active_connections:
            await self.send_personal_message(user_id, message)


# Create connection manager instance
manager = ConnectionManager()

# Redis client for pub/sub
redis_client = None

async def setup_redis():
    """Initialize Redis connection for pub/sub notifications."""
    global redis_client
    if not redis_client:
        redis_client = redis.from_url(settings.REDIS_URL)
        # Start Redis subscriber in background
        asyncio.create_task(redis_subscriber())

async def redis_subscriber():
    """Subscribe to Redis notifications and forward to WebSocket connections."""
    try:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe("websocket_notifications")
        
        logger.info("Started Redis subscriber for WebSocket notifications")
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    notification_data = json.loads(message["data"])
                    user_id = notification_data.get("user_id")
                    notification_type = notification_data.get("type")
                    data = notification_data.get("data", {})
                    
                    if user_id and notification_type:
                        await manager.send_personal_message(user_id, {
                            "type": notification_type,
                            "data": data
                        })
                        logger.info(f"Forwarded notification to user {user_id}: {notification_type}")
                    else:
                        logger.warning(f"Invalid notification data: {notification_data}")
                except Exception as e:
                    logger.error(f"Error processing Redis notification: {e}")
    except Exception as e:
        logger.error(f"Redis subscriber error: {e}")

# Function to publish notification to Redis (for use from other processes)
async def publish_notification(user_id: int, notification_type: str, data: dict):
    """Publish notification via Redis pub/sub."""
    if not redis_client:
        await setup_redis()
    
    notification = {
        "user_id": user_id,
        "type": notification_type,
        "data": data
    }
    
    try:
        await redis_client.publish("websocket_notifications", json.dumps(notification))
        logger.info(f"Published notification to Redis for user {user_id}: {notification_type}")
    except Exception as e:
        logger.error(f"Failed to publish notification to Redis: {e}")


# Authenticate WebSocket connection
async def get_user_from_websocket(
    websocket: WebSocket,
    db: Session = Depends(get_db)
):
    """Authenticate a WebSocket connection using JWT token.
    
    Extracts token from query params or cookies and verifies it.
    
    Args:
        websocket: The WebSocket connection
        db: Database session
        
    Returns:
        User object if authenticated, None otherwise
    """
    logger.info(f"Authenticating WebSocket connection from {websocket.client.host}")
    
    try:
        # Try to get token from query parameters
        token = None
        query_string = websocket.scope.get('query_string', b'').decode()
        logger.info(f"WebSocket query string: {query_string}")
        
        if query_string:
            # Parse query parameters
            import urllib.parse
            params = {k: v[0] for k, v in urllib.parse.parse_qs(query_string).items()}
            token = params.get('token')
            if token:
                logger.info(f"Found token in query parameters, token length: {len(token)}")
                # Log first and last few characters of the token for debugging
                if len(token) > 20:
                    logger.info(f"Token prefix: {token[:10]}..., suffix: ...{token[-10:]}")
            else:
                logger.error(f"No token found in query parameters: {params}")
        
        # If no token in query parameters, try cookies
        if not token:
            # Extract token from cookies
            header_cookie = websocket.headers.get('cookie', '')
            if header_cookie:
                logger.info(f"Found cookies: {header_cookie}")
                token = get_token_from_cookie(header_cookie)
                if token:
                    logger.info(f"Found token in cookies")
                else:
                    logger.error(f"No token found in cookies")
            else:
                logger.error("No cookies found in request")
        
        if not token:
            logger.error("No authentication token found in either query params or cookies")
            return None
        
        # Check if JWT_SECRET_KEY is set
        logger.info(f"Using JWT_SECRET_KEY from settings: {'set' if settings.JWT_SECRET_KEY else 'NOT SET'}")
        
        # Verify token
        try:
            payload = verify_token(token)
            logger.info(f"Token verified successfully, payload: {payload}")
            
            user_id = payload.get("sub")
            if not user_id:
                logger.error("No user_id (sub) found in token payload")
                return None
            
            # Log the user_id we're looking up
            logger.info(f"Looking up user with ID: {user_id}")
            
            # Get user from database
            try:
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    logger.info(f"Authenticated WebSocket for user {user.id} ({user.email})")
                    return user
                else:
                    logger.error(f"User with ID {user_id} not found in database")
                    return None
            except Exception as db_error:
                logger.error(f"Database error looking up user {user_id}: {str(db_error)}")
                return None
        except Exception as token_error:
            logger.error(f"Token verification error: {str(token_error)}")
            # Log the exact exception type for better debugging
            logger.error(f"Token verification error type: {type(token_error)}")
            return None
    except Exception as e:
        logger.error(f"WebSocket authentication error: {str(e)}")
        logger.error(f"WebSocket authentication error type: {type(e)}")
        return None


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    db: Session = Depends(get_db)
):
    try:
        # Add CORS headers before connection is established
        origin = websocket.headers.get("origin", "*")
        logger.info(f"WebSocket connection attempt from origin: {origin}")
        
        # Check JWT_SECRET_KEY for debugging
        from app.core.config import settings
        jwt_secret = settings.JWT_SECRET_KEY
        jwt_masked = jwt_secret[:5] + "..." + jwt_secret[-5:] if len(jwt_secret) > 10 else "***"
        logger.info(f"Using JWT_SECRET_KEY: {jwt_masked}")
        
        # Initialize Redis subscriber if not already running
        await setup_redis()
        
        # Extract token directly for debugging
        query_string = websocket.scope.get('query_string', b'').decode()
        import urllib.parse
        params = {k: v[0] for k, v in urllib.parse.parse_qs(query_string).items()} if query_string else {}
        token = params.get('token', 'None')
        token_preview = token[:10] + "..." + token[-10:] if token and len(token) > 20 else token
        logger.info(f"Received token: {token_preview}")
        
        # Verify token directly
        from ..core.security import verify_token
        try:
            if token:
                payload = verify_token(token)
                logger.info(f"Manual token verification: SUCCESS - payload: {payload}")
            else:
                logger.error("Manual token verification: FAILED - no token")
        except Exception as e:
            logger.error(f"Manual token verification: FAILED - {str(e)}")
        
        # Authenticate the connection
        user = await get_user_from_websocket(websocket, db)
        
        if not user:
            logger.error("WebSocket authentication failed - closing connection")
            await websocket.close(code=1008, reason="Authentication failed")
            return
        
        logger.info(f"WebSocket connection accepted for user {user.id}")
        
        # Accept the connection
        await manager.connect(websocket, user.id)
        
        # Send initial connection status
        await websocket.send_text(json.dumps({
            "type": "connection_established",
            "message": "Connected to WebSocket server"
        }))
        
        try:
            while True:
                # Wait for messages (we don't process client messages currently)
                # but keep the connection alive
                data = await websocket.receive_text()
                # Echo back for debugging/heartbeat
                await websocket.send_text(json.dumps({
                    "type": "echo",
                    "data": data
                }))
        except WebSocketDisconnect as disconnect_error:
            logger.info(f"WebSocket disconnected for user {user.id}: {disconnect_error}")
            manager.disconnect(websocket, user.id)
        except Exception as e:
            logger.error(f"WebSocket error for user {user.id}: {str(e)}")
            manager.disconnect(websocket, user.id)
    except Exception as outer_error:
        logger.error(f"Fatal WebSocket error: {str(outer_error)}")
        try:
            await websocket.close(code=1011, reason="Server error")
        except:
            pass


# Function to send notification to a user
async def send_notification(user_id: int, notification_type: str, data: dict):
    message = {
        "type": notification_type,
        "data": data
    }
    await manager.send_personal_message(user_id, message)


# Function to broadcast a notification to all connected users
async def broadcast_notification(notification_type: str, data: dict):
    message = {
        "type": notification_type,
        "data": data
    }
    await manager.broadcast(message)
