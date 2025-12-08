"""
System Settings SQLAlchemy model.

Provides a key-value store for system-wide configuration settings.
"""

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy.sql import func

from app.db.base import Base


class SystemSettings(Base):
    """
    System-wide key-value settings storage.

    Used for global configuration that applies to all users,
    such as transcription retry limits and garbage cleanup thresholds.
    """

    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    updated_at = Column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=True
    )

    def __repr__(self) -> str:
        return f"<SystemSettings(key='{self.key}', value='{self.value}')>"
