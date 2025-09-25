from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base

# Import models at module level to avoid circular imports


class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    role = Column(String, default="user", nullable=False)  # "user" or "admin"
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    media_files = relationship("MediaFile", back_populates="user")
    comments = relationship("Comment", back_populates="user")
    speakers = relationship("Speaker", back_populates="user")
    speaker_profiles = relationship("SpeakerProfile", back_populates="user")
    speaker_collections = relationship("SpeakerCollection", back_populates="user")
    collections = relationship("Collection", back_populates="user")
    summary_prompts = relationship("SummaryPrompt", back_populates="user")
    settings = relationship("UserSetting", back_populates="user")
    llm_settings = relationship("UserLLMSettings", back_populates="user")
