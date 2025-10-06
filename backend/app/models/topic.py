"""
SQLAlchemy models for AI-powered tag and collection suggestions

Simplified model for LLM-powered tag and collection suggestions from transcripts (Issue #79).
"""

import uuid as uuid_pkg

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class TopicSuggestion(Base):
    """
    AI-generated tag and collection suggestions for a media file

    Stores LLM-suggested tags and collections for user review and approval.
    Suggestions are stored as JSONB arrays for simplicity.

    Attributes:
        id: Primary key (internal use only)
        uuid: Public identifier for API exposure
        media_file_id: Reference to the media file
        user_id: Reference to the user
        suggested_tags: JSONB array of tag suggestions [{name, confidence, rationale}, ...]
        suggested_collections: JSONB array of collection suggestions [{name, confidence, rationale}, ...]
        status: User interaction status (pending, reviewed, accepted, rejected)
        user_decisions: JSONB tracking user's accepts {accepted_collections: [], accepted_tags: []}
    """

    __tablename__ = "topic_suggestion"

    # Primary keys and identifiers
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid_pkg.uuid4, index=True
    )

    # Foreign keys
    media_file_id = Column(
        Integer, ForeignKey("media_file.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)

    # AI-generated suggestions (JSONB arrays)
    suggested_tags = Column(JSONB, nullable=True, default=[])
    suggested_collections = Column(JSONB, nullable=True, default=[])

    # User interaction tracking
    status = Column(String(50), nullable=False, default="pending", index=True)
    user_decisions = Column(JSONB, nullable=True)  # {accepted_collections: [], accepted_tags: []}

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    media_file = relationship("MediaFile", back_populates="topic_suggestions")
    user = relationship("User", back_populates="topic_suggestions")
