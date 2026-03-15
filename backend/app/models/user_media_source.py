"""SQLAlchemy model for user media source settings."""

import uuid as uuid_pkg

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class UserMediaSource(Base):
    """User-specific media source configuration for authenticated downloads."""

    __tablename__ = "user_media_source"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid_pkg.uuid4, index=True
    )
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    hostname = Column(String(255), nullable=False)
    provider_type = Column(String(50), nullable=False, default="mediacms")
    username = Column(Text, nullable=True)
    password = Column(Text, nullable=True)  # AES-256-GCM encrypted
    verify_ssl = Column(Boolean, default=True, nullable=False)
    label = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Sharing
    is_shared = Column(Boolean, default=False, nullable=False)
    shared_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="media_sources")

    __table_args__ = (
        UniqueConstraint("user_id", "hostname", name="_user_media_source_host_unique"),
        Index(
            "ix_user_media_source_shared",
            "is_shared",
            postgresql_where=text("is_shared = TRUE"),
        ),
    )

    @property
    def has_credentials(self) -> bool:
        return bool(self.username and self.password)

    def __repr__(self) -> str:
        return (
            f"<UserMediaSource(user_id={self.user_id}, hostname={self.hostname!r}, "
            f"provider={self.provider_type})>"
        )
