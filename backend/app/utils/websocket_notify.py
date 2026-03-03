"""Utility for sending WebSocket notifications from synchronous API endpoints via Redis pub/sub."""

import json
import logging

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Module-level connection pool (reused across all calls)
_redis_pool: redis.ConnectionPool | None = None


def _get_redis_client() -> redis.Redis:
    """Return a Redis client backed by a shared connection pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool.from_url(settings.REDIS_URL)
    return redis.Redis(connection_pool=_redis_pool)


def send_ws_event(user_id: int, notification_type: str, data: dict) -> bool:
    """Publish a WebSocket notification to a specific user via Redis pub/sub.

    This is intended for use in synchronous FastAPI endpoints (not Celery tasks).
    The Redis subscriber in ``app.api.websockets`` picks up the message and
    forwards it to the user's active WebSocket connections.

    Args:
        user_id: Internal user ID of the target recipient.
        notification_type: One of the ``NOTIFICATION_TYPE_*`` constants.
        data: Arbitrary payload dict forwarded to the frontend handler.

    Returns:
        True on success, False on failure (errors are logged, never raised).
    """
    try:
        client = _get_redis_client()
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
