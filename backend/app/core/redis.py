"""Shared synchronous Redis client singleton.

All synchronous code that needs a Redis connection should import
``get_redis()`` from this module instead of calling
``redis.from_url()`` directly.  The client is lazily created once
per process via ``@lru_cache`` and reused for the lifetime of the
worker / API server.

Out of scope (they use separate Redis databases or async clients):
- ``auth/rate_limit.py`` / ``auth/lockout.py`` (Redis db != 0)
- ``redis_cache_service.py`` (db=1)
- ``video_processing_service.py`` (async)
- ``api/websockets.py`` (async subscriber)
"""

from functools import lru_cache

import redis

from app.core.config import settings


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    """Return a process-wide singleton Redis client (db 0)."""
    return redis.from_url(settings.REDIS_URL)
