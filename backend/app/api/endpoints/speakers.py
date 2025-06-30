from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import uuid
import logging
import re

from app.db.base import get_db
from app.models.user import User
from app.models.media import Speaker, SpeakerProfile, TranscriptSegment
from app.schemas.media import Speaker as SpeakerSchema, SpeakerUpdate, SpeakerProfile as SpeakerProfileSchema
from app.services.speaker_matching_service import SpeakerMatchingService, ConfidenceLevel
from app.services.speaker_embedding_service import SpeakerEmbeddingService
from app.services.opensearch_service import update_speaker_display_name, get_speaker_embedding
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
    media_file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Create a new speaker for a specific media file
    """
    # Generate a UUID for the new speaker
    speaker_uuid = str(uuid.uuid4())
    
    new_speaker = Speaker(
        name=speaker.name,
        display_name=speaker.display_name,
        uuid=speaker_uuid,
        user_id=current_user.id,
        media_file_id=media_file_id,
        verified=speaker.verified if speaker.verified is not None else False
    )
    
    # If display_name is provided, mark as verified
    if speaker.display_name and speaker.display_name.strip():
        new_speaker.verified = True
    
    db.add(new_speaker)
    db.commit()
    db.refresh(new_speaker)
    
    return new_speaker


@router.get("/")
def list_speakers(
    verified_only: bool = False,
    file_id: Optional[int] = None,
    for_filter: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    List all speakers for the current user
    
    Args:
        verified_only: If true, return only verified speakers
        file_id: If provided, return only speakers associated with this file
        for_filter: If true, return only speakers with distinct display names for filtering
    """
    try:
        query = db.query(Speaker).filter(Speaker.user_id == current_user.id)
        
        # Filter by verification status if requested
        if verified_only:
            query = query.filter(Speaker.verified == True)
        
        # If this is for filtering, only return speakers with meaningful display names
        if for_filter:
            query = query.filter(
                Speaker.display_name.isnot(None), 
                Speaker.display_name != "",
                # Exclude display names that are just the original speaker labels (SPEAKER_XX)
                ~Speaker.display_name.op('~')(r'^SPEAKER_\d+$')
            )
        
        # Filter by file_id if provided
        if file_id is not None:
            # Filter speakers directly by media_file_id
            query = query.filter(Speaker.media_file_id == file_id)
            
        speakers = query.all()
        
        # Sort speakers by SPEAKER_XX numbering for consistent ordering
        def get_speaker_number(speaker):
            match = re.match(r'^SPEAKER_(\d+)$', speaker.name)
            return int(match.group(1)) if match else 999  # Unknown speakers go to end
        
        speakers.sort(key=lambda s: (not s.verified, get_speaker_number(s), s.display_name or s.name))
        
        # If for_filter, group by display_name to avoid duplicates
        if for_filter:
            seen_names = set()
            unique_speakers = []
            for speaker in speakers:
                display_name = speaker.display_name or speaker.name
                # Additional check: skip SPEAKER_XX patterns even if they somehow made it through
                if (display_name not in seen_names and 
                    not display_name.startswith('SPEAKER_') and
                    display_name.strip() != ""):
                    seen_names.add(display_name)
                    unique_speakers.append(speaker)
            return unique_speakers
        
        # Initialize services for matching (without loading pyannote model)
        matching_service = SpeakerMatchingService(db, None)
        
        # Add profile information to speakers
        result = []
        for speaker in speakers:
            # If speaker doesn't have a suggestion but has an embedding, try to find a match
            if not speaker.suggested_name and not speaker.verified:
                embedding = get_speaker_embedding(speaker.id)
                if embedding:
                    import numpy as np
                    match = matching_service.match_speaker_to_known_speakers(
                        np.array(embedding), 
                        current_user.id
                    )
                    if match and match['confidence'] >= 0.5:  # Show suggestions from 50% confidence
                        # Update the speaker with the suggestion
                        speaker.suggested_name = match['suggested_name']
                        speaker.confidence = match['confidence']
                        
                        # Auto-populate display_name for high confidence matches (≥75%)
                        if match['confidence'] >= 0.75 and not speaker.display_name:
                            speaker.display_name = match['suggested_name']
                            speaker.verified = True
                        
                        db.commit()
            
            # Get cross-video matches for this speaker
            cross_video_matches = matching_service.get_speaker_matches(speaker.id)
            logger.info(f"Speaker {speaker.id}: get_speaker_matches returned {len(cross_video_matches)} matches")
            
            # For unlabeled speakers without suggestions, find potential cross-video matches
            if not speaker.suggested_name and not speaker.verified:
                embedding = get_speaker_embedding(speaker.id)
                logger.info(f"Speaker {speaker.id} ({speaker.name}): embedding found = {embedding is not None}")
                if embedding:
                    import numpy as np
                    # Find unlabeled speaker matches across videos
                    unlabeled_matches = matching_service.find_unlabeled_speaker_matches(
                        np.array(embedding), 
                        current_user.id,
                        speaker.id
                    )
                    logger.info(f"Speaker {speaker.id}: found {len(unlabeled_matches)} unlabeled matches")
                    
                    # Add unlabeled matches to cross_video_matches
                    if unlabeled_matches:
                        # Merge with existing matches, avoiding duplicates
                        existing_speaker_ids = {match.get('speaker_id') for match in cross_video_matches}
                        for unlabeled_match in unlabeled_matches:
                            if unlabeled_match['speaker_id'] not in existing_speaker_ids:
                                cross_video_matches.append(unlabeled_match)
                        
                        # Set confidence to highest match for UI display
                        if cross_video_matches:
                            highest_match = max(cross_video_matches, key=lambda x: x['confidence'])
                            speaker.confidence = highest_match['confidence']
                else:
                    logger.warning(f"No embedding found for speaker {speaker.id} ({speaker.name})")
            
            # Add additional match context for UI
            for match in cross_video_matches:
                match['is_cross_video_suggestion'] = True
            
            logger.info(f"Speaker {speaker.name} ({speaker.id}): Total cross_video_matches = {len(cross_video_matches)}")
            
            # Smart suggestion logic: show suggestions but let UI explain the context
            suggested_name = speaker.suggested_name
            if speaker.suggested_name and speaker.confidence and cross_video_matches:
                # Find highest cross-video match confidence
                highest_cross_video_confidence = max(match['confidence'] for match in cross_video_matches)
                
                # Only hide very low confidence suggestions (<50%) when much higher cross-video matches exist (>30% higher)
                if (speaker.confidence < 0.5 and 
                    highest_cross_video_confidence > speaker.confidence + 0.3):
                    suggested_name = None
            
            speaker_dict = {
                "id": speaker.id,
                "name": speaker.name,
                "display_name": speaker.display_name,
                "suggested_name": suggested_name,
                "uuid": speaker.uuid,
                "verified": speaker.verified,
                "user_id": speaker.user_id,
                "confidence": speaker.confidence,
                "created_at": speaker.created_at.isoformat(),
                "media_file_id": speaker.media_file_id,
                "profile": None,
                "cross_video_matches": cross_video_matches
            }
            
            # Add profile information if speaker is assigned to a profile
            if speaker.profile_id and speaker.profile:
                speaker_dict["profile"] = {
                    "id": speaker.profile.id,
                    "name": speaker.profile.name,
                    "description": speaker.profile.description
                }
            
            result.append(speaker_dict)
        
        # Debug log to see what we're returning
        for speaker_data in result:
            logger.info(f"Returning speaker {speaker_data['name']} with {len(speaker_data.get('cross_video_matches', []))} cross_video_matches")
        
        return result
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
        # Clear any suggestion since user has manually set the name
        speaker.suggested_name = None
        speaker.confidence = None
    
    db.commit()
    db.refresh(speaker)
    
    # Update OpenSearch with the new display name
    if speaker_update.display_name is not None:
        try:
            update_speaker_display_name(speaker_id, speaker.display_name)
        except Exception as e:
            logger.error(f"Failed to update speaker display name in OpenSearch: {e}")
    
    # If user just labeled a speaker, trigger retroactive matching for all other speakers
    if speaker_update.display_name is not None and speaker_update.display_name.strip():
        from app.api.endpoints.speaker_update import trigger_retroactive_matching
        trigger_retroactive_matching(speaker, db)
    
    # Clear video cache since speaker labels have changed (affects subtitles)
    try:
        from app.services.minio_service import MinIOService
        from app.services.video_processing_service import VideoProcessingService
        
        minio_service = MinIOService()
        video_processing_service = VideoProcessingService(minio_service)
        video_processing_service.clear_cache_for_media_file(speaker.media_file_id)
    except Exception as e:
        logger.error(f"Warning: Failed to clear video cache after speaker update: {e}")
    
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
    
    # Get media file IDs that are affected
    affected_media_files = {source_speaker.media_file_id, target_speaker.media_file_id}
    
    # Delete the source speaker
    db.delete(source_speaker)
    db.commit()
    db.refresh(target_speaker)
    
    # Clear video cache for affected media files since speaker associations changed
    try:
        from app.services.minio_service import MinIOService
        from app.services.video_processing_service import VideoProcessingService
        
        minio_service = MinIOService()
        video_processing_service = VideoProcessingService(minio_service)
        
        for media_file_id in affected_media_files:
            video_processing_service.clear_cache_for_media_file(media_file_id)
    except Exception as e:
        logger.error(f"Warning: Failed to clear video cache after speaker merge: {e}")
    
    # In a real implementation, we would also need to update the OpenSearch index
    # to remove the source speaker and update/merge the embeddings
    
    return target_speaker


@router.post("/{speaker_id}/verify", response_model=Dict[str, Any])
def verify_speaker_identification(
    speaker_id: int,
    action: str,  # 'accept', 'reject', 'create_profile'
    profile_id: Optional[int] = None,
    profile_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Verify or reject speaker identification suggestions.
    
    Actions:
    - 'accept': Accept suggested profile match
    - 'reject': Reject suggestion and keep unassigned
    - 'create_profile': Create new profile and assign speaker
    """
    try:
        # Get speaker
        speaker = db.query(Speaker).filter(
            Speaker.id == speaker_id,
            Speaker.user_id == current_user.id
        ).first()
        
        if not speaker:
            raise HTTPException(status_code=404, detail="Speaker not found")
        
        if action == "accept":
            if not profile_id:
                raise HTTPException(status_code=400, detail="profile_id required for accept action")
            
            # Verify profile exists
            profile = db.query(SpeakerProfile).filter(
                SpeakerProfile.id == profile_id,
                SpeakerProfile.user_id == current_user.id
            ).first()
            
            if not profile:
                raise HTTPException(status_code=404, detail="Speaker profile not found")
            
            # Assign speaker to profile
            speaker.profile_id = profile_id
            speaker.verified = True
            
            db.commit()
            
            return {
                "status": "accepted",
                "speaker_id": speaker_id,
                "profile_id": profile_id,
                "profile_name": profile.name,
                "message": f"Speaker assigned to profile '{profile.name}'"
            }
        
        elif action == "reject":
            # Mark as verified but don't assign to profile
            speaker.verified = True
            speaker.confidence = None
            
            db.commit()
            
            return {
                "status": "rejected", 
                "speaker_id": speaker_id,
                "message": "Speaker identification suggestion rejected"
            }
        
        elif action == "create_profile":
            if not profile_name:
                raise HTTPException(status_code=400, detail="profile_name required for create_profile action")
            
            # Check if profile with same name exists
            existing_profile = db.query(SpeakerProfile).filter(
                SpeakerProfile.user_id == current_user.id,
                SpeakerProfile.name == profile_name
            ).first()
            
            if existing_profile:
                raise HTTPException(
                    status_code=400,
                    detail="Profile with this name already exists"
                )
            
            # Create new profile
            new_profile = SpeakerProfile(
                user_id=current_user.id,
                name=profile_name,
                uuid=str(uuid.uuid4())
            )
            
            db.add(new_profile)
            db.flush()
            
            # Assign speaker to new profile
            speaker.profile_id = new_profile.id
            speaker.verified = True
            
            db.commit()
            
            return {
                "status": "created_and_assigned",
                "speaker_id": speaker_id,
                "profile_id": new_profile.id,
                "profile_name": profile_name,
                "message": f"Created new profile '{profile_name}' and assigned speaker"
            }
        
        else:
            raise HTTPException(status_code=400, detail="Invalid action. Must be 'accept', 'reject', or 'create_profile'")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying speaker: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{speaker_id}/matches", response_model=List[Dict[str, Any]])
def get_speaker_matches(
    speaker_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all cross-video matches for a specific speaker.
    """
    try:
        # Verify speaker belongs to user
        speaker = db.query(Speaker).filter(
            Speaker.id == speaker_id,
            Speaker.user_id == current_user.id
        ).first()
        
        if not speaker:
            raise HTTPException(status_code=404, detail="Speaker not found")
        
        # Get matches (without loading pyannote model)
        matching_service = SpeakerMatchingService(db, None)
        matches = matching_service.get_speaker_matches(speaker_id)
        
        return matches
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting speaker matches: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{speaker_id}/cross-media", response_model=List[Dict[str, Any]])
def get_speaker_cross_media_occurrences(
    speaker_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all media files where this speaker (or their profile) appears.
    """
    try:
        # Get speaker
        speaker = db.query(Speaker).filter(
            Speaker.id == speaker_id,
            Speaker.user_id == current_user.id
        ).first()
        
        if not speaker:
            raise HTTPException(status_code=404, detail="Speaker not found")
        
        result = []
        
        if speaker.profile_id:
            # Speaker has a profile - find all instances of this profile
            profile_speakers = db.query(Speaker).filter(
                Speaker.profile_id == speaker.profile_id,
                Speaker.user_id == current_user.id
            ).all()
            
            for profile_speaker in profile_speakers:
                media_file = profile_speaker.media_file
                if media_file:
                    result.append({
                        "media_file_id": media_file.id,
                        "filename": media_file.filename,
                        "title": media_file.title or media_file.filename,
                        "upload_time": media_file.upload_time.isoformat(),
                        "speaker_label": profile_speaker.name,
                        "confidence": profile_speaker.confidence,
                        "verified": profile_speaker.verified,
                        "same_speaker": profile_speaker.id == speaker_id
                    })
        else:
            # Speaker has no profile - just return this instance
            media_file = speaker.media_file
            if media_file:
                result.append({
                    "media_file_id": media_file.id,
                    "filename": media_file.filename,
                    "title": media_file.title or media_file.filename,
                    "upload_time": media_file.upload_time.isoformat(),
                    "speaker_label": speaker.name,
                    "confidence": speaker.confidence,
                    "verified": speaker.verified,
                    "same_speaker": True
                })
        
        # Sort by upload time (newest first)
        result.sort(key=lambda x: x["upload_time"], reverse=True)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting cross-media occurrences: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
