"""
Redis-based migration lock service.

Gates transcription tasks during speaker embedding migration so the GPU
is fully available for re-extraction. The lock uses a Redis key with
SET NX semantics (atomic, prevents double-acquire) and a 4-hour TTL
as a safety net — if the backend crashes mid-migration, the lock
auto-expires and transcription resumes.
"""

import logging

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_LOCK_KEY = "embedding_migration:lock"
_LOCK_TTL_SECONDS = 4 * 60 * 60  # 4 hours


class MigrationLockService:
    """Redis-based lock that pauses transcription during migration."""

    def __init__(self, redis_url: str | None = None):
        self._redis_url = redis_url or settings.CELERY_BROKER_URL
        self._client: redis.Redis | None = None

    @property
    def _redis(self) -> redis.Redis | None:
        if self._client is None:
            try:
                self._client = redis.from_url(self._redis_url, decode_responses=True)
                self._client.ping()
            except Exception as e:
                logger.error(f"Migration lock: Redis unavailable: {e}")
                self._client = None
        return self._client

    def activate(self) -> bool:
        """Acquire the migration lock (SET NX — fails if already held).

        Returns:
            True if lock was acquired, False if already held or Redis unavailable.
        """
        client = self._redis
        if not client:
            return False

        acquired = client.set(_LOCK_KEY, "1", nx=True, ex=_LOCK_TTL_SECONDS)
        if acquired:
            logger.info("Migration lock acquired (TTL=%ds)", _LOCK_TTL_SECONDS)
        else:
            logger.warning("Migration lock already held — cannot acquire")
        return bool(acquired)

    def deactivate(self) -> bool:
        """Release the migration lock.

        Returns:
            True if the key was deleted, False otherwise.
        """
        client = self._redis
        if not client:
            return False

        deleted = client.delete(_LOCK_KEY)
        if deleted:
            logger.info("Migration lock released")
        return bool(deleted)

    def is_active(self) -> bool:
        """Check whether the migration lock is currently held."""
        client = self._redis
        if not client:
            return False
        return bool(client.exists(_LOCK_KEY))

    def refresh_ttl(self, ttl: int | None = None) -> bool:
        """Reset the lock TTL (call periodically during long migrations).

        Args:
            ttl: TTL in seconds. Defaults to the standard 4-hour TTL.

        Returns:
            True if the TTL was refreshed, False if key missing or error.
        """
        client = self._redis
        if not client:
            return False

        result = client.expire(_LOCK_KEY, ttl or _LOCK_TTL_SECONDS)
        return bool(result)


# Singleton instance
migration_lock = MigrationLockService()
