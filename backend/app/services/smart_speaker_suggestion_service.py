"""
Smart Speaker Suggestion Service.

This service implements intelligent speaker identification suggestions that:
- Prioritize verified speaker profiles over individual matches
- Consolidate duplicate speaker names into single suggestions
- Filter out unlabeled speakers (SPEAKER_XX format)
- Handle all business logic for speaker suggestions server-side

The service is designed to minimize frontend complexity by providing pre-filtered,
consolidated suggestions that the frontend can display directly without additional
processing or filtering.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from app.models.media import Speaker
from app.services.opensearch_service import get_speaker_embedding
from app.services.profile_embedding_service import ProfileEmbeddingService

logger = logging.getLogger(__name__)


def _determine_confidence_level(
    confidence: float, embedding_count: int = 1, source_type: str = "profile"
) -> tuple[str, bool]:
    """
    Determine the reason string and auto_accept flag based on confidence level.

    Args:
        confidence: Confidence score (0.0 to 1.0)
        embedding_count: Number of embeddings/recordings (for profile matches)
        source_type: Either 'profile' for profile matches or 'voice' for voice matches

    Returns:
        Tuple of (reason string, auto_accept boolean)
    """
    if source_type == "profile":
        if confidence >= 0.95:
            return (
                f"Excellent voice match (verified across {embedding_count} recordings)",
                True,
            )
        elif confidence >= 0.85:
            return (
                f"Very strong voice match (verified across {embedding_count} recordings)",
                True,
            )
        elif confidence >= 0.75:
            return (
                f"Strong voice match (verified across {embedding_count} recordings)",
                True,
            )
        else:
            return (
                f"Moderate voice match (verified across {embedding_count} recordings)",
                False,
            )
    else:  # voice match
        if confidence >= 0.95:
            return (
                f"Excellent voice match from other video ({confidence:.0%} confidence)",
                True,
            )
        elif confidence >= 0.85:
            return (
                f"Very strong voice match from other video ({confidence:.0%} confidence)",
                True,
            )
        elif confidence >= 0.75:
            return (
                f"Strong voice match from other video ({confidence:.0%} confidence)",
                True,
            )
        else:
            return (
                f"Moderate voice match from other video ({confidence:.0%} confidence)",
                False,
            )


def _check_opensearch_profiles_exist(opensearch_client: Any, settings: Any, user_id: int) -> bool:
    """
    Check if any profile documents exist for the user in OpenSearch.

    Returns False if index doesn't exist or no profiles found, True otherwise.
    """
    if not opensearch_client.indices.exists(index=settings.OPENSEARCH_SPEAKER_INDEX):
        logger.info("Speakers index does not exist yet, skipping profile suggestion search")
        return False

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
        profile_check = opensearch_client.search(
            index=settings.OPENSEARCH_SPEAKER_INDEX, body=profile_check_query
        )
        if profile_check["hits"]["total"]["value"] == 0:
            logger.info(
                f"No profile documents found for user {user_id}, skipping profile KNN search"
            )
            return False
        return True
    except Exception as e:
        logger.warning(f"Profile document check failed: {e}, proceeding with KNN query")
        return True  # Proceed with query if check fails


def _execute_profile_knn_search(
    opensearch_client: Any, settings: Any, embedding: np.ndarray, user_id: int, threshold: float
) -> list[dict[str, Any]]:
    """
    Execute kNN search for profile matches and return filtered results.

    Returns list of profile match dictionaries with similarity scores.
    """
    must_filters = [
        {"term": {"document_type": "profile"}},
        {"term": {"user_id": user_id}},
    ]

    query = {
        "size": 10,
        "query": {
            "knn": {
                "embedding": {
                    "vector": embedding.tolist(),
                    "k": 10,
                    "filter": {"bool": {"must": must_filters}},
                }
            }
        },
    }

    response = opensearch_client.search(index=settings.OPENSEARCH_SPEAKER_INDEX, body=query)
    matches = []

    for hit in response["hits"]["hits"]:
        score = hit["_score"]
        source = hit["_source"]
        if score >= threshold:
            matches.append(
                {
                    "profile_id": source.get("profile_id"),
                    "profile_name": source.get("profile_name"),
                    "speaker_count": source.get("speaker_count"),
                    "similarity": score,
                }
            )

    return matches


def _convert_profile_match_to_suggestion(
    match: dict[str, Any],
) -> Optional["ConsolidatedSuggestion"]:
    """
    Convert a profile match dictionary to a ConsolidatedSuggestion.

    Returns None if required fields are missing.
    """
    profile_id = match.get("profile_id")
    profile_name = match.get("profile_name")

    if not profile_id or not profile_name:
        return None

    confidence = match["similarity"]
    embedding_count = match.get("speaker_count", 1)
    reason, auto_accept = _determine_confidence_level(confidence, embedding_count, "profile")

    return ConsolidatedSuggestion(
        name=profile_name,
        confidence=confidence,
        suggestion_type="profile",
        profile_id=profile_id,
        embedding_count=embedding_count,
        reason=reason,
        auto_accept=auto_accept,
    )


def _check_voice_candidates_exist(
    opensearch_client: Any,
    settings: Any,
    user_id: int,
    speaker_id: int,
    source_media_file_id: int,
) -> bool:
    """
    Check if candidate speaker documents exist for voice matching.

    Returns True if candidates exist, False otherwise.
    """
    check_query = {
        "size": 0,
        "query": {
            "bool": {
                "must": [{"term": {"user_id": user_id}}],
                "must_not": [
                    {"exists": {"field": "document_type"}},  # Exclude profiles
                    {"term": {"speaker_id": speaker_id}},  # Exclude self
                    {"term": {"media_file_id": source_media_file_id}},  # Exclude same video
                ],
            }
        },
    }

    check_response = opensearch_client.search(
        index=settings.OPENSEARCH_SPEAKER_INDEX, body=check_query
    )

    if check_response["hits"]["total"]["value"] == 0:
        logger.info(f"No candidate speakers found for voice matching speaker {speaker_id}")
        return False
    return True


def _execute_voice_knn_search(
    opensearch_client: Any,
    settings: Any,
    embedding: np.ndarray,
    user_id: int,
    speaker_id: int,
    source_media_file_id: int,
    threshold: float,
) -> list[dict[str, Any]]:
    """
    Execute kNN search for voice matching and return raw hits.

    Returns list of raw OpenSearch hit dictionaries.
    """
    query = {
        "size": 100,  # Get more results to account for filtering
        "query": {
            "bool": {
                "must": [
                    {
                        "knn": {
                            "embedding": {
                                "vector": embedding.tolist(),
                                "k": 50,  # Get top 50 similar
                            }
                        }
                    }
                ],
                "filter": [{"term": {"user_id": user_id}}],
                "must_not": [
                    {"exists": {"field": "document_type"}},  # Exclude profiles
                    {"term": {"speaker_id": speaker_id}},  # Exclude self
                    {"term": {"media_file_id": source_media_file_id}},  # Exclude same video
                ],
            }
        },
        "min_score": threshold,  # Use threshold directly
    }

    response = opensearch_client.search(index=settings.OPENSEARCH_SPEAKER_INDEX, body=query)
    logger.info(f"Found {len(response['hits']['hits'])} voice matches for speaker {speaker_id}")
    return response["hits"]["hits"]


def _get_media_file_title(db: Session, media_file_id: Optional[int]) -> Optional[str]:
    """
    Get the title of a media file from the database.

    Returns the title/filename or None if media file doesn't exist (orphaned data).
    """
    if not media_file_id:
        return "Unknown"

    from app.models.media import MediaFile

    try:
        media_file = db.query(MediaFile).filter(MediaFile.id == media_file_id).first()
        if media_file:
            return media_file.title or media_file.filename or f"File {media_file_id}"
        else:
            logger.warning(
                f"MediaFile {media_file_id} not found in database - skipping orphaned data"
            )
            return None  # Signal to skip this match
    except Exception as e:
        logger.warning(f"Could not fetch media file {media_file_id}: {e}")
        return f"File {media_file_id} (error)"


def _process_voice_hit(
    hit: dict[str, Any], db: Session, threshold: float
) -> Optional[tuple[str, dict[str, Any]]]:
    """
    Process a single voice match hit and return (display_name, match_data) tuple.

    Returns None if the hit should be skipped (unlabeled, below threshold, or orphaned).
    """
    source = hit["_source"]
    display_name = source.get("display_name")

    # Only include labeled speakers (not SPEAKER_XX format)
    if not display_name or display_name.startswith("SPEAKER_"):
        return None

    # kNN query returns cosine similarity scores directly (0.0 to 1.0)
    score = hit["_score"]
    if score < threshold:
        return None

    media_file_id = source.get("media_file_id")

    if not media_file_id:
        logger.warning(
            f"No media_file_id in OpenSearch document for speaker {source.get('speaker_id')}"
        )

    media_file_title = _get_media_file_title(db, media_file_id)
    if media_file_title is None:
        # Orphaned data - skip
        return None

    match_data = {
        "name": display_name,
        "confidence": score,
        "media_file_id": media_file_id,
        "speaker_id": source.get("speaker_id"),
        "media_file_title": media_file_title,
    }

    return (display_name, match_data)


def _convert_voice_matches_to_suggestions(
    voice_matches: dict[str, dict[str, Any]],
) -> list["ConsolidatedSuggestion"]:
    """
    Convert voice match dictionary to list of ConsolidatedSuggestion objects.
    """
    suggestions = []
    for name, match_data in voice_matches.items():
        confidence = match_data["confidence"]
        reason, auto_accept = _determine_confidence_level(confidence, source_type="voice")

        suggestion = ConsolidatedSuggestion(
            name=name,
            confidence=confidence,
            suggestion_type="voice",
            reason=reason,
            auto_accept=auto_accept,
            individual_matches=[match_data],
        )
        suggestions.append(suggestion)

    return suggestions


@dataclass
class ConsolidatedSuggestion:
    """
    Represents a consolidated speaker suggestion with metadata.

    This dataclass encapsulates all information needed by the frontend
    to display speaker suggestions without additional processing.
    """

    name: str
    confidence: float
    suggestion_type: str  # 'profile' or 'individual'
    profile_id: Optional[int] = None
    individual_matches: list[dict[str, Any]] = field(default_factory=list)
    embedding_count: int = 0
    reason: str = ""
    auto_accept: bool = False


class SmartSpeakerSuggestionService:
    """
    Advanced speaker suggestion service with intelligent filtering and consolidation.

    This service implements all business logic for speaker suggestions including:
    - Profile-based voice matching using consolidated embeddings
    - Individual speaker voice similarity across videos
    - Name-based deduplication and consolidation
    - Automatic filtering of unlabeled speakers (SPEAKER_XX)
    - Confidence-based suggestion ranking and auto-accept logic

    All methods are static as this service is stateless and operates on provided data.
    """

    @staticmethod
    def consolidate_suggestions(
        speaker_id: int,
        user_id: int,
        db: Session,
        confidence_threshold: float = 0.5,
        max_suggestions: int = 10,
    ) -> list[ConsolidatedSuggestion]:
        """
        Generate three types of speaker suggestions: LLM, Voice, and Profile.

        This implements the complete three-type suggestion system as specified in the fix plan:
        1. LLM suggestions (from import process, stored in suggested_name)
        2. Voice suggestions (speaker-to-speaker matching)
        3. Profile suggestions (speaker-to-profile matching)

        Args:
            speaker_id: ID of the speaker to find suggestions for
            user_id: ID of the user
            db: Database session
            confidence_threshold: Minimum confidence threshold
            max_suggestions: Maximum number of suggestions to return

        Returns:
            List of consolidated suggestions with clear type labels for frontend display.
        """
        suggestions = []

        # Get the speaker from database to check for LLM suggestions
        speaker = db.query(Speaker).filter(Speaker.id == speaker_id).first()
        if not speaker:
            logger.warning(f"Speaker {speaker_id} not found")
            return suggestions

        # Step 1: LLM suggestions (from import process) - only if LLM provider is configured
        # Note: suggested_name/confidence can also come from voice matching, so we need to distinguish
        if speaker.suggested_name and speaker.confidence:
            # Check if this came from actual LLM analysis (has specific metadata) or voice matching
            # For now, we'll skip LLM suggestions unless we can distinguish them properly
            # TODO: Add proper LLM suggestion detection when LLM provider is configured
            logger.info(
                f"Found suggested_name ({speaker.suggested_name}) but treating as voice match to avoid confusion"
            )

        # Get speaker embedding for voice and profile matching using UUID
        speaker_embedding = get_speaker_embedding(str(speaker.uuid))
        if not speaker_embedding:
            logger.warning(f"No embedding found for speaker {speaker.uuid}")
            return suggestions

        embedding_array = np.array(speaker_embedding)

        # Step 2: Profile suggestions (speaker-to-profile matching) - highest priority
        profile_suggestions = SmartSpeakerSuggestionService._get_profile_suggestions_optimized(
            embedding_array, user_id, db, confidence_threshold
        )
        suggestions.extend(profile_suggestions)

        # Step 3: Voice suggestions (speaker-to-speaker matching)
        voice_suggestions = SmartSpeakerSuggestionService._get_voice_suggestions(
            speaker_id, embedding_array, user_id, db, confidence_threshold
        )
        suggestions.extend(voice_suggestions)

        # Step 4: Deduplicate by name, keeping highest confidence with type priority
        # Priority order: profile > voice (profiles are more reliable)
        unique_suggestions = {}
        for suggestion in suggestions:
            name_key = suggestion.name.lower()
            if name_key not in unique_suggestions:
                unique_suggestions[name_key] = suggestion
            else:
                existing = unique_suggestions[name_key]
                # Replace if higher confidence OR same confidence but better type
                should_replace = suggestion.confidence > existing.confidence or (
                    suggestion.confidence == existing.confidence
                    and suggestion.suggestion_type == "profile"
                    and existing.suggestion_type == "voice"
                )
                if should_replace:
                    unique_suggestions[name_key] = suggestion

        # Step 5: Sort by type priority and confidence
        final_suggestions = list(unique_suggestions.values())
        final_suggestions.sort(
            key=lambda s: (
                0
                if s.suggestion_type == "profile"
                else 1
                if s.suggestion_type == "llm_analysis"
                else 2,  # Profile > LLM > Voice
                -s.confidence,  # Higher confidence first within each type
            )
        )

        # Step 6: Limit to max suggestions and filter out unlabeled speakers
        filtered_suggestions = []
        for suggestion in final_suggestions[:max_suggestions]:
            if suggestion.suggestion_type in [
                "profile",
                "llm_analysis",
            ] or not suggestion.name.startswith("SPEAKER_"):
                filtered_suggestions.append(suggestion)

        logger.info(
            f"Returning {len(filtered_suggestions)} suggestions for speaker {speaker_id} "
            f"(LLM: {len([s for s in filtered_suggestions if s.suggestion_type == 'llm_analysis'])}, "
            f"Profile: {len([s for s in filtered_suggestions if s.suggestion_type == 'profile'])}, "
            f"Voice: {len([s for s in filtered_suggestions if s.suggestion_type == 'voice'])})"
        )
        return filtered_suggestions

    @staticmethod
    def _get_profile_suggestions_optimized(
        embedding: np.ndarray, user_id: int, db: Session, threshold: float
    ) -> list[ConsolidatedSuggestion]:
        """Get suggestions from speaker profiles using OpenSearch native similarity."""
        try:
            from app.services.opensearch_service import opensearch_client
            from app.services.opensearch_service import settings

            if not opensearch_client:
                logger.warning("OpenSearch client not initialized for profile suggestions")
                return []

            # Check if profiles exist to avoid KNN query on empty sets
            if not _check_opensearch_profiles_exist(opensearch_client, settings, user_id):
                return []

            # Execute kNN search for profile matches
            try:
                opensearch_matches = _execute_profile_knn_search(
                    opensearch_client, settings, embedding, user_id, threshold
                )
            except Exception as e:
                logger.error(
                    f"Error in OpenSearch profile similarity search <_get_profile_suggestions_optimized - hits>: {e}"
                )
                return []

            # Convert matches to suggestions
            suggestions = []
            for match in opensearch_matches:
                suggestion = _convert_profile_match_to_suggestion(match)
                if suggestion:
                    suggestions.append(suggestion)

            return suggestions

        except Exception as e:
            logger.error(f"Error in optimized profile suggestions: {e}")
            # Fallback to original method
            return SmartSpeakerSuggestionService._get_profile_suggestions(
                embedding, user_id, db, threshold
            )

    @staticmethod
    def _get_profile_suggestions(
        embedding: np.ndarray, user_id: int, db: Session, threshold: float
    ) -> list[ConsolidatedSuggestion]:
        """Get suggestions from speaker profiles"""
        suggestions = []

        try:
            # Use ProfileEmbeddingService to find matching profiles
            profile_matches = ProfileEmbeddingService.calculate_profile_similarity(
                db, embedding.tolist(), user_id, threshold=threshold
            )

            for match in profile_matches:
                # Convert match to suggestion format expected by helper
                suggestion_match = {
                    "profile_id": match["profile_id"],
                    "profile_name": match["profile_name"],
                    "speaker_count": match["embedding_count"],
                    "similarity": match["similarity"],
                }
                suggestion = _convert_profile_match_to_suggestion(suggestion_match)
                if suggestion:
                    suggestions.append(suggestion)

        except Exception as e:
            logger.error(f"Error getting profile suggestions: {e}")

        return suggestions

    @staticmethod
    def _get_voice_suggestions(
        speaker_id: int, embedding: np.ndarray, user_id: int, db: Session, threshold: float
    ) -> list[ConsolidatedSuggestion]:
        """Get voice suggestions (speaker-to-speaker matching) using OpenSearch kNN search."""
        try:
            from app.services.opensearch_service import opensearch_client
            from app.services.opensearch_service import settings

            if not opensearch_client:
                logger.warning("OpenSearch client not initialized for voice suggestions")
                return []

            # Get the source speaker's media_file_id to exclude speakers from the same video
            source_speaker = db.query(Speaker).filter(Speaker.id == speaker_id).first()
            if not source_speaker:
                logger.warning(f"Source speaker {speaker_id} not found")
                return []

            source_media_file_id = source_speaker.media_file_id

            # Check if there are any candidate documents to avoid KNN errors
            if not _check_voice_candidates_exist(
                opensearch_client, settings, user_id, speaker_id, source_media_file_id
            ):
                return []

            # Execute kNN search for voice matches
            hits = _execute_voice_knn_search(
                opensearch_client,
                settings,
                embedding,
                user_id,
                speaker_id,
                source_media_file_id,
                threshold,
            )

            # Process hits and group by display_name to consolidate
            voice_matches = {}
            for hit in hits:
                result = _process_voice_hit(hit, db, threshold)
                if result is None:
                    continue

                display_name, match_data = result
                # Keep the highest confidence match for each name
                if (
                    display_name not in voice_matches
                    or match_data["confidence"] > voice_matches[display_name]["confidence"]
                ):
                    voice_matches[display_name] = match_data

            # Convert matches to suggestions
            suggestions = _convert_voice_matches_to_suggestions(voice_matches)
            logger.info(f"Voice matching found {len(suggestions)} suggestions")
            return suggestions

        except Exception as e:
            logger.error(f"Error in voice suggestions: {e}")
            return []

    @staticmethod
    def _get_consolidated_individual_suggestions(
        speaker_id: int, embedding: np.ndarray, user_id: int, db: Session, threshold: float
    ) -> list[ConsolidatedSuggestion]:
        """Get individual speaker suggestions and consolidate by name"""
        suggestions = []

        try:
            # Get individual speaker matches using dynamic similarity search
            individual_matches = SmartSpeakerSuggestionService._find_similar_speakers_dynamic(
                speaker_id, embedding, user_id, db
            )

            # Filter by confidence threshold
            filtered_matches = [
                match for match in individual_matches if match.get("confidence", 0) >= threshold
            ]

            # Group by speaker name (case-insensitive) - only for labeled speakers
            name_groups = defaultdict(list)
            for match in filtered_matches:
                speaker_name = match.get("speaker_name", match.get("display_name", "Unknown"))
                # Only include speakers with actual names (not SPEAKER_XX format)
                if speaker_name and not speaker_name.startswith("SPEAKER_"):
                    group_key = speaker_name.lower()
                    name_groups[group_key].append(match)

            # Create consolidated suggestions for each name group
            for matches in name_groups.values():
                if not matches:
                    continue

                # Use the highest confidence match as the representative
                best_match = max(matches, key=lambda m: m.get("confidence", 0))
                speaker_name = best_match.get(
                    "speaker_name", best_match.get("display_name", "Unknown")
                )
                confidence = best_match.get("confidence", 0)

                # Calculate average confidence across all matches
                avg_confidence = sum(m.get("confidence", 0) for m in matches) / len(matches)

                # Determine reason and auto-accept for labeled speakers
                if len(matches) == 1:
                    reason = f"Voice match from 1 other video ({confidence:.0%} confidence)"
                else:
                    reason = f"Voice match across {len(matches)} videos (avg {avg_confidence:.0%} confidence)"

                auto_accept = confidence >= 0.90 and len(matches) >= 2

                # Determine if this should be considered a "profile" based on multiple appearances
                # Labeled speakers appearing in multiple videos should be treated as profiles
                is_profile_level = (
                    len(matches) >= 2  # Appears in multiple videos
                    and not speaker_name.startswith("SPEAKER_")  # Is labeled
                    and confidence >= 0.75  # Has decent confidence
                )

                suggestion = ConsolidatedSuggestion(
                    name=speaker_name,
                    confidence=confidence,
                    suggestion_type="profile" if is_profile_level else "individual",
                    individual_matches=matches,
                    embedding_count=len(matches),
                    reason=reason,
                    auto_accept=auto_accept,
                )
                suggestions.append(suggestion)

        except Exception as e:
            logger.error(f"Error getting individual suggestions: {e}")

        return suggestions

    @staticmethod
    def _find_similar_speakers_dynamic(
        speaker_id: int, embedding: np.ndarray, user_id: int, db: Session, max_matches: int = 10
    ) -> list[dict[str, Any]]:
        """
        Find similar speakers using dynamic OpenSearch similarity search

        Args:
            speaker_id: ID of the speaker to find matches for
            embedding: Speaker embedding vector
            user_id: User ID
            db: Database session
            max_matches: Maximum number of matches to return

        Returns:
            List of similar speakers with metadata
        """
        matches = []

        try:
            from app.models.media import MediaFile
            from app.services.opensearch_service import opensearch_client

            if not opensearch_client:
                logger.warning("OpenSearch client not available for similarity search")
                return matches

            # Use batch search to get multiple matches efficiently
            from app.services.opensearch_service import batch_find_matching_speakers

            # Prepare embedding for batch search
            embedding_batch = [{"id": speaker_id, "embedding": embedding.tolist()}]

            # Find matching speakers using batch OpenSearch similarity search
            batch_results = batch_find_matching_speakers(
                embeddings=embedding_batch,
                user_id=user_id,
                threshold=0.3,
                max_candidates=max_matches,
            )

            # Extract matches for our speaker
            opensearch_matches = []
            for result in batch_results:
                if result.get("query_id") == speaker_id:
                    opensearch_matches.extend(result.get("matches", []))

            # Filter out the same speaker
            opensearch_matches = [
                match for match in opensearch_matches if match.get("speaker_id") != speaker_id
            ]

            # Convert OpenSearch results to our format
            for match in opensearch_matches:
                # Get media file info if needed
                media_file = (
                    db.query(MediaFile).filter(MediaFile.id == match.get("media_file_id")).first()
                )

                if media_file:
                    # Get the actual speaker from the database to get the correct display name
                    from app.models.media import Speaker

                    speaker_record = (
                        db.query(Speaker).filter(Speaker.id == match.get("speaker_id")).first()
                    )

                    if speaker_record:
                        # Use display_name if available, otherwise use the resolved_display_name or suggested_name
                        speaker_display_name = (
                            speaker_record.display_name
                            or speaker_record.resolved_display_name
                            or speaker_record.suggested_name
                            or speaker_record.name
                        )

                        formatted_match = {
                            "speaker_id": match.get("speaker_id"),
                            "speaker_name": speaker_display_name,
                            "display_name": speaker_display_name,
                            "confidence": match.get("confidence", 0.5),
                            "media_file_title": media_file.title
                            or media_file.filename
                            or "Unknown",
                            "media_file_id": match.get("media_file_id"),
                        }
                        matches.append(formatted_match)

        except Exception as e:
            logger.error(f"Error in dynamic speaker similarity search: {e}")

        return matches

    @staticmethod
    def format_for_api(suggestions: list[ConsolidatedSuggestion]) -> list[dict[str, Any]]:
        """Format consolidated suggestions for API response with clear type labels"""
        formatted = []

        for suggestion in suggestions:
            formatted_suggestion = {
                "name": suggestion.name,
                "confidence": suggestion.confidence,
                "confidence_percentage": f"{suggestion.confidence:.0%}",
                "suggestion_type": suggestion.suggestion_type,
                "reason": suggestion.reason,
                "auto_accept": suggestion.auto_accept,
                "embedding_count": suggestion.embedding_count,
            }

            # Add type-specific fields and labels
            if suggestion.suggestion_type == "profile":
                formatted_suggestion.update(
                    {
                        "profile_id": suggestion.profile_id,
                        "is_verified_profile": True,
                        "type_label": "Profile Match",
                        "type_description": "Verified speaker profile",
                    }
                )
            elif suggestion.suggestion_type == "llm_analysis":
                formatted_suggestion.update(
                    {
                        "is_verified_profile": False,
                        "type_label": "AI Analysis",
                        "type_description": "Context-based identification",
                    }
                )
            elif suggestion.suggestion_type == "voice":
                formatted_suggestion.update(
                    {
                        "video_count": len(suggestion.individual_matches)
                        if suggestion.individual_matches
                        else 0,
                        "is_verified_profile": False,
                        "individual_matches": suggestion.individual_matches,
                        "type_label": "Voice Match",
                        "type_description": "Similar voice from other videos",
                    }
                )
            else:
                # Legacy individual suggestions
                formatted_suggestion.update(
                    {
                        "video_count": len(suggestion.individual_matches)
                        if suggestion.individual_matches
                        else 0,
                        "is_verified_profile": False,
                        "individual_matches": suggestion.individual_matches,
                        "type_label": "Individual Match",
                        "type_description": "Speaker from other videos",
                    }
                )

            formatted.append(formatted_suggestion)

        return formatted
