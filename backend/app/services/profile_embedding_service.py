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
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from app.models.media import Speaker
from app.models.media import SpeakerProfile
from app.services.opensearch_service import get_speaker_embedding

logger = logging.getLogger(__name__)


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
                embedding = get_speaker_embedding(speaker.id)
                if embedding:
                    embeddings.append(embedding)
                else:
                    logger.warning(
                        f"No embedding found for speaker {speaker.id} in profile {profile_id}"
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
            # Get the speaker embedding
            speaker_embedding = get_speaker_embedding(speaker_id)
            if not speaker_embedding:
                logger.warning(f"No embedding found for speaker {speaker_id}")
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
        results = {}

        if not profile_ids:
            return results

        try:
            # Bulk fetch all profiles
            profiles = db.query(SpeakerProfile).filter(SpeakerProfile.id.in_(profile_ids)).all()

            profile_map = {profile.id: profile for profile in profiles}

            # Bulk fetch all speakers for these profiles
            all_speakers = db.query(Speaker).filter(Speaker.profile_id.in_(profile_ids)).all()

            # Group speakers by profile
            speakers_by_profile = {}
            for speaker in all_speakers:
                if speaker.profile_id not in speakers_by_profile:
                    speakers_by_profile[speaker.profile_id] = []
                speakers_by_profile[speaker.profile_id].append(speaker)

            # Collect all speaker IDs for batch embedding fetch
            all_speaker_ids = [speaker.id for speaker in all_speakers]

            # Batch fetch embeddings from OpenSearch
            speaker_embeddings = {}
            for speaker_id in all_speaker_ids:
                embedding = get_speaker_embedding(speaker_id)
                if embedding:
                    speaker_embeddings[speaker_id] = embedding

            # Process each profile
            for profile_id in profile_ids:
                try:
                    profile = profile_map.get(profile_id)
                    if not profile:
                        logger.error(f"Profile {profile_id} not found in batch")
                        results[profile_id] = False
                        continue

                    speakers = speakers_by_profile.get(profile_id, [])

                    if not speakers:
                        # Clear the profile embedding if no speakers
                        profile.embedding_count = 0
                        profile.last_embedding_update = datetime.utcnow()

                        try:
                            from app.services.opensearch_service import remove_profile_embedding

                            remove_profile_embedding(profile_id)
                        except Exception as e:
                            logger.warning(
                                f"Could not clear profile {profile_id} embedding from OpenSearch: {e}"
                            )

                        results[profile_id] = True
                        continue

                    # Collect embeddings for this profile
                    embeddings = []
                    for speaker in speakers:
                        if speaker.id in speaker_embeddings:
                            embeddings.append(speaker_embeddings[speaker.id])

                    if not embeddings:
                        logger.warning(f"No valid embeddings found for profile {profile_id}")
                        results[profile_id] = False
                        continue

                    # Calculate average embedding
                    embeddings_array = np.array(embeddings)
                    averaged_embedding = np.mean(embeddings_array, axis=0)

                    # Update profile metadata
                    profile.embedding_count = len(embeddings)
                    profile.last_embedding_update = datetime.utcnow()

                    # Sync to OpenSearch
                    try:
                        from app.services.opensearch_service import store_profile_embedding

                        store_profile_embedding(
                            profile_id=profile_id,
                            profile_name=profile.name,
                            embedding=averaged_embedding.tolist(),
                            speaker_count=len(embeddings),
                            user_id=profile.user_id,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to sync profile {profile_id} embedding to OpenSearch: {e}"
                        )

                    results[profile_id] = True
                    logger.info(
                        f"Updated profile {profile_id} embedding with {len(embeddings)} speaker embeddings"
                    )

                except Exception as e:
                    logger.error(f"Error updating profile {profile_id} in batch: {e}")
                    results[profile_id] = False

            # Commit all changes at once
            db.commit()
            logger.info(
                f"Batch updated {len([r for r in results.values() if r])} profiles successfully"
            )

        except Exception as e:
            logger.error(f"Error in batch profile embedding update: {e}")
            db.rollback()
            # Mark all as failed
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
            # Get embedding from OpenSearch (primary storage for vectors)
            from app.services.opensearch_service import get_profile_embedding

            return get_profile_embedding(profile_id)

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
            # Use OpenSearch's native similarity search for profiles

            # Search for similar profile embeddings using OpenSearch
            # Note: Profiles are stored in the speakers index with id prefix "profile_"
            # Since profiles are stored in speakers index, we need to do a direct search
            from app.services.opensearch_service import opensearch_client
            from app.services.opensearch_service import settings

            if not opensearch_client:
                logger.warning("OpenSearch client not initialized")
                return []

            # First check if there are any profile documents to avoid KNN query on empty sets
            # This prevents OpenSearch 2.5.0 "failed to create query: Rewrite first" errors
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
                # First check if the index exists
                if not opensearch_client.indices.exists(index=settings.OPENSEARCH_SPEAKER_INDEX):
                    logger.info(f"Speakers index does not exist yet, skipping profile similarity search")
                    return []

                profile_check = opensearch_client.search(
                    index=settings.OPENSEARCH_SPEAKER_INDEX, body=profile_check_query
                )
                if profile_check["hits"]["total"]["value"] == 0:
                    logger.info(f"No profile documents found for user {user_id}, skipping KNN search")
                    return []
            except Exception as e:
                logger.warning(f"Profile document check failed: {e}, proceeding with KNN query")

            # Build query to search only profile documents (those with document_type="profile")
            # Use OpenSearch 2.5.0 compatible KNN query structure
            filters = [
                {"term": {"document_type": "profile"}},  # CRITICAL: Only profile documents
                {"term": {"user_id": user_id}},  # User's profiles only
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
                response = opensearch_client.search(
                    index=settings.OPENSEARCH_SPEAKER_INDEX, body=query
                )
                opensearch_matches = []

                for hit in response["hits"]["hits"]:
                    score = hit["_score"]
                    if score >= threshold:
                        source = hit["_source"]
                        opensearch_matches.append(
                            {
                                "profile_id": source.get("profile_id"),
                                "profile_name": source.get("profile_name"),
                                "embedding_count": source.get("speaker_count", 1),
                                "similarity": score,
                                "opensearch_score": score,
                                "last_update": source.get("updated_at"),
                            }
                        )

                logger.info(
                    f"Found {len(opensearch_matches)} profile matches above threshold {threshold}"
                )

            except Exception as e:
                logger.error(f"Error in OpenSearch profile similarity search <calculate_profile_similarity - above threshold>: {e}")
                return []

            # Use OpenSearch data directly - no need for additional database queries
            matches = []
            for match in opensearch_matches:
                profile_id = match.get("profile_id")
                profile_name = match.get("profile_name")

                if not profile_id or not profile_name:
                    continue

                matches.append(
                    {
                        "profile_id": profile_id,
                        "profile_name": profile_name,
                        "similarity": float(match["similarity"]),
                        "embedding_count": match["embedding_count"],
                        "last_update": match.get("last_update"),
                        "opensearch_score": match.get("opensearch_score", match["similarity"]),
                    }
                )

            logger.info(
                f"OpenSearch found {len(matches)} profile matches above threshold {threshold}"
            )
            return matches

        except Exception as e:
            logger.error(f"Error in OpenSearch profile similarity search <calculate_profile_similarity - overall>: {e}")
            # Return empty list - no fallbacks for maximum performance
            return []
