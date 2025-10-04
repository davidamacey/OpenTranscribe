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
from app.utils.uuid_helpers import get_speaker_by_uuid
from app.utils.uuid_helpers import get_speaker_profile_by_uuid

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/profiles", response_model=list[dict[str, Any]])
def list_speaker_profiles(
    collection_uuid: Optional[str] = Query(None, description="Filter by collection UUID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all speaker profiles for the current user."""
    try:
        query = db.query(SpeakerProfile).filter(SpeakerProfile.user_id == current_user.id)

        if collection_uuid:
            # Filter by collection - convert UUID to ID
            from app.utils.uuid_helpers import get_by_uuid
            collection = get_by_uuid(db, SpeakerCollection, collection_uuid)
            if collection.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="Not authorized to access this collection")
            collection_id = collection.id

            query = query.join(SpeakerCollectionMember).filter(
                SpeakerCollectionMember.collection_id == collection_id
            )

        profiles = query.all()

        result = []
        for profile in profiles:
            # Count speaker instances
            instance_count = db.query(Speaker).filter(Speaker.profile_id == profile.id).count()

            # Get media files where this speaker appears
            media_files = find_speaker_across_media(profile.id, current_user.id)

            result.append(
                {
                    "id": str(profile.uuid),  # Use UUID for frontend
                    "name": profile.name,
                    "description": profile.description,
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
        raise HTTPException(status_code=500, detail="Internal server error") from e


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
            .filter(SpeakerProfile.user_id == current_user.id, SpeakerProfile.name == name)
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
            "id": str(profile.uuid),  # Use UUID for frontend
            "name": profile.name,
            "description": profile.description,
            "created_at": profile.created_at.isoformat(),
            "updated_at": profile.updated_at.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating speaker profile: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.put("/profiles/{profile_uuid}", response_model=dict[str, Any])
def update_speaker_profile(
    profile_uuid: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a speaker profile."""
    try:
        profile = get_speaker_profile_by_uuid(db, profile_uuid)

        if profile.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this profile")

        profile_id = profile.id

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
            "id": str(profile.uuid),  # Use UUID for frontend
            "name": profile.name,
            "description": profile.description,
            "updated_at": profile.updated_at.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating speaker profile: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/speakers/{speaker_uuid}/assign-profile", response_model=dict[str, Any])
def assign_speaker_to_profile(
    speaker_uuid: str,
    profile_uuid: str,
    confidence: Optional[float] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Assign a speaker instance to a profile."""
    try:
        # Verify speaker exists and belongs to user
        speaker = get_speaker_by_uuid(db, speaker_uuid)
        if speaker.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this speaker")
        speaker_id = speaker.id

        # Verify profile exists and belongs to user
        profile = get_speaker_profile_by_uuid(db, profile_uuid)
        if profile.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this profile")
        profile_id = profile.id

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
        raise HTTPException(status_code=500, detail="Internal server error") from e


def _get_embedding_suggestions(
    db: Session, speaker_id: int, current_user: User, threshold: float
) -> list[dict[str, Any]]:
    """Get profile suggestions based on voice embeddings."""
    from app.core.constants import SPEAKER_CONFIDENCE_HIGH
    from app.services.opensearch_service import get_speaker_embedding
    from app.services.profile_embedding_service import ProfileEmbeddingService
    from app.services.speaker_matching_service import SpeakerMatchingService

    suggestions = []

    # Get speaker object to extract UUID
    from app.models.media import Speaker
    speaker = db.query(Speaker).filter(Speaker.id == speaker_id).first()
    if not speaker:
        return suggestions

    speaker_embedding = get_speaker_embedding(str(speaker.uuid))
    if speaker_embedding:
        profile_matches = ProfileEmbeddingService.calculate_profile_similarity(
            db, speaker_embedding, current_user.id, threshold=threshold
        )

        for match in profile_matches:
            confidence = match["similarity"]
            matching_service = SpeakerMatchingService(db, None)
            confidence_level = matching_service.get_confidence_level(confidence)
            auto_accept = confidence >= SPEAKER_CONFIDENCE_HIGH

            # Generate reason based on confidence
            if confidence >= 0.9:
                reason = f"Very strong voice match (based on {match['embedding_count']} recordings)"
            elif confidence >= 0.8:
                reason = f"Strong voice match (based on {match['embedding_count']} recordings)"
            elif confidence >= 0.7:
                reason = f"Good voice match (based on {match['embedding_count']} recordings)"
            else:
                reason = f"Possible voice match (based on {match['embedding_count']} recordings)"

            suggestions.append(
                {
                    "profile_id": match["profile_id"],
                    "profile_name": match["profile_name"],
                    "confidence": confidence,
                    "confidence_level": confidence_level,
                    "auto_accept": auto_accept,
                    "reason": reason,
                    "source": "voice_embedding",
                    "embedding_count": match["embedding_count"],
                    "last_update": match.get("last_update"),
                }
            )
    else:
        logger.warning(f"No embedding found for speaker {speaker_id}")

    return suggestions


def _get_llm_suggestions(db: Session, speaker: Speaker, current_user: User) -> list[dict[str, Any]]:
    """Get profile suggestions based on LLM analysis."""
    from app.services.speaker_matching_service import SpeakerMatchingService

    suggestions = []
    if speaker.suggested_name and speaker.confidence:
        # Check if suggested_name matches any existing profiles
        suggested_profile = (
            db.query(SpeakerProfile)
            .filter(
                SpeakerProfile.user_id == current_user.id,
                SpeakerProfile.name.ilike(f"%{speaker.suggested_name}%"),
            )
            .first()
        )

        matching_service = SpeakerMatchingService(db, None)
        confidence_level = matching_service.get_confidence_level(speaker.confidence)

        if suggested_profile:
            # Add LLM suggestion for existing profile
            suggestions.append(
                {
                    "profile_id": suggested_profile.id,
                    "profile_name": suggested_profile.name,
                    "confidence": speaker.confidence,
                    "confidence_level": confidence_level,
                    "auto_accept": speaker.confidence >= 0.8,
                    "reason": f"AI content analysis suggests this speaker is '{speaker.suggested_name}'",
                    "source": "llm_analysis",
                    "suggested_name": speaker.suggested_name,
                }
            )
        else:
            # Add LLM suggestion for new profile creation
            suggestions.append(
                {
                    "profile_id": None,  # Indicates new profile should be created
                    "profile_name": speaker.suggested_name,
                    "confidence": speaker.confidence,
                    "confidence_level": confidence_level,
                    "auto_accept": False,  # Never auto-create new profiles
                    "reason": f"AI content analysis suggests creating new profile for '{speaker.suggested_name}'",
                    "source": "llm_analysis",
                    "suggested_name": speaker.suggested_name,
                    "create_new": True,
                }
            )

    return suggestions


@router.get("/speakers/{speaker_uuid}/suggestions", response_model=list[dict[str, Any]])
def get_speaker_profile_suggestions(
    speaker_uuid: str,
    threshold: float = Query(ConfidenceLevel.MEDIUM, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get profile suggestions for a speaker based on both embeddings and LLM analysis."""
    try:
        # Verify speaker exists and belongs to user
        speaker = get_speaker_by_uuid(db, speaker_uuid)
        if speaker.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this speaker")
        speaker_id = speaker.id

        # Check if speaker already has a profile
        if speaker.profile_id:
            return []

        # Get media file for audio processing
        media_file = db.query(MediaFile).filter(MediaFile.id == speaker.media_file_id).first()
        if not media_file:
            return []

        # Get suggestions from different sources
        suggestions = []
        suggestions.extend(_get_embedding_suggestions(db, speaker_id, current_user, threshold))
        suggestions.extend(_get_llm_suggestions(db, speaker, current_user))

        # Sort suggestions by confidence (highest first) and source priority
        def sort_key(suggestion):
            source_priority = 0 if suggestion["source"] == "voice_embedding" else 1
            return (source_priority, -suggestion["confidence"])

        suggestions.sort(key=sort_key)
        return suggestions

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting speaker suggestions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/profiles/{profile_uuid}/occurrences", response_model=list[dict[str, Any]])
def get_speaker_profile_occurrences(
    profile_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get all media files where a speaker profile appears."""
    try:
        # Verify profile exists and belongs to user
        profile = get_speaker_profile_by_uuid(db, profile_uuid)
        if profile.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this profile")
        profile_id = profile.id

        # Initialize matching service
        embedding_service = SpeakerEmbeddingService()
        matching_service = SpeakerMatchingService(db, embedding_service)

        # Get occurrences
        occurrences = matching_service.find_speaker_occurrences(profile_id, current_user.id)

        return occurrences

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting speaker occurrences: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete("/profiles/{profile_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_speaker_profile(
    profile_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Delete a speaker profile."""
    try:
        profile = get_speaker_profile_by_uuid(db, profile_uuid)
        if profile.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this profile")
        profile_id = profile.id

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
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/collections", response_model=list[dict[str, Any]])
def list_speaker_collections(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)
):
    """List all speaker collections for the current user."""
    try:
        collections = (
            db.query(SpeakerCollection).filter(SpeakerCollection.user_id == current_user.id).all()
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
                    "id": str(collection.uuid),  # Use UUID for frontend
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
        raise HTTPException(status_code=500, detail="Internal server error") from e


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
            raise HTTPException(status_code=400, detail="Collection with this name already exists")

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
            "id": str(collection.uuid),  # Use UUID for frontend
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
        raise HTTPException(status_code=500, detail="Internal server error") from e
