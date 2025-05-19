from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, List, Optional
import json
import logging
from ..core.security import get_token_from_cookie, verify_token
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
