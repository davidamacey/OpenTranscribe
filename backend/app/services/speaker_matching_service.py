import logging
import uuid
from typing import Any
from typing import Optional

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import SPEAKER_CONFIDENCE_HIGH
from app.core.constants import SPEAKER_CONFIDENCE_LOW
from app.core.constants import SPEAKER_CONFIDENCE_MEDIUM
from app.models.media import Speaker
from app.models.media import SpeakerCollectionMember
from app.models.media import SpeakerMatch
from app.models.media import SpeakerProfile
from app.services.opensearch_service import add_speaker_embedding
from app.services.opensearch_service import find_matching_speaker
from app.services.speaker_embedding_service import SpeakerEmbeddingService

logger = logging.getLogger(__name__)


class ConfidenceLevel:
    """Confidence level thresholds for speaker matching"""

    HIGH = SPEAKER_CONFIDENCE_HIGH  # Auto-accept (green)
    MEDIUM = SPEAKER_CONFIDENCE_MEDIUM  # Requires validation (yellow)
    LOW = SPEAKER_CONFIDENCE_LOW  # Requires user input (red)


class SpeakerMatchingService:
    """Service for matching speakers across media files with confidence levels."""

    def __init__(self, db: Session, embedding_service: Optional[SpeakerEmbeddingService]):
        self.db = db
        self.embedding_service = embedding_service

    def get_confidence_level(self, confidence: float) -> str:
        """
        Determine the confidence level for UI display.

        Args:
            confidence: Confidence score (0-1)

        Returns:
            'high', 'medium', or 'low'
        """
        if confidence >= ConfidenceLevel.HIGH:
            return "high"
        elif confidence >= ConfidenceLevel.MEDIUM:
            return "medium"
        else:
            return "low"

    def match_speaker_to_known_speakers(
        self, embedding: np.ndarray, user_id: int
    ) -> Optional[dict[str, Any]]:
        """
        Match a speaker embedding to known speakers, prioritizing profile embeddings
        for better cross-file recognition accuracy.

        Args:
            embedding: Speaker embedding vector
            user_id: User ID

        Returns:
            Dictionary with speaker info and confidence, or None
        """
        # First, try to match against profile embeddings for better accuracy
        profile_match = self.match_speaker_to_profiles(embedding, user_id)

        if profile_match and profile_match["confidence"] >= ConfidenceLevel.MEDIUM:
            return profile_match

        # Fallback to individual speaker matching in OpenSearch
        match = find_matching_speaker(
            embedding.tolist(),
            user_id,
            threshold=ConfidenceLevel.MEDIUM,  # Minimum threshold
        )

        if not match:
            return None

        # Get the speaker from database
        speaker = (
            self.db.query(Speaker)
            .filter(
                Speaker.id == match["speaker_id"],
                Speaker.user_id == user_id,
                Speaker.verified,
                Speaker.display_name.isnot(None),
            )
            .first()
        )

        if not speaker:
            return None

        confidence = match.get("confidence", 0.5)

        return {
            "speaker_id": speaker.id,
            "suggested_name": speaker.display_name,
            "confidence": confidence,
            "confidence_level": self.get_confidence_level(confidence),
            "auto_accept": confidence >= ConfidenceLevel.HIGH,
            "source": "individual_embedding",
        }

    def match_speaker_to_profiles(
        self, embedding: np.ndarray, user_id: int
    ) -> Optional[dict[str, Any]]:
        """
        Match a speaker embedding against consolidated profile embeddings.
        This provides better accuracy than individual speaker matching.

        Args:
            embedding: Speaker embedding vector
            user_id: User ID

        Returns:
            Dictionary with profile match info and confidence, or None
        """
        try:
            from app.services.profile_embedding_service import ProfileEmbeddingService

            # Get profile matches using the ProfileEmbeddingService
            profile_matches = ProfileEmbeddingService.calculate_profile_similarity(
                self.db, embedding.tolist(), user_id, threshold=ConfidenceLevel.LOW
            )

            if not profile_matches:
                return None

            # Return the best match
            best_match = profile_matches[0]
            confidence = best_match["similarity"]

            # Get the profile from database to verify it exists
            profile = (
                self.db.query(SpeakerProfile)
                .filter(
                    SpeakerProfile.id == best_match["profile_id"],
                    SpeakerProfile.user_id == user_id,
                )
                .first()
            )

            if not profile:
                return None

            # Try to get a representative speaker from this profile if one exists
            # This is optional - the profile itself is sufficient for matching
            profile_speaker = (
                self.db.query(Speaker)
                .filter(
                    Speaker.profile_id == best_match["profile_id"],
                    Speaker.user_id == user_id,
                    Speaker.verified,
                    Speaker.display_name.isnot(None),
                )
                .first()
            )

            # Use profile_speaker.id if available, otherwise None
            # The system will handle None speaker_id correctly
            speaker_id = profile_speaker.id if profile_speaker else None

            return {
                "speaker_id": speaker_id,
                "suggested_name": best_match["profile_name"],
                "confidence": confidence,
                "confidence_level": self.get_confidence_level(confidence),
                "auto_accept": confidence >= ConfidenceLevel.HIGH,
                "profile_id": best_match["profile_id"],
                "source": "profile_embedding",
                "embedding_count": best_match["embedding_count"],
            }

        except Exception as e:
            logger.error(f"Error matching speaker to profiles: {e}")
            return None

    def find_unlabeled_speaker_matches(
        self, embedding: np.ndarray, user_id: int, exclude_speaker_id: int
    ) -> list[dict[str, Any]]:
        """
        Find matches to unlabeled speakers across videos (for pre-labeling suggestions).

        Args:
            embedding: Speaker embedding vector
            user_id: User ID
            exclude_speaker_id: Speaker ID to exclude from results

        Returns:
            List of matched speakers with video source information
        """
        matches = []
        logger.info(f"Finding unlabeled matches for speaker {exclude_speaker_id}, user {user_id}")

        try:
            from app.services.opensearch_service import opensearch_client
            from app.services.opensearch_service import settings

            query = {
                "size": 10,  # Get more potential matches for unlabeled speakers
                "query": {
                    "knn": {
                        "embedding": {
                            "vector": embedding.tolist(),
                            "k": 10,
                            "filter": {
                                "bool": {
                                    "filter": [
                                        {"term": {"user_id": user_id}},
                                        {
                                            "bool": {
                                                "must_not": [
                                                    {"term": {"speaker_id": exclude_speaker_id}},
                                                    {
                                                        "exists": {"field": "document_type"}
                                                    },  # Exclude profile documents
                                                ]
                                            }
                                        },
                                    ]
                                }
                            },
                        }
                    }
                },
            }

            response = opensearch_client.search(index=settings.OPENSEARCH_SPEAKER_INDEX, body=query)

            logger.info(
                f"OpenSearch response for speaker {exclude_speaker_id}: {len(response['hits']['hits'])} hits"
            )

            # Process each match and get speaker details
            for hit in response["hits"]["hits"]:
                confidence = hit["_score"]
                if (
                    confidence >= ConfidenceLevel.HIGH
                ):  # ConfidenceLevel.HIGH threshold for high-confidence matches only
                    # Safely access speaker_id - skip if not present (e.g., profile documents)
                    source = hit.get("_source", {})
                    match_speaker_id = source.get("speaker_id")
                    if not match_speaker_id:
                        continue

                    # Get the matched speaker details
                    matched_speaker = (
                        self.db.query(Speaker).filter(Speaker.id == match_speaker_id).first()
                    )

                    if matched_speaker and matched_speaker.media_file:
                        matches.append(
                            {
                                "speaker_id": match_speaker_id,
                                "speaker_name": matched_speaker.name,
                                "display_name": matched_speaker.display_name,
                                "media_file_id": matched_speaker.media_file_id,
                                "media_file_title": matched_speaker.media_file.title
                                or matched_speaker.media_file.filename,
                                "confidence": confidence,
                                "confidence_level": self.get_confidence_level(confidence),
                                "verified": matched_speaker.verified,
                                "is_cross_video_suggestion": True,
                            }
                        )

            # Sort by confidence (highest first)
            matches.sort(key=lambda x: x["confidence"], reverse=True)

        except Exception as e:
            logger.error(f"Error finding unlabeled speaker matches: {e}")

        logger.info(f"Returning {len(matches)} unlabeled matches for speaker {exclude_speaker_id}")
        return matches

    def match_speaker_to_profile(
        self, embedding: np.ndarray, user_id: int
    ) -> Optional[dict[str, Any]]:
        """
        Match a speaker embedding to an existing profile.

        Args:
            embedding: Speaker embedding vector
            user_id: User ID

        Returns:
            Dictionary with profile info and confidence, or None
        """
        # Search for matching speaker in OpenSearch
        match = find_matching_speaker(
            embedding.tolist(),
            user_id,
            threshold=ConfidenceLevel.MEDIUM,  # Minimum threshold
        )

        if not match:
            return None

        # Get the speaker profile from database
        profile = (
            self.db.query(SpeakerProfile)
            .filter(
                SpeakerProfile.id == match["speaker_id"],
                SpeakerProfile.user_id == user_id,
            )
            .first()
        )

        if not profile:
            return None

        confidence = match.get("confidence", 0.5)

        return {
            "profile_id": profile.id,
            "profile_name": profile.name,
            "confidence": confidence,
            "confidence_level": self.get_confidence_level(confidence),
            "auto_accept": confidence >= ConfidenceLevel.HIGH,
        }

    def create_speaker_profile(
        self,
        name: str,
        user_id: int,
        description: Optional[str] = None,
        initial_embedding: Optional[np.ndarray] = None,
    ) -> SpeakerProfile:
        """
        Create a new speaker profile.

        Args:
            name: Speaker name
            user_id: User ID
            description: Optional description
            initial_embedding: Optional initial embedding

        Returns:
            Created SpeakerProfile
        """
        profile = SpeakerProfile(
            user_id=user_id, name=name, description=description, uuid=str(uuid.uuid4())
        )

        self.db.add(profile)
        self.db.flush()

        # Add initial embedding to OpenSearch if provided
        if initial_embedding is not None:
            add_speaker_embedding(
                speaker_id=profile.id,
                speaker_uuid=profile.uuid,
                user_id=user_id,
                name=name,
                embedding=initial_embedding.tolist(),
            )

        return profile

    def assign_speaker_to_profile(
        self, speaker_id: int, profile_id: int, confidence: Optional[float] = None
    ) -> Speaker:
        """
        Assign a speaker instance to a profile.

        Args:
            speaker_id: Speaker instance ID
            profile_id: Speaker profile ID
            confidence: Optional confidence score

        Returns:
            Updated Speaker instance
        """
        speaker = self.db.query(Speaker).filter(Speaker.id == speaker_id).first()
        if not speaker:
            raise ValueError(f"Speaker {speaker_id} not found")

        speaker.profile_id = profile_id
        speaker.verified = True
        if confidence is not None:
            speaker.confidence = confidence

        self.db.flush()
        return speaker

    def process_speaker_segments(
        self,
        audio_path: str,
        media_file_id: int,
        user_id: int,
        segments: list[dict[str, Any]],
        speaker_mapping: dict[str, int],
    ) -> list[dict[str, Any]]:
        """
        Process speaker segments and match to profiles.

        Args:
            audio_path: Path to audio file
            media_file_id: Media file ID
            user_id: User ID
            segments: Transcript segments
            speaker_mapping: Mapping of speaker labels to IDs

        Returns:
            List of speaker match results
        """
        # Extract embeddings for all speakers
        speaker_embeddings = self.embedding_service.extract_embeddings_for_segments(
            audio_path, segments, speaker_mapping
        )

        results = []

        for speaker_id, embeddings in speaker_embeddings.items():
            result = self._process_single_speaker(speaker_id, embeddings, user_id, media_file_id)
            if result:
                results.append(result)

        self.db.commit()
        return results

    def _process_single_speaker(
        self, speaker_id: int, embeddings: list[np.ndarray], user_id: int, media_file_id: int
    ) -> Optional[dict[str, Any]]:
        """
        Process a single speaker's embeddings and find matches.

        Args:
            speaker_id: Speaker ID
            embeddings: List of embeddings for this speaker
            user_id: User ID
            media_file_id: Media file ID

        Returns:
            Speaker processing result or None if failed
        """

        if not embeddings:
            logger.warning(f"No valid embeddings for speaker {speaker_id}")
            return None

        # Aggregate embeddings for this speaker
        try:
            aggregated_embedding = self.embedding_service.aggregate_embeddings(embeddings)
        except Exception as e:
            logger.error(f"Error aggregating embeddings for speaker {speaker_id}: {e}")
            return None

        speaker = self.db.query(Speaker).filter(Speaker.id == speaker_id).first()
        if not speaker:
            return None

        # Try to match to known speakers with display names
        match = self.match_speaker_to_known_speakers(aggregated_embedding, user_id)

        if match:
            return self._handle_speaker_match(
                speaker, match, aggregated_embedding, user_id, media_file_id
            )
        else:
            return self._handle_no_speaker_match(
                speaker, aggregated_embedding, user_id, media_file_id
            )

    def _handle_speaker_match(
        self,
        speaker: Speaker,
        match: dict[str, Any],
        aggregated_embedding: np.ndarray,
        user_id: int,
        media_file_id: int,
    ) -> dict[str, Any]:
        """
        Handle case where speaker match is found.

        Args:
            speaker: Speaker object
            match: Match result dictionary
            aggregated_embedding: Aggregated embedding
            user_id: User ID
            media_file_id: Media file ID

        Returns:
            Speaker processing result
        """
        # Found a matching speaker - store the suggestion only if high confidence
        speaker.confidence = match["confidence"]
        if match["confidence"] >= ConfidenceLevel.HIGH:  # Only suggest if ≥75% confidence
            speaker.suggested_name = match["suggested_name"]

        # If high confidence, auto-apply the suggestion
        if match["auto_accept"]:
            logger.info(
                f"Auto-accepting match for speaker {speaker.id} -> {match['suggested_name']}"
            )
            speaker.display_name = match["suggested_name"]
            speaker.verified = True
            # Assign to profile if this match came from a profile
            if match.get("profile_id"):
                speaker.profile_id = match["profile_id"]

        self.db.flush()

        # Sync profile assignment to OpenSearch immediately
        if match["auto_accept"] and match.get("profile_id"):
            from app.services.opensearch_service import update_speaker_profile

            # Get profile UUID
            profile_uuid = None
            if speaker.profile_id:
                profile = (
                    self.db.query(SpeakerProfile)
                    .filter(SpeakerProfile.id == speaker.profile_id)
                    .first()
                )
                if profile:
                    profile_uuid = str(profile.uuid)

            update_speaker_profile(
                speaker_uuid=str(speaker.uuid),
                profile_id=speaker.profile_id,
                profile_uuid=profile_uuid,
                verified=speaker.verified,
            )

            # Update the profile embedding to include this newly assigned speaker
            from app.services.profile_embedding_service import ProfileEmbeddingService

            ProfileEmbeddingService.update_profile_embedding(self.db, speaker.profile_id)

            # Propagate profile assignment to other similar speakers
            self._propagate_profile_assignment(speaker.id, speaker.profile_id, user_id)

        # Store/update embedding with suggested name for future matching
        if aggregated_embedding is not None and aggregated_embedding.size > 0:
            add_speaker_embedding(
                speaker_id=speaker.id,
                speaker_uuid=speaker.uuid,
                user_id=user_id,
                name=speaker.name,
                embedding=aggregated_embedding.tolist(),
                profile_id=speaker.profile_id,  # Include profile_id for cross-video matching
                profile_uuid=speaker.profile.uuid if speaker.profile else None,
                display_name=speaker.display_name
                if speaker.display_name
                else match["suggested_name"],
                media_file_id=media_file_id,
            )

            # Find and store matches with other speakers
            self.find_and_store_speaker_matches(
                speaker.id, aggregated_embedding, user_id, threshold=0.5
            )

        return {
            "speaker_id": speaker.id,
            "speaker_label": speaker.name,
            "suggested_name": match["suggested_name"],
            "confidence": match["confidence"],
            "status": "matched",
        }

    def _handle_no_speaker_match(
        self,
        speaker: Speaker,
        aggregated_embedding: np.ndarray,
        user_id: int,
        media_file_id: int,
    ) -> dict[str, Any]:
        """
        Handle case where no speaker match is found.

        Args:
            speaker: Speaker object
            aggregated_embedding: Aggregated embedding
            user_id: User ID
            media_file_id: Media file ID

        Returns:
            Speaker processing result
        """
        # No match found, store embedding for future matching
        if aggregated_embedding is not None and aggregated_embedding.size > 0:
            embedding_list = aggregated_embedding.tolist()
            logger.info(
                f"Storing embedding for speaker {speaker.id}: length={len(embedding_list)}, first_few={embedding_list[:3]}"
            )
            add_speaker_embedding(
                speaker_id=speaker.id,
                speaker_uuid=speaker.uuid,
                user_id=user_id,
                name=speaker.name,
                embedding=embedding_list,
                profile_id=speaker.profile_id,  # Include profile_id for cross-video matching
                profile_uuid=speaker.profile.uuid if speaker.profile else None,
                display_name=speaker.display_name if speaker.display_name else None,
                media_file_id=media_file_id,
            )

            # Find and store matches with other speakers
            found_matches = self.find_and_store_speaker_matches(
                speaker.id, aggregated_embedding, user_id, threshold=0.5
            )

            if found_matches:
                logger.info(f"Found {len(found_matches)} matches for speaker {speaker.id}")
                # If there are high-confidence matches from verified speakers, suggest them
                for match in found_matches:
                    if match["confidence"] >= ConfidenceLevel.HIGH and match["display_name"]:
                        speaker.suggested_name = match["display_name"]
                        speaker.confidence = match["confidence"]
                        self.db.flush()
                        break

            return {
                "speaker_id": speaker.id,
                "speaker_label": speaker.name,
                "profile_match": None,
                "status": "new",
            }
        else:
            logger.warning(f"Invalid embedding for speaker {speaker.id}, skipping storage")
            return {
                "speaker_id": speaker.id,
                "speaker_label": speaker.name,
                "profile_match": None,
                "status": "failed",
            }

    def find_speaker_occurrences(self, profile_id: int, user_id: int) -> list[dict[str, Any]]:
        """
        Find all media files where a speaker profile appears.

        Args:
            profile_id: Speaker profile ID
            user_id: User ID

        Returns:
            List of media file information
        """
        # Get all speaker instances for this profile
        speakers = (
            self.db.query(Speaker)
            .filter(Speaker.profile_id == profile_id, Speaker.user_id == user_id)
            .all()
        )

        occurrences = []
        for speaker in speakers:
            media_file = speaker.media_file
            occurrences.append(
                {
                    "media_file_id": media_file.id,
                    "filename": media_file.filename,
                    "title": media_file.title or media_file.filename,
                    "upload_time": media_file.upload_time.isoformat(),
                    "speaker_label": speaker.name,
                    "confidence": speaker.confidence,
                    "verified": speaker.verified,
                }
            )

        # Sort by upload time (newest first)
        occurrences.sort(key=lambda x: x["upload_time"], reverse=True)

        return occurrences

    def _get_speaker_embedding_for_propagation(
        self, matched_speaker_id: int
    ) -> tuple[Optional[list[float]], Optional[str]]:
        """
        Get speaker embedding for profile propagation.

        Args:
            matched_speaker_id: ID of the speaker to get embedding for

        Returns:
            Tuple of (embedding, speaker_uuid) or (None, None) if not found
        """
        from app.db.base import get_db
        from app.services.opensearch_service import get_speaker_embedding

        db = next(get_db())
        try:
            matched_speaker = db.query(Speaker).filter(Speaker.id == matched_speaker_id).first()
            if not matched_speaker:
                logger.warning(f"Speaker {matched_speaker_id} not found, skipping propagation")
                return None, None

            embedding = get_speaker_embedding(str(matched_speaker.uuid))
            if not embedding:
                logger.warning(
                    f"No embedding found for speaker {matched_speaker.uuid}, skipping propagation"
                )
                return None, None

            return embedding, str(matched_speaker.uuid)
        finally:
            db.close()

    def _should_propagate_to_speaker(self, speaker: Speaker) -> bool:
        """
        Check if a speaker should receive profile propagation.

        Args:
            speaker: Speaker to check

        Returns:
            True if speaker should be updated with profile
        """
        if speaker.profile_id:
            return False
        if not speaker.display_name:
            return False
        return not speaker.display_name.startswith("SPEAKER_")

    def _update_speakers_in_opensearch(
        self, updated_speakers: list[Speaker], profile_id: int
    ) -> None:
        """
        Update speakers in OpenSearch after profile propagation.

        Args:
            updated_speakers: List of speakers to update
            profile_id: Profile ID assigned to speakers
        """
        from app.services.opensearch_service import update_speaker_profile

        profile_uuid = None
        if profile_id:
            profile = self.db.query(SpeakerProfile).filter(SpeakerProfile.id == profile_id).first()
            if profile:
                profile_uuid = str(profile.uuid)

        for speaker in updated_speakers:
            update_speaker_profile(
                speaker_uuid=str(speaker.uuid),
                profile_id=speaker.profile_id,
                profile_uuid=profile_uuid,
                verified=speaker.verified,
            )

    def _propagate_profile_assignment(self, matched_speaker_id: int, profile_id: int, user_id: int):
        """
        When a speaker is assigned to a profile, find and update other similar speakers
        with the same profile assignment.

        Args:
            matched_speaker_id: ID of the speaker that was just assigned to a profile
            profile_id: ID of the profile assigned
            user_id: User ID for scoping
        """
        try:
            embedding, _ = self._get_speaker_embedding_for_propagation(matched_speaker_id)
            if not embedding:
                return

            from app.services.similarity_service import SimilarityService

            similar_matches = SimilarityService.opensearch_similarity_search(
                embedding=embedding,
                user_id=user_id,
                index_name="speakers",
                threshold=0.75,  # High confidence for automatic assignment (matches SPEAKER_CONFIDENCE_HIGH)
                max_results=20,
                exclude_ids=[matched_speaker_id],
            )

            updated_speakers = []
            for match in similar_matches:
                speaker_id = match.get("speaker_id")
                if not speaker_id:
                    continue

                speaker = self.db.query(Speaker).filter(Speaker.id == speaker_id).first()
                if not speaker or not self._should_propagate_to_speaker(speaker):
                    continue

                speaker.profile_id = profile_id
                speaker.verified = True
                speaker.confidence = match["similarity"]
                updated_speakers.append(speaker)

                logger.info(
                    f"Propagated profile {profile_id} to similar speaker {speaker_id} "
                    f"(confidence: {match['similarity']:.3f})"
                )

            if not updated_speakers:
                return

            self.db.commit()
            self._update_speakers_in_opensearch(updated_speakers, profile_id)
            logger.info(
                f"Propagated profile {profile_id} to {len(updated_speakers)} similar speakers"
            )

        except Exception as e:
            logger.error(f"Error propagating profile assignment: {e}")
            self.db.rollback()

    def update_speaker_embeddings(self, profile_id: int, audio_paths: list[str]) -> bool:
        """
        Update speaker profile embeddings with new reference audio.

        Args:
            profile_id: Speaker profile ID
            audio_paths: List of audio file paths

        Returns:
            Success status
        """
        try:
            profile = self.db.query(SpeakerProfile).filter(SpeakerProfile.id == profile_id).first()

            if not profile:
                logger.error(f"Speaker profile {profile_id} not found")
                return False

            # Extract reference embedding
            embedding = self.embedding_service.extract_reference_embedding(audio_paths)

            if embedding is None:
                logger.error("Failed to extract reference embedding")
                return False

            # Update in OpenSearch
            add_speaker_embedding(
                speaker_id=profile_id,
                speaker_uuid=profile.uuid,
                user_id=profile.user_id,
                name=profile.name,
                embedding=embedding.tolist(),
            )

            return True

        except Exception as e:
            logger.error(f"Error updating speaker embeddings: {e}")
            return False

    def add_speaker_to_collection(self, profile_id: int, collection_id: int) -> bool:
        """
        Add a speaker profile to a collection.

        Args:
            profile_id: Speaker profile ID
            collection_id: Collection ID

        Returns:
            Success status
        """
        try:
            # Check if already exists
            existing = (
                self.db.query(SpeakerCollectionMember)
                .filter(
                    SpeakerCollectionMember.collection_id == collection_id,
                    SpeakerCollectionMember.speaker_profile_id == profile_id,
                )
                .first()
            )

            if existing:
                return True

            member = SpeakerCollectionMember(
                collection_id=collection_id, speaker_profile_id=profile_id
            )

            self.db.add(member)
            self.db.commit()

            return True

        except Exception as e:
            logger.error(f"Error adding speaker to collection: {e}")
            self.db.rollback()
            return False

    def _build_speaker_match_query(
        self, embedding: np.ndarray, user_id: int, exclude_speaker_id: int
    ) -> dict[str, Any]:
        """
        Build OpenSearch query for finding speaker matches.

        Args:
            embedding: Speaker embedding vector
            user_id: User ID
            exclude_speaker_id: Speaker ID to exclude from results

        Returns:
            OpenSearch query dictionary
        """
        filters = [
            {"term": {"user_id": user_id}},
            {
                "bool": {
                    "must_not": [
                        {"term": {"speaker_id": exclude_speaker_id}},
                        {"exists": {"field": "document_type"}},  # Exclude profile documents
                    ]
                }
            },
        ]

        return {
            "size": 20,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": embedding.tolist(),
                        "k": 20,
                        "filter": {"bool": {"filter": filters}},
                    }
                }
            },
        }

    def _create_speaker_match_record(
        self, speaker1_id: int, speaker2_id: int, score: float
    ) -> bool:
        """
        Create a new speaker match record in the database.

        Args:
            speaker1_id: First speaker ID (smaller)
            speaker2_id: Second speaker ID (larger)
            score: Confidence score

        Returns:
            True if match was created successfully
        """
        speaker1_exists = self.db.query(Speaker).filter(Speaker.id == speaker1_id).first()
        speaker2_exists = self.db.query(Speaker).filter(Speaker.id == speaker2_id).first()

        if not speaker1_exists or not speaker2_exists:
            logger.debug(
                f"Skipping speaker match - speaker1_id {speaker1_id} exists: "
                f"{bool(speaker1_exists)}, speaker2_id {speaker2_id} exists: {bool(speaker2_exists)}"
            )
            return False

        try:
            speaker_match = SpeakerMatch(
                speaker1_id=speaker1_id,
                speaker2_id=speaker2_id,
                confidence=score,
            )
            self.db.add(speaker_match)
            self.db.flush()
            return True
        except Exception as e:
            logger.warning(
                f"Failed to create speaker match between {speaker1_id} and {speaker2_id}: {e}"
            )
            self.db.rollback()
            return False

    def _build_match_result(self, matched_speaker: Speaker, score: float) -> dict[str, Any]:
        """
        Build a match result dictionary from a speaker.

        Args:
            matched_speaker: Speaker object
            score: Confidence score

        Returns:
            Match result dictionary
        """
        return {
            "speaker_id": matched_speaker.id,
            "speaker_name": matched_speaker.name,
            "display_name": matched_speaker.display_name,
            "media_file_id": matched_speaker.media_file_id,
            "confidence": score,
            "confidence_level": self.get_confidence_level(score),
        }

    def find_and_store_speaker_matches(
        self,
        new_speaker_id: int,
        embedding: np.ndarray,
        user_id: int,
        threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """
        Find all similar speakers and store matches in the database.

        Args:
            new_speaker_id: ID of the newly processed speaker
            embedding: Speaker embedding vector
            user_id: User ID
            threshold: Minimum similarity threshold

        Returns:
            List of found matches
        """
        matches = []

        try:
            search_results = find_matching_speaker(
                embedding.tolist(),
                user_id,
                threshold=threshold,
                exclude_speaker_ids=[new_speaker_id],
            )

            if not search_results:
                return matches

            from app.services.opensearch_service import opensearch_client
            from app.services.opensearch_service import settings

            query = self._build_speaker_match_query(embedding, user_id, new_speaker_id)
            response = opensearch_client.search(index=settings.OPENSEARCH_SPEAKER_INDEX, body=query)

            for hit in response["hits"]["hits"]:
                score = hit["_score"]
                if score < threshold:
                    continue

                match_speaker_id = hit.get("_source", {}).get("speaker_id")
                if not match_speaker_id:
                    continue

                speaker1_id = min(new_speaker_id, match_speaker_id)
                speaker2_id = max(new_speaker_id, match_speaker_id)

                existing_match = (
                    self.db.query(SpeakerMatch)
                    .filter(
                        SpeakerMatch.speaker1_id == speaker1_id,
                        SpeakerMatch.speaker2_id == speaker2_id,
                    )
                    .first()
                )

                if existing_match:
                    if score > existing_match.confidence:
                        existing_match.confidence = score
                        existing_match.updated_at = func.now()
                    continue

                if not self._create_speaker_match_record(speaker1_id, speaker2_id, score):
                    continue

                matched_speaker = (
                    self.db.query(Speaker).filter(Speaker.id == match_speaker_id).first()
                )
                if matched_speaker:
                    matches.append(self._build_match_result(matched_speaker, score))

            self.db.flush()

        except Exception as e:
            logger.error(f"Error finding and storing speaker matches: {e}")

        return matches

    def get_speaker_matches(self, speaker_id: int) -> list[dict[str, Any]]:
        """
        Get all matches for a given speaker.

        Args:
            speaker_id: Speaker ID

        Returns:
            List of matched speakers with details
        """
        matches = []

        try:
            # Query matches where speaker is either speaker1 or speaker2
            speaker_matches = (
                self.db.query(SpeakerMatch)
                .filter(
                    (SpeakerMatch.speaker1_id == speaker_id)
                    | (SpeakerMatch.speaker2_id == speaker_id)
                )
                .all()
            )

            for match in speaker_matches:
                # Determine which speaker is the match
                matched_speaker_id = (
                    match.speaker2_id if match.speaker1_id == speaker_id else match.speaker1_id
                )

                # Get the matched speaker details
                matched_speaker = (
                    self.db.query(Speaker).filter(Speaker.id == matched_speaker_id).first()
                )

                if (
                    matched_speaker and match.confidence >= ConfidenceLevel.HIGH
                ):  # Only include high-confidence matches (≥75%)
                    matches.append(
                        {
                            "speaker_id": matched_speaker.id,
                            "speaker_name": matched_speaker.name,
                            "display_name": matched_speaker.display_name,
                            "media_file_id": matched_speaker.media_file_id,
                            "media_file_title": matched_speaker.media_file.title
                            or matched_speaker.media_file.filename,
                            "confidence": match.confidence,
                            "confidence_level": self.get_confidence_level(match.confidence),
                            "verified": matched_speaker.verified,
                        }
                    )

            # Sort by confidence (highest first)
            matches.sort(key=lambda x: x["confidence"], reverse=True)

        except Exception as e:
            logger.error(f"Error getting speaker matches: {e}")

        return matches
