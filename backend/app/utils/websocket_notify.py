"""Utility for sending WebSocket notifications via Redis pub/sub.

``send_ws_event`` is THE standard function for publishing notifications
from any synchronous code (API endpoints, Celery tasks, services).
The Redis subscriber in ``app.api.websockets`` picks up the message
and forwards it to the user's active WebSocket connections.
"""

import json
import logging

from app.core.redis import get_redis

logger = logging.getLogger(__name__)


def send_ws_event(user_id: int, notification_type: str, data: dict) -> bool:
    """Publish a WebSocket notification to a specific user via Redis pub/sub.

    Args:
        user_id: Internal user ID of the target recipient.
        notification_type: One of the ``NOTIFICATION_TYPE_*`` constants.
        data: Arbitrary payload dict forwarded to the frontend handler.

    Returns:
        True on success, False on failure (errors are logged, never raised).
    """
    try:
        client = get_redis()
        notification = {
            "user_id": user_id,
            "type": notification_type,
            "data": data,
        }
        client.publish("websocket_notifications", json.dumps(notification))
        logger.info(
            "Published WS notification for user %s: %s",
            user_id,
            notification_type,
        )
        return True
    except Exception as e:
        logger.error(
            "Failed to publish WS notification for user %s (%s): %s",
            user_id,
            notification_type,
            e,
        )
        return False
