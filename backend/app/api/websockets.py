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
) -> Optional[User]:
    try:
        # Get token from cookie or query param
        token = None
        if "token" in websocket.query_params:
            token = websocket.query_params["token"]
        else:
            cookies = websocket.headers.get("cookie", "")
            token = get_token_from_cookie(cookies)
        
        if not token:
            return None
        
        # Verify token and get user
        payload = verify_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
        
        # Get user from database
        user = db.query(User).filter(User.id == user_id).first()
        return user
    except Exception as e:
        logger.error(f"WebSocket authentication error: {str(e)}")
        return None


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    db: Session = Depends(get_db)
):
    # Initialize Redis subscriber if not already running
    await setup_redis()
    
    # Authenticate the connection
    user = await get_user_from_websocket(websocket, db)
    
    if not user:
        await websocket.close(code=1008, reason="Authentication failed")
        return
    
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
    except WebSocketDisconnect:
        manager.disconnect(websocket, user.id)
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        manager.disconnect(websocket, user.id)


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
