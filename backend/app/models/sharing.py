"""SQLAlchemy model for collection sharing."""

import uuid as uuid_pkg

from sqlalchemy import CheckConstraint
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class CollectionShare(Base):
    """Sharing grant on a collection for a user or group."""

    __tablename__ = "collection_share"

    id = Column(Integer, primary_key=True)
    uuid = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid_pkg.uuid4, index=True
    )
    collection_id = Column(
        Integer, ForeignKey("collection.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shared_by_id = Column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_type = Column(String(20), nullable=False)  # "user" or "group"
    target_user_id = Column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=True, index=True
    )
    target_group_id = Column(
        Integer, ForeignKey("user_group.id", ondelete="CASCADE"), nullable=True, index=True
    )
    permission = Column(String(20), nullable=False, default="viewer")  # "viewer" or "editor"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "(target_user_id IS NOT NULL AND target_group_id IS NULL) OR "
            "(target_user_id IS NULL AND target_group_id IS NOT NULL)",
            name="_collection_share_target_check",
        ),
        Index(
            "_collection_share_user_uc",
            "collection_id",
            "target_user_id",
            unique=True,
            postgresql_where=text("target_user_id IS NOT NULL"),
        ),
        Index(
            "_collection_share_group_uc",
            "collection_id",
            "target_group_id",
            unique=True,
            postgresql_where=text("target_group_id IS NOT NULL"),
        ),
    )

    # Relationships
    collection = relationship("Collection", back_populates="shares")
    shared_by = relationship("User", foreign_keys=[shared_by_id], back_populates="shared_by_me")
    target_user = relationship(
        "User", foreign_keys=[target_user_id], back_populates="shared_with_me"
    )
    target_group = relationship("UserGroup", back_populates="collection_shares")
