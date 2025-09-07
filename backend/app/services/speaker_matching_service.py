import logging
import uuid
from typing import Any
from typing import Optional

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

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

    HIGH = 0.75  # Auto-accept (green)
    MEDIUM = 0.50  # Requires validation (yellow)
    LOW = 0.0  # Requires user input (red)


class SpeakerMatchingService:
    """Service for matching speakers across media files with confidence levels."""

    def __init__(
        self, db: Session, embedding_service: Optional[SpeakerEmbeddingService]
    ):
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
        Match a speaker embedding to known speakers with display names.

        Args:
            embedding: Speaker embedding vector
            user_id: User ID

        Returns:
            Dictionary with speaker info and confidence, or None
        """
        # Search for matching speaker in OpenSearch
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
        }

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
        logger.info(
            f"Finding unlabeled matches for speaker {exclude_speaker_id}, user {user_id}"
        )

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
                                                "must_not": {
                                                    "term": {
                                                        "speaker_id": exclude_speaker_id
                                                    }
                                                }
                                            }
                                        },
                                    ]
                                }
                            },
                        }
                    }
                },
            }

            response = opensearch_client.search(
                index=settings.OPENSEARCH_SPEAKER_INDEX, body=query
            )

            logger.info(
                f"OpenSearch response for speaker {exclude_speaker_id}: {len(response['hits']['hits'])} hits"
            )

            # Process each match and get speaker details
            for hit in response["hits"]["hits"]:
                confidence = hit["_score"]
                if (
                    confidence >= ConfidenceLevel.HIGH
                ):  # 0.75 threshold for high-confidence matches only
                    match_speaker_id = hit["_source"]["speaker_id"]

                    # Get the matched speaker details
                    matched_speaker = (
                        self.db.query(Speaker)
                        .filter(Speaker.id == match_speaker_id)
                        .first()
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
                                "confidence_level": self.get_confidence_level(
                                    confidence
                                ),
                                "verified": matched_speaker.verified,
                                "is_cross_video_suggestion": True,
                            }
                        )

            # Sort by confidence (highest first)
            matches.sort(key=lambda x: x["confidence"], reverse=True)

        except Exception as e:
            logger.error(f"Error finding unlabeled speaker matches: {e}")

        logger.info(
            f"Returning {len(matches)} unlabeled matches for speaker {exclude_speaker_id}"
        )
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
            if not embeddings:
                logger.warning(f"No valid embeddings for speaker {speaker_id}")
                continue

            # Aggregate embeddings for this speaker
            try:
                aggregated_embedding = self.embedding_service.aggregate_embeddings(
                    embeddings
                )
            except Exception as e:
                logger.error(
                    f"Error aggregating embeddings for speaker {speaker_id}: {e}"
                )
                continue

            speaker = self.db.query(Speaker).filter(Speaker.id == speaker_id).first()
            if not speaker:
                continue

            # Try to match to known speakers with display names
            match = self.match_speaker_to_known_speakers(aggregated_embedding, user_id)

            if match:
                # Found a matching speaker - store the suggestion only if high confidence
                speaker.confidence = match["confidence"]
                if (
                    match["confidence"] >= ConfidenceLevel.HIGH
                ):  # Only suggest if ≥75% confidence
                    speaker.suggested_name = match["suggested_name"]

                # If high confidence, auto-apply the suggestion
                if match["auto_accept"]:
                    speaker.display_name = match["suggested_name"]
                    speaker.verified = True

                self.db.flush()

                # Store/update embedding with suggested name for future matching
                if aggregated_embedding is not None and aggregated_embedding.size > 0:
                    add_speaker_embedding(
                        speaker_id=speaker_id,
                        user_id=user_id,
                        name=speaker.name,
                        embedding=aggregated_embedding.tolist(),
                        display_name=speaker.display_name
                        if speaker.display_name
                        else match["suggested_name"],
                        media_file_id=media_file_id,
                    )

                    # Find and store matches with other speakers
                    self.find_and_store_speaker_matches(
                        speaker_id, aggregated_embedding, user_id, threshold=0.5
                    )

                results.append(
                    {
                        "speaker_id": speaker_id,
                        "speaker_label": speaker.name,
                        "suggested_name": match["suggested_name"],
                        "confidence": match["confidence"],
                        "status": "matched",
                    }
                )
            else:
                # No match found, store embedding for future matching
                if aggregated_embedding is not None and aggregated_embedding.size > 0:
                    embedding_list = aggregated_embedding.tolist()
                    logger.info(
                        f"Storing embedding for speaker {speaker_id}: length={len(embedding_list)}, first_few={embedding_list[:3]}"
                    )
                    add_speaker_embedding(
                        speaker_id=speaker_id,
                        user_id=user_id,
                        name=speaker.name,
                        embedding=embedding_list,
                        display_name=speaker.display_name
                        if speaker.display_name
                        else None,
                        media_file_id=media_file_id,
                    )

                    # Find and store matches with other speakers
                    found_matches = self.find_and_store_speaker_matches(
                        speaker_id, aggregated_embedding, user_id, threshold=0.5
                    )

                    if found_matches:
                        logger.info(
                            f"Found {len(found_matches)} matches for speaker {speaker_id}"
                        )
                        # If there are high-confidence matches from verified speakers, suggest them
                        for match in found_matches:
                            if match["confidence"] >= 0.75 and match["display_name"]:
                                speaker.suggested_name = match["display_name"]
                                speaker.confidence = match["confidence"]
                                self.db.flush()
                                break

                    results.append(
                        {
                            "speaker_id": speaker_id,
                            "speaker_label": speaker.name,
                            "profile_match": None,
                            "status": "new",
                        }
                    )
                else:
                    logger.warning(
                        f"Invalid embedding for speaker {speaker_id}, skipping storage"
                    )
                    results.append(
                        {
                            "speaker_id": speaker_id,
                            "speaker_label": speaker.name,
                            "profile_match": None,
                            "status": "failed",
                        }
                    )

        self.db.commit()
        return results

    def find_speaker_occurrences(
        self, profile_id: int, user_id: int
    ) -> list[dict[str, Any]]:
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

    def update_speaker_embeddings(
        self, profile_id: int, audio_paths: list[str]
    ) -> bool:
        """
        Update speaker profile embeddings with new reference audio.

        Args:
            profile_id: Speaker profile ID
            audio_paths: List of audio file paths

        Returns:
            Success status
        """
        try:
            profile = (
                self.db.query(SpeakerProfile)
                .filter(SpeakerProfile.id == profile_id)
                .first()
            )

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
            # Search for similar speakers in OpenSearch
            search_results = find_matching_speaker(
                embedding.tolist(),
                user_id,
                threshold=threshold,
                exclude_speaker_ids=[new_speaker_id],
            )

            if not search_results:
                return matches

            # The search returns the best match, but we want to find all matches
            # So we need to do a broader search
            from app.services.opensearch_service import opensearch_client
            from app.services.opensearch_service import settings

            query = {
                "size": 20,  # Get more potential matches
                "query": {
                    "knn": {
                        "embedding": {
                            "vector": embedding.tolist(),
                            "k": 20,
                            "filter": {
                                "bool": {
                                    "filter": [
                                        {"term": {"user_id": user_id}},
                                        {
                                            "bool": {
                                                "must_not": {
                                                    "term": {
                                                        "speaker_id": new_speaker_id
                                                    }
                                                }
                                            }
                                        },
                                    ]
                                }
                            },
                        }
                    }
                },
            }

            response = opensearch_client.search(
                index=settings.OPENSEARCH_SPEAKER_INDEX, body=query
            )

            # Process each match
            for hit in response["hits"]["hits"]:
                score = hit["_score"]
                if score >= threshold:
                    match_speaker_id = hit["_source"]["speaker_id"]

                    # Ensure consistent ordering (smaller ID first)
                    speaker1_id = min(new_speaker_id, match_speaker_id)
                    speaker2_id = max(new_speaker_id, match_speaker_id)

                    # Check if this match already exists
                    existing_match = (
                        self.db.query(SpeakerMatch)
                        .filter(
                            SpeakerMatch.speaker1_id == speaker1_id,
                            SpeakerMatch.speaker2_id == speaker2_id,
                        )
                        .first()
                    )

                    if not existing_match:
                        # Store the match
                        speaker_match = SpeakerMatch(
                            speaker1_id=speaker1_id,
                            speaker2_id=speaker2_id,
                            confidence=score,
                        )
                        self.db.add(speaker_match)

                        # Get speaker details for the match
                        matched_speaker = (
                            self.db.query(Speaker)
                            .filter(Speaker.id == match_speaker_id)
                            .first()
                        )

                        if matched_speaker:
                            matches.append(
                                {
                                    "speaker_id": match_speaker_id,
                                    "speaker_name": matched_speaker.name,
                                    "display_name": matched_speaker.display_name,
                                    "media_file_id": matched_speaker.media_file_id,
                                    "confidence": score,
                                    "confidence_level": self.get_confidence_level(
                                        score
                                    ),
                                }
                            )
                    else:
                        # Update confidence if higher
                        if score > existing_match.confidence:
                            existing_match.confidence = score
                            existing_match.updated_at = func.now()

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
                    match.speaker2_id
                    if match.speaker1_id == speaker_id
                    else match.speaker1_id
                )

                # Get the matched speaker details
                matched_speaker = (
                    self.db.query(Speaker)
                    .filter(Speaker.id == matched_speaker_id)
                    .first()
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
                            "confidence_level": self.get_confidence_level(
                                match.confidence
                            ),
                            "verified": matched_speaker.verified,
                        }
                    )

            # Sort by confidence (highest first)
            matches.sort(key=lambda x: x["confidence"], reverse=True)

        except Exception as e:
            logger.error(f"Error getting speaker matches: {e}")

        return matches
