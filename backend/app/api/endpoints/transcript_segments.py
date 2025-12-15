"""API endpoints for transcript segment operations."""

import logging
from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.models.media import MediaFile
from app.models.media import Speaker
from app.models.media import TranscriptSegment
from app.models.user import User
from app.schemas.media import TranscriptSegment as TranscriptSegmentSchema
from app.schemas.transcript import SegmentSpeakerUpdate
from app.utils.uuid_helpers import get_by_uuid

logger = logging.getLogger(__name__)

router = APIRouter()


def _cleanup_orphaned_speaker(db: Session, speaker_id: int) -> bool:
    """
    Delete a speaker if it has no remaining segments.

    This is called after a segment is reassigned to clean up speakers
    that are no longer used. This keeps the speaker list clean and
    prevents accumulation of unused speakers.

    Args:
        db: Database session
        speaker_id: ID of the speaker to check

    Returns:
        True if the speaker was deleted, False otherwise
    """
    if not speaker_id:
        return False

    # Check if speaker has any remaining segments
    segment_count = (
        db.query(TranscriptSegment).filter(TranscriptSegment.speaker_id == speaker_id).count()
    )

    if segment_count == 0:
        # Speaker has no segments - delete it
        speaker = db.query(Speaker).filter(Speaker.id == speaker_id).first()
        if speaker:
            speaker_uuid = speaker.uuid
            speaker_name = speaker.name
            db.delete(speaker)
            db.commit()
            logger.info(
                f"Deleted orphaned speaker {speaker_uuid} ({speaker_name}) - no remaining segments"
            )
            return True

    return False


def _get_new_speaker_id(
    db: Session, update: SegmentSpeakerUpdate, segment: TranscriptSegment, current_user: User
) -> Optional[int]:
    """
    Resolve and validate the new speaker ID from the update request.

    Args:
        db: Database session
        update: SegmentSpeakerUpdate containing the new speaker UUID (or null)
        segment: The segment being updated
        current_user: Currently authenticated user

    Returns:
        The speaker ID if valid, None if unassigning

    Raises:
        HTTPException 400: Invalid speaker UUID or speaker doesn't belong to same file
        HTTPException 403: User doesn't own the speaker
    """
    if update.speaker_uuid is None:
        return None

    # Look up the speaker by UUID
    speaker = get_by_uuid(db, Speaker, update.speaker_uuid, error_message="Speaker not found")

    # Verify the speaker belongs to the same media file
    if speaker.media_file_id != segment.media_file_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Speaker does not belong to the same media file as this segment",
        )

    # Verify the user owns this speaker
    if speaker.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to use this speaker",
        )

    return speaker.id


def _handle_speaker_change(
    db: Session,
    original_speaker_id: Optional[int],
    new_speaker_id: Optional[int],
    media_file_id: int,
) -> None:
    """
    Handle side effects of speaker assignment change.

    Cleans up orphaned speakers and refreshes analytics.

    Args:
        db: Database session
        original_speaker_id: Previous speaker ID (or None)
        new_speaker_id: New speaker ID (or None)
        media_file_id: ID of the media file for analytics refresh
    """
    if original_speaker_id == new_speaker_id:
        return

    # Check if the old speaker is now orphaned (no remaining segments)
    # and delete it if so - this keeps the speaker list clean
    if original_speaker_id:
        _cleanup_orphaned_speaker(db, original_speaker_id)

    try:
        from app.services.analytics_service import AnalyticsService

        AnalyticsService.refresh_analytics(db, media_file_id)
        logger.info(f"Refreshed analytics for file {media_file_id} after segment speaker change")
    except Exception as e:
        # Don't fail the operation if analytics refresh fails
        logger.warning(f"Failed to refresh analytics after segment speaker change: {e}")


@router.put("/segments/{segment_uuid}/speaker", response_model=TranscriptSegmentSchema)
def update_segment_speaker(
    segment_uuid: str,
    update: SegmentSpeakerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Update the speaker assignment for a transcript segment.

    This endpoint allows users to reassign a transcript segment to a different speaker
    or unassign it completely. The segment must belong to a media file owned by the user.

    Args:
        segment_uuid: UUID of the transcript segment to update
        update: SegmentSpeakerUpdate containing the new speaker UUID (or null)
        db: Database session
        current_user: Currently authenticated user

    Returns:
        Updated TranscriptSegment with speaker information

    Raises:
        HTTPException 404: Segment not found
        HTTPException 403: User does not own the media file
        HTTPException 400: Invalid speaker UUID or speaker doesn't belong to same file
    """
    # Get the segment by UUID
    segment = get_by_uuid(
        db, TranscriptSegment, segment_uuid, error_message="Transcript segment not found"
    )

    # Get the media file to verify ownership
    media_file = db.query(MediaFile).filter(MediaFile.id == segment.media_file_id).first()
    if not media_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found")

    # Verify the user owns this file
    if media_file.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this transcript segment",
        )

    # Track original speaker_id for change detection
    original_speaker_id = segment.speaker_id

    # Resolve and validate the new speaker
    new_speaker_id = _get_new_speaker_id(db, update, segment, current_user)

    # Update the segment's speaker
    segment.speaker_id = new_speaker_id
    db.commit()
    db.refresh(segment)

    # Handle side effects of speaker change (cleanup orphans, refresh analytics)
    _handle_speaker_change(db, original_speaker_id, new_speaker_id, media_file.id)

    # Format the response with speaker details
    def format_timestamp(seconds: float) -> str:
        """Format seconds as MM:SS or H:MM:SS"""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        if minutes >= 60:
            hours = minutes // 60
            minutes = minutes % 60
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    response_data = TranscriptSegmentSchema(
        uuid=segment.uuid,
        media_file_id=media_file.uuid,
        start_time=segment.start_time,
        end_time=segment.end_time,
        text=segment.text,
        speaker_id=segment.speaker.uuid if segment.speaker else None,
        speaker=segment.speaker,
        formatted_timestamp=format_timestamp(segment.start_time),
        display_timestamp=format_timestamp(segment.start_time),
        speaker_label=(segment.speaker.name if segment.speaker else None),  # Original speaker ID
        resolved_speaker_name=(
            segment.speaker.display_name or segment.speaker.name if segment.speaker else None
        ),
    )

    logger.info(
        f"Updated segment {segment_uuid} speaker assignment to "
        f"{'speaker ' + update.speaker_uuid if update.speaker_uuid else 'no speaker'}"
    )

    return response_data
