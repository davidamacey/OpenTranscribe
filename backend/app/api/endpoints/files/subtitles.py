"""
API endpoints for subtitle generation.
"""

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.models.media import MediaFile
from app.models.user import User
from app.schemas.media import SubtitleValidationResult
from app.services.subtitle_service import SubtitleService

router = APIRouter()


@router.get("/{file_id}/subtitles", response_class=Response)
async def get_subtitles(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    include_speakers: bool = Query(
        True, description="Include speaker labels in subtitles"
    ),
    format: str = Query("srt", description="Subtitle format (srt, webvtt)"),
):
    """
    Generate and download subtitles for a media file.

    Returns subtitles in the requested format (SRT by default).
    """
    # Get media file and check permissions
    media_file = (
        db.query(MediaFile)
        .filter(MediaFile.id == file_id, MediaFile.user_id == current_user.id)
        .first()
    )

    if not media_file:
        raise HTTPException(status_code=404, detail="Media file not found")

    if media_file.status != "completed":
        raise HTTPException(status_code=400, detail="Transcription not completed yet")

    try:
        # Generate subtitle content based on format
        if format.lower() == "webvtt":
            subtitle_content = SubtitleService.generate_webvtt_content(
                db, file_id, include_speakers
            )
        else:
            subtitle_content = SubtitleService.generate_srt_content(
                db, file_id, include_speakers
            )

        if not subtitle_content.strip():
            raise HTTPException(
                status_code=404, detail="No transcript available for this file"
            )

        # Determine content type based on format
        content_type_map = {"srt": "application/x-subrip", "webvtt": "text/vtt"}
        content_type = content_type_map.get(format.lower(), "text/plain")

        # Generate filename
        base_filename = (
            media_file.filename.rsplit(".", 1)[0]
            if "." in media_file.filename
            else media_file.filename
        )
        filename = f"{base_filename}.{format.lower()}"

        return Response(
            content=subtitle_content,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(subtitle_content.encode("utf-8"))),
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate subtitles: {str(e)}"
        )


@router.get("/{file_id}/subtitles/validate", response_model=SubtitleValidationResult)
async def validate_subtitles(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Validate subtitle timing and content for a media file.

    Returns validation results including any timing issues or problems found.
    """
    # Get media file and check permissions
    media_file = (
        db.query(MediaFile)
        .filter(MediaFile.id == file_id, MediaFile.user_id == current_user.id)
        .first()
    )

    if not media_file:
        raise HTTPException(status_code=404, detail="Media file not found")

    if media_file.status != "completed":
        raise HTTPException(status_code=400, detail="Transcription not completed yet")

    try:
        # Validate subtitle timing
        issues = SubtitleService.validate_subtitle_timing(db, file_id)

        # Get segment count and total duration
        from app.models.media import TranscriptSegment

        segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.media_file_id == file_id)
            .all()
        )

        total_segments = len(segments)
        total_duration = max([seg.end_time for seg in segments]) if segments else 0.0

        return SubtitleValidationResult(
            is_valid=len(issues) == 0,
            issues=issues,
            total_segments=total_segments,
            total_duration=total_duration,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to validate subtitles: {str(e)}"
        )


@router.get("/supported-formats")
async def get_supported_formats():
    """
    Get list of supported subtitle formats.
    """
    return {"subtitle_formats": ["srt", "webvtt"]}
