"""
SQLAlchemy models for user LLM provider settings
"""

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class UserLLMSettings(Base):
    """
    Model for storing user-specific LLM provider configurations
    
    Each user can have their own LLM provider settings that override the system defaults.
    API keys are stored encrypted for security.
    """
    __tablename__ = "user_llm_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Provider configuration
    provider = Column(String(50), nullable=False, index=True)  # openai, vllm, ollama, claude, custom
    model_name = Column(String(100), nullable=False)
    api_key = Column(Text, nullable=True)  # Encrypted API key
    base_url = Column(String(500), nullable=True)  # Custom endpoint URL
    
    # Optional settings
    max_tokens = Column(Integer, default=2000, nullable=False)
    temperature = Column(String(10), default="0.3", nullable=False)  # Store as string to avoid float precision issues
    timeout = Column(Integer, default=60, nullable=False)
    
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

    def __repr__(self):
        return f"<UserLLMSettings(user_id={self.user_id}, provider={self.provider}, model={self.model_name})>"