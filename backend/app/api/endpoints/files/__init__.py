"""
Files API module - refactored for modularity.

This module contains the refactored files endpoint split into modular components:
- upload.py: File upload functionality
- crud.py: Basic CRUD operations
- filtering.py: Complex filtering logic for file listing
- streaming.py: Video/audio streaming endpoints
"""

from fastapi import APIRouter, Depends, UploadFile, File, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from datetime import datetime

from app.db.base import get_db
from app.models.user import User
from app.models.media import MediaFile
from app.schemas.media import MediaFile as MediaFileSchema, MediaFileDetail, TranscriptSegmentUpdate, MediaFileUpdate
from app.api.endpoints.auth import get_current_active_user

# Import main functions for use in the router
from .upload import process_file_upload
from .crud import (
    get_media_file_detail, update_media_file, delete_media_file,
    update_transcript_segments, get_stream_url_info, get_media_file_by_id
)
from .filtering import apply_all_filters, get_metadata_filters
from .streaming import (
    get_content_streaming_response, get_video_streaming_response,
    get_enhanced_video_streaming_response, validate_file_exists
)

# Create the router
router = APIRouter()


@router.post("/", response_model=MediaFileSchema)
@router.post("", response_model=MediaFileSchema)
async def upload_media_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Upload a media file for transcription"""
    return await process_file_upload(file, db, current_user)


@router.get("/", response_model=List[MediaFileSchema])
@router.get("", response_model=List[MediaFileSchema])
def list_media_files(
    search: Optional[str] = None,
    tag: Optional[List[str]] = Query(None),
    speaker: Optional[List[str]] = Query(None),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    min_duration: Optional[float] = None,
    max_duration: Optional[float] = None,
    min_file_size: Optional[int] = None,  # In MB
    max_file_size: Optional[int] = None,  # In MB
    file_type: Optional[List[str]] = Query(None),  # ['audio', 'video']
    status: Optional[List[str]] = Query(None),  # ['pending', 'processing', 'completed', 'error']
    transcript_search: Optional[str] = None,  # Search in transcript content
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List all media files for the current user with optional filters"""
    base_query = db.query(MediaFile).filter(MediaFile.user_id == current_user.id)
    
    # Prepare filters dictionary
    filters = {
        'search': search,
        'tag': tag,
        'speaker': speaker,
        'from_date': from_date,
        'to_date': to_date,
        'min_duration': min_duration,
        'max_duration': max_duration,
        'min_file_size': min_file_size,
        'max_file_size': max_file_size,
        'file_type': file_type,
        'status': status,
        'transcript_search': transcript_search
    }
    
    # Apply all filters
    filtered_query = apply_all_filters(base_query, filters)
    
    # Order by most recent
    filtered_query = filtered_query.order_by(MediaFile.upload_time.desc())
    
    return filtered_query.all()


@router.get("/{file_id}", response_model=MediaFileDetail)
def get_media_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific media file with transcript details"""
    return get_media_file_detail(db, file_id, current_user)


@router.put("/{file_id}", response_model=MediaFileSchema)
def update_media_file_endpoint(
    file_id: int,
    media_file_update: MediaFileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update a media file's metadata"""
    return update_media_file(db, file_id, media_file_update, current_user)


@router.delete("/{file_id}", status_code=204)
def delete_media_file_endpoint(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a media file and all associated data"""
    delete_media_file(db, file_id, current_user)
    return None


@router.get("/{file_id}/stream-url")
def get_media_file_stream_url(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a streaming URL for the media file that works from any client"""
    return get_stream_url_info(db, file_id, current_user)


@router.get("/{file_id}/content")
def get_media_file_content(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get the content of a media file"""
    db_file = get_media_file_by_id(db, file_id, current_user.id)
    return get_content_streaming_response(db_file)


@router.get("/{file_id}/video")
async def video_file(file_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Direct video endpoint for video player
    No authentication required - this is a public endpoint for video files only
    """
    db_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
    validate_file_exists(db_file)
    
    range_header = request.headers.get("range")
    return get_video_streaming_response(db_file, range_header)


@router.get("/{file_id}/simple-video")
async def simple_video(file_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Enhanced video streaming endpoint that efficiently serves video content with YouTube-like streaming.
    """
    db_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
    validate_file_exists(db_file)
    
    range_header = request.headers.get("range")
    return get_enhanced_video_streaming_response(db_file, range_header)


@router.get("/metadata-filters", response_model=Dict)
def get_metadata_filters_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get available metadata filters like formats, codecs, etc."""
    return get_metadata_filters(db, current_user.id)


@router.put("/{file_id}/transcript", response_model=MediaFileDetail)
def update_transcript(
    file_id: int,
    segments: List[TranscriptSegmentUpdate],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update transcript segments"""
    return update_transcript_segments(db, file_id, segments, current_user)


__all__ = [
    "router",
    "process_file_upload",
    "get_media_file_detail",
    "update_media_file", 
    "delete_media_file",
    "update_transcript_segments",
    "get_stream_url_info",
    "apply_all_filters",
    "get_metadata_filters",
    "get_content_streaming_response",
    "get_video_streaming_response", 
    "get_enhanced_video_streaming_response",
    "validate_file_exists"
]