"""
Helper functions for speaker updates and retroactive matching.
"""

import logging

import numpy as np
from sqlalchemy.orm import Session

from app.models.media import Speaker
from app.models.media import SpeakerMatch
from app.services.opensearch_service import get_speaker_embedding

logger = logging.getLogger(__name__)


def trigger_retroactive_matching(updated_speaker: Speaker, db: Session) -> None:
    """
    Trigger retroactive matching when a speaker is labeled.
    This updates all other speakers that might match the newly labeled one.
    Auto-propagates for 75%+ confidence, suggests for 50-75%.
    """
    try:
        # Get the embedding for the updated speaker
        embedding = get_speaker_embedding(updated_speaker.id)
        if not embedding:
            logger.warning(f"No embedding found for speaker {updated_speaker.id}")
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
                continue

            # Get embedding for this speaker
            other_embedding = get_speaker_embedding(speaker.id)
            if not other_embedding:
                continue

            # Calculate similarity
            similarity = calculate_cosine_similarity(embedding_array, np.array(other_embedding))

            logger.info(
                f"Similarity between {updated_speaker.display_name} and {speaker.name}: {similarity:.3f}"
            )

            # Store the suggestion if similarity is above threshold
            if similarity >= 0.5:
                # Update confidence and suggestion
                speaker.confidence = similarity
                speaker.suggested_name = updated_speaker.display_name

                # Auto-apply for high confidence (75%+)
                if similarity >= 0.75:
                    speaker.display_name = updated_speaker.display_name
                    speaker.verified = True
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

        db.commit()

        logger.info(
            f"Retroactive matching complete: {auto_applied_count} auto-applied, {suggested_count} suggested"
        )

    except Exception as e:
        logger.error(f"Error in retroactive matching: {e}")
        db.rollback()


def calculate_cosine_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
    """Calculate cosine similarity between two embeddings."""
    # Normalize embeddings
    norm1 = embedding1 / np.linalg.norm(embedding1)
    norm2 = embedding2 / np.linalg.norm(embedding2)

    # Compute cosine similarity
    similarity = np.dot(norm1, norm2)

    # Convert to 0-1 range and ensure it's a Python float
    return float((similarity + 1) / 2)


def store_speaker_match(speaker1_id: int, speaker2_id: int, confidence: float, db: Session) -> None:
    """Store a speaker match in the database."""
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
