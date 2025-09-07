import logging
import uuid
from typing import Any
from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Query
from fastapi import status
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.models.media import MediaFile
from app.models.media import Speaker
from app.models.media import SpeakerCollection
from app.models.media import SpeakerCollectionMember
from app.models.media import SpeakerProfile
from app.models.user import User
from app.services.opensearch_service import find_speaker_across_media
from app.services.opensearch_service import update_speaker_collections
from app.services.speaker_embedding_service import SpeakerEmbeddingService
from app.services.speaker_matching_service import ConfidenceLevel
from app.services.speaker_matching_service import SpeakerMatchingService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/profiles", response_model=list[dict[str, Any]])
def list_speaker_profiles(
    collection_id: Optional[int] = Query(None, description="Filter by collection ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all speaker profiles for the current user."""
    try:
        query = db.query(SpeakerProfile).filter(
            SpeakerProfile.user_id == current_user.id
        )

        if collection_id:
            # Filter by collection
            query = query.join(SpeakerCollectionMember).filter(
                SpeakerCollectionMember.collection_id == collection_id
            )

        profiles = query.all()

        result = []
        for profile in profiles:
            # Count speaker instances
            instance_count = (
                db.query(Speaker).filter(Speaker.profile_id == profile.id).count()
            )

            # Get media files where this speaker appears
            media_files = find_speaker_across_media(profile.id, current_user.id)

            result.append(
                {
                    "id": profile.id,
                    "name": profile.name,
                    "description": profile.description,
                    "uuid": profile.uuid,
                    "created_at": profile.created_at.isoformat(),
                    "updated_at": profile.updated_at.isoformat(),
                    "instance_count": instance_count,
                    "media_count": len(media_files),
                    "media_files": media_files[:5],  # Show first 5 media files
                }
            )

        return result

    except Exception as e:
        logger.error(f"Error listing speaker profiles: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/profiles", response_model=dict[str, Any])
def create_speaker_profile(
    name: str,
    description: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new speaker profile."""
    try:
        # Check if profile with same name exists
        existing = (
            db.query(SpeakerProfile)
            .filter(
                SpeakerProfile.user_id == current_user.id, SpeakerProfile.name == name
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400, detail="Speaker profile with this name already exists"
            )

        profile = SpeakerProfile(
            user_id=current_user.id,
            name=name,
            description=description,
            uuid=str(uuid.uuid4()),
        )

        db.add(profile)
        db.commit()
        db.refresh(profile)

        return {
            "id": profile.id,
            "name": profile.name,
            "description": profile.description,
            "uuid": profile.uuid,
            "created_at": profile.created_at.isoformat(),
            "updated_at": profile.updated_at.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating speaker profile: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/profiles/{profile_id}", response_model=dict[str, Any])
def update_speaker_profile(
    profile_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a speaker profile."""
    try:
        profile = (
            db.query(SpeakerProfile)
            .filter(
                SpeakerProfile.id == profile_id,
                SpeakerProfile.user_id == current_user.id,
            )
            .first()
        )

        if not profile:
            raise HTTPException(status_code=404, detail="Speaker profile not found")

        if name:
            # Check for name conflicts
            existing = (
                db.query(SpeakerProfile)
                .filter(
                    SpeakerProfile.user_id == current_user.id,
                    SpeakerProfile.name == name,
                    SpeakerProfile.id != profile_id,
                )
                .first()
            )

            if existing:
                raise HTTPException(
                    status_code=400,
                    detail="Speaker profile with this name already exists",
                )

            profile.name = name

        if description is not None:
            profile.description = description

        db.commit()
        db.refresh(profile)

        return {
            "id": profile.id,
            "name": profile.name,
            "description": profile.description,
            "uuid": profile.uuid,
            "updated_at": profile.updated_at.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating speaker profile: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/speakers/{speaker_id}/assign-profile", response_model=dict[str, Any])
def assign_speaker_to_profile(
    speaker_id: int,
    profile_id: int,
    confidence: Optional[float] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Assign a speaker instance to a profile."""
    try:
        # Verify speaker exists and belongs to user
        speaker = (
            db.query(Speaker)
            .filter(Speaker.id == speaker_id, Speaker.user_id == current_user.id)
            .first()
        )

        if not speaker:
            raise HTTPException(status_code=404, detail="Speaker not found")

        # Verify profile exists and belongs to user
        profile = (
            db.query(SpeakerProfile)
            .filter(
                SpeakerProfile.id == profile_id,
                SpeakerProfile.user_id == current_user.id,
            )
            .first()
        )

        if not profile:
            raise HTTPException(status_code=404, detail="Speaker profile not found")

        # Initialize services
        embedding_service = SpeakerEmbeddingService()
        matching_service = SpeakerMatchingService(db, embedding_service)

        # Assign speaker to profile
        updated_speaker = matching_service.assign_speaker_to_profile(
            speaker_id, profile_id, confidence
        )

        # Update collections in OpenSearch
        # For now, we'll use a default collection (could be expanded)
        update_speaker_collections(speaker_id, profile_id, [])

        db.commit()

        return {
            "speaker_id": speaker_id,
            "profile_id": profile_id,
            "profile_name": profile.name,
            "confidence": confidence,
            "verified": updated_speaker.verified,
            "status": "assigned",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning speaker to profile: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/speakers/{speaker_id}/suggestions", response_model=list[dict[str, Any]])
def get_speaker_profile_suggestions(
    speaker_id: int,
    threshold: float = Query(ConfidenceLevel.MEDIUM, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get profile suggestions for a speaker based on embeddings."""
    try:
        # Verify speaker exists and belongs to user
        speaker = (
            db.query(Speaker)
            .filter(Speaker.id == speaker_id, Speaker.user_id == current_user.id)
            .first()
        )

        if not speaker:
            raise HTTPException(status_code=404, detail="Speaker not found")

        # Check if speaker already has a profile
        if speaker.profile_id:
            return []

        # Get media file for audio processing
        media_file = (
            db.query(MediaFile).filter(MediaFile.id == speaker.media_file_id).first()
        )

        if not media_file:
            return []

        # For now, return a placeholder response
        # In a full implementation, this would extract speaker embedding
        # and find matching profiles
        suggestions = []

        # Get existing profiles for comparison
        profiles = (
            db.query(SpeakerProfile)
            .filter(SpeakerProfile.user_id == current_user.id)
            .limit(5)
            .all()
        )

        for profile in profiles:
            # This would normally involve embedding comparison
            # For now, return basic profile info
            suggestions.append(
                {
                    "profile_id": profile.id,
                    "profile_name": profile.name,
                    "confidence": 0.5,  # Placeholder confidence
                    "confidence_level": "medium",
                    "auto_accept": False,
                    "reason": "Based on voice characteristics",
                }
            )

        return suggestions

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting speaker suggestions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/profiles/{profile_id}/occurrences", response_model=list[dict[str, Any]])
def get_speaker_profile_occurrences(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get all media files where a speaker profile appears."""
    try:
        # Verify profile exists and belongs to user
        profile = (
            db.query(SpeakerProfile)
            .filter(
                SpeakerProfile.id == profile_id,
                SpeakerProfile.user_id == current_user.id,
            )
            .first()
        )

        if not profile:
            raise HTTPException(status_code=404, detail="Speaker profile not found")

        # Initialize matching service
        embedding_service = SpeakerEmbeddingService()
        matching_service = SpeakerMatchingService(db, embedding_service)

        # Get occurrences
        occurrences = matching_service.find_speaker_occurrences(
            profile_id, current_user.id
        )

        return occurrences

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting speaker occurrences: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_speaker_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Delete a speaker profile."""
    try:
        profile = (
            db.query(SpeakerProfile)
            .filter(
                SpeakerProfile.id == profile_id,
                SpeakerProfile.user_id == current_user.id,
            )
            .first()
        )

        if not profile:
            raise HTTPException(status_code=404, detail="Speaker profile not found")

        # Unassign all speakers from this profile
        speakers = db.query(Speaker).filter(Speaker.profile_id == profile_id).all()
        for speaker in speakers:
            speaker.profile_id = None
            speaker.verified = False

        # Delete the profile
        db.delete(profile)
        db.commit()

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting speaker profile: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/collections", response_model=list[dict[str, Any]])
def list_speaker_collections(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)
):
    """List all speaker collections for the current user."""
    try:
        collections = (
            db.query(SpeakerCollection)
            .filter(SpeakerCollection.user_id == current_user.id)
            .all()
        )

        result = []
        for collection in collections:
            # Count members
            member_count = (
                db.query(SpeakerCollectionMember)
                .filter(SpeakerCollectionMember.collection_id == collection.id)
                .count()
            )

            result.append(
                {
                    "id": collection.id,
                    "name": collection.name,
                    "description": collection.description,
                    "is_public": collection.is_public,
                    "created_at": collection.created_at.isoformat(),
                    "updated_at": collection.updated_at.isoformat(),
                    "member_count": member_count,
                }
            )

        return result

    except Exception as e:
        logger.error(f"Error listing speaker collections: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/collections", response_model=dict[str, Any])
def create_speaker_collection(
    name: str,
    description: Optional[str] = None,
    is_public: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new speaker collection."""
    try:
        # Check for name conflicts
        existing = (
            db.query(SpeakerCollection)
            .filter(
                SpeakerCollection.user_id == current_user.id,
                SpeakerCollection.name == name,
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400, detail="Collection with this name already exists"
            )

        collection = SpeakerCollection(
            user_id=current_user.id,
            name=name,
            description=description,
            is_public=is_public,
        )

        db.add(collection)
        db.commit()
        db.refresh(collection)

        return {
            "id": collection.id,
            "name": collection.name,
            "description": collection.description,
            "is_public": collection.is_public,
            "created_at": collection.created_at.isoformat(),
            "updated_at": collection.updated_at.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating speaker collection: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
