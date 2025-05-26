from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import os
import io
import logging

# Set up logging
logger = logging.getLogger(__name__)

from app.db.base import get_db
from app.models.user import User
from app.models.media import MediaFile, TranscriptSegment, FileTag, Tag, FileStatus
from app.schemas.media import MediaFile as MediaFileSchema, MediaFileDetail, TranscriptSegmentUpdate, MediaFileUpdate
from app.api.endpoints.auth import get_current_active_user
from app.services.minio_service import upload_file, get_file_url, download_file, get_file_stream
from app.tasks.transcription import transcribe_audio_task
from app.core.config import settings

router = APIRouter()


@router.post("/", response_model=MediaFileSchema)
@router.post("", response_model=MediaFileSchema)  # Additional route without trailing slash for flexible routing
async def upload_media_file(
    file: UploadFile = File(...),  # Use File(...) to mark as required
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Upload a media file for transcription
    """
    try:
        logger.info(f"File upload request received from user: {current_user.email}")
        if file:
            logger.info(f"File details - filename: {file.filename}, content_type: {file.content_type}")
        else:
            logger.error("No file was received in the request!")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file was uploaded. Please select a file."
            )
    except Exception as e:
        logger.error(f"Error logging file upload request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing file upload request"
        )

    # Log the request details for debugging
    logger.info(f"File content type: {file.content_type if file else 'None'}")
    
    # Validate file type (accept audio and video formats)
    allowed_types = ["audio/", "video/"]
    if not any(file.content_type.startswith(t) for t in allowed_types):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an audio or video format"
        )
    
    # Read file content
    file_content = await file.read()
    file_size = len(file_content)
    
    # Create a new media file record with all required fields
    try:
        # Check if required enum is available, this helps with debugging
        if not hasattr(FileStatus, 'PENDING'):
            raise ValueError("FileStatus enum is not properly defined or imported")
            
        # Create MediaFile with all required fields that match the SQL schema
        # Explicitly log what we're trying to create to help with debugging
        logger.info(f"Creating MediaFile with filename={file.filename}, size={file_size}, type={file.content_type}")
        
        db_file = MediaFile(
            filename=file.filename,
            user_id=current_user.id,
            storage_path="",  # Will be updated after upload
            file_size=file_size,
            content_type=file.content_type,
            status=FileStatus.PENDING,
            is_public=False,
            # These fields can be null in the database
            duration=None,
            language=None,
            summary=None,
            translated_text=None
        )
    except Exception as e:
        print(f"Error creating MediaFile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating media file record: {str(e)}"
        )
    
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    
    # Generate storage path
    storage_path = f"user_{current_user.id}/file_{db_file.id}/{file.filename}"
    
    # Upload to MinIO (skip in test environment)
    if os.environ.get('SKIP_S3', 'False').lower() != 'true':
        upload_file(
            file_content=io.BytesIO(file_content),
            file_size=file_size,
            object_name=storage_path,
            content_type=file.content_type
        )
    else:
        logger.info("Skipping S3 upload in test environment")
    
    # Update storage path
    db_file.storage_path = storage_path
    db.commit()
    db.refresh(db_file)
    
    # Start transcription task in background (skip in test environment)
    if os.environ.get('SKIP_CELERY', 'False').lower() != 'true':
        transcribe_audio_task.delay(db_file.id)
    else:
        logger.info("Skipping Celery task in test environment")
    
    return db_file


@router.get("/", response_model=List[MediaFileSchema])
@router.get("", response_model=List[MediaFileSchema])  # Add route without trailing slash
async def list_media_files(
    search: Optional[str] = None,
    tag: Optional[str] = None,
    speaker: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    List all media files for the current user with optional filters
    """
    # Add detailed logging to debug authentication issues
    logger.info(f"Listing files for user: {current_user.email} (ID: {current_user.id})")
    logger.info(f"Request parameters: search={search}, tag={tag}, speaker={speaker}, date range: {from_date} to {to_date}")
    try:
        query = db.query(MediaFile).filter(MediaFile.user_id == current_user.id)
        
        # Apply search filter
        if search:
            query = query.filter(MediaFile.filename.ilike(f"%{search}%"))
        
        # Apply date filter
        if from_date:
            query = query.filter(MediaFile.upload_time >= from_date)
        if to_date:
            query = query.filter(MediaFile.upload_time <= to_date)
        
        # Apply tag filter
        if tag:
            tag_obj = db.query(Tag).filter(Tag.name == tag).first()
            if tag_obj:
                query = query.join(FileTag).filter(FileTag.tag_id == tag_obj.id)
        
        # Apply speaker filter (more complex, would need to join with transcripts and speakers)
        try:
            if speaker:
                query = query.join(TranscriptSegment).join("speaker").filter(
                    TranscriptSegment.speaker.has(name=speaker)
                )
        except Exception as speaker_error:
            print(f"Error applying speaker filter: {speaker_error}")
            # Continue without the speaker filter if it fails
        
        # Order by most recent
        query = query.order_by(MediaFile.upload_time.desc())
        
        return query.all()
    except Exception as e:
        print(f"Error in list_media_files: {e}")
        # If there's an error, return an empty list
        return []


@router.get("/{file_id}", response_model=MediaFileDetail)
def get_media_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get a specific media file with transcript details
    """
    # First check if the file exists - don't wrap this in a try/except
    db_file = db.query(MediaFile).filter(
        MediaFile.id == file_id,
        MediaFile.user_id == current_user.id
    ).first()
    
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found"
        )
        
    try:
        # Get tags for this file - handle case where tag tables might not exist yet
        tags = []
        try:
            # Check if tag table exists first
            from sqlalchemy import inspect
            inspector = inspect(db.bind)
            if 'tag' in inspector.get_table_names() and 'file_tag' in inspector.get_table_names():
                tags = db.query(Tag.name).join(FileTag).filter(
                    FileTag.media_file_id == file_id
                ).all()
            else:
                logger.warning("Tag tables don't exist yet, skipping tag retrieval")
        except Exception as tag_error:
            logger.error(f"Error getting tags: {tag_error}")
            # Continue without tags if there's an error
            db.rollback()  # Important to roll back the failed transaction
            
        # Provide a direct URL to the video content via our proxy endpoint (no auth required)
        logger.info(f"File status: {db_file.status}, Storage path: {db_file.storage_path or 'None'}")
        
        # For all files with a storage path, provide a direct URL to the video
        if db_file.storage_path:  # Allow any status as long as we have a storage path
            # Create a simple direct URL to our video endpoint - no authentication needed
            logger.info(f"Setting up direct video URL for file {file_id}")
            
            # Simple video URL that doesn't require authentication
            video_url = f"/api/files/{file_id}/video"
            
            # Set both download_url and preview_url to our video URL
            db_file.download_url = video_url
            db_file.preview_url = video_url
            
            logger.info(f"Direct video URL set: {video_url}")
            
            # Ensure these property changes are reflected in the response
            db.commit()
        else:
            logger.warning(f"Cannot generate video URL: no storage path available")
            # For files without a storage path, indicate they're not available
            db_file.download_url = None
            db_file.preview_url = None
        
        # Prepare the response
        response = MediaFileDetail.model_validate(db_file)
        response.tags = [tag[0] for tag in tags]
        
        return response
    except Exception as e:
        print(f"Error in get_media_file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving media file: {str(e)}"
        )


@router.put("/{file_id}", response_model=MediaFileSchema)
def update_media_file(
    file_id: int,
    media_file_update: MediaFileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Update a media file's metadata
    """
    db_file = db.query(MediaFile).filter(
        MediaFile.id == file_id,
        MediaFile.user_id == current_user.id
    ).first()
    
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found"
        )
    
    # Update fields
    for field, value in media_file_update.model_dump(exclude_unset=True).items():
        setattr(db_file, field, value)
    
    db.commit()
    db.refresh(db_file)
    
    return db_file


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Delete a media file and all associated data
    """
    db_file = db.query(MediaFile).filter(
        MediaFile.id == file_id,
        MediaFile.user_id == current_user.id
    ).first()
    
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found"
        )
    
    # Delete from MinIO (if exists)
    # This may need error handling if file doesn't exist in storage
    try:
        delete_file(db_file.storage_path)
    except Exception:
        # Log error but continue with DB deletion
        pass
    
    # Delete from database (cascade will handle related records)
    db.delete(db_file)
    db.commit()
    
    return None


@router.get("/{file_id}/stream-url")
def get_media_file_stream_url(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get a streaming URL for the media file that works from any client
    """
    db_file = db.query(MediaFile).filter(
        MediaFile.id == file_id,
        MediaFile.user_id == current_user.id
    ).first()
    
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found"
        )
    
    # Skip S3 operations in test environment
    if os.environ.get('SKIP_S3', 'False').lower() == 'true':
        # Return a mock URL in test environment
        logger.info("Returning mock URL in test environment")
        return {"url": f"/api/files/{file_id}/content", "content_type": db_file.content_type}
    
    # Return the URL to our video endpoint
    return {
        "url": f"/api/files/{file_id}/video",  # Video endpoint
        "content_type": db_file.content_type,
        "requires_auth": False  # No auth required for video endpoint
    }

@router.get("/{file_id}/content")
def get_media_file_content(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get the content of a media file
    """
    db_file = db.query(MediaFile).filter(
        MediaFile.id == file_id,
        MediaFile.user_id == current_user.id
    ).first()
    
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found"
        )
    
    # Skip S3 operations in test environment
    if os.environ.get('SKIP_S3', 'False').lower() == 'true':
        return StreamingResponse(
            content=io.BytesIO(b"Mock file content"),
            media_type=db_file.content_type
        )
    
    try:
        # Get the file from MinIO
        content = download_file(db_file.storage_path)
        return StreamingResponse(
            content=io.BytesIO(content),
            media_type=db_file.content_type,
            headers={
                'Content-Disposition': f'attachment; filename="{db_file.filename}"'
            }
        )
    except Exception as e:
        logger.error(f"Error retrieving file content: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving file content: {e}"
        )


# Simple endpoints for video playback - no authentication needed
@router.get("/{file_id}/video")
async def video_file(file_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Direct video endpoint for video player
    No authentication required - this is a public endpoint for video files only
    """
    # Log the video request
    logger.info(f"Video request for file {file_id}")
    
    # Get the file without user filtering
    db_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
    
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file not found"
        )
    
    if not db_file.storage_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file not available"
        )
    
    # Skip S3 operations in test environment
    if os.environ.get('SKIP_S3', 'False').lower() == 'true':
        # Return mock data in test environment
        return {"content": "Mock video content", "content_type": db_file.content_type}
    
    try:
        # Get range header if present
        range_header = request.headers.get("range")
        
        # Log the range request
        if range_header:
            logger.info(f"Range header received: {range_header}")
        
        # Get the file from MinIO with range handling
        file_stream = get_file_stream(db_file.storage_path, range_header)
        
        # Set appropriate headers for video streaming with proper CORS support
        headers = {
            'Content-Disposition': f'inline; filename="{db_file.filename}"',
            'Accept-Ranges': 'bytes',
            'Cache-Control': 'max-age=3600',  # Allow caching for 1 hour
            'Access-Control-Allow-Origin': '*',  # Allow access from any origin
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Range, Content-Type, Accept',
            'Content-Type': db_file.content_type
        }
        
        # Determine status code based on range request
        status_code = status.HTTP_206_PARTIAL_CONTENT if range_header else status.HTTP_200_OK
        
        # Return the video as a streaming response
        return StreamingResponse(
            content=file_stream,
            media_type=db_file.content_type,
            headers=headers,
            status_code=status_code
        )
    except Exception as e:
        logger.error(f"Error serving video file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error serving video: {e}"
        )


# Removed unused endpoint stream_media_file

@router.get("/{file_id}/simple-video")
async def simple_video(file_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Enhanced video streaming endpoint that efficiently serves video content with YouTube-like streaming.
    Features:
    - Precise range request handling for seeking
    - Adaptive chunk sizes based on file size
    - Proper content-length headers for progress indication
    - Efficient memory usage for large files
    - Browser caching support
    """
    # Log the request
    logger.info(f"Video streaming request for file {file_id}")
    
    # Get the file without user filtering (public endpoint)
    db_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
    
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    if not db_file.storage_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not available"
        )
    
    # Skip S3 operations in test environment
    if os.environ.get('SKIP_S3', 'False').lower() == 'true':
        # Return mock data in test environment
        return {"content": "Mock video content", "content_type": db_file.content_type}
    
    try:
        # Get the range header if present (used for video seeking)
        range_header = request.headers.get("range")
        
        # Log the range request if present
        if range_header:
            logger.info(f"Range request: {range_header} for file {file_id}")
        
        # Set media type based on file content type with fallback to mp4
        media_type = db_file.content_type or 'video/mp4'
        
        # Get file content as a stream with range information
        # The enhanced get_file_stream now returns more information
        logger.info(f"Streaming file: id={file_id}, path={db_file.storage_path}")
        file_stream, start_byte, end_byte, total_length = get_file_stream(db_file.storage_path, range_header)
        
        # Determine response status code (206 Partial Content for range requests)
        status_code = status.HTTP_206_PARTIAL_CONTENT if range_header else status.HTTP_200_OK
        
        # Set comprehensive response headers for optimal streaming
        headers = {
            'Content-Disposition': f'inline; filename="{db_file.filename}"',
            'Content-Type': media_type,
            'Accept-Ranges': 'bytes',  # Inform client we support range requests
            'Access-Control-Allow-Origin': '*',  # Allow any origin for development
            'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
            'Access-Control-Allow-Headers': 'Range, Origin, Content-Type, Accept',
        }
        
        # Add Content-Range header for range requests (required for 206 responses)
        if range_header and total_length is not None:
            content_range = f'bytes {start_byte}-{end_byte}/{total_length}'
            headers['Content-Range'] = content_range
            
            # For range requests, content length is the actual bytes being sent
            content_length = end_byte - start_byte + 1 if end_byte is not None else total_length - start_byte
            headers['Content-Length'] = str(content_length)
            
            logger.info(f"Serving range: {content_range}, length: {content_length}")
        elif total_length is not None:
            # For full file requests, content length is the total file size
            headers['Content-Length'] = str(total_length)
        
        # Add caching headers based on content type
        # Video files can be cached longer as they rarely change
        if media_type.startswith('video/') or media_type.startswith('audio/'):
            headers['Cache-Control'] = 'public, max-age=86400, stale-while-revalidate=604800'  # 1 day cache, 7 day stale
            # Add ETag if available to support conditional requests
            if hasattr(db_file, 'md5_hash') and db_file.md5_hash:
                headers['ETag'] = f'"{db_file.md5_hash}"'
        else:
            # Other media types get shorter cache times
            headers['Cache-Control'] = 'public, max-age=3600'  # 1 hour cache
        
        # Return a streaming response that doesn't load the entire file into memory
        return StreamingResponse(
            content=file_stream,
            status_code=status_code,
            media_type=media_type,
            headers=headers
        )
    except Exception as e:
        logger.error(f"Error streaming video: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error streaming video: {e}"
        )

@router.put("/{file_id}/transcript", response_model=MediaFileDetail)
def update_transcript(
    file_id: int,
    segments: List[TranscriptSegmentUpdate],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Update transcript segments
    """
    db_file = db.query(MediaFile).filter(
        MediaFile.id == file_id,
        MediaFile.user_id == current_user.id
    ).first()
    
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found"
        )
    
    for segment_update in segments:
        segment = db.query(TranscriptSegment).filter(
            TranscriptSegment.id == segment_update.id,
            TranscriptSegment.media_file_id == file_id
        ).first()
        
        if segment:
            # Update fields
            for field, value in segment_update.model_dump(exclude_unset=True).items():
                setattr(segment, field, value)
    
    db.commit()
    
    # Return updated file details
    tags = db.query(Tag.name).join(FileTag).filter(
        FileTag.media_file_id == file_id
    ).all()
    
    response = MediaFileDetail.model_validate(db_file)
    response.tags = [tag[0] for tag in tags]
    
    return response
