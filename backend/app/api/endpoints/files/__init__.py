"""
Files API module - refactored for modularity.

This module contains the refactored files endpoint split into modular components:
- upload.py: File upload functionality
- crud.py: Basic CRUD operations
- filtering.py: Complex filtering logic for file listing
- streaming.py: Video/audio streaming endpoints
"""

from fastapi import APIRouter, Depends, UploadFile, File, Query, Request, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from datetime import datetime

from app.db.base import get_db
from app.models.user import User
from app.models.media import MediaFile
from app.schemas.media import MediaFile as MediaFileSchema, MediaFileDetail, TranscriptSegmentUpdate, MediaFileUpdate, TranscriptSegment
from app.api.endpoints.auth import get_current_active_user

# Import main functions for use in the router
from .upload import process_file_upload
from .crud import (
    get_media_file_detail, update_media_file, delete_media_file,
    update_single_transcript_segment, get_stream_url_info, get_media_file_by_id,
    set_file_urls
)
from .filtering import apply_all_filters, get_metadata_filters
from .streaming import (
    get_content_streaming_response, get_video_streaming_response,
    get_enhanced_video_streaming_response, validate_file_exists,
    get_thumbnail_streaming_response
)
from .reprocess import process_file_reprocess
from . import cancel_upload
from . import prepare_upload

# Create the router
router = APIRouter()

# Include all routers
router.include_router(cancel_upload.router, prefix="", tags=["files"])
router.include_router(prepare_upload.router, prefix="", tags=["files"])

# Import and include subtitle router
from .subtitles import router as subtitles_router
router.include_router(subtitles_router, prefix="", tags=["subtitles"])

@router.post("/", response_model=MediaFileSchema)
@router.post("", response_model=MediaFileSchema)
async def upload_media_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None
):
    """Upload a media file for transcription"""
    # Check if we have a file_id from prepare step
    existing_file_id = None
    if request and request.headers.get("X-File-ID"):
        try:
            existing_file_id = int(request.headers.get("X-File-ID"))
        except (ValueError, TypeError):
            pass
            
    # Get file hash from header if provided
    file_hash = None
    if request and request.headers.get("X-File-Hash"):
        file_hash = request.headers.get("X-File-Hash")
    
    # Process the file upload
    db_file = await process_file_upload(file, db, current_user, existing_file_id, file_hash)
    
    # Create a response with the file ID in headers
    response = JSONResponse(content=jsonable_encoder(db_file))
    # Add file ID to header so frontend can access it early
    response.headers["X-File-ID"] = str(db_file.id)
    
    return response


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
    # Admin users can see all files, regular users only see their own files
    if current_user.role == "admin":
        base_query = db.query(MediaFile)
    else:
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
    
    # Get the result
    result = filtered_query.all()
    
    # Set URLs for each file
    for file in result:
        set_file_urls(file)
    
    return result


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


@router.get("/{file_id}/download")
def download_media_file(
    file_id: int,
    token: str = None,
    with_subtitles: bool = Query(True, description="Include embedded subtitles for video files"),
    original: bool = Query(False, description="Download original file without subtitles"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Download a media file (with embedded subtitles for videos by default)"""
    db_file = get_media_file_by_id(db, file_id, current_user.id)
    
    # TODO: Re-enable subtitle processing once backend is stable
    # Temporarily disabled to restore normal functionality
    # Check if this is a video file and user wants subtitles
    # is_video = db_file.content_type and db_file.content_type.startswith('video/')
    # has_transcript = db_file.status == "completed"
    
    # if is_video and has_transcript and with_subtitles and not original:
    #     try:
    #         # Subtitle processing code temporarily disabled
    #         pass
    #     except Exception as e:
    #         print(f"Warning: Failed to process video with subtitles: {e}")
    #         pass
    
    # Return original file
    return get_content_streaming_response(db_file)


@router.get("/{file_id}/download-with-token")
def download_media_file_with_token(
    file_id: int,
    token: str,
    db: Session = Depends(get_db)
):
    """
    Download a media file using token parameter (for native browser downloads)
    No authentication required - token is validated manually
    """
    from jose import JWTError, jwt
    from app.core.config import settings
    from app.schemas.user import TokenPayload
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Validate JWT token manually
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Get user from database
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid user")
        
        # Get file and check ownership
        is_admin = user.role == "admin"
        db_file = get_media_file_by_id(db, file_id, user.id, is_admin=is_admin)
        return get_content_streaming_response(db_file)
        
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error(f"Error in download with token: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


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


@router.get("/{file_id}/thumbnail")
async def get_thumbnail(file_id: int, db: Session = Depends(get_db)):
    """
    Get the thumbnail image for a media file.
    No authentication required - this is a public endpoint for thumbnail images only.
    """
    db_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
    validate_file_exists(db_file)
    return get_thumbnail_streaming_response(db_file)


@router.get("/metadata-filters", response_model=Dict)
def get_metadata_filters_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get available metadata filters like formats, codecs, etc."""
    return get_metadata_filters(db, current_user.id)


@router.put("/{file_id}/transcript/segments/{segment_id}", response_model=TranscriptSegment)
def update_transcript_segment(
    file_id: int,
    segment_id: int,
    segment_update: TranscriptSegmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update a specific transcript segment"""
    from .crud import update_single_transcript_segment
    
    # Update the transcript segment
    result = update_single_transcript_segment(db, file_id, segment_id, segment_update, current_user)
    
    # Transcript has been updated - subtitles will be regenerated on-demand
    
    return result


@router.post("/{file_id}/reprocess", response_model=MediaFileSchema)
async def reprocess_media_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Reprocess a media file for transcription"""
    return await process_file_reprocess(file_id, db, current_user)


__all__ = [
    "router",
    "process_file_upload",
    "process_file_reprocess",
    "get_media_file_detail",
    "update_media_file", 
    "delete_media_file",
    "update_single_transcript_segment",
    "get_stream_url_info",
    "apply_all_filters",
    "get_metadata_filters",
    "get_content_streaming_response",
    "get_video_streaming_response", 
    "get_enhanced_video_streaming_response",
    "validate_file_exists",
    "get_thumbnail_streaming_response"
]