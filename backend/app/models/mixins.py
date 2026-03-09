"""Reusable SQLAlchemy model mixins for common column patterns."""

import uuid as _uuid

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import String
from sqlalchemy import func


class UUIDMixin:
    """Mixin that adds a ``uuid`` column with auto-generated UUID4."""

    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(_uuid.uuid4()))


class TimestampMixin:
    """Mixin that adds ``created_at`` and ``updated_at`` columns."""

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
