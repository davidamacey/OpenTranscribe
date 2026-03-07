"""Unified progress tracking service with ETA calculation.

Provides Redis-backed progress tracking for long-running tasks
(reindex, migration, clustering, auto-label) with EWMA-based ETA
estimation and rate-limited Redis writes.
"""

import json
import logging
import time
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from functools import lru_cache

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Redis key pattern: task_progress:{task_type}:{user_id}
_KEY_PREFIX = "task_progress"
_TTL_ACTIVE = 86400  # 24h while running
_TTL_COMPLETED = 3600  # 1h after completion

# Rate limiting: max 1 Redis write per this many seconds (except first/last)
_MIN_WRITE_INTERVAL = 0.5

# EWMA smoothing factor for rate estimation
_EWMA_ALPHA = 0.3

# Suppress ETA until this many updates have occurred
_MIN_UPDATES_FOR_ETA = 3


@lru_cache(maxsize=1)
def _get_redis() -> redis.Redis:
    """Lazy Redis connection (same pattern as reindex_task.py)."""
    return redis.from_url(settings.REDIS_URL)


@dataclass
class ProgressState:
    """Serializable progress state stored in Redis."""

    task_type: str
    user_id: int
    total: int
    processed: int = 0
    status: str = "running"  # running | completed | failed
    message: str = "Starting..."
    eta_seconds: float | None = None
    failed_items: list[str] = field(default_factory=list)
    started_at: float = 0.0  # time.time()
    updated_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProgressState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ProgressTracker:
    """Track progress of a long-running task with ETA calculation.

    Uses EWMA (Exponentially Weighted Moving Average) for rate smoothing
    to avoid jumpy ETAs. Rate-limits Redis writes to avoid flooding.
    """

    def __init__(self, task_type: str, user_id: int, total: int):
        self.task_type = task_type
        self.user_id = user_id
        self.total = total

        self._update_count = 0
        self._ewma_rate: float | None = None  # items/sec
        self._last_update_time: float = 0.0
        self._last_write_time: float = 0.0
        self._last_processed: int = 0

    @property
    def _key(self) -> str:
        return f"{_KEY_PREFIX}:{self.task_type}:{self.user_id}"

    def start(self, message: str = "Starting...") -> None:
        """Mark task as started and write initial state to Redis."""
        now = time.time()
        self._last_update_time = now
        state = ProgressState(
            task_type=self.task_type,
            user_id=self.user_id,
            total=self.total,
            processed=0,
            status="running",
            message=message,
            started_at=now,
            updated_at=now,
        )
        self._write_state(state, force=True)

    def update(
        self,
        processed: int,
        message: str = "",
        failed_item: str | None = None,
    ) -> ProgressState | None:
        """Update progress and compute ETA.

        Returns ProgressState if a Redis write occurred (rate-limited),
        None if the update was throttled.
        """
        now = time.time()
        self._update_count += 1

        # Update EWMA rate
        elapsed = now - self._last_update_time
        if elapsed > 0 and processed > self._last_processed:
            items_delta = processed - self._last_processed
            instant_rate = items_delta / elapsed
            if self._ewma_rate is None:
                self._ewma_rate = instant_rate
            else:
                self._ewma_rate = _EWMA_ALPHA * instant_rate + (1 - _EWMA_ALPHA) * self._ewma_rate

        self._last_update_time = now
        self._last_processed = processed

        # Compute ETA
        eta: float | None = None
        remaining = self.total - processed
        if (
            self._update_count >= _MIN_UPDATES_FOR_ETA
            and self._ewma_rate
            and self._ewma_rate > 0
            and remaining > 0
        ):
            eta = remaining / self._ewma_rate

        # Rate-limit Redis writes (except first update and final)
        is_final = processed >= self.total
        is_first = self._update_count <= 1
        time_since_write = now - self._last_write_time

        if not is_first and not is_final and time_since_write < _MIN_WRITE_INTERVAL:
            return None

        state = ProgressState(
            task_type=self.task_type,
            user_id=self.user_id,
            total=self.total,
            processed=processed,
            status="running",
            message=message or f"Processing {processed}/{self.total}",
            eta_seconds=round(eta, 1) if eta is not None else None,
            started_at=self._last_update_time,
            updated_at=now,
        )

        if failed_item:
            # Read existing failed items from Redis to accumulate
            existing = self.get_state(self.task_type, self.user_id)
            if existing:
                state.failed_items = existing.failed_items
            if failed_item not in state.failed_items:
                state.failed_items.append(failed_item)

        self._write_state(state)
        return state

    def complete(self, message: str = "Complete") -> None:
        """Mark task as completed."""
        state = ProgressState(
            task_type=self.task_type,
            user_id=self.user_id,
            total=self.total,
            processed=self.total,
            status="completed",
            message=message,
            eta_seconds=None,
            updated_at=time.time(),
        )
        self._write_state(state, force=True, ttl=_TTL_COMPLETED)

    def fail(self, message: str = "Failed") -> None:
        """Mark task as failed."""
        existing = self.get_state(self.task_type, self.user_id)
        state = ProgressState(
            task_type=self.task_type,
            user_id=self.user_id,
            total=self.total,
            processed=existing.processed if existing else 0,
            status="failed",
            message=message,
            eta_seconds=None,
            failed_items=existing.failed_items if existing else [],
            updated_at=time.time(),
        )
        self._write_state(state, force=True, ttl=_TTL_COMPLETED)

    def _write_state(
        self,
        state: ProgressState,
        force: bool = False,
        ttl: int = _TTL_ACTIVE,
    ) -> None:
        """Write state to Redis with optional force (bypass rate limit)."""
        try:
            r = _get_redis()
            r.set(self._key, json.dumps(state.to_dict()), ex=ttl)
            self._last_write_time = time.time()
        except Exception as e:
            logger.debug(f"Failed to write progress state: {e}")

    @classmethod
    def get_state(cls, task_type: str, user_id: int) -> ProgressState | None:
        """Read current state from Redis."""
        try:
            r = _get_redis()
            raw = r.get(f"{_KEY_PREFIX}:{task_type}:{user_id}")
            if raw:
                return ProgressState.from_dict(json.loads(raw))
        except Exception as e:
            logger.debug(f"Failed to read progress state: {e}")
        return None

    @classmethod
    def get_active_tasks(cls, user_id: int) -> list[dict]:
        """Get all active (running) tasks for a user.

        Scans Redis for task_progress:*:{user_id} keys.
        """
        results: list[dict] = []
        try:
            r = _get_redis()
            pattern = f"{_KEY_PREFIX}:*:{user_id}"
            for key in r.scan_iter(match=pattern, count=100):
                raw = r.get(key)
                if raw:
                    state = ProgressState.from_dict(json.loads(raw))
                    if state.status == "running":
                        results.append(state.to_dict())
        except Exception as e:
            logger.debug(f"Failed to scan active tasks: {e}")
        return results


def emit_progress_notification(
    tracker: ProgressTracker,
    processed: int,
    user_id: int,
    notification_type: str,
    extra_data: dict | None = None,
    message: str = "",
    failed_item: str | None = None,
) -> None:
    """Update tracker + publish WebSocket notification in one call.

    Respects tracker rate limiting — if the tracker throttles
    the update, no notification is published either.
    """
    state = tracker.update(processed, message=message, failed_item=failed_item)
    if state is None:
        return  # Throttled

    try:
        r = _get_redis()
        data: dict = {
            "progress": round(processed / tracker.total, 4) if tracker.total > 0 else 0,
            "message": state.message,
            "eta_seconds": state.eta_seconds,
            **(extra_data or {}),
        }
        notification = {
            "user_id": user_id,
            "type": notification_type,
            "data": data,
        }
        r.publish("websocket_notifications", json.dumps(notification))
    except Exception as e:
        logger.debug(f"Failed to emit progress notification: {e}")
