"""Authentication configuration database models for super admin UI."""

import uuid as uuid_pkg
from datetime import datetime
from datetime import timezone

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class AuthConfig(Base):
    """Stores authentication configuration settings.

    This table holds all configurable authentication settings for the application,
    including LDAP, Keycloak, PKI, MFA, password policy, and session configurations.
    Sensitive values (like passwords and secrets) are encrypted at rest.
    """

    __tablename__ = "auth_config"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid_pkg.uuid4)
    config_key = Column(String(100), unique=True, nullable=False, index=True)
    config_value = Column(Text, nullable=True)  # Encrypted for sensitive fields
    is_sensitive = Column(Boolean, default=False)
    category = Column(
        String(50), nullable=False, index=True
    )  # ldap, keycloak, pki, local, mfa, password_policy, session
    data_type = Column(String(20), default="string")  # string, int, bool, json
    description = Column(Text, nullable=True)
    requires_restart = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])


class AuthConfigAudit(Base):
    """Audit log for authentication configuration changes.

    Records all changes to authentication configuration settings for
    security compliance and troubleshooting purposes. Sensitive values
    are masked in the audit log.
    """

    __tablename__ = "auth_config_audit"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid_pkg.uuid4)
    config_key = Column(String(100), nullable=False, index=True)
    old_value = Column(Text, nullable=True)  # Masked for sensitive fields
    new_value = Column(Text, nullable=True)  # Masked for sensitive fields
    changed_by = Column(Integer, ForeignKey("user.id"), nullable=False)
    change_type = Column(String(20), nullable=False)  # create, update, delete
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", foreign_keys=[changed_by])
