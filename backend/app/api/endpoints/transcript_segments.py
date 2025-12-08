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

    # Handle speaker assignment
    new_speaker_id: Optional[int] = None
    if update.speaker_uuid is not None:
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

        new_speaker_id = speaker.id

    # Update the segment's speaker
    segment.speaker_id = new_speaker_id
    db.commit()
    db.refresh(segment)

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
