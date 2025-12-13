"""
Video processing service for embedding subtitles into video files.
"""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

import redis.asyncio as redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import VIDEO_CHUNK_SIZE
from app.services.minio_service import MinIOService
from app.services.subtitle_service import SubtitleService

logger = logging.getLogger(__name__)


def _parse_range_header(range_header: str, total_length: int | None) -> tuple[int, int | None]:
    """
    Parse HTTP Range header and return start and end bytes.

    Args:
        range_header: The Range header value (e.g., "bytes=0-1023")
        total_length: Total file size in bytes, or None if unknown

    Returns:
        Tuple of (start_byte, end_byte) where end_byte may be None
    """
    if not range_header or not range_header.startswith("bytes="):
        return 0, total_length - 1 if total_length else None

    try:
        range_value = range_header.replace("bytes=", "")
        parts = range_value.split("-")

        # Format: bytes=start-end
        if parts[0] and parts[1]:
            start_byte = int(parts[0])
            end_byte = min(int(parts[1]), total_length - 1) if total_length else int(parts[1])
            return start_byte, end_byte

        # Format: bytes=start-
        if parts[0]:
            start_byte = int(parts[0])
            end_byte = total_length - 1 if total_length else None
            return start_byte, end_byte

        # Format: bytes=-end (last N bytes)
        if parts[1]:
            requested_length = int(parts[1])
            if total_length:
                start_byte = max(0, total_length - requested_length)
                return start_byte, total_length - 1
            return 0, None

    except Exception as e:
        logger.error(f"Error parsing range header '{range_header}': {e}")

    # Default fallback
    return 0, total_length - 1 if total_length else None


def _get_video_codecs(output_format: str) -> tuple[str, str, str]:
    """
    Get video and subtitle codecs for the given output format.

    Args:
        output_format: Output video format (mp4, mkv, etc.)

    Returns:
        Tuple of (video_codec, subtitle_codec, normalized_format)
    """
    format_lower = output_format.lower()

    if format_lower == "mp4":
        return "copy", "mov_text", "mp4"
    if format_lower == "mkv":
        return "copy", "srt", "mkv"

    # Default to mp4
    return "copy", "mov_text", "mp4"


def _validate_ffmpeg_paths(original_video_path, subtitle_path) -> str:
    """
    Validate paths and return ffmpeg executable path.

    Args:
        original_video_path: Path to the original video file
        subtitle_path: Path to the subtitle file

    Returns:
        Full path to ffmpeg executable

    Raises:
        Exception: If ffmpeg not found or paths are invalid
    """
    import shutil

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise Exception("ffmpeg not found in system PATH")

    original_path_obj = Path(original_video_path)
    if not original_path_obj.exists():
        raise Exception(f"Input video file not found: {original_video_path}")
    if not subtitle_path.exists():
        raise Exception(f"Subtitle file not found: {subtitle_path}")

    return ffmpeg_path


def _build_ffmpeg_command(
    ffmpeg_path: str,
    video_path: str,
    subtitle_path: str,
    output_path: str,
    video_codec: str,
    subtitle_codec: str,
) -> list[str]:
    """Build the ffmpeg command for embedding subtitles."""
    return [
        ffmpeg_path,
        "-i",
        str(video_path),
        "-i",
        str(subtitle_path),
        "-map",
        "0:v",
        "-map",
        "0:a",
        "-map",
        "1:0",
        "-c:v",
        video_codec,
        "-c:a",
        "copy",
        "-c:s",
        subtitle_codec,
        "-disposition:s:0",
        "default",
        "-metadata:s:s:0",
        "language=eng",
        "-metadata:s:s:0",
        "title=English (Auto-generated)",
        "-y",
        str(output_path),
    ]


def _run_ffmpeg(ffmpeg_cmd: list[str], file_id: int) -> None:
    """
    Run ffmpeg command and handle errors.

    Args:
        ffmpeg_cmd: The ffmpeg command to run
        file_id: Media file ID for logging

    Raises:
        Exception: If ffmpeg fails or times out
    """
    logger.info(f"Running ffmpeg command: {' '.join(ffmpeg_cmd)}")

    result = subprocess.run(  # noqa: S603
        ffmpeg_cmd,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )

    if result.returncode != 0:
        logger.error(f"ffmpeg failed with return code {result.returncode}")
        logger.error(f"ffmpeg stderr: {result.stderr}")
        logger.error(f"ffmpeg stdout: {result.stdout}")
        raise Exception(f"Video processing failed: {result.stderr}")

    logger.info(f"ffmpeg completed successfully for file {file_id}")


class VideoProcessingService:
    """Service for processing video files, including subtitle embedding."""

    def __init__(self, minio_service: MinIOService):
        self.minio_service = minio_service
        self.cache_bucket = "processed-videos"
        self._ensure_cache_bucket_exists()

    async def _send_download_progress(
        self,
        user_id: int,
        file_id: int,
        status: str,
        progress: int = None,
        error: str = None,
    ):
        """Send download progress update via WebSocket."""
        try:
            redis_client = redis.from_url(settings.REDIS_URL)
            notification_data = {
                "user_id": user_id,
                "type": "download_progress",
                "data": {
                    "file_id": str(file_id),
                    "status": status,
                    "progress": progress,
                    "error": error,
                },
            }
            await redis_client.publish("websocket_notifications", json.dumps(notification_data))
            await redis_client.close()
            logger.info(
                f"Sent download progress update: user={user_id}, file={file_id}, status={status}"
            )
        except Exception as e:
            logger.error(f"Failed to send download progress update: {e}")

    def _send_download_progress_sync(
        self,
        user_id: int,
        file_id: int,
        status: str,
        progress: int = None,
        error: str = None,
    ):
        """Synchronous wrapper for sending download progress updates."""
        try:
            # Create new event loop for this thread if needed
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Run the async function
            loop.run_until_complete(
                self._send_download_progress(user_id, file_id, status, progress, error)
            )
        except Exception as e:
            logger.error(f"Failed to send download progress update (sync): {e}")

    def _ensure_cache_bucket_exists(self):
        """Ensure the cache bucket exists."""
        try:
            if not self.minio_service.bucket_exists(self.cache_bucket):
                logger.info(f"Creating cache bucket: {self.cache_bucket}")
                self.minio_service.make_bucket(self.cache_bucket)
                logger.info(f"Cache bucket created successfully: {self.cache_bucket}")
            else:
                logger.info(f"Cache bucket already exists: {self.cache_bucket}")
        except Exception as e:
            logger.error(f"Failed to create cache bucket: {e}")
            raise

    def generate_cache_key(
        self, file_id: int, original_filename: str, include_speakers: bool = True
    ) -> str:
        """Generate a cache key for processed video using original filename."""
        # Get base filename without extension
        base_name = (
            original_filename.rsplit(".", 1)[0] if "." in original_filename else original_filename
        )
        speaker_suffix = "_with_speakers" if include_speakers else "_no_speakers"
        return f"{base_name}{speaker_suffix}.mp4"

    def is_video_cached(self, cache_key: str) -> bool:
        """Check if a cached video exists."""
        try:
            # Check if cached video exists
            self.minio_service.stat_object(self.cache_bucket, cache_key)
            return True
        except Exception:
            return False

    def get_cached_video_stream(self, cache_key: str):
        """Get streaming response for a cached video."""
        try:
            # Use our custom cache bucket streaming function
            return self._get_cache_file_stream(cache_key)
        except Exception as e:
            logger.error(f"Error getting cached video stream: {e}")
            raise

    def _get_object_size(self, object_name: str) -> int | None:
        """Get the size of a cached object, or None if unavailable."""
        try:
            stats = self.minio_service.stat_object(self.cache_bucket, object_name)
            logger.info(f"Cached file size for {object_name}: {stats.size} bytes")
            return stats.size
        except Exception as e:
            logger.error(f"Error getting cached object stats: {e}")
            return None

    def _create_chunk_generator(self, response, max_bytes: int | None):
        """Create a generator that yields chunks from the MinIO response."""
        chunk_size = VIDEO_CHUNK_SIZE

        def generate_chunks():
            try:
                bytes_read = 0
                while True:
                    # Adjust final chunk size if we're at the end of requested range
                    if max_bytes is not None and bytes_read + chunk_size > max_bytes:
                        final_chunk_size = max_bytes - bytes_read
                        if final_chunk_size <= 0:
                            break
                        chunk = response.read(final_chunk_size)
                    else:
                        chunk = response.read(chunk_size)

                    if not chunk:
                        break

                    bytes_read += len(chunk)
                    yield chunk
            finally:
                try:
                    response.close()
                    response.release_conn()
                except Exception as e:
                    logger.error(f"Error closing MinIO response: {e}")

        return generate_chunks()

    def _get_cache_file_stream(self, object_name: str, range_header: str = None):
        """Get a file stream from the cache bucket."""
        try:
            total_length = self._get_object_size(object_name)
            start_byte, end_byte = _parse_range_header(range_header, total_length)

            # Build MinIO request kwargs
            kwargs = {"bucket_name": self.cache_bucket, "object_name": object_name}
            if range_header and range_header.startswith("bytes="):
                kwargs["offset"] = start_byte
                if end_byte is not None:
                    kwargs["length"] = end_byte - start_byte + 1

                logger.info(
                    f"Streaming cached video with range: start={start_byte}, "
                    f"end={end_byte if end_byte is not None else 'EOF'}, total={total_length}"
                )

            response = self.minio_service.client.get_object(**kwargs)
            chunks = self._create_chunk_generator(response, kwargs.get("length"))

            return chunks, start_byte, end_byte, total_length

        except Exception as e:
            logger.error(f"Error setting up cached file stream for {object_name}: {e}")
            raise Exception(f"Error streaming cached file: {e}") from e

    def _notify_progress(
        self,
        user_id: int | None,
        file_id: int,
        status: str,
        progress: int = None,
        error: str = None,
    ):
        """Send progress notification if user_id is provided."""
        if user_id:
            self._send_download_progress_sync(user_id, file_id, status, progress, error)

    def _generate_subtitle_file(
        self, db: Session, file_id: int, subtitle_path: Path, include_speakers: bool
    ) -> None:
        """Generate subtitle file from transcript segments."""
        subtitle_content = SubtitleService.generate_srt_content(db, file_id, include_speakers)
        with open(subtitle_path, "w", encoding="utf-8") as f:
            f.write(subtitle_content)

    def _upload_to_cache(self, output_path: Path, cache_key: str, output_format: str) -> None:
        """Upload processed video to cache bucket."""
        logger.info(f"Uploading processed video to cache bucket: {self.cache_bucket}/{cache_key}")
        self.minio_service.upload_file(
            file_path=str(output_path),
            bucket_name=self.cache_bucket,
            object_name=cache_key,
            content_type=f"video/{output_format}",
        )
        logger.info("Upload complete, video processing finished")

    def _process_video_in_temp_dir(
        self,
        db: Session,
        file_id: int,
        original_video_path,
        user_id: int | None,
        include_speakers: bool,
        output_format: str,
        cache_key: str,
    ) -> str:
        """Process video with subtitles in temporary directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            subtitle_path = temp_dir_path / "subtitles.srt"

            # Generate subtitle file
            self._notify_progress(user_id, file_id, "processing", 20)
            self._generate_subtitle_file(db, file_id, subtitle_path, include_speakers)
            self._notify_progress(user_id, file_id, "processing", 30)

            # Get codecs and normalize format
            video_codec, subtitle_codec, normalized_format = _get_video_codecs(output_format)
            output_path = temp_dir_path / f"output.{normalized_format}"

            # Validate paths and get ffmpeg
            ffmpeg_path = _validate_ffmpeg_paths(original_video_path, subtitle_path)

            # Build and run ffmpeg command
            ffmpeg_cmd = _build_ffmpeg_command(
                ffmpeg_path,
                original_video_path,
                subtitle_path,
                output_path,
                video_codec,
                subtitle_codec,
            )

            self._notify_progress(user_id, file_id, "processing", 50)
            _run_ffmpeg(ffmpeg_cmd, file_id)
            logger.info(f"Output file size: {os.path.getsize(output_path)} bytes")

            # Upload to cache
            self._notify_progress(user_id, file_id, "processing", 80)
            self._upload_to_cache(output_path, cache_key, normalized_format)
            self._notify_progress(user_id, file_id, "completed", 100)

            return cache_key

    def embed_subtitles_in_video(
        self,
        db: Session,
        file_id: int,
        original_video_path,
        user_id: int = None,
        include_speakers: bool = True,
        output_format: str = "mp4",
    ) -> str:
        """
        Embed subtitles into a video file using ffmpeg.

        Args:
            db: Database session
            file_id: Media file ID
            original_video_path: Path to the original video file
            include_speakers: Whether to include speaker labels
            output_format: Output video format (mp4, mkv, etc.)

        Returns:
            Path to the processed video file with embedded subtitles
        """
        from app.models.media import MediaFile

        db_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
        if not db_file:
            raise Exception(f"Media file {file_id} not found")

        cache_key = self.generate_cache_key(file_id, db_file.filename, include_speakers)

        # Return cached version if available
        if self.is_video_cached(cache_key):
            logger.info(f"Using cached video for file {file_id}")
            self._notify_progress(user_id, file_id, "completed")
            return cache_key

        self._notify_progress(user_id, file_id, "processing", 10)

        try:
            return self._process_video_in_temp_dir(
                db,
                file_id,
                original_video_path,
                user_id,
                include_speakers,
                output_format,
                cache_key,
            )
        except subprocess.TimeoutExpired as e:
            logger.error(f"ffmpeg timeout for file {file_id}")
            self._notify_progress(user_id, file_id, "error", error="Video processing timeout")
            raise Exception("Video processing timeout") from e
        except Exception as e:
            logger.error(f"Video processing error for file {file_id}: {e}")
            self._notify_progress(user_id, file_id, "error", error=str(e))
            raise

    def process_video_with_subtitles(
        self,
        db: Session,
        file_id: int,
        original_object_name: str,
        user_id: int = None,
        include_speakers: bool = True,
        output_format: str = "mp4",
    ) -> str:
        """
        Complete workflow to process a video with embedded subtitles.

        Args:
            db: Database session
            file_id: Media file ID
            original_object_name: MinIO object name for the original video
            include_speakers: Whether to include speaker labels
            output_format: Output video format

        Returns:
            Presigned URL to download the processed video
        """
        # Get the MediaFile to access original filename
        from app.models.media import MediaFile

        db_file_for_name = db.query(MediaFile).filter(MediaFile.id == file_id).first()
        if not db_file_for_name:
            raise Exception(f"Media file {file_id} not found")

        cache_key = self.generate_cache_key(file_id, db_file_for_name.filename, include_speakers)

        # Check cache first
        if self.is_video_cached(cache_key):
            return cache_key

        # Download original video to temporary location
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            original_path = temp_dir_path / "original_video"

            try:
                # Download original video from MinIO
                self.minio_service.download_file(
                    object_name=original_object_name,
                    file_path=str(original_path),
                    bucket_name=settings.MEDIA_BUCKET_NAME,
                )

                # Process video with subtitles
                return self.embed_subtitles_in_video(
                    db=db,
                    file_id=file_id,
                    original_video_path=original_path,
                    user_id=user_id,
                    include_speakers=include_speakers,
                    output_format=output_format,
                )

            except Exception as e:
                logger.error(f"Failed to process video {file_id}: {e}")
                raise

    def clear_cache_for_media_file(self, db: Session, file_id: int):
        """Clear cached processed videos for a media file."""
        try:
            # Get the MediaFile to access original filename
            from app.models.media import MediaFile

            db_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
            if not db_file:
                logger.warning(f"Media file {file_id} not found for cache clearing")
                return

            # Clear both speaker variants
            for include_speakers in [True, False]:
                cache_key = self.generate_cache_key(file_id, db_file.filename, include_speakers)
                try:
                    self.minio_service.delete_object(self.cache_bucket, cache_key)
                    logger.info(f"Cleared cache for {cache_key}")
                except Exception as cache_error:
                    # Cache file might not exist, which is fine, but we should log for debugging
                    logger.debug(
                        f"Cache file {cache_key} not found or could not be deleted: {cache_error}"
                    )
        except Exception as e:
            logger.error(f"Failed to clear cache for file {file_id}: {e}")

    def check_ffmpeg_availability(self) -> bool:
        """Check if ffmpeg is available on the system."""
        import shutil

        try:
            # Use shutil.which to find the full path to ffmpeg
            ffmpeg_path = shutil.which("ffmpeg")
            if not ffmpeg_path:
                logger.warning("ffmpeg not found in system PATH")
                return False

            # Use full path for security - validated path, not user input
            result = subprocess.run(  # noqa: S603
                [ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,  # Don't raise exception on non-zero return code
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning(f"Failed to check ffmpeg availability: {e}")
            return False
