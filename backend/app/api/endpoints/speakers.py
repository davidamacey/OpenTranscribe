from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid
import logging

from app.db.base import get_db
from app.models.user import User
from app.models.media import Speaker, TranscriptSegment
from app.schemas.media import Speaker as SpeakerSchema, SpeakerUpdate
from app.api.endpoints.auth import get_current_active_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.delete("/{speaker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_speaker(
    speaker_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Delete a speaker
    """
    # Find the speaker
    speaker = db.query(Speaker).filter(
        Speaker.id == speaker_id,
        Speaker.user_id == current_user.id
    ).first()
    
    if not speaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Speaker not found"
        )
    
    # Delete the speaker
    db.delete(speaker)
    db.commit()
    
    return None


@router.post("/", response_model=SpeakerSchema)
def create_speaker(
    speaker: SpeakerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Create a new speaker
    """
    # Generate a UUID for the new speaker
    speaker_uuid = str(uuid.uuid4())
    
    new_speaker = Speaker(
        name=speaker.name,
        display_name=speaker.display_name,
        uuid=speaker_uuid,
        user_id=current_user.id,
        verified=speaker.verified if speaker.verified is not None else False
    )
    
    # If display_name is provided, mark as verified
    if speaker.display_name and speaker.display_name.strip():
        new_speaker.verified = True
    
    db.add(new_speaker)
    db.commit()
    db.refresh(new_speaker)
    
    return new_speaker


@router.get("/", response_model=List[SpeakerSchema])
def list_speakers(
    verified_only: bool = False,
    file_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    List all speakers for the current user
    
    Args:
        verified_only: If true, return only verified speakers
        file_id: If provided, return only speakers associated with this file
    """
    try:
        query = db.query(Speaker).filter(Speaker.user_id == current_user.id)
        
        # Filter by verification status if requested
        if verified_only:
            query = query.filter(Speaker.verified == True)
        
        # Filter by file_id if provided
        if file_id is not None:
            # Get the speaker IDs that appear in this file's transcript segments
            speaker_ids = db.query(TranscriptSegment.speaker_id).filter(
                TranscriptSegment.media_file_id == file_id
            ).distinct().all()
            speaker_ids = [s[0] for s in speaker_ids if s[0] is not None]
            
            if speaker_ids:
                query = query.filter(Speaker.id.in_(speaker_ids))
            else:
                # No speakers in this file, return empty list
                return []
            
        speakers = query.order_by(Speaker.verified.desc(), Speaker.name).all()
        return speakers
    except Exception as e:
        logger.error(f"Error in list_speakers: {e}")
        # If there's an error or no speakers, return an empty list
        return []


@router.get("/{speaker_id}", response_model=SpeakerSchema)
def get_speaker(
    speaker_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get details of a specific speaker
    """
    speaker = db.query(Speaker).filter(
        Speaker.id == speaker_id,
        Speaker.user_id == current_user.id
    ).first()
    
    if not speaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Speaker not found"
        )
    
    return speaker


@router.put("/{speaker_id}", response_model=SpeakerSchema)
def update_speaker(
    speaker_id: int,
    speaker_update: SpeakerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Update a speaker's information including display name and verification status
    """
    speaker = db.query(Speaker).filter(
        Speaker.id == speaker_id,
        Speaker.user_id == current_user.id
    ).first()
    
    if not speaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Speaker not found"
        )
    
    # Update fields
    for field, value in speaker_update.model_dump(exclude_unset=True).items():
        setattr(speaker, field, value)
    
    # If display_name is being set, automatically mark as verified
    if speaker_update.display_name is not None and speaker_update.display_name.strip():
        speaker.verified = True
    
    db.commit()
    db.refresh(speaker)
    
    return speaker


@router.post("/{speaker_id}/merge/{target_speaker_id}", response_model=SpeakerSchema)
def merge_speakers(
    speaker_id: int,
    target_speaker_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Merge two speakers into one (target absorbs source)
    """
    # Get both speakers
    source_speaker = db.query(Speaker).filter(
        Speaker.id == speaker_id,
        Speaker.user_id == current_user.id
    ).first()
    
    target_speaker = db.query(Speaker).filter(
        Speaker.id == target_speaker_id,
        Speaker.user_id == current_user.id
    ).first()
    
    if not source_speaker or not target_speaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or both speakers not found"
        )
    
    # Update all transcript segments from source to target
    db.query(TranscriptSegment).filter(
        TranscriptSegment.speaker_id == source_speaker.id
    ).update({"speaker_id": target_speaker.id})
    
    # Optionally, merge the embedding vectors (e.g., by averaging)
    # This would require more complex logic in a real implementation
    
    # Delete the source speaker
    db.delete(source_speaker)
    db.commit()
    db.refresh(target_speaker)
    
    # In a real implementation, we would also need to update the OpenSearch index
    # to remove the source speaker and update/merge the embeddings
    
    return target_speaker
