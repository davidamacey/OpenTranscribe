"""
Profile Embedding Service for managing speaker profile embeddings.

This service handles the consolidation and management of speaker embeddings
at the profile level to improve cross-file speaker recognition accuracy.

The service provides intelligent embedding aggregation that:
- Consolidates multiple speaker embeddings into profile-level representations
- Enables accurate cross-video speaker recognition
- Maintains embedding quality through incremental updates
- Supports both PostgreSQL metadata and OpenSearch vector storage
"""

import logging
from datetime import datetime
from typing import Any
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from app.models.media import Speaker
from app.models.media import SpeakerProfile
from app.services.opensearch_service import get_speaker_embedding

logger = logging.getLogger(__name__)


def _clear_profile_embedding_from_opensearch(profile_id: int) -> None:
    """Clear a profile embedding from OpenSearch."""
    try:
        from app.services.opensearch_service import remove_profile_embedding

        remove_profile_embedding(profile_id)
    except Exception as e:
        logger.warning(f"Could not clear profile {profile_id} embedding from OpenSearch: {e}")


def _store_profile_embedding_to_opensearch(
    profile_id: int,
    profile_uuid: str,
    profile_name: str,
    embedding: list[float],
    speaker_count: int,
    user_id: int,
) -> None:
    """Store a profile embedding to OpenSearch."""
    try:
        from app.services.opensearch_service import store_profile_embedding

        store_profile_embedding(
            profile_id=profile_id,
            profile_uuid=profile_uuid,
            profile_name=profile_name,
            embedding=embedding,
            speaker_count=speaker_count,
            user_id=user_id,
        )
    except Exception as e:
        logger.warning(f"Failed to sync profile {profile_id} embedding to OpenSearch: {e}")


def _collect_speaker_embeddings(speakers: list[Speaker]) -> dict[int, list[float]]:
    """Collect embeddings for all speakers, keyed by speaker ID."""
    speaker_embeddings = {}
    for speaker in speakers:
        embedding = get_speaker_embedding(str(speaker.uuid))
        if embedding:
            speaker_embeddings[speaker.id] = embedding
    return speaker_embeddings


def _calculate_average_embedding(embeddings: list[list[float]]) -> list[float]:
    """Calculate the average of multiple embeddings."""
    embeddings_array = np.array(embeddings)
    return np.mean(embeddings_array, axis=0).tolist()


def _process_profile_with_no_speakers(
    profile: SpeakerProfile,
    profile_id: int,
) -> bool:
    """Handle case when profile has no speakers assigned."""
    profile.embedding_count = 0
    profile.last_embedding_update = datetime.utcnow()
    _clear_profile_embedding_from_opensearch(profile_id)
    return True


def _process_profile_with_embeddings(
    profile: SpeakerProfile,
    profile_id: int,
    embeddings: list[list[float]],
) -> bool:
    """Process a profile that has valid embeddings."""
    averaged_embedding = _calculate_average_embedding(embeddings)

    profile.embedding_count = len(embeddings)
    profile.last_embedding_update = datetime.utcnow()

    _store_profile_embedding_to_opensearch(
        profile_id=profile_id,
        profile_uuid=str(profile.uuid),
        profile_name=profile.name,
        embedding=averaged_embedding,
        speaker_count=len(embeddings),
        user_id=profile.user_id,
    )

    logger.info(f"Updated profile {profile_id} embedding with {len(embeddings)} speaker embeddings")
    return True


def _check_opensearch_profile_prerequisites(
    user_id: int,
) -> tuple[Any, Any, bool]:
    """
    Check prerequisites for OpenSearch profile similarity search.

    Returns:
        Tuple of (opensearch_client, settings, should_continue)
    """
    from app.services.opensearch_service import opensearch_client
    from app.services.opensearch_service import settings

    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return None, None, False

    if not opensearch_client.indices.exists(index=settings.OPENSEARCH_SPEAKER_INDEX):
        logger.info("Speakers index does not exist yet, skipping profile similarity search")
        return None, None, False

    return opensearch_client, settings, True


def _check_profiles_exist_in_opensearch(
    opensearch_client: Any,
    index_name: str,
    user_id: int,
) -> bool:
    """Check if any profile documents exist for the user in OpenSearch."""
    profile_check_query = {
        "size": 1,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"document_type": "profile"}},
                    {"term": {"user_id": user_id}},
                ]
            }
        },
    }

    try:
        profile_check = opensearch_client.search(index=index_name, body=profile_check_query)
        if profile_check["hits"]["total"]["value"] == 0:
            logger.info(f"No profile documents found for user {user_id}, skipping KNN search")
            return False
    except Exception as e:
        logger.warning(f"Profile document check failed: {e}, proceeding with KNN query")

    return True


def _execute_knn_search(
    opensearch_client: Any,
    index_name: str,
    embedding: list[float],
    user_id: int,
    threshold: float,
) -> list[dict]:
    """Execute KNN search and return matches above threshold."""
    filters = [
        {"term": {"document_type": "profile"}},
        {"term": {"user_id": user_id}},
    ]

    query = {
        "size": 25,
        "query": {
            "knn": {
                "embedding": {
                    "vector": embedding,
                    "k": 25,
                    "filter": {"bool": {"filter": filters}},
                }
            }
        },
    }

    try:
        response = opensearch_client.search(index=index_name, body=query)
    except Exception as e:
        logger.error(f"Error in OpenSearch KNN search: {e}")
        return []

    return _extract_matches_from_response(response, threshold)


def _extract_matches_from_response(response: dict, threshold: float) -> list[dict]:
    """Extract and filter matches from OpenSearch response."""
    matches = []
    for hit in response["hits"]["hits"]:
        score = hit["_score"]
        if score < threshold:
            continue

        source = hit["_source"]
        profile_id = source.get("profile_id")
        profile_uuid = source.get("profile_uuid")
        profile_name = source.get("profile_name")

        if not profile_id or not profile_name:
            continue

        matches.append(
            {
                "profile_id": profile_id,  # Integer ID for internal database operations
                "profile_uuid": profile_uuid or str(profile_id),  # UUID for external API responses
                "profile_name": profile_name,
                "similarity": float(score),
                "embedding_count": source.get("speaker_count", 1),
                "last_update": source.get("updated_at"),
                "opensearch_score": score,
            }
        )

    return matches


class ProfileEmbeddingService:
    """Service for managing profile-level speaker embeddings."""

    @staticmethod
    def update_profile_embedding(db: Session, profile_id: int) -> bool:
        """
        Update the consolidated embedding for a speaker profile by averaging
        all embeddings from speakers assigned to this profile.

        Args:
            db: Database session
            profile_id: ID of the speaker profile to update

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get the profile
            profile = db.query(SpeakerProfile).filter(SpeakerProfile.id == profile_id).first()
            if not profile:
                logger.error(f"Profile {profile_id} not found")
                return False

            # Get all speakers assigned to this profile
            speakers = db.query(Speaker).filter(Speaker.profile_id == profile_id).all()

            if not speakers:
                logger.warning(f"No speakers assigned to profile {profile_id}")
                # Clear the profile embedding if no speakers are assigned
                profile.embedding_count = 0
                profile.last_embedding_update = datetime.utcnow()
                db.commit()

                # Clear from OpenSearch as well
                try:
                    from app.services.opensearch_service import remove_profile_embedding

                    remove_profile_embedding(profile_id)
                    logger.info(f"Cleared profile {profile_id} embedding from OpenSearch")
                except Exception as e:
                    logger.warning(f"Could not clear profile embedding from OpenSearch: {e}")

                return True

            # Collect embeddings from all speakers
            embeddings = []
            for speaker in speakers:
                embedding = get_speaker_embedding(str(speaker.uuid))
                if embedding:
                    embeddings.append(embedding)
                else:
                    logger.warning(
                        f"No embedding found for speaker {speaker.uuid} in profile {profile_id}"
                    )

            if not embeddings:
                logger.warning(f"No valid embeddings found for profile {profile_id}")
                return False

            # Calculate the average embedding using numpy
            embeddings_array = np.array(embeddings)
            averaged_embedding = np.mean(embeddings_array, axis=0)

            # Update the profile metadata
            profile.embedding_count = len(embeddings)
            profile.last_embedding_update = datetime.utcnow()

            db.commit()

            # Store in OpenSearch with proper document type for efficient retrieval
            try:
                from app.services.opensearch_service import store_profile_embedding

                store_profile_embedding(
                    profile_id=profile_id,
                    profile_uuid=str(profile.uuid),
                    profile_name=profile.name,
                    embedding=averaged_embedding.tolist(),
                    speaker_count=len(embeddings),
                    user_id=profile.user_id,
                )
                logger.info(f"Stored profile {profile_id} embedding in OpenSearch")
            except Exception as e:
                logger.warning(f"Failed to store profile {profile_id} embedding in OpenSearch: {e}")

            logger.info(
                f"Updated profile {profile_id} embedding with average of {len(embeddings)} speaker embeddings"
            )
            return True

        except Exception as e:
            logger.error(f"Error updating profile embedding for profile {profile_id}: {e}")
            db.rollback()
            return False

    @staticmethod
    def add_speaker_to_profile_embedding(db: Session, speaker_id: int, profile_id: int) -> bool:
        """
        Add a speaker's embedding to the profile's consolidated embedding.
        This is an incremental update that adjusts the profile embedding
        without recalculating from all speakers.

        Args:
            db: Database session
            speaker_id: ID of the speaker to add
            profile_id: ID of the profile to update

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get the speaker object to extract UUID
            speaker = db.query(Speaker).filter(Speaker.id == speaker_id).first()
            if not speaker:
                logger.error(f"Speaker {speaker_id} not found")
                return False

            # Get the speaker embedding using UUID
            speaker_embedding = get_speaker_embedding(str(speaker.uuid))
            if not speaker_embedding:
                logger.warning(f"No embedding found for speaker {speaker.uuid}")
                # Fall back to full recalculation
                return ProfileEmbeddingService.update_profile_embedding(db, profile_id)

            # Get the profile
            profile = db.query(SpeakerProfile).filter(SpeakerProfile.id == profile_id).first()
            if not profile:
                logger.error(f"Profile {profile_id} not found")
                return False

            # Update embedding count and timestamp (vectors stored in OpenSearch)
            profile.embedding_count = profile.embedding_count + 1 if profile.embedding_count else 1
            profile.last_embedding_update = datetime.utcnow()
            db.commit()

            # Store/update embedding in OpenSearch for optimal vector similarity performance
            try:
                from app.services.opensearch_service import store_profile_embedding

                store_profile_embedding(
                    profile_id=profile_id,
                    profile_uuid=str(profile.uuid),
                    profile_name=profile.name,
                    embedding=speaker_embedding,
                    speaker_count=profile.embedding_count,
                    user_id=profile.user_id,
                )
                logger.info(f"Updated profile {profile_id} embedding in OpenSearch")
            except Exception as e:
                logger.error(f"Failed to update profile embedding in OpenSearch: {e}")

            logger.info(
                f"Added speaker {speaker_id} embedding to profile {profile_id} "
                f"(now has {profile.embedding_count} embeddings)"
            )
            return True

        except Exception as e:
            logger.error(
                f"Error adding speaker {speaker_id} to profile {profile_id} embedding: {e}"
            )
            db.rollback()
            return False

    @staticmethod
    def remove_speaker_from_profile_embedding(
        db: Session, speaker_id: int, profile_id: int
    ) -> bool:
        """
        Remove a speaker's contribution from the profile's consolidated embedding.
        This triggers a full recalculation of the profile embedding.

        Args:
            db: Database session
            speaker_id: ID of the speaker to remove
            profile_id: ID of the profile to update

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Removing speaker {speaker_id} from profile {profile_id} embedding")
            # For removal, we always do a full recalculation to ensure accuracy
            return ProfileEmbeddingService.update_profile_embedding(db, profile_id)

        except Exception as e:
            logger.error(
                f"Error removing speaker {speaker_id} from profile {profile_id} embedding: {e}"
            )
            return False

    @staticmethod
    def _group_speakers_by_profile(speakers: list[Speaker]) -> dict[int, list[Speaker]]:
        """Group speakers by their profile ID."""
        speakers_by_profile: dict[int, list[Speaker]] = {}
        for speaker in speakers:
            if speaker.profile_id not in speakers_by_profile:
                speakers_by_profile[speaker.profile_id] = []
            speakers_by_profile[speaker.profile_id].append(speaker)
        return speakers_by_profile

    @staticmethod
    def _process_single_profile_in_batch(
        profile: SpeakerProfile,
        profile_id: int,
        speakers: list[Speaker],
        speaker_embeddings: dict[int, list[float]],
    ) -> bool:
        """Process a single profile during batch update."""
        if not speakers:
            return _process_profile_with_no_speakers(profile, profile_id)

        embeddings = [
            speaker_embeddings[speaker.id]
            for speaker in speakers
            if speaker.id in speaker_embeddings
        ]

        if not embeddings:
            logger.warning(f"No valid embeddings found for profile {profile_id}")
            return False

        return _process_profile_with_embeddings(profile, profile_id, embeddings)

    @staticmethod
    def batch_update_profile_embeddings(db: Session, profile_ids: list[int]) -> dict[int, bool]:
        """
        Update embeddings for multiple profiles in a batch operation.

        This method efficiently processes multiple profiles by:
        - Collecting all speaker data in bulk queries
        - Processing embeddings in batches
        - Minimizing database round trips

        Args:
            db: SQLAlchemy database session
            profile_ids: List of profile IDs to update

        Returns:
            Dictionary mapping profile_id to success status (True/False)
        """
        if not profile_ids:
            return {}

        results: dict[int, bool] = {}

        try:
            # Bulk fetch all profiles and speakers
            profiles = db.query(SpeakerProfile).filter(SpeakerProfile.id.in_(profile_ids)).all()
            profile_map = {profile.id: profile for profile in profiles}

            all_speakers = db.query(Speaker).filter(Speaker.profile_id.in_(profile_ids)).all()
            speakers_by_profile = ProfileEmbeddingService._group_speakers_by_profile(all_speakers)
            speaker_embeddings = _collect_speaker_embeddings(all_speakers)

            # Process each profile
            for profile_id in profile_ids:
                profile = profile_map.get(profile_id)
                if not profile:
                    logger.error(f"Profile {profile_id} not found in batch")
                    results[profile_id] = False
                    continue

                try:
                    speakers = speakers_by_profile.get(profile_id, [])
                    results[profile_id] = ProfileEmbeddingService._process_single_profile_in_batch(
                        profile, profile_id, speakers, speaker_embeddings
                    )
                except Exception as e:
                    logger.error(f"Error updating profile {profile_id} in batch: {e}")
                    results[profile_id] = False

            db.commit()
            success_count = sum(1 for r in results.values() if r)
            logger.info(f"Batch updated {success_count} profiles successfully")

        except Exception as e:
            logger.error(f"Error in batch profile embedding update: {e}")
            db.rollback()
            for profile_id in profile_ids:
                results[profile_id] = False

        return results

    @staticmethod
    def get_profile_embedding(db: Session, profile_id: int) -> Optional[list[float]]:
        """
        Get the consolidated embedding for a speaker profile.

        Args:
            db: Database session
            profile_id: ID of the speaker profile

        Returns:
            The profile's embedding vector, or None if not available
        """
        try:
            # Get profile object to extract UUID
            from app.models.media import SpeakerProfile

            profile = db.query(SpeakerProfile).filter(SpeakerProfile.id == profile_id).first()
            if not profile:
                logger.error(f"Profile {profile_id} not found")
                return None

            # Get embedding from OpenSearch (primary storage for vectors) using UUID
            from app.services.opensearch_service import get_profile_embedding

            return get_profile_embedding(str(profile.uuid))

        except Exception as e:
            logger.error(f"Error retrieving profile embedding for profile {profile_id}: {e}")
            return None

    @staticmethod
    def calculate_profile_similarity(
        db: Session, embedding: list[float], user_id: int, threshold: float = 0.7
    ) -> list[dict]:
        """
        Find speaker profiles using OpenSearch native kNN search for optimal performance.

        Completely leverages OpenSearch's HNSW algorithm with cosine similarity
        instead of manual calculations for maximum efficiency.

        Args:
            db: Database session
            embedding: The embedding to compare against
            user_id: User ID to filter profiles
            threshold: Minimum similarity threshold

        Returns:
            List of matching profiles with similarity scores
        """
        try:
            opensearch_client, settings, should_continue = _check_opensearch_profile_prerequisites(
                user_id
            )
            if not should_continue:
                return []

            if not _check_profiles_exist_in_opensearch(
                opensearch_client, settings.OPENSEARCH_SPEAKER_INDEX, user_id
            ):
                return []

            matches = _execute_knn_search(
                opensearch_client,
                settings.OPENSEARCH_SPEAKER_INDEX,
                embedding,
                user_id,
                threshold,
            )

            logger.info(
                f"OpenSearch found {len(matches)} profile matches above threshold {threshold}"
            )
            return matches

        except Exception as e:
            logger.error(f"Error in OpenSearch profile similarity search: {e}")
            return []
