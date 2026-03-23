"""SQLAlchemy model for user diarization provider settings."""

from __future__ import annotations

import uuid as uuid_pkg

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class UserDiarizationSettings(Base):
    """User-specific diarization provider configuration. Mirrors UserASRSettings pattern."""

    __tablename__ = "user_diarization_settings"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid_pkg.uuid4, index=True
    )
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)

    provider = Column(String(50), nullable=False)  # e.g., "pyannote"
    model_name = Column(String(100), nullable=False)  # e.g., "precision-2"
    api_key = Column(Text, nullable=True)  # AES-256-GCM encrypted
    base_url = Column(String(500), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    last_tested = Column(DateTime(timezone=True), nullable=True)
    test_status = Column(String(20), nullable=True)
    test_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="diarization_settings")

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="_user_diarization_config_name_unique"),
    )

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    def __repr__(self) -> str:
        return (
            f"<UserDiarizationSettings(user_id={self.user_id}, "
            f"name={self.name!r}, provider={self.provider})>"
        )
