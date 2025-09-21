"""
Transcription tasks module - refactored for modularity.

This file now serves as the main entry point for transcription tasks,
with the actual implementation moved to the transcription/ submodule.
"""

import logging
import tempfile
from pathlib import Path

from app.core.celery import celery_app
from app.db.session_utils import get_refreshed_object
from app.db.session_utils import session_scope
from app.models.media import Analytics
from app.models.media import MediaFile
from app.models.media import TranscriptSegment
from app.services.minio_service import download_file
from app.services.minio_service import upload_file

# Import the main transcription task from the modular implementation

logger = logging.getLogger(__name__)


@celery_app.task(name="extract_audio")
def extract_audio_task(file_id: int, output_format: str = "wav"):
    """
    Extract audio from a video file

    Args:
        file_id: Database ID of the MediaFile
        output_format: Output audio format (default: wav)
    """
    try:
        with session_scope() as db:
            media_file = get_refreshed_object(db, MediaFile, file_id)
            if not media_file:
                logger.error(f"Media file with ID {file_id} not found")
                return {
                    "status": "error",
                    "message": f"Media file with ID {file_id} not found",
                }

            user_id = media_file.user_id
            storage_path = media_file.storage_path
            filename = media_file.filename

        file_data, file_size, content_type = download_file(storage_path)

        if not content_type.startswith("video/"):
            return {"status": "error", "message": "Not a video file"}

        video_suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(suffix=video_suffix, delete=False) as temp_video:
            temp_video.write(file_data.read())
            video_path = temp_video.name

        try:
            import io
            import os

            import ffmpeg

            audio_filename = f"{Path(filename).stem}.{output_format}"
            audio_storage_path = f"user_{user_id}/file_{file_id}/audio/{audio_filename}"

            with tempfile.NamedTemporaryFile(
                suffix=f".{output_format}", delete=False
            ) as temp_audio:
                audio_path = temp_audio.name

            ffmpeg.input(video_path).output(audio_path).run(quiet=True, overwrite_output=True)

            with open(audio_path, "rb") as audio_file:
                audio_data = audio_file.read()

            upload_file(
                file_content=io.BytesIO(audio_data),
                file_size=os.path.getsize(audio_path),
                object_name=audio_storage_path,
                content_type=f"audio/{output_format}",
            )

            logger.info(f"Audio extraction completed for file {file_id}")
            return {
                "status": "success",
                "file_id": file_id,
                "audio_path": audio_storage_path,
            }

        finally:
            try:
                if os.path.exists(video_path):
                    os.unlink(video_path)
                if "audio_path" in locals() and os.path.exists(audio_path):
                    os.unlink(audio_path)
            except Exception as e:
                logger.error(f"Error cleaning up temporary files: {e}")

    except Exception as e:
        logger.error(f"Error extracting audio from file {file_id}: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(name="analyze_transcript")
def analyze_transcript_task(file_id: int):
    """
    Analyze a transcript for additional metadata and insights

    Args:
        file_id: Database ID of the MediaFile to analyze
    """
    try:
        with session_scope() as db:
            media_file = get_refreshed_object(db, MediaFile, file_id)
            if not media_file:
                logger.error(f"Media file with ID {file_id} not found")
                return {
                    "status": "error",
                    "message": f"Media file with ID {file_id} not found",
                }

            segments = (
                db.query(TranscriptSegment)
                .filter(TranscriptSegment.media_file_id == file_id)
                .order_by(TranscriptSegment.segment_index)
                .all()
            )

            if not segments:
                logger.warning(f"No transcript segments found for file {file_id}")
                return {"status": "error", "message": "No transcript segments found"}

            full_text = " ".join([segment.text for segment in segments])

            analytics = db.query(Analytics).filter(Analytics.media_file_id == file_id).first()
            if not analytics:
                analytics = Analytics(media_file_id=file_id)
                db.add(analytics)

            word_count = len(full_text.split())
            unique_speakers = len(set([segment.speaker_id for segment in segments]))

            analytics.word_count = word_count
            analytics.speaker_count = unique_speakers
            analytics.segment_count = len(segments)

            db.commit()

            logger.info(f"Analytics completed for file {file_id}")
            return {"status": "success", "file_id": file_id}

    except Exception as e:
        logger.error(f"Error analyzing transcript for file {file_id}: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(name="summarize_transcript")
def summarize_transcript_task(file_id: int):
    """
    Generate a summary of a transcript

    Args:
        file_id: Database ID of the MediaFile to summarize
    """
    try:
        with session_scope() as db:
            media_file = get_refreshed_object(db, MediaFile, file_id)
            if not media_file:
                logger.error(f"Media file with ID {file_id} not found")
                return {
                    "status": "error",
                    "message": f"Media file with ID {file_id} not found",
                }

            segments = (
                db.query(TranscriptSegment)
                .filter(TranscriptSegment.media_file_id == file_id)
                .order_by(TranscriptSegment.segment_index)
                .all()
            )

            if not segments:
                logger.warning(f"No transcript segments found for file {file_id}")
                return {"status": "error", "message": "No transcript segments found"}

            full_text = " ".join([segment.text for segment in segments])

            # Simple extractive summarization using NLTK
            try:
                import nltk
                from nltk.corpus import stopwords
                from nltk.probability import FreqDist
                from nltk.tokenize import sent_tokenize

                try:
                    nltk.data.find("tokenizers/punkt")
                except LookupError:
                    nltk.download("punkt")
                try:
                    nltk.data.find("corpora/stopwords")
                except LookupError:
                    nltk.download("stopwords")

                sentences = sent_tokenize(full_text)
                stop_words = set(stopwords.words("english"))
                words = [
                    word.lower()
                    for sentence in sentences
                    for word in nltk.word_tokenize(sentence)
                    if word.isalnum() and word.lower() not in stop_words
                ]

                word_frequencies = FreqDist(words)

                sentence_scores = {}
                for i, sentence in enumerate(sentences):
                    for word in nltk.word_tokenize(sentence.lower()):
                        if word in word_frequencies:
                            if i in sentence_scores:
                                sentence_scores[i] += word_frequencies[word]
                            else:
                                sentence_scores[i] = word_frequencies[word]

                num_summary_sentences = min(3, len(sentences))
                top_sentences = sorted(sentence_scores.items(), key=lambda x: x[1], reverse=True)[
                    :num_summary_sentences
                ]
                top_sentences = sorted(top_sentences, key=lambda x: x[0])

                summary = " ".join([sentences[i] for i, _ in top_sentences])

                if not summary.strip():
                    summary = f"Transcript with {len(segments)} segments and approximately {len(full_text.split())} words."

                media_file.summary = summary
                db.commit()

                logger.info(f"Summarization completed for file {file_id}")
                return {"status": "success", "file_id": file_id, "summary": summary}

            except ImportError:
                # Fallback summary if NLTK is not available
                summary = f"Transcript with {len(segments)} segments and approximately {len(full_text.split())} words."
                media_file.summary = summary
                db.commit()
                return {"status": "success", "file_id": file_id, "summary": summary}

    except Exception as e:
        logger.error(f"Error summarizing transcript for file {file_id}: {str(e)}")
        return {"status": "error", "message": str(e)}
