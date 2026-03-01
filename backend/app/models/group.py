"""SQLAlchemy models for user groups and group membership."""

import uuid as uuid_pkg

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


class UserGroup(Base):
    """User-created group for sharing collections."""

    __tablename__ = "user_group"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid_pkg.uuid4, index=True
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("owner_id", "name", name="_user_group_owner_name_uc"),)

    # Relationships
    owner = relationship("User", back_populates="owned_groups")
    members = relationship("UserGroupMember", back_populates="group", cascade="all, delete-orphan")
    collection_shares = relationship(
        "CollectionShare",
        back_populates="target_group",
        foreign_keys="CollectionShare.target_group_id",
        cascade="all, delete-orphan",
    )


class UserGroupMember(Base):
    """Membership record linking users to groups with roles."""

    __tablename__ = "user_group_member"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid_pkg.uuid4, index=True
    )
    group_id = Column(Integer, ForeignKey("user_group.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False, default="member")  # "owner", "admin", "member"
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("group_id", "user_id", name="_group_member_uc"),)

    # Relationships
    group = relationship("UserGroup", back_populates="members")
    user = relationship("User", back_populates="group_memberships")
