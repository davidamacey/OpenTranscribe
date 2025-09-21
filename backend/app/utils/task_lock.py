"""
Task execution lock utilities for preventing overlapping periodic tasks.

This module provides Redis-based distributed locking to prevent multiple
instances of the same task from running simultaneously.
"""

import logging
from contextlib import contextmanager
from typing import Optional

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class TaskLockError(Exception):
    """Exception raised when task lock operations fail."""


class TaskLockManager:
    """Manages distributed locks for task execution."""

    def __init__(self, redis_url: Optional[str] = None):
        """Initialize the lock manager with Redis connection."""
        self.redis_url = redis_url or settings.CELERY_BROKER_URL
        self._redis_client = None

    @property
    def redis_client(self):
        """Lazy initialization of Redis client."""
        if self._redis_client is None:
            try:
                # Parse Redis URL and create client
                self._redis_client = redis.from_url(self.redis_url, decode_responses=True)
                # Test connection
                self._redis_client.ping()
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                # Fallback to None - will disable locking
                self._redis_client = False
        return self._redis_client if self._redis_client is not False else None

    @contextmanager
    def acquire_lock(self, lock_key: str, timeout: int = 300, blocking_timeout: int = 0):
        """
        Acquire a distributed lock for task execution.

        Args:
            lock_key: Unique identifier for the lock
            timeout: Lock expiration time in seconds
            blocking_timeout: How long to wait for lock acquisition (0 = non-blocking)

        Yields:
            bool: True if lock was acquired, False otherwise

        Raises:
            TaskLockError: If lock operations fail
        """
        if not self.redis_client:
            # If Redis is not available, allow execution without locking
            logger.warning(f"Redis unavailable, executing {lock_key} without lock")
            yield True
            return

        lock = None
        acquired = False

        try:
            # Create lock with expiration
            lock = self.redis_client.lock(
                lock_key, timeout=timeout, blocking_timeout=blocking_timeout
            )

            # Try to acquire lock
            acquired = lock.acquire(blocking=blocking_timeout > 0)

            if acquired:
                logger.info(f"Acquired lock for {lock_key}")
            else:
                logger.info(f"Could not acquire lock for {lock_key} - task may already be running")

            yield acquired

        except redis.RedisError as e:
            logger.error(f"Redis error during lock operation for {lock_key}: {e}")
            # Allow execution without lock on Redis errors
            yield True

        except Exception as e:
            logger.error(f"Unexpected error during lock operation for {lock_key}: {e}")
            raise TaskLockError(f"Lock operation failed: {e}") from e

        finally:
            # Release lock if acquired
            if acquired and lock:
                try:
                    lock.release()
                    logger.info(f"Released lock for {lock_key}")
                except Exception as e:
                    logger.error(f"Error releasing lock for {lock_key}: {e}")

    def is_locked(self, lock_key: str) -> bool:
        """
        Check if a lock is currently held.

        Args:
            lock_key: Lock identifier to check

        Returns:
            bool: True if lock exists, False otherwise
        """
        if not self.redis_client:
            return False

        try:
            return self.redis_client.exists(lock_key) > 0
        except Exception as e:
            logger.error(f"Error checking lock status for {lock_key}: {e}")
            return False

    def force_unlock(self, lock_key: str) -> bool:
        """
        Force release a lock (use with caution).

        Args:
            lock_key: Lock identifier to release

        Returns:
            bool: True if lock was released, False otherwise
        """
        if not self.redis_client:
            return False

        try:
            result = self.redis_client.delete(lock_key)
            if result:
                logger.warning(f"Force released lock for {lock_key}")
            return bool(result)
        except Exception as e:
            logger.error(f"Error force releasing lock for {lock_key}: {e}")
            return False


# Global lock manager instance
task_lock_manager = TaskLockManager()


def with_task_lock(lock_key: str, timeout: int = 300):
    """
    Decorator to ensure only one instance of a task runs at a time.

    Args:
        lock_key: Unique identifier for the lock
        timeout: Lock expiration time in seconds

    Usage:
        @with_task_lock("health_check", timeout=480)
        def my_task():
            # Task code here
            pass
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            with task_lock_manager.acquire_lock(lock_key, timeout=timeout) as acquired:
                if acquired:
                    return func(*args, **kwargs)
                else:
                    logger.info(f"Skipping {func.__name__} - already running")
                    return {
                        "skipped": True,
                        "reason": "Task already running",
                        "function": func.__name__,
                    }

        return wrapper

    return decorator
