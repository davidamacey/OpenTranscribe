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
from app.services.minio_service import MinIOService
from app.services.subtitle_service import SubtitleService

logger = logging.getLogger(__name__)


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

    def _get_cache_file_stream(self, object_name: str, range_header: str = None):
        """Get a file stream from the cache bucket."""
        import logging

        logger = logging.getLogger(__name__)

        # Default values
        start_byte = 0
        end_byte = None
        total_length = None

        try:
            # Get object stats first to know the total size
            try:
                stats = self.minio_service.stat_object(self.cache_bucket, object_name)
                total_length = stats.size
                logger.info(f"Cached file size for {object_name}: {total_length} bytes")
            except Exception as e:
                logger.error(f"Error getting cached object stats: {e}")

            kwargs = {"bucket_name": self.cache_bucket, "object_name": object_name}

            # Parse range header if present
            if range_header and range_header.startswith("bytes="):
                try:
                    # Parse range from format "bytes=start-end"
                    range_value = range_header.replace("bytes=", "")
                    parts = range_value.split("-")

                    # Handle different range request formats
                    if parts[0] and parts[1]:  # Format: bytes=start-end
                        start_byte = int(parts[0])
                        end_byte = (
                            min(int(parts[1]), total_length - 1) if total_length else int(parts[1])
                        )
                    elif parts[0]:  # Format: bytes=start-
                        start_byte = int(parts[0])
                        end_byte = total_length - 1 if total_length else None
                    elif parts[1]:  # Format: bytes=-end (last N bytes)
                        requested_length = int(parts[1])
                        if total_length:
                            start_byte = max(0, total_length - requested_length)
                            end_byte = total_length - 1

                    # Add offset and length parameters for MinIO
                    kwargs["offset"] = start_byte
                    if end_byte is not None:
                        kwargs["length"] = (
                            end_byte - start_byte + 1
                        )  # +1 because range is inclusive

                    logger.info(
                        f"Streaming cached video with range: start={start_byte}, end={end_byte if end_byte is not None else 'EOF'}, total={total_length}"
                    )
                except Exception as e:
                    logger.error(f"Error parsing range header '{range_header}': {e}")
                    # Continue without range if parsing fails
                    start_byte = 0
                    end_byte = total_length - 1 if total_length else None
            elif total_length:  # No range but we know the size
                end_byte = total_length - 1

            # Get the file from MinIO cache bucket
            response = self.minio_service.client.get_object(**kwargs)

            # Choose optimal chunk size
            chunk_size = 65536  # 64KB chunks for processed videos

            # Function to yield chunks with proper resource cleanup
            def generate_chunks():
                try:
                    bytes_read = 0
                    max_bytes = kwargs.get("length")

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
                    # Ensure resources are properly cleaned up
                    try:
                        response.close()
                        response.release_conn()
                    except Exception as e:
                        logger.error(f"Error closing MinIO response: {e}")

            # Return the generator along with range information
            return generate_chunks(), start_byte, end_byte, total_length

        except Exception as e:
            logger.error(f"Error setting up cached file stream for {object_name}: {e}")
            raise Exception(f"Error streaming cached file: {e}") from e

    def embed_subtitles_in_video(
        self,
        db: Session,
        file_id: int,
        original_video_path: str,
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
        # Get the MediaFile to access original filename
        from app.models.media import MediaFile

        db_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
        if not db_file:
            raise Exception(f"Media file {file_id} not found")

        cache_key = self.generate_cache_key(file_id, db_file.filename, include_speakers)

        # Check if cached version exists
        if self.is_video_cached(cache_key):
            logger.info(f"Using cached video for file {file_id}")
            if user_id:
                self._send_download_progress_sync(user_id, file_id, "completed")
            return cache_key

        # Send initial processing status
        if user_id:
            self._send_download_progress_sync(user_id, file_id, "processing", 10)

        # Create temporary files
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)

            # Generate subtitle file
            subtitle_path = temp_dir_path / "subtitles.srt"
            try:
                if user_id:
                    self._send_download_progress_sync(user_id, file_id, "processing", 20)

                subtitle_content = SubtitleService.generate_srt_content(
                    db, file_id, include_speakers
                )

                with open(subtitle_path, "w", encoding="utf-8") as f:
                    f.write(subtitle_content)

                if user_id:
                    self._send_download_progress_sync(user_id, file_id, "processing", 30)

            except Exception as e:
                logger.error(f"Failed to generate subtitles for file {file_id}: {e}")
                if user_id:
                    self._send_download_progress_sync(user_id, file_id, "error", error=str(e))
                raise

            # Output video path
            output_path = temp_dir_path / f"output.{output_format}"

            # Determine video codec and subtitle codec based on format
            # Use 'copy' to avoid re-encoding the video stream (preserves quality and reduces processing time)
            if output_format.lower() == "mp4":
                video_codec = "copy"  # Don't re-encode video
                subtitle_codec = "mov_text"
            elif output_format.lower() == "mkv":
                video_codec = "copy"  # Don't re-encode video
                subtitle_codec = "srt"
            else:
                # Default to mp4
                video_codec = "copy"  # Don't re-encode video
                subtitle_codec = "mov_text"
                output_format = "mp4"
                output_path = temp_dir_path / f"output.{output_format}"

            # Build ffmpeg command with proper subtitle embedding
            ffmpeg_cmd = [
                "ffmpeg",
                "-i",
                original_video_path,  # Input video
                "-i",
                str(subtitle_path),  # Input subtitles
                "-map",
                "0:v",  # Map video from first input
                "-map",
                "0:a",  # Map audio from first input
                "-map",
                "1:s",  # Map subtitles from second input
                "-c:v",
                video_codec,  # Video codec
                "-c:a",
                "copy",  # Copy audio without re-encoding
                "-c:s",
                subtitle_codec,  # Subtitle codec
                "-disposition:s:0",
                "default",  # Make subtitles default
                "-metadata:s:s:0",
                "language=eng",  # Set subtitle language
                "-metadata:s:s:0",
                "title=English (Auto-generated)",  # Set subtitle title
                "-y",  # Overwrite output file
                str(output_path),
            ]

            try:
                # Run ffmpeg command
                if user_id:
                    self._send_download_progress_sync(user_id, file_id, "processing", 50)

                logger.info(f"Running ffmpeg command: {' '.join(ffmpeg_cmd)}")
                result = subprocess.run(
                    ffmpeg_cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                )

                if result.returncode != 0:
                    logger.error(f"ffmpeg failed with return code {result.returncode}")
                    logger.error(f"ffmpeg stderr: {result.stderr}")
                    logger.error(f"ffmpeg stdout: {result.stdout}")
                    if user_id:
                        self._send_download_progress_sync(
                            user_id,
                            file_id,
                            "error",
                            error=f"Video processing failed: {result.stderr}",
                        )
                    raise Exception(f"Video processing failed: {result.stderr}")

                logger.info(f"ffmpeg completed successfully for file {file_id}")
                logger.info(f"Output file size: {os.path.getsize(output_path)} bytes")

                if user_id:
                    self._send_download_progress_sync(user_id, file_id, "processing", 80)

                # Upload processed video to cache
                logger.info(
                    f"Uploading processed video to cache bucket: {self.cache_bucket}/{cache_key}"
                )
                self.minio_service.upload_file(
                    file_path=str(output_path),
                    bucket_name=self.cache_bucket,
                    object_name=cache_key,
                    content_type=f"video/{output_format}",
                )

                logger.info("Upload complete, video processing finished")

                if user_id:
                    self._send_download_progress_sync(user_id, file_id, "completed", 100)

                # Return the cache key instead of presigned URL - we'll stream through backend
                return cache_key

            except subprocess.TimeoutExpired as e:
                logger.error(f"ffmpeg timeout for file {file_id}")
                if user_id:
                    self._send_download_progress_sync(
                        user_id, file_id, "error", error="Video processing timeout"
                    )
                raise Exception("Video processing timeout") from e
            except Exception as e:
                logger.error(f"Video processing error for file {file_id}: {e}")
                if user_id:
                    self._send_download_progress_sync(user_id, file_id, "error", error=str(e))
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
                    original_video_path=str(original_path),
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
                except Exception:
                    # Cache file might not exist, which is fine
                    pass
        except Exception as e:
            logger.error(f"Failed to clear cache for file {file_id}: {e}")

    def check_ffmpeg_availability(self) -> bool:
        """Check if ffmpeg is available on the system."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"], capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
