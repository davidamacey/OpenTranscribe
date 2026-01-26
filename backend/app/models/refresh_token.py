"""
RefreshToken model for JWT refresh token management.

Stores refresh token metadata for token revocation and session tracking.
Part of FedRAMP AC-12 compliance for token management.
"""

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class RefreshToken(Base):
    """
    Model for storing refresh token metadata.

    Stores the hash of the refresh token (not the token itself) along with
    expiration and revocation information. This allows for:
    - Token validation without storing the actual token
    - Token revocation by marking tokens as revoked
    - Session management by tracking all user tokens
    - Automatic cleanup of expired tokens

    Attributes:
        id: Primary key
        user_id: Foreign key to user table
        token_hash: SHA-256 hash of the refresh token (64 chars hex)
        jti: JWT ID claim from the token for Redis blacklist lookup
        expires_at: Token expiration timestamp
        revoked_at: Timestamp when token was revoked (null if active)
        created_at: Token creation timestamp
        user_agent: Optional user agent string for session identification
        ip_address: Optional IP address for session identification
    """

    __tablename__ = "refresh_token"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    jti = Column(String(36), unique=True, nullable=False, index=True)  # UUID format
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    user_agent = Column(String(512), nullable=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 max length

    # Relationship to user
    user = relationship("User", back_populates="refresh_tokens")

    @property
    def is_revoked(self) -> bool:
        """Check if the token has been revoked."""
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        """Check if the token has expired."""
        from datetime import datetime
        from datetime import timezone

        return datetime.now(timezone.utc) > self.expires_at  # type: ignore[no-any-return]

    @property
    def is_valid(self) -> bool:
        """Check if the token is valid (not revoked and not expired)."""
        return not self.is_revoked and not self.is_expired
