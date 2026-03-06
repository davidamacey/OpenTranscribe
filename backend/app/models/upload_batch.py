"""Upload batch model for tracking multi-file imports."""

import uuid as uuid_pkg

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class UploadBatch(Base):
    """Tracks files uploaded together for batch topic grouping."""

    __tablename__ = "upload_batch"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid_pkg.uuid4)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(50), nullable=False)  # "multi_upload" | "playlist" | "url_batch"
    file_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    grouping_status = Column(
        String(50), server_default="pending"
    )  # pending | processing | completed | skipped

    # Relationships
    user = relationship("User")
    media_files = relationship("MediaFile", back_populates="upload_batch")
