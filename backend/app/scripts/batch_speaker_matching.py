#!/usr/bin/env python3
"""
Batch process existing speakers to find and store cross-video matches.
This script can be run manually to process speakers that were added before
the matching system was implemented.
"""

import sys

# Add the app directory to Python path
sys.path.insert(0, '/app')

import logging

import numpy as np

from app.db.base import get_db
from app.models.media import Speaker
from app.models.media import SpeakerMatch
from app.services.opensearch_service import get_speaker_embedding
from app.services.speaker_embedding_service import SpeakerEmbeddingService
from app.services.speaker_matching_service import SpeakerMatchingService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def batch_process_speaker_matches():
    """Process all speakers to find and store matches."""
    db = next(get_db())

    try:
        # Initialize services
        embedding_service = SpeakerEmbeddingService()
        matching_service = SpeakerMatchingService(db, embedding_service)

        # Get all speakers with embeddings
        speakers = db.query(Speaker).all()

        logger.info(f"Processing {len(speakers)} speakers for matches...")

        processed = 0
        matches_found = 0

        for speaker in speakers:
            # Get embedding from OpenSearch
            embedding = get_speaker_embedding(speaker.id)

            if embedding:
                # Find and store matches
                found_matches = matching_service.find_and_store_speaker_matches(
                    speaker.id,
                    np.array(embedding),
                    speaker.user_id,
                    threshold=0.5
                )

                if found_matches:
                    matches_found += len(found_matches)
                    logger.info(f"Found {len(found_matches)} matches for speaker {speaker.id} ({speaker.name})")

                    # Update suggested name if high confidence match found
                    for match in found_matches:
                        if match['confidence'] >= 0.75 and match['display_name'] and not speaker.suggested_name:
                            speaker.suggested_name = match['display_name']
                            speaker.confidence = match['confidence']
                            db.flush()
                            break

                processed += 1

                if processed % 10 == 0:
                    logger.info(f"Processed {processed}/{len(speakers)} speakers...")
                    db.commit()

        db.commit()

        logger.info("Batch processing complete!")
        logger.info(f"Processed: {processed} speakers")
        logger.info(f"Matches found: {matches_found}")

        # Show some statistics
        match_count = db.query(SpeakerMatch).count()
        logger.info(f"Total speaker matches in database: {match_count}")

    except Exception as e:
        logger.error(f"Error in batch processing: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    batch_process_speaker_matches()
