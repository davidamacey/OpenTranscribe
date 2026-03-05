"""Medical keyterm model for ASR vocabulary boosting."""

import uuid as uuid_pkg

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class MedicalKeyterm(Base):
    """Medical keyterm for ASR vocabulary boosting (e.g., Deepgram keyterm prompting)."""

    __tablename__ = "medical_keyterm"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid_pkg.uuid4, index=True
    )
    user_id = Column(Integer, ForeignKey("user.id"), nullable=True)  # NULL = system-wide
    term = Column(String(255), nullable=False)
    category = Column(String(100), nullable=True)  # medication, anatomy, procedure, diagnosis
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User")
