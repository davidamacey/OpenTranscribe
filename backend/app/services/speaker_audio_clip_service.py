"""
Speaker Audio Clip Service for extracting and managing speaker voice samples.

Extracts short audio clips (3-10s) from media files for rapid speaker
identification in the global speaker management page.
"""

import logging
import os
import subprocess
import tempfile
from typing import Any
from uuid import uuid4

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.media import MediaFile
from app.models.media import Speaker
from app.models.media import SpeakerAudioClip
from app.models.media import TranscriptSegment

logger = logging.getLogger(__name__)

# Clip extraction parameters
MIN_CLIP_DURATION = 2.0  # Minimum useful clip duration in seconds
MAX_CLIP_DURATION = 10.0  # Maximum clip duration
TARGET_CLIP_DURATION = 5.0  # Ideal clip duration
AUDIO_BITRATE = "48k"  # WebM/Opus bitrate
CLIP_FORMAT = "webm"
MINIO_BUCKET = "speaker-clips"


class SpeakerAudioClipService:
    """Service for extracting and managing speaker audio clips."""

    def __init__(self, db: Session):
        self.db = db

    def select_best_segment(
        self,
        speaker_id: int,
        media_file_id: int,
    ) -> dict[str, float] | None:
        """Select the best transcript segment for audio clip extraction.

        Prefers longer, higher-confidence, non-overlapping segments.

        Args:
            speaker_id: Speaker database ID.
            media_file_id: Media file database ID.

        Returns:
            Dict with start_time, end_time, duration, or None.
        """
        segments = (
            self.db.query(TranscriptSegment)
            .filter(
                TranscriptSegment.speaker_id == speaker_id,
                TranscriptSegment.media_file_id == media_file_id,
            )
            .order_by(TranscriptSegment.start_time)
            .all()
        )

        if not segments:
            return None

        best_score = -1.0
        best_segment = None

        for seg in segments:
            start = float(seg.start_time)
            end = float(seg.end_time)
            duration = end - start

            if duration < MIN_CLIP_DURATION:
                continue

            # Score: prefer segments near TARGET_CLIP_DURATION
            duration_score = 1.0 - abs(duration - TARGET_CLIP_DURATION) / TARGET_CLIP_DURATION
            duration_score = max(0.0, min(1.0, duration_score))

            # Confidence bonus
            confidence = float(seg.confidence) if seg.confidence else 0.5
            score = duration_score * 0.6 + confidence * 0.4

            # Prefer non-overlapping segments
            is_overlap = getattr(seg, "is_overlap", False)
            if is_overlap:
                score *= 0.5

            if score > best_score:
                best_score = score
                best_segment = {
                    "start_time": start,
                    "end_time": min(end, start + MAX_CLIP_DURATION),
                    "duration": min(duration, MAX_CLIP_DURATION),
                    "quality_score": score,
                }

        return best_segment

    def extract_clip_for_speaker(
        self,
        speaker_id: int,
        media_file_id: int,
        user_id: int,
    ) -> SpeakerAudioClip | None:
        """Extract an audio clip for a speaker from a media file.

        Args:
            speaker_id: Speaker database ID.
            media_file_id: Media file database ID.
            user_id: Owner user ID.

        Returns:
            Created SpeakerAudioClip record, or None on error.
        """
        try:
            # Check if clip already exists
            existing = (
                self.db.query(SpeakerAudioClip)
                .filter(
                    SpeakerAudioClip.speaker_id == speaker_id,
                    SpeakerAudioClip.media_file_id == media_file_id,
                )
                .first()
            )
            if existing:
                return existing  # type: ignore[no-any-return]

            # Select best segment
            segment = self.select_best_segment(speaker_id, media_file_id)
            if not segment:
                logger.debug(
                    f"No suitable segment for speaker {speaker_id} in file {media_file_id}"
                )
                return None

            # Get media file info
            media_file = self.db.query(MediaFile).filter(MediaFile.id == media_file_id).first()
            if not media_file:
                return None

            speaker = self.db.query(Speaker).filter(Speaker.id == speaker_id).first()
            if not speaker:
                return None

            clip_uuid = uuid4()
            storage_path = f"{user_id}/{clip_uuid}.{CLIP_FORMAT}"

            # Download source from MinIO and extract clip
            clip_data = self._extract_audio_clip(
                media_file.storage_path,
                segment["start_time"],
                segment["end_time"],
            )

            if clip_data is None:
                logger.warning(
                    f"Failed to extract clip for speaker {speaker_id} from file {media_file_id}"
                )
                return None

            # Upload to MinIO
            if not self._upload_to_minio(storage_path, clip_data):
                return None

            # Create database record
            clip = SpeakerAudioClip(
                uuid=clip_uuid,
                speaker_id=speaker_id,
                media_file_id=media_file_id,
                storage_path=storage_path,
                start_time=segment["start_time"],
                end_time=segment["end_time"],
                duration=segment["duration"],
                quality_score=segment["quality_score"],
                is_representative=False,
            )
            self.db.add(clip)
            self.db.flush()

            logger.info(
                f"Extracted clip for speaker {speaker_id}: "
                f"{segment['start_time']:.1f}-{segment['end_time']:.1f}s"
            )
            return clip

        except Exception as e:
            logger.error(f"Error extracting clip for speaker {speaker_id}: {e}")
            return None

    def extract_clips_for_file(
        self,
        media_file_id: int,
        user_id: int,
    ) -> list[SpeakerAudioClip]:
        """Extract audio clips for all speakers in a media file.

        Args:
            media_file_id: Media file database ID.
            user_id: Owner user ID.

        Returns:
            List of created SpeakerAudioClip records.
        """
        speakers = (
            self.db.query(Speaker)
            .filter(
                Speaker.media_file_id == media_file_id,
                Speaker.user_id == user_id,
            )
            .all()
        )

        clips: list[SpeakerAudioClip] = []
        for speaker in speakers:
            clip = self.extract_clip_for_speaker(int(speaker.id), media_file_id, user_id)
            if clip:
                clips.append(clip)

        # Mark the best clip per speaker as representative
        speaker_ids = {int(s.id) for s in speakers}
        for sid in speaker_ids:
            self._update_representative_clip(sid)

        self.db.commit()
        return clips

    def get_representative_clip(self, speaker_id: int) -> SpeakerAudioClip | None:
        """Get the representative audio clip for a speaker.

        Args:
            speaker_id: Speaker database ID.

        Returns:
            The representative clip, or the best available clip.
        """
        clip = (
            self.db.query(SpeakerAudioClip)
            .filter(
                SpeakerAudioClip.speaker_id == speaker_id,
                SpeakerAudioClip.is_representative.is_(True),
            )
            .first()
        )
        if clip:
            return clip  # type: ignore[no-any-return]

        # Fallback to highest quality
        return (  # type: ignore[no-any-return]
            self.db.query(SpeakerAudioClip)
            .filter(SpeakerAudioClip.speaker_id == speaker_id)
            .order_by(desc(SpeakerAudioClip.quality_score))
            .first()
        )

    def get_clip_stream_url(self, clip_uuid: str) -> str | None:
        """Generate a presigned URL for streaming an audio clip.

        Args:
            clip_uuid: UUID of the audio clip.

        Returns:
            Presigned URL string, or None.
        """
        clip = self.db.query(SpeakerAudioClip).filter(SpeakerAudioClip.uuid == clip_uuid).first()
        if not clip:
            return None

        try:
            minio_client = self._get_minio_client()
            if not minio_client:
                return None

            from datetime import timedelta

            url = minio_client.presigned_get_object(
                MINIO_BUCKET,
                clip.storage_path,
                expires=timedelta(hours=1),
            )
            return str(url)
        except Exception as e:
            logger.error(f"Error generating stream URL for clip {clip_uuid}: {e}")
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_audio_clip(
        self,
        source_storage_path: str,
        start_time: float,
        end_time: float,
    ) -> bytes | None:
        """Download source file from MinIO and extract audio clip via ffmpeg."""
        tmp_input = None
        tmp_output = None
        try:
            minio_client = self._get_minio_client()
            if not minio_client:
                logger.error("MinIO client not available")
                return None

            from app.core.config import settings

            # Download source to temp file
            tmp_input = tempfile.NamedTemporaryFile(suffix=".media", delete=False)  # noqa: SIM115
            tmp_output = tempfile.NamedTemporaryFile(suffix=f".{CLIP_FORMAT}", delete=False)  # noqa: SIM115
            tmp_input.close()
            tmp_output.close()

            minio_client.fget_object(
                settings.MINIO_BUCKET,
                source_storage_path,
                tmp_input.name,
            )

            # Extract clip with ffmpeg
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                tmp_input.name,
                "-ss",
                str(start_time),
                "-to",
                str(end_time),
                "-c:a",
                "libopus",
                "-b:a",
                AUDIO_BITRATE,
                "-vn",
                tmp_output.name,
            ]

            result = subprocess.run(  # noqa: S603  # nosec B603
                cmd,
                capture_output=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.error(f"ffmpeg failed: {result.stderr.decode()[:500]}")
                return None

            with open(tmp_output.name, "rb") as f:
                return f.read()

        except FileNotFoundError:
            logger.warning("ffmpeg not found, cannot extract audio clips")
            return None
        except subprocess.TimeoutExpired:
            logger.error("ffmpeg timed out extracting audio clip")
            return None
        except Exception as e:
            logger.error(f"Error extracting audio clip: {e}")
            return None
        finally:
            if tmp_input and os.path.exists(tmp_input.name):
                os.unlink(tmp_input.name)
            if tmp_output and os.path.exists(tmp_output.name):
                os.unlink(tmp_output.name)

    def _upload_to_minio(self, storage_path: str, data: bytes) -> bool:
        """Upload clip data to MinIO."""
        try:
            import io

            minio_client = self._get_minio_client()
            if not minio_client:
                return False

            # Ensure bucket exists
            if not minio_client.bucket_exists(MINIO_BUCKET):
                minio_client.make_bucket(MINIO_BUCKET)

            minio_client.put_object(
                MINIO_BUCKET,
                storage_path,
                io.BytesIO(data),
                len(data),
                content_type=f"audio/{CLIP_FORMAT}",
            )
            return True

        except Exception as e:
            logger.error(f"Error uploading clip to MinIO: {e}")
            return False

    def _get_minio_client(self) -> Any:
        """Get the MinIO client instance."""
        try:
            from minio import Minio

            from app.core.config import settings

            return Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=False,
            )
        except Exception as e:
            logger.error(f"Failed to create MinIO client: {e}")
            return None

    def _update_representative_clip(self, speaker_id: int) -> None:
        """Mark the best clip for a speaker as representative."""
        clips = (
            self.db.query(SpeakerAudioClip)
            .filter(SpeakerAudioClip.speaker_id == speaker_id)
            .order_by(desc(SpeakerAudioClip.quality_score))
            .all()
        )

        for i, clip in enumerate(clips):
            clip.is_representative = i == 0  # type: ignore[assignment]
