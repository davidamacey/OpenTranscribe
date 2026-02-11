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
from app.models.user import User
from app.schemas.media import SubtitleValidationResult
from app.services.subtitle_service import SubtitleService
from app.utils.uuid_helpers import get_file_by_uuid_with_permission

router = APIRouter()


@router.get("/{file_uuid}/subtitles", response_class=Response)
async def get_subtitles(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    include_speakers: bool = Query(True, description="Include speaker labels in subtitles"),
    subtitle_format: str = Query("srt", description="Subtitle format (srt, webvtt, txt)"),
):
    """
    Generate and download subtitles for a media file.

    Returns subtitles in the requested format (SRT by default).
    Supports: srt, webvtt, txt (plain text with timestamps).
    """
    # Get media file and check permissions
    media_file = get_file_by_uuid_with_permission(db, file_uuid, int(current_user.id))
    file_id = int(media_file.id)  # Get internal ID for subtitle generation

    if media_file.status != "completed":
        raise HTTPException(status_code=400, detail="Transcription not completed yet")

    try:
        # Generate subtitle content based on format
        format_lower = subtitle_format.lower()
        if format_lower == "webvtt":
            subtitle_content = SubtitleService.generate_webvtt_content(
                db, file_id, include_speakers
            )
        elif format_lower == "txt":
            subtitle_content = SubtitleService.generate_txt_content(db, file_id, include_speakers)
        else:
            subtitle_content = SubtitleService.generate_srt_content(db, file_id, include_speakers)

        if not subtitle_content.strip():
            raise HTTPException(status_code=404, detail="No transcript available for this file")

        # Determine content type based on format
        content_type_map = {
            "srt": "application/x-subrip",
            "webvtt": "text/vtt",
            "txt": "text/plain",
        }
        content_type = content_type_map.get(format_lower, "text/plain")

        # Generate filename
        base_filename = (
            media_file.filename.rsplit(".", 1)[0]
            if "." in media_file.filename
            else media_file.filename
        )
        filename = f"{base_filename}.{format_lower}"

        return Response(
            content=subtitle_content,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(subtitle_content.encode("utf-8"))),
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate subtitles: {str(e)}"
        ) from e


@router.get("/{file_uuid}/subtitles/validate", response_model=SubtitleValidationResult)
async def validate_subtitles(
    file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Validate subtitle timing and content for a media file.

    Returns validation results including any timing issues or problems found.
    """
    # Get media file and check permissions
    media_file = get_file_by_uuid_with_permission(db, file_uuid, int(current_user.id))
    file_id = int(media_file.id)  # Get internal ID for validation

    if media_file.status != "completed":
        raise HTTPException(status_code=400, detail="Transcription not completed yet")

    try:
        # Validate subtitle timing
        issues = SubtitleService.validate_subtitle_timing(db, file_id)

        # Get segment count and total duration via SQL aggregation
        from sqlalchemy import func

        from app.models.media import TranscriptSegment

        stats = (
            db.query(
                func.count(TranscriptSegment.id),
                func.max(TranscriptSegment.end_time),
            )
            .filter(TranscriptSegment.media_file_id == file_id)
            .first()
        )

        total_segments = stats[0] if stats else 0
        total_duration = float(stats[1]) if stats and stats[1] is not None else 0.0

        return SubtitleValidationResult(
            is_valid=len(issues) == 0,
            issues=issues,
            total_segments=total_segments,
            total_duration=float(total_duration),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to validate subtitles: {str(e)}"
        ) from e


@router.get("/supported-formats")
async def get_supported_formats():
    """
    Get list of supported subtitle formats.

    Formats:
    - srt: SubRip Text (most compatible)
    - webvtt: Web Video Text Tracks (web-friendly)
    - txt: Plain text with timestamps (human-readable)
    """
    return {"subtitle_formats": ["srt", "webvtt", "txt"]}
