"""
Speaker Update and Profile Management Module.

This module provides automatic speaker profile creation and management functionality.
It handles the core business logic for:
- Automatic profile creation when speakers are labeled
- Cross-video speaker matching and assignment
- Profile embedding updates and consolidation

The module implements intelligent speaker recognition that learns from user labeling
patterns and automatically groups speakers across multiple videos.
"""

import logging
import uuid

import numpy as np
from sqlalchemy.orm import Session

from app.models.media import Speaker
from app.models.media import SpeakerMatch
from app.models.media import SpeakerProfile
from app.services.opensearch_service import get_speaker_embedding

logger = logging.getLogger(__name__)


def calculate_cosine_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
    """
    Calculate cosine similarity between two voice embeddings.

    This function now delegates to the centralized SimilarityService for
    optimal performance and consistency across the application.

    Args:
        embedding1 (np.ndarray): First voice embedding vector.
        embedding2 (np.ndarray): Second voice embedding vector.

    Returns:
        float: Similarity score between 0 and 1, where 1 is identical voices.
    """
    from app.services.similarity_service import SimilarityService

    return SimilarityService.cosine_similarity(embedding1, embedding2)


def auto_create_or_assign_profile(speaker: Speaker, display_name: str, db: Session) -> bool:
    """
    Automatically create or assign speaker to a profile when labeled.

    This function implements the core auto-profiling logic:
    1. Searches for existing profiles with the same name (case-insensitive)
    2. If found, assigns speaker to existing profile and updates embedding
    3. If not found, creates new profile and assigns speaker
    4. Updates the profile's consolidated voice embedding

    Args:
        speaker (Speaker): The speaker instance to assign to a profile.
        display_name (str): The display name/label for the speaker.
        db (Session): SQLAlchemy database session.

    Returns:
        bool: True if profile was successfully created/assigned, False otherwise.

    Raises:
        Exception: Logs errors but does not re-raise to avoid breaking speaker updates.
    """
    try:
        # Check if a profile with this name already exists for this user
        existing_profile = (
            db.query(SpeakerProfile)
            .filter(
                SpeakerProfile.user_id == speaker.user_id,
                SpeakerProfile.name.ilike(display_name.strip()),
            )
            .first()
        )

        if existing_profile:
            # Assign speaker to existing profile
            speaker.profile_id = existing_profile.id
            logger.info(
                f"Assigned speaker {speaker.id} to existing profile '{existing_profile.name}' (ID: {existing_profile.id})"
            )

            # Update profile embedding
            try:
                from app.services.profile_embedding_service import ProfileEmbeddingService

                ProfileEmbeddingService.add_speaker_to_profile_embedding(
                    db, speaker.id, existing_profile.id
                )
            except Exception as e:
                logger.warning(f"Failed to update profile embedding: {e}")

            # Sync profile assignment to OpenSearch
            try:
                from app.services.opensearch_service import update_speaker_profile

                # Get profile UUID if profile is assigned
                profile_uuid = None
                if speaker.profile_id and existing_profile:
                    profile_uuid = str(existing_profile.uuid)

                update_speaker_profile(
                    speaker_uuid=str(speaker.uuid),
                    profile_id=speaker.profile_id,
                    profile_uuid=profile_uuid,
                    verified=speaker.verified,
                )
                logger.info(f"Synced speaker {speaker.uuid} profile assignment to OpenSearch")
            except Exception as e:
                logger.warning(f"Failed to sync speaker {speaker.uuid} profile to OpenSearch: {e}")

        else:
            # Create new profile for this speaker name
            new_profile = SpeakerProfile(
                user_id=speaker.user_id,
                name=display_name.strip(),
                description=f"Auto-created profile for {display_name.strip()}",
                uuid=str(uuid.uuid4()),
            )
            db.add(new_profile)
            db.flush()  # Get the ID without committing

            # Assign speaker to new profile
            speaker.profile_id = new_profile.id
            logger.info(
                f"Created new profile '{new_profile.name}' (ID: {new_profile.id}) and assigned speaker {speaker.id}"
            )

            # Initialize profile embedding
            try:
                from app.services.profile_embedding_service import ProfileEmbeddingService

                ProfileEmbeddingService.add_speaker_to_profile_embedding(
                    db, speaker.id, new_profile.id
                )
            except Exception as e:
                logger.warning(f"Failed to initialize profile embedding: {e}")

            # Sync new profile assignment to OpenSearch
            try:
                from app.services.opensearch_service import update_speaker_profile

                update_speaker_profile(
                    speaker_uuid=str(speaker.uuid),
                    profile_id=speaker.profile_id,
                    profile_uuid=str(new_profile.uuid),
                    verified=speaker.verified,
                )
                logger.info(f"Synced speaker {speaker.uuid} new profile assignment to OpenSearch")
            except Exception as e:
                logger.warning(
                    f"Failed to sync speaker {speaker.uuid} new profile to OpenSearch: {e}"
                )

        return True

    except Exception as e:
        logger.error(f"Error in auto profile creation/assignment: {e}")
        return False


def trigger_retroactive_matching(updated_speaker: Speaker, db: Session) -> None:
    """
    Apply retroactive voice matching when a speaker is labeled.

    This function implements intelligent cross-video speaker recognition:
    1. Compares the newly labeled speaker's voice against all other speakers
    2. Auto-applies labels for high confidence matches (≥75%)
    3. Creates suggestions for medium confidence matches (50-74%)
    4. Automatically assigns matched speakers to the same profile

    The function uses voice embedding similarity to identify the same speaker
    across different videos and automatically consolidates them under a single
    profile, reducing manual labeling effort.

    Args:
        updated_speaker (Speaker): The speaker that was just labeled by the user.
        db (Session): SQLAlchemy database session.

    Returns:
        None

    Note:
        - Only processes unverified speakers or those with matching names
        - Updates profile embeddings for all automatically assigned speakers
        - Logs detailed information about matching decisions for debugging
    """
    try:
        logger.info(
            f"Starting retroactive matching for speaker {updated_speaker.id} labeled as '{updated_speaker.display_name}'"
        )

        # Get the embedding for the updated speaker
        embedding = get_speaker_embedding(str(updated_speaker.uuid))
        if not embedding:
            logger.warning(f"No embedding found for speaker {updated_speaker.uuid}")
            return

        embedding_array = np.array(embedding)

        # Find ALL speakers (including cross-video matches) for this user
        all_speakers = (
            db.query(Speaker)
            .filter(
                Speaker.user_id == updated_speaker.user_id,
                Speaker.id != updated_speaker.id,
            )
            .all()
        )

        logger.info(
            f"Checking {len(all_speakers)} speakers for matches with {updated_speaker.display_name}"
        )

        auto_applied_count = 0
        suggested_count = 0

        for speaker in all_speakers:
            # Skip already verified speakers with different names
            if (
                speaker.verified
                and speaker.display_name
                and speaker.display_name != updated_speaker.display_name
            ):
                logger.info(
                    f"Skipping speaker {speaker.id} ({speaker.name}): already verified as '{speaker.display_name}'"
                )
                continue

            # Get embedding for this speaker
            other_embedding = get_speaker_embedding(str(speaker.uuid))
            if not other_embedding:
                logger.warning(f"No embedding found for speaker {speaker.uuid} ({speaker.name})")
                continue

            # Calculate similarity
            similarity = calculate_cosine_similarity(embedding_array, np.array(other_embedding))

            logger.info(
                f"Similarity between {updated_speaker.display_name} and {speaker.name}: {similarity:.3f}"
            )

            # Store the suggestion if similarity is above threshold
            if similarity >= 0.5:
                # Update confidence and suggestion in PostgreSQL
                speaker.confidence = similarity
                speaker.suggested_name = updated_speaker.display_name

                # Auto-apply for high confidence (75%+)
                if similarity >= 0.75:
                    speaker.display_name = updated_speaker.display_name
                    speaker.verified = True

                    # Also assign to the same profile if the updated speaker has one
                    if updated_speaker.profile_id:
                        speaker.profile_id = updated_speaker.profile_id

                        # Update profile embedding
                        try:
                            from app.services.profile_embedding_service import (
                                ProfileEmbeddingService,
                            )

                            ProfileEmbeddingService.add_speaker_to_profile_embedding(
                                db, speaker.id, updated_speaker.profile_id
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to update profile embedding for auto-applied speaker: {e}"
                            )

                    # CRITICAL FIX: Sync the updates to OpenSearch immediately
                    # This ensures PostgreSQL and OpenSearch stay in sync for all speaker changes
                    try:
                        from app.services.opensearch_service import update_speaker_display_name
                        from app.services.opensearch_service import update_speaker_profile

                        # Update display name in OpenSearch
                        update_speaker_display_name(str(speaker.uuid), speaker.display_name)

                        # Get profile UUID if assigned
                        profile_uuid = None
                        if speaker.profile_id:
                            profile = (
                                db.query(SpeakerProfile)
                                .filter(SpeakerProfile.id == speaker.profile_id)
                                .first()
                            )
                            if profile:
                                profile_uuid = str(profile.uuid)

                        # Update profile assignment and verification status in OpenSearch
                        update_speaker_profile(
                            speaker_uuid=str(speaker.uuid),
                            profile_id=speaker.profile_id,
                            profile_uuid=profile_uuid,
                            verified=speaker.verified,
                        )

                        logger.info(
                            f"Synced auto-applied speaker {speaker.id} to OpenSearch: "
                            f"display_name='{speaker.display_name}', profile_id={speaker.profile_id}, verified={speaker.verified}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to sync auto-applied speaker {speaker.id} to OpenSearch: {e}"
                        )

                    auto_applied_count += 1
                    logger.info(
                        f"Auto-applied {updated_speaker.display_name} to {speaker.name} ({similarity:.1%} confidence)"
                    )
                else:
                    # Just suggest for medium confidence (50-75%)
                    suggested_count += 1
                    logger.info(
                        f"Suggested {updated_speaker.display_name} for {speaker.name} ({similarity:.1%} confidence)"
                    )

                # Store the match in the database
                store_speaker_match(updated_speaker.id, speaker.id, similarity, db)

        # Commit database changes first
        db.commit()

        # ADDITIONAL FIX: Batch sync all suggestion updates to OpenSearch
        # This ensures suggestions (confidence + suggested_name) are also synced
        try:
            from app.services.opensearch_service import update_speaker_display_name
            from app.services.opensearch_service import update_speaker_profile

            # Get all speakers that received suggestions in this round
            suggestion_speakers = (
                db.query(Speaker)
                .filter(
                    Speaker.user_id == updated_speaker.user_id,
                    Speaker.suggested_name == updated_speaker.display_name,
                    Speaker.confidence >= 0.5,
                    Speaker.confidence
                    < 0.75,  # Only medium confidence (high confidence already synced above)
                    not Speaker.verified,  # Suggestions are for unverified speakers
                )
                .all()
            )

            for suggestion_speaker in suggestion_speakers:
                try:
                    # Sync confidence and suggested_name updates to OpenSearch for suggestions
                    # Note: These speakers keep their original display_name=None but get updated confidence/suggestion
                    update_speaker_display_name(
                        str(suggestion_speaker.uuid), suggestion_speaker.display_name
                    )

                    # Get profile UUID if assigned
                    profile_uuid = None
                    if suggestion_speaker.profile_id:
                        profile = (
                            db.query(SpeakerProfile)
                            .filter(SpeakerProfile.id == suggestion_speaker.profile_id)
                            .first()
                        )
                        if profile:
                            profile_uuid = str(profile.uuid)

                    update_speaker_profile(
                        speaker_uuid=str(suggestion_speaker.uuid),
                        profile_id=suggestion_speaker.profile_id,
                        profile_uuid=profile_uuid,
                        verified=suggestion_speaker.verified,
                    )
                    logger.debug(
                        f"Synced suggestion updates for speaker {suggestion_speaker.uuid} to OpenSearch"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to sync suggestion speaker {suggestion_speaker.uuid} to OpenSearch: {e}"
                    )

            if suggestion_speakers:
                logger.info(f"Synced {len(suggestion_speakers)} speaker suggestions to OpenSearch")

        except Exception as e:
            logger.error(f"Error during batch OpenSearch sync for suggestions: {e}")

        logger.info(
            f"Retroactive matching complete: {auto_applied_count} auto-applied, {suggested_count} suggested"
        )

        # Send WebSocket notification about bulk speaker updates
        if auto_applied_count > 0:
            try:
                import asyncio

                from app.api.websockets import publish_notification

                asyncio.create_task(
                    publish_notification(
                        user_id=updated_speaker.user_id,
                        notification_type="speakers_bulk_updated",
                        data={
                            "trigger_speaker_id": updated_speaker.id,
                            "display_name": updated_speaker.display_name,
                            "auto_applied_count": auto_applied_count,
                            "suggested_count": suggested_count,
                            "message": f"Auto-applied '{updated_speaker.display_name}' to {auto_applied_count} additional speakers",
                        },
                    )
                )
                logger.info(
                    f"Sent WebSocket notification for bulk speaker update: {auto_applied_count} speakers"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to send WebSocket notification for bulk speaker update: {e}"
                )

    except Exception as e:
        logger.error(f"Error in retroactive matching: {e}")
        db.rollback()


def store_speaker_match(speaker1_id: int, speaker2_id: int, confidence: float, db: Session) -> None:
    """
    Store or update a speaker voice similarity match in the database.

    Maintains a record of voice similarity scores between speakers for
    analytics and debugging purposes. Uses consistent ID ordering to
    avoid duplicate entries.

    Args:
        speaker1_id (int): ID of the first speaker.
        speaker2_id (int): ID of the second speaker.
        confidence (float): Voice similarity confidence score (0-1).
        db (Session): SQLAlchemy database session.

    Returns:
        None
    """
    # Ensure consistent ordering (smaller ID first)
    smaller_id = min(speaker1_id, speaker2_id)
    larger_id = max(speaker1_id, speaker2_id)

    # Check if match already exists
    existing_match = (
        db.query(SpeakerMatch)
        .filter(
            SpeakerMatch.speaker1_id == smaller_id,
            SpeakerMatch.speaker2_id == larger_id,
        )
        .first()
    )

    if existing_match:
        # Update confidence if higher
        if confidence > existing_match.confidence:
            existing_match.confidence = confidence
    else:
        # Create new match
        speaker_match = SpeakerMatch(
            speaker1_id=smaller_id, speaker2_id=larger_id, confidence=confidence
        )
        db.add(speaker_match)
