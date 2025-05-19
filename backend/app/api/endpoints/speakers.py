from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.base import get_db
from app.models.user import User
from app.models.media import Speaker, TranscriptSegment
from app.schemas.media import Speaker as SpeakerSchema, SpeakerUpdate
from app.api.endpoints.auth import get_current_active_user

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
    new_speaker = Speaker(
        name=speaker.name,
        user_id=current_user.id
    )
    
    db.add(new_speaker)
    db.commit()
    db.refresh(new_speaker)
    
    return new_speaker


@router.get("/", response_model=List[SpeakerSchema])
def list_speakers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    List all speakers for the current user
    """
    try:
        speakers = db.query(Speaker).filter(Speaker.user_id == current_user.id).all()
        return speakers
    except Exception as e:
        print(f"Error in list_speakers: {e}")
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
    Update a speaker's information
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
