"""
API endpoints for subtitle generation and video with embedded subtitles.
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.api.endpoints.auth import get_current_active_user
from app.models.user import User
from app.models.media import MediaFile
from app.schemas.media import (
    SubtitleRequest, 
    VideoWithSubtitlesRequest, 
    VideoWithSubtitlesResponse,
    SubtitleValidationResult,
    VideoFormat
)
from app.services.subtitle_service import SubtitleService
from app.services.video_processing_service import VideoProcessingService
from app.services.minio_service import MinIOService
from app.core.config import settings
router = APIRouter()

# Initialize services
minio_service = MinIOService()
video_processing_service = VideoProcessingService(minio_service)


@router.get("/{file_id}/subtitles", response_class=Response)
async def get_subtitles(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    include_speakers: bool = Query(True, description="Include speaker labels in subtitles"),
    format: str = Query("srt", description="Subtitle format (srt, webvtt)")
):
    """
    Generate and download subtitles for a media file.
    
    Returns subtitles in the requested format (SRT by default).
    """
    # Get media file and check permissions
    media_file = db.query(MediaFile).filter(
        MediaFile.id == file_id,
        MediaFile.user_id == current_user.id
    ).first()
    
    if not media_file:
        raise HTTPException(status_code=404, detail="Media file not found")
    
    if media_file.status != "completed":
        raise HTTPException(status_code=400, detail="Transcription not completed yet")
    
    try:
        # Generate subtitle content
        subtitle_content = SubtitleService.generate_srt_content(
            db, file_id, include_speakers
        )
        
        if not subtitle_content.strip():
            raise HTTPException(status_code=404, detail="No transcript available for this file")
        
        # Determine content type based on format
        content_type_map = {
            "srt": "application/x-subrip",
            "webvtt": "text/vtt"
        }
        content_type = content_type_map.get(format.lower(), "text/plain")
        
        # Generate filename
        base_filename = media_file.filename.rsplit('.', 1)[0] if '.' in media_file.filename else media_file.filename
        filename = f"{base_filename}.{format.lower()}"
        
        return Response(
            content=subtitle_content,
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename=\"{filename}\"",
                "Content-Length": str(len(subtitle_content.encode('utf-8')))
            }
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate subtitles: {str(e)}")


@router.post("/{file_id}/video-with-subtitles", response_model=VideoWithSubtitlesResponse)
async def get_video_with_subtitles(
    file_id: int,
    request: VideoWithSubtitlesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Process video with embedded subtitles and return download URL.
    
    This endpoint processes the video file and embeds subtitles directly into it.
    The processed video is cached to avoid reprocessing unless forced.
    """
    # Get media file and check permissions
    media_file = db.query(MediaFile).filter(
        MediaFile.id == file_id,
        MediaFile.user_id == current_user.id
    ).first()
    
    if not media_file:
        raise HTTPException(status_code=404, detail="Media file not found")
    
    if media_file.status != "completed":
        raise HTTPException(status_code=400, detail="Transcription not completed yet")
    
    try:
        # Convert enum to string if provided
        output_format = request.output_format.value if request.output_format else None
        
        # Process video with subtitles
        processed_path = video_processing_service.process_video_with_subtitles(
            db=db,
            media_file_id=file_id,
            output_format=output_format,
            include_speakers=request.include_speakers,
            force_regenerate=request.force_regenerate
        )
        
        # Generate presigned URL for download (valid for 1 hour)
        expires_in = 3600  # 1 hour
        bucket, object_path = processed_path.split('/', 1)
        download_url = minio_service.get_presigned_url(
            bucket_name=bucket,
            object_name=object_path,
            expires=expires_in
        )
        
        # Get file size
        try:
            stat = minio_service.client.stat_object(bucket, object_path)
            file_size = stat.size
        except:
            file_size = None
        
        # Determine final format
        final_format = output_format or video_processing_service._detect_output_format(media_file.storage_path)
        
        return VideoWithSubtitlesResponse(
            download_url=download_url,
            format=final_format,
            cache_key=object_path.split('/')[-1].split('.')[0],
            expires_at=datetime.utcnow() + timedelta(seconds=expires_in),
            file_size=file_size
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process video: {str(e)}")


@router.get("/{file_id}/video-with-subtitles/stream")
async def stream_video_with_subtitles(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    output_format: Optional[VideoFormat] = Query(None, description="Output video format"),
    include_speakers: bool = Query(True, description="Include speaker labels in subtitles")
):
    """
    Stream video with embedded subtitles directly.
    
    This endpoint provides direct streaming of the processed video without requiring
    a separate download step.
    """
    # Get media file and check permissions
    media_file = db.query(MediaFile).filter(
        MediaFile.id == file_id,
        MediaFile.user_id == current_user.id
    ).first()
    
    if not media_file:
        raise HTTPException(status_code=404, detail="Media file not found")
    
    if media_file.status != "completed":
        raise HTTPException(status_code=400, detail="Transcription not completed yet")
    
    try:
        # Convert enum to string if provided
        format_str = output_format.value if output_format else None
        
        # Process video with subtitles
        processed_path = video_processing_service.process_video_with_subtitles(
            db=db,
            media_file_id=file_id,
            output_format=format_str,
            include_speakers=include_speakers
        )
        
        # Stream the processed video
        bucket, object_path = processed_path.split('/', 1)
        
        def generate_stream():
            try:
                response = minio_service.client.get_object(bucket, object_path)
                for chunk in response.stream(8192):
                    yield chunk
            finally:
                response.close()
                response.release_conn()
        
        # Determine content type
        format_str = format_str or video_processing_service._detect_output_format(media_file.storage_path)
        content_type = f"video/{format_str}"
        
        # Generate filename for download
        base_filename = media_file.filename.rsplit('.', 1)[0] if '.' in media_file.filename else media_file.filename
        filename = f"{base_filename}_with_subtitles.{format_str}"
        
        return StreamingResponse(
            generate_stream(),
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename=\"{filename}\"",
                "Accept-Ranges": "bytes"
            }
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stream video: {str(e)}")


@router.get("/{file_id}/subtitles/validate", response_model=SubtitleValidationResult)
async def validate_subtitles(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Validate subtitle timing and content for a media file.
    
    Returns validation results including any timing issues or problems found.
    """
    # Get media file and check permissions
    media_file = db.query(MediaFile).filter(
        MediaFile.id == file_id,
        MediaFile.user_id == current_user.id
    ).first()
    
    if not media_file:
        raise HTTPException(status_code=404, detail="Media file not found")
    
    if media_file.status != "completed":
        raise HTTPException(status_code=400, detail="Transcription not completed yet")
    
    try:
        # Validate subtitle timing
        issues = SubtitleService.validate_subtitle_timing(db, file_id)
        
        # Get segment count and total duration
        from app.models.media import TranscriptSegment
        segments = db.query(TranscriptSegment).filter(
            TranscriptSegment.media_file_id == file_id
        ).all()
        
        total_segments = len(segments)
        total_duration = max([seg.end_time for seg in segments]) if segments else 0.0
        
        return SubtitleValidationResult(
            is_valid=len(issues) == 0,
            issues=issues,
            total_segments=total_segments,
            total_duration=total_duration
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate subtitles: {str(e)}")


@router.delete("/{file_id}/video-cache")
async def clear_video_cache(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Clear cached processed videos for a media file.
    
    Use this when transcript has been updated and you want to force regeneration
    of videos with embedded subtitles.
    """
    # Get media file and check permissions
    media_file = db.query(MediaFile).filter(
        MediaFile.id == file_id,
        MediaFile.user_id == current_user.id
    ).first()
    
    if not media_file:
        raise HTTPException(status_code=404, detail="Media file not found")
    
    try:
        video_processing_service.clear_cache_for_media_file(file_id)
        return {"message": "Video cache cleared successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@router.get("/supported-formats")
async def get_supported_formats():
    """
    Get list of supported video and subtitle formats.
    """
    return {
        "video_formats": video_processing_service.get_supported_formats(),
        "subtitle_formats": ["srt", "webvtt", "mov_text"]
    }