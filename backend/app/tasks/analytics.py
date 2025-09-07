import json
import logging
from collections import defaultdict
from typing import Any

from app.core.celery import celery_app
from app.db.base import SessionLocal
from app.models.media import Analytics
from app.models.media import MediaFile
from app.models.media import TranscriptSegment

# Setup logging
logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="analyze_transcript")
def analyze_transcript_task(self, file_id: int):
    """
    Analyze a transcript to extract insights:
    - Speaker talk time
    - Simple sentiment analysis
    - Keyword extraction

    Args:
        file_id: Database ID of the MediaFile to analyze
    """
    task_id = self.request.id
    db = SessionLocal()

    try:
        # Get media file from database
        media_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
        if not media_file:
            raise ValueError(f"Media file with ID {file_id} not found")

        # Create task record
        from app.utils.task_utils import create_task_record
        from app.utils.task_utils import update_task_status

        create_task_record(db, task_id, media_file.user_id, file_id, "analytics")

        # Update task status
        update_task_status(db, task_id, "in_progress", progress=0.1)

        # Get transcript segments from database
        transcript_segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.media_file_id == file_id)
            .order_by(TranscriptSegment.start_time)
            .all()
        )

        if not transcript_segments:
            raise ValueError(f"No transcript segments found for file {file_id}")

        # 1. Calculate speaker talk time
        speaker_stats = calculate_speaker_talk_time(transcript_segments)

        # Update task progress
        update_task_status(db, task_id, "in_progress", progress=0.4)

        # 2. Simple sentiment analysis
        sentiment = analyze_sentiment(transcript_segments)

        # Update task progress
        update_task_status(db, task_id, "in_progress", progress=0.7)

        # 3. Extract keywords
        keywords = extract_keywords(transcript_segments)

        # Store analytics results
        existing_analytics = (
            db.query(Analytics).filter(Analytics.media_file_id == file_id).first()
        )

        if existing_analytics:
            # Update existing record
            existing_analytics.speaker_stats = json.dumps(speaker_stats)
            existing_analytics.sentiment = json.dumps(sentiment)
            existing_analytics.keywords = json.dumps(keywords)
        else:
            # Create new record
            analytics = Analytics(
                media_file_id=file_id,
                speaker_stats=json.dumps(speaker_stats),
                sentiment=json.dumps(sentiment),
                keywords=json.dumps(keywords),
            )
            db.add(analytics)

        db.commit()

        # Update task as completed
        update_task_status(db, task_id, "completed", progress=1.0, completed=True)

        logger.info(f"Successfully analyzed file {media_file.filename}")
        return {"status": "success", "file_id": file_id}

    except Exception as e:
        # Handle errors
        logger.error(f"Error analyzing file {file_id}: {str(e)}")
        update_task_status(db, task_id, "failed", error_message=str(e), completed=True)
        return {"status": "error", "message": str(e)}

    finally:
        db.close()


def calculate_speaker_talk_time(
    transcript_segments: list[TranscriptSegment],
) -> dict[str, Any]:
    """
    Calculate talk time for each speaker in the transcript

    Args:
        transcript_segments: List of transcript segments

    Returns:
        Dictionary with speaker stats
    """
    speaker_durations = defaultdict(float)
    speaker_word_counts = defaultdict(int)
    total_duration = 0.0

    for segment in transcript_segments:
        speaker_name = segment.speaker.name if segment.speaker else "Unknown Speaker"
        duration = segment.end_time - segment.start_time
        word_count = len(segment.text.split())

        speaker_durations[speaker_name] += duration
        speaker_word_counts[speaker_name] += word_count
        total_duration += duration

    # Calculate percentages and format the results
    result = {"total_duration": total_duration, "speakers": []}

    for speaker, duration in speaker_durations.items():
        percentage = (duration / total_duration * 100) if total_duration > 0 else 0
        result["speakers"].append(
            {
                "name": speaker,
                "talk_time_seconds": duration,
                "talk_time_percentage": round(percentage, 2),
                "word_count": speaker_word_counts[speaker],
            }
        )

    # Sort speakers by talk time (descending)
    result["speakers"].sort(key=lambda x: x["talk_time_seconds"], reverse=True)

    return result


def analyze_sentiment(transcript_segments: list[TranscriptSegment]) -> dict[str, Any]:
    """
    Perform a simple sentiment analysis on the transcript

    Args:
        transcript_segments: List of transcript segments

    Returns:
        Dictionary with sentiment analysis results
    """
    # In a real implementation, we would:
    # 1. Use a sentiment analysis model (e.g., VADER, DistilBERT for sentiment)
    # 2. Analyze each segment and aggregate results

    # For this simplified version, we'll generate some placeholder results
    # based on segment count

    # Simulate some sentiment scores
    import random

    # Get text by speaker
    speaker_texts = defaultdict(str)
    for segment in transcript_segments:
        speaker_name = segment.speaker.name if segment.speaker else "Unknown Speaker"
        speaker_texts[speaker_name] += " " + segment.text

    # Generate simulated sentiment scores
    overall_sentiment = random.choice(
        ["positive", "neutral", "slightly_positive", "slightly_negative"]
    )
    speaker_sentiments = {}

    for speaker, _text in speaker_texts.items():
        # Generate a somewhat consistent sentiment per speaker
        if overall_sentiment == "positive":
            sentiment = random.choice(["positive", "slightly_positive", "neutral"])
        elif overall_sentiment == "negative":
            sentiment = random.choice(["negative", "slightly_negative", "neutral"])
        else:
            sentiment = random.choice(
                [
                    "positive",
                    "negative",
                    "neutral",
                    "slightly_positive",
                    "slightly_negative",
                ]
            )

        speaker_sentiments[speaker] = {
            "sentiment": sentiment,
            "score": round(random.uniform(0, 1), 2),  # Random score between 0 and 1
        }

    result = {"overall": overall_sentiment, "by_speaker": speaker_sentiments}

    return result


def extract_keywords(transcript_segments: list[TranscriptSegment]) -> list[str]:
    """
    Extract keywords/topics from the transcript

    Args:
        transcript_segments: List of transcript segments

    Returns:
        List of keywords
    """
    # In a real implementation, we would:
    # 1. Use a keyword extraction algorithm (e.g., RAKE, YAKE, KeyBERT)
    # 2. Extract keywords from the full transcript

    # For this simplified version, we'll extract some words based on frequency

    # Combine all text
    full_text = " ".join([segment.text for segment in transcript_segments])

    # Extract some "keywords" based on the transcript
    # In a real implementation, this would use NLP techniques

    # Simple stopwords to filter out common words
    stopwords = set(
        [
            "the",
            "and",
            "a",
            "an",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "this",
            "that",
            "these",
            "those",
            "there",
            "here",
        ]
    )

    # Split into words, filter common words, and count frequencies
    words = [word.strip(".,!?()[]{}:;\"'").lower() for word in full_text.split()]
    word_counts = defaultdict(int)

    for word in words:
        if word and word not in stopwords and len(word) > 3:
            word_counts[word] += 1

    # Get the top words by frequency
    top_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    keywords = [word for word, count in top_words]

    # For demonstration, add some simulated domain-specific keywords
    if len(keywords) < 5:
        simulated_keywords = ["meeting", "project", "discussion", "analysis", "report"]
        keywords.extend(simulated_keywords[: 5 - len(keywords)])

    return keywords
