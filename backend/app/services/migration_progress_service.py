"""
Migration progress tracking service using Redis.

This module provides a Redis-based service for tracking the progress of
long-running migrations like the v3 to v4 speaker embedding migration.
"""

import json
import logging
from datetime import datetime
from typing import TypedDict
from typing import cast

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Redis key prefix for migration tracking
MIGRATION_KEY_PREFIX = "embedding_migration"


class MigrationStatus(TypedDict):
    """Type definition for migration status."""

    running: bool
    total_files: int
    processed_files: int
    failed_files: list[str]  # List of file UUIDs that failed
    started_at: str | None  # ISO timestamp
    completed_at: str | None  # ISO timestamp
    orchestrator_task_id: str | None
    last_updated: str | None  # ISO timestamp


class MigrationProgressService:
    """Service for tracking migration progress in Redis."""

    def __init__(self, redis_url: str | None = None):
        """Initialize the service with Redis connection.

        Args:
            redis_url: Redis connection URL. Defaults to settings.CELERY_BROKER_URL.
        """
        self.redis_url = redis_url or settings.CELERY_BROKER_URL
        self._redis_client: redis.Redis | None = None

    @property
    def redis_client(self) -> redis.Redis | None:
        """Lazy initialization of Redis client."""
        if self._redis_client is None:
            try:
                self._redis_client = redis.from_url(self.redis_url, decode_responses=True)
                self._redis_client.ping()
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self._redis_client = None
        return self._redis_client

    def _get_key(self, suffix: str) -> str:
        """Get the full Redis key with prefix.

        Args:
            suffix: Key suffix to append.

        Returns:
            Full Redis key.
        """
        return f"{MIGRATION_KEY_PREFIX}:{suffix}"

    def get_status(self) -> MigrationStatus:
        """Get the current migration status.

        Returns:
            MigrationStatus dict with current progress information.
        """
        default_status: MigrationStatus = {
            "running": False,
            "total_files": 0,
            "processed_files": 0,
            "failed_files": [],
            "started_at": None,
            "completed_at": None,
            "orchestrator_task_id": None,
            "last_updated": None,
        }

        if not self.redis_client:
            return default_status

        try:
            status_key = self._get_key("status")
            status_json = self.redis_client.get(status_key)

            if status_json:
                return cast(MigrationStatus, json.loads(status_json))
            return default_status

        except Exception as e:
            logger.error(f"Error getting migration status from Redis: {e}")
            return default_status

    def is_running(self) -> bool:
        """Check if a migration is currently running.

        Returns:
            True if a migration is in progress.
        """
        status = self.get_status()
        return status.get("running", False)

    def start_migration(self, total_files: int, task_id: str | None = None) -> bool:
        """Mark a migration as started.

        Args:
            total_files: Total number of files to migrate.
            task_id: Celery task ID of the orchestrator task.

        Returns:
            True if migration was started successfully.
        """
        if not self.redis_client:
            logger.warning("Redis not available, cannot track migration progress")
            return False

        try:
            status: MigrationStatus = {
                "running": True,
                "total_files": total_files,
                "processed_files": 0,
                "failed_files": [],
                "started_at": datetime.utcnow().isoformat(),
                "completed_at": None,
                "orchestrator_task_id": task_id,
                "last_updated": datetime.utcnow().isoformat(),
            }

            status_key = self._get_key("status")
            # Set with 24-hour TTL as a safety measure
            self.redis_client.set(status_key, json.dumps(status), ex=86400)
            logger.info(f"Started migration tracking: {total_files} files")
            return True

        except Exception as e:
            logger.error(f"Error starting migration tracking: {e}")
            return False

    def increment_processed(self, success: bool = True, file_uuid: str | None = None) -> bool:
        """Increment the processed file count.

        Args:
            success: Whether the file was processed successfully.
            file_uuid: UUID of the file (required if success=False).

        Returns:
            True if the increment was successful.
        """
        if not self.redis_client:
            return False

        try:
            status = self.get_status()

            status["processed_files"] = status.get("processed_files", 0) + 1
            status["last_updated"] = datetime.utcnow().isoformat()

            if not success and file_uuid:
                failed_files = status.get("failed_files", [])
                if file_uuid not in failed_files:
                    failed_files.append(file_uuid)
                status["failed_files"] = failed_files

            status_key = self._get_key("status")
            self.redis_client.set(status_key, json.dumps(status), ex=86400)
            return True

        except Exception as e:
            logger.error(f"Error incrementing processed count: {e}")
            return False

    def complete_migration(self, success: bool = True) -> bool:
        """Mark the migration as complete.

        Args:
            success: Whether the migration completed successfully.

        Returns:
            True if the completion was recorded successfully.
        """
        if not self.redis_client:
            return False

        try:
            status = self.get_status()
            status["running"] = False
            status["completed_at"] = datetime.utcnow().isoformat()
            status["last_updated"] = datetime.utcnow().isoformat()

            status_key = self._get_key("status")
            # Keep completed status for 7 days for review
            self.redis_client.set(status_key, json.dumps(status), ex=604800)

            processed = status.get("processed_files", 0)
            total = status.get("total_files", 0)
            failed = len(status.get("failed_files", []))
            logger.info(f"Migration completed: {processed}/{total} processed, {failed} failed")
            return True

        except Exception as e:
            logger.error(f"Error completing migration: {e}")
            return False

    def clear_status(self) -> bool:
        """Clear the migration status from Redis.

        Returns:
            True if the status was cleared successfully.
        """
        if not self.redis_client:
            return False

        try:
            status_key = self._get_key("status")
            self.redis_client.delete(status_key)
            logger.info("Migration status cleared")
            return True

        except Exception as e:
            logger.error(f"Error clearing migration status: {e}")
            return False

    def force_stop(self) -> bool:
        """Force stop a running migration by marking it as not running.

        This does not actually stop running Celery tasks, but prevents
        new tasks from being dispatched and marks the migration as stopped.

        Returns:
            True if the status was updated successfully.
        """
        if not self.redis_client:
            return False

        try:
            status = self.get_status()
            if not status.get("running"):
                logger.warning("No migration running to stop")
                return False

            status["running"] = False
            status["completed_at"] = datetime.utcnow().isoformat()
            status["last_updated"] = datetime.utcnow().isoformat()

            status_key = self._get_key("status")
            self.redis_client.set(status_key, json.dumps(status), ex=604800)
            logger.warning("Migration force stopped")
            return True

        except Exception as e:
            logger.error(f"Error force stopping migration: {e}")
            return False


# Global instance for easy access
migration_progress = MigrationProgressService()
