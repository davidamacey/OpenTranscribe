"""
API endpoints for subtitle generation.
"""

import io
import logging
import zipfile

from fastapi import APIRouter
from fastapi import Body
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Query
from fastapi.responses import Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.models.user import User
from app.schemas.media import SubtitleValidationResult
from app.services.subtitle_service import SubtitleService
from app.utils.uuid_helpers import get_file_by_uuid_with_permission

router = APIRouter()
logger = logging.getLogger(__name__)


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


class BulkExportRequest(BaseModel):
    """Request for bulk subtitle export."""

    file_uuids: list[str]
    subtitle_format: str = "srt"
    include_speakers: bool = True


@router.post("/bulk-export", response_class=StreamingResponse)
async def bulk_export_subtitles(
    request: BulkExportRequest = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Export subtitles for multiple files as a single ZIP download.

    Generates subtitle files for each requested file and bundles them into
    a ZIP archive. Files that are not completed or not accessible are skipped.
    """
    if not request.file_uuids:
        raise HTTPException(status_code=400, detail="No file UUIDs provided")

    if len(request.file_uuids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 files per export")

    format_lower = request.subtitle_format.lower()
    if format_lower not in ("srt", "webvtt", "txt"):
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format_lower}")

    ext = "vtt" if format_lower == "webvtt" else format_lower
    zip_buffer = io.BytesIO()
    exported = 0
    skipped = 0

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_uuid in request.file_uuids:
            try:
                media_file = get_file_by_uuid_with_permission(db, file_uuid, int(current_user.id))
                file_id = int(media_file.id)

                if media_file.status != "completed":
                    skipped += 1
                    continue

                if format_lower == "webvtt":
                    content = SubtitleService.generate_webvtt_content(
                        db, file_id, request.include_speakers
                    )
                elif format_lower == "txt":
                    content = SubtitleService.generate_txt_content(
                        db, file_id, request.include_speakers
                    )
                else:
                    content = SubtitleService.generate_srt_content(
                        db, file_id, request.include_speakers
                    )

                if not content.strip():
                    skipped += 1
                    continue

                base_name = (
                    media_file.filename.rsplit(".", 1)[0]
                    if "." in media_file.filename
                    else media_file.filename
                )
                zf.writestr(f"{base_name}.{ext}", content.encode("utf-8"))
                exported += 1

            except HTTPException:
                skipped += 1
            except Exception as e:
                logger.warning(f"Failed to export subtitles for {file_uuid}: {e}")
                skipped += 1

    if exported == 0:
        raise HTTPException(
            status_code=404,
            detail="No files could be exported. Ensure files are completed and accessible.",
        )

    zip_buffer.seek(0)
    zip_filename = f"transcripts_{format_lower}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"',
            "Content-Length": str(zip_buffer.getbuffer().nbytes),
            "X-Exported-Count": str(exported),
            "X-Skipped-Count": str(skipped),
        },
    )


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
