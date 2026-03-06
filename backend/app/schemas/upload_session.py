"""Pydantic schemas for TUS upload session."""

from uuid import UUID

from pydantic import BaseModel


class UploadSessionCreate(BaseModel):
    upload_id: UUID
    media_file_id: int
    user_id: int
    storage_path: str
    total_size: int
    content_type: str
    filename: str


class UploadSessionResponse(BaseModel):
    upload_id: UUID
    status: str
    offset: int
    total_size: int
    filename: str

    class Config:
        from_attributes = True
