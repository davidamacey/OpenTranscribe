import logging
import re
import uuid
from typing import Any
from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Response
from fastapi import status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.models.media import MediaFile
from app.models.media import Speaker
from app.models.media import SpeakerProfile
from app.models.media import TranscriptSegment
from app.models.user import User
from app.schemas.media import Speaker as SpeakerSchema
from app.schemas.media import SpeakerUpdate
from app.services.opensearch_service import update_speaker_display_name
from app.services.speaker_status_service import SpeakerStatusService
from app.utils.uuid_helpers import get_speaker_by_uuid

logger = logging.getLogger(__name__)

router = APIRouter()


@router.delete("/{speaker_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_speaker(
    speaker_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Delete a speaker
    """
    # Find the speaker by UUID
    speaker = get_speaker_by_uuid(db, speaker_uuid)

    # Verify ownership
    if speaker.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Delete the speaker
    db.delete(speaker)
    db.commit()

    return None


@router.post("/", response_model=SpeakerSchema)
def create_speaker(
    speaker: SpeakerUpdate,
    media_file_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Create a new speaker for a specific media file
    """
    from app.utils.uuid_helpers import get_file_by_uuid_with_permission

    # Get media file by UUID and verify permission
    media_file = get_file_by_uuid_with_permission(db, media_file_uuid, current_user.id)

    # Generate a UUID for the new speaker
    speaker_uuid = str(uuid.uuid4())

    new_speaker = Speaker(
        name=speaker.name,
        display_name=speaker.display_name,
        uuid=speaker_uuid,
        user_id=current_user.id,
        media_file_id=media_file.id,  # Use internal integer ID
        verified=speaker.verified if speaker.verified is not None else False,
    )

    # If display_name is provided, mark as verified
    if speaker.display_name and speaker.display_name.strip():
        new_speaker.verified = True

    db.add(new_speaker)
    db.commit()
    db.refresh(new_speaker)

    # Add computed status fields
    SpeakerStatusService.add_computed_status(new_speaker)

    return new_speaker


def _filter_speakers_query(query, verified_only: bool, for_filter: bool, file_id: Optional[int]):
    """Apply filters to the speakers query."""
    if verified_only:
        query = query.filter(Speaker.verified)

    if for_filter:
        query = query.filter(
            Speaker.display_name.isnot(None),
            Speaker.display_name != "",
            ~Speaker.display_name.op("~")(r"^SPEAKER_\d+$"),
        )

    if file_id is not None:
        query = query.filter(Speaker.media_file_id == file_id)

    return query


def _sort_speakers(speakers):
    """Sort speakers by SPEAKER_XX numbering for consistent ordering."""

    def get_speaker_number(speaker):
        match = re.match(r"^SPEAKER_(\d+)$", speaker.name)
        return int(match.group(1)) if match else 999

    # Always sort by original speaker number first, regardless of verification status
    # This ensures SPEAKER_01, SPEAKER_02, SPEAKER_03... order is maintained
    speakers.sort(key=lambda s: get_speaker_number(s))
    return speakers


def _get_unique_speakers_for_filter(speakers, db: Session, current_user: User):
    """
    Get unique speakers by display name for filter use with media file counts.
    Returns list of dicts with id, name, display_name, and media_count.
    """
    from sqlalchemy import func

    # Query to get distinct display names with media file counts
    # Group by display_name and count distinct media files for each
    speaker_counts = (
        db.query(
            Speaker.display_name,
            func.count(func.distinct(Speaker.media_file_id)).label("media_count"),
        )
        .filter(
            Speaker.user_id == current_user.id,
            Speaker.display_name.isnot(None),
            Speaker.display_name != "",
            ~Speaker.display_name.op("~")(r"^SPEAKER_\d+$"),
        )
        .group_by(Speaker.display_name)
        .order_by(func.count(func.distinct(Speaker.media_file_id)).desc(), Speaker.display_name)
        .all()
    )

    # Convert to list of dicts with proper format
    unique_speakers = []
    for display_name, media_count in speaker_counts:
        # Get a representative speaker for this display name to get ID
        representative_speaker = (
            db.query(Speaker)
            .filter(Speaker.user_id == current_user.id, Speaker.display_name == display_name)
            .first()
        )

        if representative_speaker:
            unique_speakers.append(
                {
                    "uuid": str(representative_speaker.uuid),
                    "name": representative_speaker.name,
                    "display_name": display_name,
                    "media_count": media_count,
                }
            )

    return unique_speakers


def _resolve_file_uuid_to_id(
    file_uuid: Optional[str], current_user: User, db: Session
) -> Optional[int]:
    """Convert file UUID to internal ID if provided."""
    if not file_uuid:
        return None
    from app.utils.uuid_helpers import get_file_by_uuid_with_permission

    media_file = get_file_by_uuid_with_permission(db, file_uuid, current_user.id)
    return media_file.id


def _get_segment_counts_for_speakers(speaker_ids: list[int], db: Session) -> dict[int, int]:
    """Pre-calculate segment counts for all speakers in one query."""
    from sqlalchemy import func

    if not speaker_ids:
        return {}

    count_results = (
        db.query(TranscriptSegment.speaker_id, func.count(TranscriptSegment.id))
        .filter(TranscriptSegment.speaker_id.in_(speaker_ids))
        .group_by(TranscriptSegment.speaker_id)
        .all()
    )
    return {speaker_id: count for speaker_id, count in count_results}


def _get_voice_suggestions(raw_cross_video_matches: list[dict]) -> list[dict]:
    """Extract voice suggestions from cross-video matches."""
    voice_suggestions = []
    for match in raw_cross_video_matches:
        if (
            float(match.get("confidence", 0)) >= 0.50
            and match.get("name")
            and match.get("name").strip()
            and match.get("suggestion_type")
        ):
            voice_suggestions.append(
                {
                    "name": match["name"],
                    "confidence": match["confidence"],
                    "confidence_percentage": match["confidence_percentage"],
                    "suggestion_type": match["suggestion_type"],
                    "reason": match.get("reason", ""),
                }
            )
    return voice_suggestions


def _build_cross_video_match(individual_match: dict) -> dict:
    """Build a single cross-video match entry from an individual match."""
    return {
        "media_file_id": individual_match["media_file_id"],
        "filename": individual_match.get("filename")
        or individual_match.get("media_file_title", "Unknown File"),
        "title": individual_match.get("media_file_title")
        or individual_match.get("filename", "Unknown File"),
        "media_file_title": individual_match.get("media_file_title")
        or individual_match.get("filename", "Unknown File"),
        "speaker_label": individual_match["name"],
        "confidence": individual_match["confidence"],
        "verified": True,
        "same_speaker": False,
    }


def _get_cross_video_matches_for_unlabeled(raw_cross_video_matches: list[dict]) -> list[dict]:
    """Extract file appearances from individual_matches for unlabeled speakers."""
    temp_matches = []
    for match in raw_cross_video_matches:
        if not match.get("individual_matches"):
            continue
        for individual_match in match["individual_matches"]:
            if float(individual_match.get("confidence", 0)) >= 0.50:
                temp_matches.append(_build_cross_video_match(individual_match))

    # Sort by confidence (highest first) and limit to top 8 for display
    return sorted(temp_matches, key=lambda x: x["confidence"], reverse=True)[:8]


def _compute_suggested_name(speaker: Speaker, raw_cross_video_matches: list[dict]) -> Optional[str]:
    """Determine whether to show the suggested name based on cross-video confidence."""
    suggested_name = speaker.suggested_name

    if not (speaker.suggested_name and speaker.confidence and raw_cross_video_matches):
        return suggested_name

    # Find highest cross-video match confidence
    highest_cross_video_confidence = max(match["confidence"] for match in raw_cross_video_matches)

    # Only hide very low confidence suggestions (<50%) when much higher cross-video matches exist (>30% higher)
    if speaker.confidence < 0.5 and highest_cross_video_confidence > speaker.confidence + 0.3:
        return None

    return suggested_name


def _get_suggestion_source(speaker: Speaker) -> Optional[str]:
    """Determine suggestion source for frontend display."""
    if not (speaker.suggested_name and speaker.confidence):
        return None

    if hasattr(speaker, "_suggestion_source"):
        return speaker._suggestion_source

    # Default assumption: embedding match
    return "embedding_match"


def _compute_display_flags(
    speaker: Speaker,
    suggested_name: Optional[str],
    suggestion_source: Optional[str],
    voice_suggestions: list[dict],
) -> dict:
    """Pre-compute frontend display flags."""
    has_llm_suggestion = bool(
        suggested_name and speaker.confidence and suggestion_source == "llm_analysis"
    )
    total_suggestions = (1 if has_llm_suggestion else 0) + len(voice_suggestions)
    show_suggestions_section = has_llm_suggestion or len(voice_suggestions) > 0

    # Pre-compute input field display logic based on voice embedding confidence
    voice_confidence = 0.0
    if voice_suggestions:
        voice_confidence = max(s["confidence"] for s in voice_suggestions)

    is_high_confidence = bool(
        voice_confidence >= 0.75 and suggested_name and not speaker.display_name
    )
    is_medium_confidence = bool(
        voice_confidence >= 0.5
        and voice_confidence < 0.75
        and suggested_name
        and not speaker.display_name
    )

    # Pre-compute placeholder text
    if is_high_confidence:
        input_placeholder = suggested_name
    elif suggested_name:
        input_placeholder = f"Suggested: {suggested_name}"
    else:
        input_placeholder = f"Label {speaker.name}"

    # Pre-compute profile badge visibility
    show_profile_badge = bool(
        speaker.profile
        and speaker.display_name
        and speaker.display_name.strip()
        and not speaker.display_name.startswith("SPEAKER_")
    )

    return {
        "has_llm_suggestion": has_llm_suggestion,
        "total_suggestions": total_suggestions,
        "show_suggestions_section": show_suggestions_section,
        "is_high_confidence": is_high_confidence,
        "is_medium_confidence": is_medium_confidence,
        "input_placeholder": input_placeholder,
        "show_profile_badge": show_profile_badge,
    }


def _is_labeled_speaker(speaker: Speaker) -> bool:
    """Check if a speaker is labeled (has a non-SPEAKER_ display name)."""
    return bool(
        speaker.display_name
        and speaker.display_name.strip()
        and not speaker.display_name.startswith("SPEAKER_")
    )


def _build_speaker_dict(
    speaker: Speaker,
    current_user: User,
    suggested_name: Optional[str],
    suggestion_source: Optional[str],
    voice_suggestions: list[dict],
    cross_video_matches: list[dict],
    display_flags: dict,
    segment_count: int,
) -> dict:
    """Build the speaker dictionary for API response."""
    speaker_dict = {
        "uuid": str(speaker.uuid),
        "name": speaker.name,
        "display_name": speaker.display_name or "",  # Handle nulls in backend
        "suggested_name": suggested_name,
        "verified": speaker.verified,
        "user_id": str(current_user.uuid),  # Use user UUID
        "confidence": speaker.confidence,
        "suggestion_source": suggestion_source,
        "created_at": speaker.created_at.isoformat(),
        "media_file_id": str(speaker.media_file.uuid)
        if speaker.media_file
        else speaker.media_file_id,
        "profile": None,
        "voice_suggestions": voice_suggestions,
        "cross_video_matches": cross_video_matches,
        "needsCrossMediaCall": _is_labeled_speaker(speaker),
        "segment_count": segment_count,
        # Pre-computed display flags
        **display_flags,
    }

    # Add profile information if speaker is assigned to a profile
    if speaker.profile_id and speaker.profile:
        speaker_dict["profile"] = {
            "uuid": str(speaker.profile.uuid) if speaker.profile.uuid else None,
            "name": speaker.profile.name,
            "description": speaker.profile.description,
        }

    return speaker_dict


def _process_single_speaker(
    speaker: Speaker,
    current_user: User,
    segment_count: int,
    db: Session,
) -> dict:
    """Process a single speaker and build its response dictionary."""
    from app.services.smart_speaker_suggestion_service import SmartSpeakerSuggestionService

    # Compute status information using SpeakerStatusService
    status_info = SpeakerStatusService.compute_speaker_status(speaker)
    speaker.computed_status = status_info["computed_status"]
    speaker.status_text = status_info["status_text"]
    speaker.status_color = status_info["status_color"]
    speaker.resolved_display_name = status_info["resolved_display_name"]

    # Get smart, consolidated speaker suggestions
    smart_suggestions = SmartSpeakerSuggestionService.consolidate_suggestions(
        speaker_id=speaker.id,
        user_id=current_user.id,
        db=db,
        confidence_threshold=0.5,
        max_suggestions=5,
    )

    # Format suggestions for API response
    raw_cross_video_matches = SmartSpeakerSuggestionService.format_for_api(smart_suggestions)

    # Get voice suggestions
    voice_suggestions = _get_voice_suggestions(raw_cross_video_matches)

    # Get cross-video matches based on whether speaker is labeled
    if _is_labeled_speaker(speaker):
        cross_video_matches = []  # Will be populated by cross-media API
    else:
        cross_video_matches = _get_cross_video_matches_for_unlabeled(raw_cross_video_matches)

    # Compute suggested name
    suggested_name = _compute_suggested_name(speaker, raw_cross_video_matches)

    # Get suggestion source
    suggestion_source = _get_suggestion_source(speaker)

    # Compute display flags
    display_flags = _compute_display_flags(
        speaker, suggested_name, suggestion_source, voice_suggestions
    )

    # Build the speaker dictionary
    return _build_speaker_dict(
        speaker,
        current_user,
        suggested_name,
        suggestion_source,
        voice_suggestions,
        cross_video_matches,
        display_flags,
        segment_count,
    )


def _create_no_cache_response(content: list) -> JSONResponse:
    """Create a JSONResponse with cache-busting headers."""
    return JSONResponse(
        content=content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/")
def list_speakers(
    verified_only: bool = False,
    file_uuid: Optional[str] = None,
    for_filter: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    List all speakers for the current user with intelligent suggestions.

    This endpoint provides comprehensive speaker data including:
    - Basic speaker information and verification status
    - Automatic profile assignments when speakers are labeled
    - Smart cross-video suggestions via embedding similarity
    - Pre-filtered, consolidated suggestions ready for frontend display

    All business logic for speaker suggestions and filtering is handled server-side.
    The frontend receives clean, ready-to-display data without needing additional processing.

    Args:
        verified_only (bool): If true, return only verified speakers.
        file_uuid (Optional[str]): If provided, return only speakers associated with this file.
        for_filter (bool): If true, return only speakers with distinct display names for filtering.

    Returns:
        List[dict]: Speaker objects with embedded suggestion data and profile information.
    """
    try:
        from sqlalchemy.orm import joinedload

        # Convert file_uuid to file_id if provided
        file_id = _resolve_file_uuid_to_id(file_uuid, current_user, db)

        query = (
            db.query(Speaker)
            .options(joinedload(Speaker.profile), joinedload(Speaker.media_file))
            .filter(Speaker.user_id == current_user.id)
        )
        query = _filter_speakers_query(query, verified_only, for_filter, file_id)
        speakers = query.all()
        speakers = _sort_speakers(speakers)

        if for_filter:
            return _get_unique_speakers_for_filter(speakers, db, current_user)

        # Pre-calculate segment counts for all speakers in one query
        speaker_ids = [s.id for s in speakers]
        segment_counts = _get_segment_counts_for_speakers(speaker_ids, db)

        # Process each speaker and build result
        result = [
            _process_single_speaker(speaker, current_user, segment_counts.get(speaker.id, 0), db)
            for speaker in speakers
        ]

        return _create_no_cache_response(result)

    except Exception as e:
        logger.error(f"Error in list_speakers: {e}")
        return _create_no_cache_response([])


@router.get("/{speaker_uuid}", response_model=SpeakerSchema)
def get_speaker(
    speaker_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get details of a specific speaker with computed status
    """
    speaker = get_speaker_by_uuid(db, speaker_uuid)

    # Verify ownership
    if speaker.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Add computed status fields
    SpeakerStatusService.add_computed_status(speaker)

    return speaker


def _handle_profile_embedding_updates(
    db: Session,
    speaker_id: int,
    old_profile_id: int,
    new_profile_id: int,
    was_auto_labeled: bool,
    display_name_changed: bool,
) -> None:
    """Handle profile embedding updates when speaker assignments change."""
    try:
        from app.services.profile_embedding_service import ProfileEmbeddingService

        # Case 1: Speaker was auto-labeled and user corrected it (removed from old profile)
        if (
            was_auto_labeled
            and display_name_changed
            and old_profile_id
            and old_profile_id != new_profile_id
        ):
            success = ProfileEmbeddingService.remove_speaker_from_profile_embedding(
                db, speaker_id, old_profile_id
            )
            if success:
                logger.info(
                    f"Removed speaker {speaker_id} from old profile {old_profile_id} after user correction"
                )
            else:
                logger.warning(
                    f"Failed to remove speaker {speaker_id} from old profile {old_profile_id}"
                )

        # Case 2: Speaker was assigned to a new profile
        if new_profile_id and new_profile_id != old_profile_id:
            success = ProfileEmbeddingService.add_speaker_to_profile_embedding(
                db, speaker_id, new_profile_id
            )
            if success:
                logger.info(f"Added speaker {speaker_id} to new profile {new_profile_id}")
            else:
                logger.warning(
                    f"Failed to add speaker {speaker_id} to new profile {new_profile_id}"
                )

        # Case 3: Speaker was removed from a profile (unassigned)
        elif old_profile_id and new_profile_id is None:
            success = ProfileEmbeddingService.remove_speaker_from_profile_embedding(
                db, speaker_id, old_profile_id
            )
            if success:
                logger.info(
                    f"Removed speaker {speaker_id} from profile {old_profile_id} after unassignment"
                )

        # Case 4: Speaker display name changed but same profile - recalculate to ensure accuracy
        elif display_name_changed and new_profile_id and new_profile_id == old_profile_id:
            success = ProfileEmbeddingService.update_profile_embedding(db, new_profile_id)
            if success:
                logger.info(
                    f"Updated profile {new_profile_id} embedding after speaker {speaker_id} name change"
                )

    except Exception as e:
        logger.error(f"Error updating profile embeddings for speaker {speaker_id}: {e}")
        # Don't fail the operation if embedding update fails


def _update_opensearch_speaker_name(speaker_uuid: str, display_name: str) -> None:
    """Update speaker display name in OpenSearch."""
    try:
        update_speaker_display_name(speaker_uuid, display_name)
    except Exception as e:
        logger.error(f"Failed to update speaker display name in OpenSearch: {e}")


def _handle_speaker_labeling_workflow(speaker: Speaker, display_name: str, db: Session) -> None:
    """Handle auto-creation of profiles and retroactive matching when speaker is labeled."""
    # Auto-create profile if needed and assign speaker to it
    from app.api.endpoints.speaker_update import auto_create_or_assign_profile

    auto_create_or_assign_profile(speaker, display_name, db)

    # Commit profile changes before retroactive matching
    db.commit()
    db.refresh(speaker)

    # Then trigger retroactive matching for all other speakers
    from app.api.endpoints.speaker_update import trigger_retroactive_matching

    trigger_retroactive_matching(speaker, db)


def _clear_video_cache_for_speaker(db: Session, media_file_id: int) -> None:
    """Clear video cache since speaker labels have changed (affects subtitles)."""
    try:
        from app.services.minio_service import MinIOService
        from app.services.video_processing_service import VideoProcessingService

        minio_service = MinIOService()
        video_processing_service = VideoProcessingService(minio_service)
        video_processing_service.clear_cache_for_media_file(db, media_file_id)
    except Exception as e:
        logger.error(f"Warning: Failed to clear video cache after speaker update: {e}")


def _handle_update_profile_action(
    profile_id: int, new_name: str, current_user: User, db: Session
) -> None:
    """Handle 'update_profile' action - update profile name globally."""
    profile = (
        db.query(SpeakerProfile)
        .filter(SpeakerProfile.id == profile_id, SpeakerProfile.user_id == current_user.id)
        .first()
    )

    if not profile:
        return

    profile.name = new_name
    logger.info(f"Updated profile {profile.id} name to '{new_name}' globally")

    # Update all speakers linked to this profile
    linked_speakers = (
        db.query(Speaker)
        .filter(Speaker.profile_id == profile_id, Speaker.user_id == current_user.id)
        .all()
    )

    for linked_speaker in linked_speakers:
        linked_speaker.display_name = new_name
        _update_opensearch_speaker_name(str(linked_speaker.uuid), new_name)

    logger.info(f"Updated {len(linked_speakers)} speakers with new profile name '{new_name}'")

    # Update the profile embedding in OpenSearch
    try:
        from app.services.profile_embedding_service import ProfileEmbeddingService

        success = ProfileEmbeddingService.update_profile_embedding(db, profile_id)
        if success:
            logger.info(
                f"Updated profile {profile_id} embedding in OpenSearch with new name '{new_name}'"
            )
        else:
            logger.warning(f"Failed to update profile {profile_id} embedding in OpenSearch")
    except Exception as e:
        logger.error(f"Error updating profile embedding in OpenSearch: {e}")


def _handle_create_new_profile_action(
    speaker: Speaker, new_name: str, current_user: User, db: Session
) -> None:
    """Handle 'create_new_profile' action - create new profile and assign speaker."""
    new_profile = SpeakerProfile(
        user_id=current_user.id,
        name=new_name,
        description=f"Profile for {new_name}",
        uuid=str(uuid.uuid4()),
    )
    db.add(new_profile)
    db.flush()  # Get the ID

    speaker.profile_id = new_profile.id
    logger.info(
        f"Created new profile {new_profile.id} '{new_name}' and assigned speaker {speaker.id}"
    )


def _handle_profile_action(
    profile_action: Optional[str],
    speaker_update: SpeakerUpdate,
    speaker: Speaker,
    old_profile_id: Optional[int],
    current_user: User,
    db: Session,
) -> None:
    """Handle profile actions (update_profile or create_new_profile)."""
    if not (profile_action and speaker_update.display_name):
        return

    new_name = speaker_update.display_name.strip()

    if profile_action == "update_profile" and old_profile_id:
        _handle_update_profile_action(old_profile_id, new_name, current_user, db)
    elif profile_action == "create_new_profile":
        _handle_create_new_profile_action(speaker, new_name, current_user, db)


def _get_profile_uuid(speaker: Speaker, db: Session) -> Optional[str]:
    """Get profile UUID from speaker, fetching from DB if necessary."""
    if not speaker.profile_id:
        return None

    if speaker.profile:
        return str(speaker.profile.uuid)

    profile = db.query(SpeakerProfile).filter(SpeakerProfile.id == speaker.profile_id).first()
    return str(profile.uuid) if profile else None


def _update_opensearch_profile_info(
    speaker: Speaker, old_profile_id: Optional[int], display_name_changed: bool, db: Session
) -> None:
    """Update OpenSearch with profile information changes."""
    new_profile_id = speaker.profile_id

    if old_profile_id == new_profile_id and not display_name_changed:
        return

    from app.services.opensearch_service import update_speaker_profile

    profile_uuid = _get_profile_uuid(speaker, db)
    update_speaker_profile(
        speaker_uuid=str(speaker.uuid),
        profile_id=speaker.profile_id,
        profile_uuid=profile_uuid,
        verified=speaker.verified,
    )


def _get_media_file_uuid(speaker: Speaker, db: Session) -> Optional[str]:
    """Get media file UUID from speaker."""
    if speaker.media_file:
        return str(speaker.media_file.uuid)

    if speaker.media_file_id:
        media_file = db.query(MediaFile).filter(MediaFile.id == speaker.media_file_id).first()
        if media_file:
            return str(media_file.uuid)

    return None


def _send_websocket_notification(speaker: Speaker, current_user: User, db: Session) -> None:
    """Send WebSocket notification for speaker update (best-effort)."""
    try:
        import asyncio

        from app.api.websockets import publish_notification

        notification_data = {
            "speaker_id": str(speaker.uuid),
            "media_file_id": _get_media_file_uuid(speaker, db),
            "display_name": speaker.display_name,
            "verified": speaker.verified,
            "profile_id": _get_profile_uuid(speaker, db),
        }

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                publish_notification(
                    user_id=current_user.id,
                    notification_type="speaker_updated",
                    data=notification_data,
                )
            )
        except RuntimeError:
            logger.debug(
                f"Skipped WebSocket notification for speaker {speaker.uuid} (no event loop)"
            )
    except Exception as e:
        logger.debug(f"WebSocket notification skipped for speaker update: {e}")


def _set_no_cache_headers(response: Response) -> None:
    """Set cache-busting headers on response."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


def _apply_verification_on_display_name(speaker: Speaker, speaker_update: SpeakerUpdate) -> None:
    """Mark speaker as verified when display name is set."""
    if speaker_update.display_name is not None and speaker_update.display_name.strip():
        speaker.verified = True
        speaker.suggested_name = None
        speaker.confidence = None


@router.put("/{speaker_uuid}", response_model=SpeakerSchema)
def update_speaker(
    speaker_uuid: str,
    speaker_update: SpeakerUpdate,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Update a speaker's information including display name and verification status.
    This also handles profile embedding updates when speakers are corrected or reassigned.
    """
    # Find and validate speaker
    speaker = get_speaker_by_uuid(db, speaker_uuid)
    if speaker.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    speaker_id = speaker.id
    old_profile_id = speaker.profile_id
    was_auto_labeled = speaker.suggested_name is not None and not speaker.verified

    # Update speaker fields
    update_data = speaker_update.model_dump(exclude_unset=True)
    profile_action = update_data.pop("profile_action", None)

    for field, value in update_data.items():
        setattr(speaker, field, value)

    # Handle profile actions
    _handle_profile_action(
        profile_action, speaker_update, speaker, old_profile_id, current_user, db
    )

    # Handle verification when display name is set
    _apply_verification_on_display_name(speaker, speaker_update)

    db.commit()
    db.refresh(speaker)

    # Process side effects
    display_name_changed = speaker_update.display_name is not None

    _handle_profile_embedding_updates(
        db, speaker_id, old_profile_id, speaker.profile_id, was_auto_labeled, display_name_changed
    )

    if speaker_update.display_name is not None:
        _update_opensearch_speaker_name(str(speaker.uuid), speaker.display_name)

    _update_opensearch_profile_info(speaker, old_profile_id, display_name_changed, db)

    if speaker_update.display_name is not None and speaker_update.display_name.strip():
        _handle_speaker_labeling_workflow(speaker, speaker_update.display_name, db)

    _clear_video_cache_for_speaker(db, speaker.media_file_id)
    _send_websocket_notification(speaker, current_user, db)

    SpeakerStatusService.add_computed_status(speaker)
    _set_no_cache_headers(response)

    return speaker


def _merge_speaker_embeddings(source_speaker: Speaker, target_speaker: Speaker) -> None:
    """Merge and average speaker embeddings in OpenSearch."""
    try:
        import numpy as np

        from app.services.opensearch_service import add_speaker_embedding
        from app.services.opensearch_service import get_speaker_embedding

        # Get embeddings for both speakers
        source_embedding = get_speaker_embedding(str(source_speaker.uuid))
        target_embedding = get_speaker_embedding(str(target_speaker.uuid))

        if source_embedding and target_embedding:
            # Average the embeddings
            embeddings_array = np.array([source_embedding, target_embedding])
            averaged_embedding = np.mean(embeddings_array, axis=0).tolist()

            # Store the averaged embedding in OpenSearch
            add_speaker_embedding(
                speaker_id=target_speaker.id,
                user_id=target_speaker.user_id,
                name=target_speaker.name,
                embedding=averaged_embedding,
                profile_id=target_speaker.profile_id,
                media_file_id=target_speaker.media_file_id,
                display_name=target_speaker.display_name,
                segment_count=2,  # Merged from 2 speakers
            )
            logger.info(f"Updated target speaker {target_speaker.id} with averaged embedding")
        else:
            logger.warning("Could not retrieve embeddings for speaker merge")
    except Exception as e:
        logger.error(f"Error averaging speaker embeddings during merge: {e}")


def _clear_speaker_video_cache(db: Session, affected_media_files: set[int]) -> None:
    """Clear video cache for affected media files after speaker merge."""
    try:
        from app.services.minio_service import MinIOService
        from app.services.video_processing_service import VideoProcessingService

        minio_service = MinIOService()
        video_processing_service = VideoProcessingService(minio_service)

        for media_file_id in affected_media_files:
            video_processing_service.clear_cache_for_media_file(db, media_file_id)
    except Exception as e:
        logger.error(f"Warning: Failed to clear video cache after speaker merge: {e}")


def _update_opensearch_speaker_merge(source_speaker_id: int, target_speaker_id: int) -> None:
    """Update OpenSearch index after speaker merge."""
    try:
        from app.services.opensearch_service import merge_speaker_embeddings

        merge_speaker_embeddings(source_speaker_id, target_speaker_id, [])
        logger.info(
            f"Merged speaker embeddings in OpenSearch: {source_speaker_id} -> {target_speaker_id}"
        )
    except Exception as e:
        logger.error(f"Error merging speaker embeddings in OpenSearch: {e}")


def _refresh_analytics_after_merge(db: Session, affected_media_files: set[int]) -> None:
    """Recalculate analytics for affected media files after speaker merge."""
    try:
        from app.services.analytics_service import AnalyticsService

        for media_file_id in affected_media_files:
            if AnalyticsService.refresh_analytics(db, media_file_id):
                logger.info(
                    f"Refreshed analytics for media file {media_file_id} after speaker merge"
                )
            else:
                logger.warning(f"Failed to refresh analytics for media file {media_file_id}")
    except Exception as e:
        logger.error(f"Error refreshing analytics after speaker merge: {e}")


def _update_profile_embeddings_after_merge(
    db: Session,
    source_profile_id: int | None,
    target_profile_id: int | None,
    source_speaker_id: int,
) -> None:
    """Update profile embeddings affected by speaker merge."""
    try:
        from app.services.profile_embedding_service import ProfileEmbeddingService

        # Update source profile embedding if it exists
        if (
            source_profile_id
            and source_profile_id != target_profile_id
            and ProfileEmbeddingService.remove_speaker_from_profile_embedding(
                db, source_speaker_id, source_profile_id
            )
        ):
            logger.info(f"Updated source profile {source_profile_id} embedding after speaker merge")

        # Update target profile embedding if it exists
        if target_profile_id and ProfileEmbeddingService.update_profile_embedding(
            db, target_profile_id
        ):
            logger.info(f"Updated target profile {target_profile_id} embedding after speaker merge")

    except Exception as e:
        logger.error(f"Error updating profile embeddings after speaker merge: {e}")


@router.post("/{speaker_uuid}/merge/{target_speaker_uuid}", response_model=SpeakerSchema)
def merge_speakers(
    speaker_uuid: str,
    target_speaker_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Merge two speakers into one (target absorbs source)."""
    # Get both speakers by UUID
    source_speaker = get_speaker_by_uuid(db, speaker_uuid)
    target_speaker = get_speaker_by_uuid(db, target_speaker_uuid)

    # Verify ownership
    if source_speaker.user_id != current_user.id or target_speaker.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Store profile IDs for embedding updates
    source_profile_id = source_speaker.profile_id
    target_profile_id = target_speaker.profile_id
    source_speaker_id = source_speaker.id

    # Update all transcript segments from source to target
    db.query(TranscriptSegment).filter(TranscriptSegment.speaker_id == source_speaker.id).update(
        {"speaker_id": target_speaker.id}
    )

    # Merge the embedding vectors by averaging them
    _merge_speaker_embeddings(source_speaker, target_speaker)

    # Get media file IDs that are affected
    affected_media_files = {source_speaker.media_file_id, target_speaker.media_file_id}

    # Delete the source speaker
    db.delete(source_speaker)
    db.commit()
    db.refresh(target_speaker)

    # Clear video cache for affected media files
    _clear_speaker_video_cache(db, affected_media_files)

    # Update OpenSearch index
    _update_opensearch_speaker_merge(source_speaker_id, target_speaker.id)

    # Update profile embeddings
    _update_profile_embeddings_after_merge(
        db, source_profile_id, target_profile_id, source_speaker_id
    )

    # Recalculate analytics for affected media files
    _refresh_analytics_after_merge(db, affected_media_files)

    # Add computed status fields
    SpeakerStatusService.add_computed_status(target_speaker)

    return target_speaker


def _accept_speaker_profile_match(
    speaker: Speaker, speaker_id: int, profile_id: int, current_user: User, db: Session
) -> dict[str, Any]:
    """Handle acceptance of a speaker profile match."""
    # Verify profile exists
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

    # Assign speaker to profile
    speaker.profile_id = profile_id
    speaker.verified = True
    db.commit()

    # Update the profile's consolidated embedding
    try:
        from app.services.profile_embedding_service import ProfileEmbeddingService

        success = ProfileEmbeddingService.add_speaker_to_profile_embedding(
            db, speaker_id, profile_id
        )
        if success:
            logger.info(f"Updated profile {profile_id} embedding after adding speaker {speaker_id}")
        else:
            logger.warning(
                f"Failed to update profile {profile_id} embedding for speaker {speaker_id}"
            )
    except Exception as e:
        logger.error(f"Error updating profile embedding: {e}")

    return {
        "status": "accepted",
        "speaker_id": str(speaker.uuid),
        "profile_id": str(profile.uuid),
        "profile_name": profile.name,
        "message": f"Speaker assigned to profile '{profile.name}'",
    }


def _reject_speaker_suggestion(speaker: Speaker, speaker_id: int, db: Session) -> dict[str, Any]:
    """Handle rejection of a speaker identification suggestion."""
    old_profile_id = speaker.profile_id

    # Mark as verified but don't assign to profile
    speaker.profile_id = None
    speaker.verified = True
    speaker.confidence = None
    db.commit()

    # Update the old profile's embedding if speaker was previously assigned
    if old_profile_id:
        try:
            from app.services.profile_embedding_service import ProfileEmbeddingService

            success = ProfileEmbeddingService.remove_speaker_from_profile_embedding(
                db, speaker_id, old_profile_id
            )
            if success:
                logger.info(
                    f"Updated profile {old_profile_id} embedding after removing speaker {speaker_id}"
                )
            else:
                logger.warning(
                    f"Failed to update profile {old_profile_id} embedding after removing speaker {speaker_id}"
                )
        except Exception as e:
            logger.error(f"Error updating profile embedding after rejection: {e}")

    return {
        "status": "rejected",
        "speaker_id": str(speaker.uuid),
        "message": "Speaker identification suggestion rejected",
    }


def _create_new_speaker_profile(
    speaker: Speaker, speaker_id: int, profile_name: str, current_user: User, db: Session
) -> dict[str, Any]:
    """Handle creation of a new speaker profile."""
    # Check if profile with same name exists
    existing_profile = (
        db.query(SpeakerProfile)
        .filter(
            SpeakerProfile.user_id == current_user.id,
            SpeakerProfile.name == profile_name,
        )
        .first()
    )

    if existing_profile:
        raise HTTPException(status_code=400, detail="Profile with this name already exists")

    # Create new profile
    new_profile = SpeakerProfile(user_id=current_user.id, name=profile_name, uuid=str(uuid.uuid4()))

    db.add(new_profile)
    db.flush()

    # Assign speaker to new profile
    speaker.profile_id = new_profile.id
    speaker.verified = True
    db.commit()

    # Update the new profile's consolidated embedding
    try:
        from app.services.profile_embedding_service import ProfileEmbeddingService

        success = ProfileEmbeddingService.add_speaker_to_profile_embedding(
            db, speaker_id, new_profile.id
        )
        if success:
            logger.info(
                f"Updated new profile {new_profile.id} embedding after adding speaker {speaker_id}"
            )
        else:
            logger.warning(
                f"Failed to update new profile {new_profile.id} embedding for speaker {speaker_id}"
            )
    except Exception as e:
        logger.error(f"Error updating new profile embedding: {e}")

    return {
        "status": "created_and_assigned",
        "speaker_id": str(speaker.uuid),
        "profile_id": str(new_profile.uuid),
        "profile_name": profile_name,
        "message": f"Created new profile '{profile_name}' and assigned speaker",
    }


def _resolve_profile_uuid_to_id(
    profile_uuid: Optional[str], current_user: User, db: Session
) -> Optional[int]:
    """Convert profile UUID to internal ID if provided, validating ownership."""
    if not profile_uuid:
        return None

    from app.utils.uuid_helpers import get_profile_by_uuid

    profile = get_profile_by_uuid(db, profile_uuid)
    if profile.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    return profile.id


def _dispatch_verify_action(
    action: str,
    speaker: Speaker,
    speaker_id: int,
    profile_id: Optional[int],
    profile_name: Optional[str],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    """Dispatch to the appropriate verification action handler."""
    if action == "accept":
        if not profile_id:
            raise HTTPException(status_code=400, detail="profile_id required for accept action")
        return _accept_speaker_profile_match(speaker, speaker_id, profile_id, current_user, db)

    if action == "reject":
        return _reject_speaker_suggestion(speaker, speaker_id, db)

    if action == "create_profile":
        if not profile_name:
            raise HTTPException(
                status_code=400,
                detail="profile_name required for create_profile action",
            )
        return _create_new_speaker_profile(speaker, speaker_id, profile_name, current_user, db)

    raise HTTPException(
        status_code=400,
        detail="Invalid action. Must be 'accept', 'reject', or 'create_profile'",
    )


@router.post("/{speaker_uuid}/verify", response_model=dict[str, Any])
def verify_speaker_identification(
    speaker_uuid: str,
    action: str,  # 'accept', 'reject', 'create_profile'
    profile_uuid: Optional[str] = None,
    profile_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Verify or reject speaker identification suggestions.

    Actions:
    - 'accept': Accept suggested profile match
    - 'reject': Reject suggestion and keep unassigned
    - 'create_profile': Create new profile and assign speaker
    """
    try:
        speaker = get_speaker_by_uuid(db, speaker_uuid)
        if speaker.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

        profile_id = _resolve_profile_uuid_to_id(profile_uuid, current_user, db)

        return _dispatch_verify_action(
            action, speaker, speaker.id, profile_id, profile_name, current_user, db
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying speaker: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error") from e


def _build_occurrence_dict(
    media_file: MediaFile,
    speaker_obj: Speaker,
    same_speaker: bool,
) -> dict[str, Any]:
    """Build occurrence dictionary for a speaker/media file pair."""
    return {
        "media_file_id": str(media_file.uuid),
        "filename": media_file.filename,
        "title": media_file.title or media_file.filename,
        "media_file_title": media_file.title or media_file.filename,
        "upload_time": media_file.upload_time.isoformat(),
        "speaker_label": speaker_obj.name,
        "confidence": speaker_obj.confidence,
        "verified": speaker_obj.verified,
        "same_speaker": same_speaker,
    }


def _get_profile_based_occurrences(
    speaker: Speaker, current_user: User, db: Session
) -> list[dict[str, Any]]:
    """Get cross-media occurrences for a speaker with a profile."""
    profile_speakers = (
        db.query(Speaker)
        .join(MediaFile)
        .filter(
            Speaker.profile_id == speaker.profile_id,
            Speaker.user_id == current_user.id,
        )
        .all()
    )

    result = []
    for profile_speaker in profile_speakers:
        if profile_speaker.media_file:
            result.append(
                _build_occurrence_dict(
                    profile_speaker.media_file,
                    profile_speaker,
                    same_speaker=(profile_speaker.id == speaker.id),
                )
            )
    return result


def _get_display_name_based_occurrences(
    speaker: Speaker, current_user: User, db: Session
) -> list[dict[str, Any]]:
    """Get cross-media occurrences for a speaker without a profile, by display name."""
    result = []

    # Add this speaker instance first
    if speaker.media_file:
        result.append(_build_occurrence_dict(speaker.media_file, speaker, same_speaker=True))

    # Skip if speaker doesn't have a valid display name
    if not speaker.display_name or speaker.display_name.startswith("SPEAKER_"):
        return result

    # Find other speakers with the same display name
    similar_speakers = (
        db.query(Speaker)
        .join(MediaFile)
        .filter(
            Speaker.display_name == speaker.display_name,
            Speaker.user_id == current_user.id,
            Speaker.id != speaker.id,
        )
        .all()
    )

    for similar_speaker in similar_speakers:
        if similar_speaker.media_file:
            result.append(
                _build_occurrence_dict(
                    similar_speaker.media_file, similar_speaker, same_speaker=False
                )
            )

    return result


@router.get("/{speaker_uuid}/cross-media", response_model=list[dict[str, Any]])
def get_speaker_cross_media_occurrences(
    speaker_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get all media files where this speaker (or their profile) appears.
    """
    try:
        speaker = get_speaker_by_uuid(db, speaker_uuid)
        if speaker.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

        if speaker.profile_id:
            result = _get_profile_based_occurrences(speaker, current_user, db)
        else:
            result = _get_display_name_based_occurrences(speaker, current_user, db)

        # Sort by confidence (highest first), with same_speaker files prioritized
        result.sort(key=lambda x: (x["same_speaker"], x.get("confidence") or 0.0), reverse=True)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting cross-media occurrences: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/cleanup-orphaned-embeddings", response_model=dict[str, Any])
def cleanup_orphaned_embeddings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Clean up orphaned speaker embeddings in OpenSearch for non-existent MediaFiles.
    """
    try:
        from app.services.opensearch_service import cleanup_orphaned_speaker_embeddings

        deleted_count = cleanup_orphaned_speaker_embeddings(current_user.id)

        return {
            "status": "success",
            "deleted_count": deleted_count,
            "message": f"Cleaned up {deleted_count} orphaned speaker embeddings",
        }
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/debug/cross-media-data", response_model=dict[str, Any])
def debug_cross_media_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Debug endpoint to examine cross-media matching data in PostgreSQL and OpenSearch.
    """
    try:
        debug_info = {
            "user_id": current_user.id,
            "media_files": [],
            "speakers": [],
            "profiles": [],
            "opensearch_speakers": [],
            "opensearch_profiles": [],
        }

        # Get all media files for this user
        media_files = db.query(MediaFile).filter(MediaFile.user_id == current_user.id).all()
        for mf in media_files:
            debug_info["media_files"].append(
                {
                    "id": mf.id,
                    "filename": mf.filename,
                    "title": mf.title,
                    "status": mf.status.value if mf.status else None,
                }
            )

        # Get all speakers for this user, especially Joe Rogan ones
        speakers = (
            db.query(Speaker)
            .filter(Speaker.user_id == current_user.id)
            .order_by(Speaker.media_file_id, Speaker.id)
            .all()
        )

        joe_rogan_speakers = []
        for speaker in speakers:
            speaker_data = {
                "id": speaker.id,
                "name": speaker.name,
                "display_name": speaker.display_name,
                "profile_id": speaker.profile_id,
                "media_file_id": speaker.media_file_id,
                "verified": speaker.verified,
                "confidence": speaker.confidence,
            }
            debug_info["speakers"].append(speaker_data)

            # Track Joe Rogan speakers specifically
            if speaker.display_name == "Joe Rogan":
                joe_rogan_speakers.append(speaker_data)

        # Get all speaker profiles
        profiles = db.query(SpeakerProfile).filter(SpeakerProfile.user_id == current_user.id).all()
        for profile in profiles:
            debug_info["profiles"].append(
                {
                    "id": profile.id,
                    "name": profile.name,
                    "uuid": profile.uuid,
                    "description": profile.description,
                }
            )

        # Get OpenSearch speaker documents
        try:
            from app.services.opensearch_service import opensearch_client
            from app.services.opensearch_service import settings

            if opensearch_client:
                # Query all speaker documents for this user
                query = {
                    "size": 100,
                    "query": {
                        "bool": {
                            "must": [{"term": {"user_id": current_user.id}}],
                            "must_not": [
                                {"exists": {"field": "document_type"}}
                            ],  # Only speakers, not profiles
                        }
                    },
                }

                response = opensearch_client.search(
                    index=settings.OPENSEARCH_SPEAKER_INDEX, body=query
                )
                for hit in response["hits"]["hits"]:
                    source = hit["_source"]
                    debug_info["opensearch_speakers"].append(
                        {
                            "opensearch_id": hit["_id"],
                            "speaker_id": source.get("speaker_id"),
                            "display_name": source.get("display_name"),
                            "profile_id": source.get("profile_id"),
                            "media_file_id": source.get("media_file_id"),
                            "user_id": source.get("user_id"),
                        }
                    )

                # Query profile documents
                profile_query = {
                    "size": 100,
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"user_id": current_user.id}},
                                {"term": {"document_type": "profile"}},
                            ]
                        }
                    },
                }

                profile_response = opensearch_client.search(
                    index=settings.OPENSEARCH_SPEAKER_INDEX, body=profile_query
                )
                for hit in profile_response["hits"]["hits"]:
                    source = hit["_source"]
                    debug_info["opensearch_profiles"].append(
                        {
                            "opensearch_id": hit["_id"],
                            "profile_id": source.get("profile_id"),
                            "profile_name": source.get("profile_name"),
                            "speaker_count": source.get("speaker_count"),
                            "user_id": source.get("user_id"),
                        }
                    )

        except Exception as e:
            debug_info["opensearch_error"] = str(e)

        # Add summary analysis
        debug_info["analysis"] = {
            "total_media_files": len(debug_info["media_files"]),
            "total_speakers": len(debug_info["speakers"]),
            "joe_rogan_speakers": joe_rogan_speakers,
            "joe_rogan_count": len(joe_rogan_speakers),
            "total_profiles": len(debug_info["profiles"]),
            "opensearch_speaker_count": len(debug_info["opensearch_speakers"]),
            "opensearch_profile_count": len(debug_info["opensearch_profiles"]),
        }

        return debug_info

    except Exception as e:
        logger.error(f"Error in debug endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/debug/joe-rogan-cross-media", response_model=dict[str, Any])
def debug_joe_rogan_cross_media(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Debug endpoint to test cross-media logic specifically for Joe Rogan speakers.
    """
    try:
        # Find all Joe Rogan speakers
        joe_rogan_speakers = (
            db.query(Speaker)
            .filter(Speaker.user_id == current_user.id, Speaker.display_name == "Joe Rogan")
            .all()
        )

        results = {"joe_rogan_speakers_found": len(joe_rogan_speakers), "cross_media_results": []}

        for speaker in joe_rogan_speakers:
            # Test the cross-media logic for this speaker
            cross_media_result = {
                "speaker_id": speaker.id,
                "speaker_name": speaker.name,
                "media_file_id": speaker.media_file_id,
                "profile_id": speaker.profile_id,
                "verified": speaker.verified,
                "occurrences": [],
            }

            # Replicate the cross-media logic
            if speaker.profile_id:
                # Speaker has a profile - find all instances of this profile
                profile_speakers = (
                    db.query(Speaker)
                    .join(MediaFile)
                    .filter(
                        Speaker.profile_id == speaker.profile_id,
                        Speaker.user_id == current_user.id,
                    )
                    .all()
                )

                cross_media_result["method_used"] = "profile_based"
                cross_media_result["profile_speakers_found"] = len(profile_speakers)

                for profile_speaker in profile_speakers:
                    media_file = profile_speaker.media_file
                    if media_file:
                        occurrence = {
                            "speaker_id": profile_speaker.id,
                            "media_file_id": media_file.id,
                            "media_file_title": media_file.title or media_file.filename,
                            "same_speaker": profile_speaker.id == speaker.id,
                        }
                        cross_media_result["occurrences"].append(occurrence)

            else:
                # Speaker has no profile - search by display_name
                similar_speakers = (
                    db.query(Speaker)
                    .join(MediaFile)
                    .filter(
                        Speaker.display_name == speaker.display_name,
                        Speaker.user_id == current_user.id,
                        Speaker.id != speaker.id,  # Exclude self
                    )
                    .all()
                )

                cross_media_result["method_used"] = "display_name_based"
                cross_media_result["similar_speakers_found"] = len(similar_speakers)

                # Add self first
                if speaker.media_file:
                    cross_media_result["occurrences"].append(
                        {
                            "speaker_id": speaker.id,
                            "media_file_id": speaker.media_file.id,
                            "media_file_title": speaker.media_file.title
                            or speaker.media_file.filename,
                            "same_speaker": True,
                        }
                    )

                # Add similar speakers
                for similar_speaker in similar_speakers:
                    similar_media_file = similar_speaker.media_file
                    if similar_media_file:
                        occurrence = {
                            "speaker_id": similar_speaker.id,
                            "media_file_id": similar_media_file.id,
                            "media_file_title": similar_media_file.title
                            or similar_media_file.filename,
                            "same_speaker": False,
                        }
                        cross_media_result["occurrences"].append(occurrence)

            results["cross_media_results"].append(cross_media_result)

        return results

    except Exception as e:
        logger.error(f"Error in Joe Rogan debug endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e
