"""
SQLAlchemy models for user LLM provider settings
"""
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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class UserLLMSettings(Base):
    """
    Model for storing user-specific LLM provider configurations

    Each user can have multiple LLM provider configurations. The active configuration
    is tracked via the UserSetting table with key 'active_llm_config_id'.
    API keys are stored encrypted for security.
    """

    __tablename__ = "user_llm_settings"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid_pkg.uuid4, index=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # User-friendly name for the configuration

    # Provider configuration
    provider = Column(
        String(50), nullable=False, index=True
    )  # openai, vllm, ollama, claude, custom
    model_name = Column(String(100), nullable=False)
    api_key = Column(Text, nullable=True)  # Encrypted API key
    base_url = Column(String(500), nullable=True)  # Custom endpoint URL

    # Optional settings
    max_tokens = Column(
        Integer, default=8192, nullable=False
    )  # Model's context window in tokens (user-configured)
    temperature = Column(
        String(10), default="0.3", nullable=False
    )  # Store as string to avoid float precision issues

    # Status tracking
    is_active = Column(Boolean, default=True, nullable=False)
    last_tested = Column(DateTime(timezone=True), nullable=True)
    test_status = Column(String(20), nullable=True)  # success, failed, pending
    test_message = Column(Text, nullable=True)  # Error message or success details

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="llm_settings")

    # Table constraints
    __table_args__ = (
        # Ensure unique configuration names per user
        UniqueConstraint("user_id", "name", name="_user_llm_config_name_unique"),
        Index("ix_user_llm_settings_user_provider", "user_id", "provider"),
    )

    @property
    def has_api_key(self) -> bool:
        """Indicates whether an API key is stored (computed property for schema compatibility)"""
        return bool(self.api_key)

    def __repr__(self):
        return f"<UserLLMSettings(user_id={self.user_id}, name={self.name}, provider={self.provider}, model={self.model_name})>"
