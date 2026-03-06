"""Pydantic schemas for speaker clustering."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel
from pydantic import Field

# --- Speaker Cluster ---


class SpeakerClusterBase(BaseModel):
    """Base schema for speaker clusters."""

    label: Optional[str] = None
    description: Optional[str] = None


class SpeakerClusterCreate(SpeakerClusterBase):
    """Schema for creating a speaker cluster."""


class SpeakerClusterUpdate(BaseModel):
    """Schema for updating a speaker cluster."""

    label: Optional[str] = None
    description: Optional[str] = None


class SpeakerClusterMemberResponse(BaseModel):
    """Response schema for a cluster member."""

    uuid: UUID
    speaker_uuid: UUID
    speaker_name: str
    display_name: Optional[str] = None
    suggested_name: Optional[str] = None
    media_file_uuid: Optional[UUID] = None
    media_file_title: Optional[str] = None
    confidence: float = 0.0
    verified: bool = False
    predicted_gender: Optional[str] = None
    predicted_age_range: Optional[str] = None
    has_audio_clip: bool = False
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SpeakerClusterResponse(SpeakerClusterBase):
    """Response schema for a speaker cluster."""

    uuid: UUID
    user_id: int
    member_count: int = 0
    promoted_to_profile_id: Optional[int] = None
    promoted_to_profile_uuid: Optional[UUID] = None
    promoted_to_profile_name: Optional[str] = None
    quality_score: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SpeakerClusterDetailResponse(SpeakerClusterResponse):
    """Detailed response schema with members."""

    members: list[SpeakerClusterMemberResponse] = []


# --- Speaker Inbox ---


class SpeakerInboxItem(BaseModel):
    """Schema for an item in the unverified speakers inbox."""

    speaker_uuid: UUID
    speaker_name: str
    display_name: Optional[str] = None
    suggested_name: Optional[str] = None
    suggestion_source: Optional[str] = None
    confidence: Optional[float] = None
    media_file_uuid: Optional[UUID] = None
    media_file_title: Optional[str] = None
    media_file_duration: Optional[float] = None
    cluster_uuid: Optional[UUID] = None
    cluster_label: Optional[str] = None
    cluster_member_count: int = 0
    verified: bool = False
    predicted_gender: Optional[str] = None
    predicted_age_range: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Batch Operations ---


class BatchVerifyRequest(BaseModel):
    """Request schema for batch speaker verification."""

    speaker_uuids: list[UUID] = Field(..., min_length=1)
    profile_uuid: Optional[UUID] = None
    display_name: Optional[str] = None
    action: str = Field(
        default="accept",
        description="Action: 'accept' (apply suggestion), 'assign' (assign to profile), 'name' (set display_name), 'skip' (mark as reviewed/skipped)",
    )


class BatchVerifyResponse(BaseModel):
    """Response schema for batch verification."""

    updated_count: int
    failed_count: int = 0
    errors: list[str] = []


class ReclusterRequest(BaseModel):
    """Request schema for triggering re-clustering."""

    force: bool = Field(
        default=False, description="Reserved for future use. Currently has no effect."
    )
    threshold: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Clustering threshold (default 0.75)"
    )


class ReclusterResponse(BaseModel):
    """Response schema for re-clustering operation."""

    status: str
    task_id: Optional[str] = None
    message: str


class ClusterSplitRequest(BaseModel):
    """Request schema for splitting a cluster."""

    speaker_uuids: list[UUID] = Field(
        ..., min_length=1, description="Speaker UUIDs to split into new cluster"
    )


class ClusterPromoteRequest(BaseModel):
    """Request schema for promoting a cluster to a profile."""

    name: str = Field(
        ..., min_length=1, max_length=255, description="Name for the new speaker profile"
    )
    description: Optional[str] = None


# --- Paginated Responses ---


class PaginatedClusterResponse(BaseModel):
    """Paginated list of clusters."""

    items: list[SpeakerClusterResponse] = []
    total: int = 0
    page: int = 1
    per_page: int = 20
    pages: int = 0


class PaginatedInboxResponse(BaseModel):
    """Paginated list of inbox items."""

    items: list[SpeakerInboxItem] = []
    total: int = 0
    page: int = 1
    per_page: int = 20
    pages: int = 0
