"""
Files API module - refactored for modularity.

This module contains the refactored files endpoint split into modular components:
- upload.py: File upload functionality
- crud.py: Basic CRUD operations
- filtering.py: Complex filtering logic for file listing
- streaming.py: Video/audio streaming endpoints
"""

import contextlib
from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import File
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from fastapi import UploadFile
from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.models.media import MediaFile
from app.models.media import Speaker
from app.models.user import User
from app.schemas.media import MediaFile as MediaFileSchema
from app.schemas.media import MediaFileDetail
from app.schemas.media import MediaFileUpdate
from app.schemas.media import TranscriptSegment
from app.schemas.media import TranscriptSegmentUpdate
from app.services.formatting_service import FormattingService

from . import cancel_upload
from . import prepare_upload
from .crud import delete_media_file
from .crud import get_media_file_by_id
from .crud import get_media_file_by_uuid
from .crud import get_media_file_detail
from .crud import get_stream_url_info
from .crud import set_file_urls
from .crud import update_media_file
from .crud import update_single_transcript_segment
from .filtering import apply_all_filters
from .filtering import get_metadata_filters
from .reprocess import process_file_reprocess
from .streaming import get_content_streaming_response
from .streaming import get_enhanced_video_streaming_response
from .streaming import get_thumbnail_streaming_response
from .streaming import get_video_streaming_response
from .streaming import validate_file_exists
from .subtitles import router as subtitles_router
from .summary_status import router as summary_status_router
from .upload import process_file_upload
from .url_processing import router as url_processing_router
from .waveform import router as waveform_router

# Create the router
router = APIRouter()

# Include all routers
router.include_router(cancel_upload.router, prefix="", tags=["files"])
router.include_router(prepare_upload.router, prefix="", tags=["files"])
router.include_router(subtitles_router, prefix="", tags=["subtitles"])
router.include_router(waveform_router, prefix="", tags=["waveform"])
router.include_router(url_processing_router, prefix="", tags=["url-processing"])
router.include_router(summary_status_router, prefix="", tags=["summary"])


@router.post("/", response_model=MediaFileSchema)
@router.post("", response_model=MediaFileSchema)
async def upload_media_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """Upload a media file for transcription"""
    # Check if we have a file_uuid from prepare step
    existing_file_uuid = None
    if request and request.headers.get("X-File-ID"):
        # X-File-ID now contains UUID string (not integer)
        existing_file_uuid = request.headers.get("X-File-ID")

    # Get file hash from header if provided
    file_hash = None
    if request and request.headers.get("X-File-Hash"):
        file_hash = request.headers.get("X-File-Hash")

    # Process the file upload
    db_file = await process_file_upload(file, db, current_user, existing_file_uuid, file_hash)

    # Create a response with the file ID in headers
    response = JSONResponse(content=jsonable_encoder(db_file))
    # Add file UUID to header so frontend can access it early
    response.headers["X-File-ID"] = str(db_file.uuid)

    return response


@router.get("/", response_model=list[MediaFileSchema])
@router.get("", response_model=list[MediaFileSchema])
def list_media_files(
    search: Optional[str] = None,
    tag: Optional[list[str]] = Query(None),
    speaker: Optional[list[str]] = Query(None),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    min_duration: Optional[float] = None,
    max_duration: Optional[float] = None,
    min_file_size: Optional[int] = None,  # In MB
    max_file_size: Optional[int] = None,  # In MB
    file_type: Optional[list[str]] = Query(None),  # ['audio', 'video']
    status: Optional[list[str]] = Query(
        None
    ),  # ['pending', 'processing', 'completed', 'error', 'cancelling', 'cancelled', 'orphaned']
    transcript_search: Optional[str] = None,  # Search in transcript content
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all media files for the current user with optional filters"""
    from sqlalchemy.orm import joinedload

    # Admin users can see all files, regular users only see their own files
    # Eagerly load the user relationship to get UUID for validation
    if current_user.role == "admin":
        base_query = db.query(MediaFile).options(joinedload(MediaFile.user))
    else:
        base_query = db.query(MediaFile).options(joinedload(MediaFile.user)).filter(MediaFile.user_id == current_user.id)

    # Prepare filters dictionary
    filters = {
        "search": search,
        "tag": tag,
        "speaker": speaker,
        "from_date": from_date,
        "to_date": to_date,
        "min_duration": min_duration,
        "max_duration": max_duration,
        "min_file_size": min_file_size,
        "max_file_size": max_file_size,
        "file_type": file_type,
        "status": status,
        "transcript_search": transcript_search,
    }

    # Apply all filters
    filtered_query = apply_all_filters(base_query, filters)

    # Order by most recent
    filtered_query = filtered_query.order_by(MediaFile.upload_time.desc())

    # Get the result
    result = filtered_query.all()

    # Format each file with URLs and formatted fields
    formatted_files = []
    for file in result:
        set_file_urls(file)

        # Convert to schema and add formatted fields
        file_schema = MediaFileSchema.model_validate(file)
        file_schema.formatted_duration = FormattingService.format_duration(file.duration)
        file_schema.formatted_upload_date = FormattingService.format_upload_date(file.upload_time)
        file_schema.display_status = FormattingService.format_status(file.status)
        file_schema.status_badge_class = FormattingService.get_status_badge_class(file.status.value)

        formatted_files.append(file_schema)

    return formatted_files


@router.get("/{file_uuid}", response_model=MediaFileDetail)
def get_media_file(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a specific media file with transcript details"""
    return get_media_file_detail(db, file_uuid, current_user)


@router.put("/{file_uuid}", response_model=MediaFileSchema)
def update_media_file_endpoint(
    file_uuid: str,
    media_file_update: MediaFileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a media file's metadata"""
    return update_media_file(db, file_uuid, media_file_update, current_user)


@router.delete("/{file_uuid}", status_code=204)
def delete_media_file_endpoint(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Delete a media file and all associated data"""
    delete_media_file(db, file_uuid, current_user)
    return None


@router.get("/{file_uuid}/stream-url")
def get_media_file_stream_url(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a streaming URL for the media file that works from any client"""
    return get_stream_url_info(db, file_uuid, current_user)


@router.get("/{file_uuid}/content")
def get_media_file_content(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get the content of a media file"""
    is_admin = current_user.role == "admin"
    db_file = get_media_file_by_uuid(db, file_uuid, current_user.id, is_admin=is_admin)
    return get_content_streaming_response(db_file)


@router.get("/{file_uuid}/download")
def download_media_file(
    file_uuid: str,
    token: str = None,
    original: bool = Query(False, description="Download original file without subtitles"),
    include_speakers: bool = Query(True, description="Include speaker labels in subtitles"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Download a media file (with embedded subtitles for videos by default)"""
    is_admin = current_user.role == "admin"
    db_file = get_media_file_by_uuid(db, file_uuid, current_user.id, is_admin=is_admin)
    file_id = db_file.id  # Get internal ID for video processing

    # Check if this is a video file with available subtitles
    is_video = db_file.content_type and db_file.content_type.startswith("video/")
    has_transcript = db_file.status == "completed"

    # Always embed subtitles for videos when available, unless user explicitly requests original
    if is_video and has_transcript and not original:
        try:
            import logging

            logger = logging.getLogger(__name__)
            logger.info(f"Processing video download with subtitles for file {file_uuid} (id: {file_id})")

            from app.services.minio_service import MinIOService
            from app.services.video_processing_service import VideoProcessingService

            # Initialize services
            minio_service = MinIOService()
            video_service = VideoProcessingService(minio_service)

            # Check if ffmpeg is available
            if not video_service.check_ffmpeg_availability():
                # Fall back to original file if ffmpeg is not available
                logger.warning(f"ffmpeg not available, serving original file for {file_uuid} (id: {file_id})")
                return get_content_streaming_response(db_file)

            logger.info(f"ffmpeg available, processing video {file_uuid} (id: {file_id}) with subtitles")

            # Process video with embedded subtitles
            cache_key = video_service.process_video_with_subtitles(
                db=db,
                file_id=file_id,
                original_object_name=db_file.storage_path,
                user_id=current_user.id,
                include_speakers=include_speakers,
                output_format="mp4",
            )

            logger.info(f"Video processing complete, streaming processed video: {cache_key}")

            # Stream the processed video through backend
            from fastapi.responses import StreamingResponse

            # Get range header for video streaming support
            range_header = None
            # Note: request object not available here, will handle basic streaming

            file_stream, _, _, total_length = video_service._get_cache_file_stream(
                cache_key, range_header
            )

            # Generate proper filename for download
            base_name = (
                db_file.filename.rsplit(".", 1)[0] if "." in db_file.filename else db_file.filename
            )
            download_filename = f"{base_name}_with_subtitles.mp4"

            headers = {
                "Content-Disposition": f'attachment; filename="{download_filename}"',
                "Content-Type": "video/mp4",
                "Accept-Ranges": "bytes",
            }

            if total_length:
                headers["Content-Length"] = str(total_length)

            return StreamingResponse(content=file_stream, media_type="video/mp4", headers=headers)

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"Failed to process video with subtitles for file {file_id}: {e}",
                exc_info=True,
            )
            # Fall back to original file on error

    # Return original file
    return get_content_streaming_response(db_file)


@router.get("/{file_uuid}/download-with-token")
def download_media_file_with_token(
    file_uuid: str,
    token: str,
    original: bool = Query(False, description="Download original file without subtitles"),
    include_speakers: bool = Query(True, description="Include speaker labels in subtitles"),
    db: Session = Depends(get_db),
):
    """
    Download a media file using token parameter (for native browser downloads)
    No authentication required - token is validated manually
    """
    import logging

    from jose import JWTError
    from jose import jwt

    from app.core.config import settings

    logger = logging.getLogger(__name__)

    try:
        # Validate JWT token manually
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Get user from database
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid user")

        # Get file and check ownership
        is_admin = user.role == "admin"
        db_file = get_media_file_by_uuid(db, file_uuid, user.id, is_admin=is_admin)
        file_id = db_file.id  # Get internal ID for video processing

        # Check if this is a video file with available subtitles
        is_video = db_file.content_type and db_file.content_type.startswith("video/")
        has_transcript = db_file.status == "completed"

        # Always embed subtitles for videos when available, unless user explicitly requests original
        if is_video and has_transcript and not original:
            try:
                logger.info(
                    f"Processing video download with subtitles for file {file_uuid} (id: {file_id}, token endpoint)"
                )

                from app.services.minio_service import MinIOService
                from app.services.video_processing_service import VideoProcessingService

                # Initialize services
                minio_service = MinIOService()
                video_service = VideoProcessingService(minio_service)

                # Check if ffmpeg is available
                if not video_service.check_ffmpeg_availability():
                    # Fall back to original file if ffmpeg is not available
                    logger.warning(
                        f"ffmpeg not available, serving original file for {file_id} (token endpoint)"
                    )
                    return get_content_streaming_response(db_file)

                logger.info(
                    f"ffmpeg available, processing video {file_id} with subtitles (token endpoint)"
                )

                # Process video with embedded subtitles
                cache_key = video_service.process_video_with_subtitles(
                    db=db,
                    file_id=file_id,
                    original_object_name=db_file.storage_path,
                    user_id=user.id,
                    include_speakers=include_speakers,
                    output_format="mp4",
                )

                logger.info(f"Video processing complete, streaming processed video: {cache_key}")

                # Stream the processed video through backend
                from fastapi.responses import StreamingResponse

                # Get range header for video streaming support
                range_header = None
                # Note: request object not available here, will handle basic streaming

                file_stream, _, _, total_length = video_service._get_cache_file_stream(
                    cache_key, range_header
                )

                # Generate proper filename for download
                base_name = (
                    db_file.filename.rsplit(".", 1)[0]
                    if "." in db_file.filename
                    else db_file.filename
                )
                download_filename = f"{base_name}_with_subtitles.mp4"

                headers = {
                    "Content-Disposition": f'attachment; filename="{download_filename}"',
                    "Content-Type": "video/mp4",
                    "Accept-Ranges": "bytes",
                }

                if total_length:
                    headers["Content-Length"] = str(total_length)

                return StreamingResponse(
                    content=file_stream, media_type="video/mp4", headers=headers
                )

            except Exception as e:
                logger.error(
                    f"Failed to process video with subtitles for file {file_id} (token endpoint): {e}",
                    exc_info=True,
                )
                # Fall back to original file on error

        # Return original file
        return get_content_streaming_response(db_file)

    except JWTError as e:
        raise HTTPException(status_code=401, detail="Invalid token") from e
    except Exception as e:
        logger.error(f"Error in download with token: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed") from e


@router.get("/{file_uuid}/video")
async def video_file(file_uuid: str, request: Request, db: Session = Depends(get_db)):
    """
    Direct video endpoint for video player
    No authentication required - this is a public endpoint for video files only
    """
    from app.utils.uuid_helpers import get_file_by_uuid
    db_file = get_file_by_uuid(db, file_uuid)
    validate_file_exists(db_file)

    range_header = request.headers.get("range")
    return get_video_streaming_response(db_file, range_header)


@router.get("/{file_uuid}/simple-video")
async def simple_video(file_uuid: str, request: Request, db: Session = Depends(get_db)):
    """
    Enhanced video streaming endpoint that efficiently serves video content with YouTube-like streaming.
    """
    from app.utils.uuid_helpers import get_file_by_uuid
    db_file = get_file_by_uuid(db, file_uuid)
    validate_file_exists(db_file)

    range_header = request.headers.get("range")
    return get_enhanced_video_streaming_response(db_file, range_header)


@router.get("/{file_uuid}/thumbnail")
async def get_thumbnail(file_uuid: str, db: Session = Depends(get_db)):
    """
    Get the thumbnail image for a media file.
    No authentication required - this is a public endpoint for thumbnail images only.
    """
    from app.utils.uuid_helpers import get_file_by_uuid
    db_file = get_file_by_uuid(db, file_uuid)
    validate_file_exists(db_file)
    return get_thumbnail_streaming_response(db_file)


@router.get("/metadata-filters", response_model=dict)
def get_metadata_filters_endpoint(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)
):
    """Get available metadata filters like formats, codecs, etc."""
    return get_metadata_filters(db, current_user.id)


@router.put("/{file_uuid}/transcript/segments/{segment_id}", response_model=TranscriptSegment)
def update_transcript_segment(
    file_uuid: str,
    segment_id: int,
    segment_update: TranscriptSegmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a specific transcript segment"""
    from .crud import update_single_transcript_segment

    # Update the transcript segment
    result = update_single_transcript_segment(db, file_uuid, segment_id, segment_update, current_user)

    # Transcript has been updated - subtitles will be regenerated on-demand

    return result


@router.post("/{file_uuid}/reprocess", response_model=MediaFileSchema)
async def reprocess_media_file(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Reprocess a media file for transcription"""
    return await process_file_reprocess(file_uuid, db, current_user)


@router.delete("/{file_uuid}/cache", status_code=204)
def clear_video_cache(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Clear cached processed videos for a file (e.g., after speaker name updates)"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Verify user owns the file or is admin
        is_admin = current_user.role == "admin"
        db_file = get_media_file_by_uuid(db, file_uuid, current_user.id, is_admin=is_admin)
        file_id = db_file.id  # Get internal ID for cache operations

        # Clear the cache using video processing service
        from app.services.minio_service import MinIOService
        from app.services.video_processing_service import VideoProcessingService

        minio_service = MinIOService()
        video_service = VideoProcessingService(minio_service)

        # Clear cached videos for this file
        video_service.clear_cache_for_media_file(db, file_id)

        logger.info(f"Cleared video cache for file {file_id} after speaker updates")

        return None

    except Exception as e:
        logger.error(f"Error clearing video cache for file {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error clearing video cache: {str(e)}",
        ) from e


@router.post("/{file_uuid}/analytics/refresh", status_code=204)
def refresh_analytics(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Refresh analytics for a media file by recomputing them"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Verify user owns the file or is admin
        is_admin = current_user.role == "admin"
        db_file = get_media_file_by_uuid(db, file_uuid, current_user.id, is_admin=is_admin)
        file_id = db_file.id  # Get internal ID for analytics refresh

        # Refresh analytics using the analytics service
        from app.services.analytics_service import AnalyticsService

        success = AnalyticsService.refresh_analytics(db, file_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to refresh analytics",
            )

        logger.info(f"Refreshed analytics for file {file_id}")

        return None

    except Exception as e:
        logger.error(f"Error refreshing analytics for file {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error refreshing analytics: {str(e)}",
        ) from e


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
    "get_thumbnail_streaming_response",
]
