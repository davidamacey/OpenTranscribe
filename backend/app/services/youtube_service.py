"""
YouTube processing service for downloading and processing YouTube videos.

This service handles all YouTube-related operations including URL validation,
video downloading, metadata extraction, and integration with the media processing pipeline.
"""

import io
import logging
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Optional

import requests
import yt_dlp
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.media import FileStatus
from app.models.media import MediaFile
from app.models.user import User
from app.services.minio_service import upload_file
from app.utils.thumbnail import generate_and_upload_thumbnail_sync

logger = logging.getLogger(__name__)

# YouTube URL validation regex - supports both videos and playlists
YOUTUBE_URL_PATTERN = re.compile(
    r"^https?://(www\.)?(youtube\.com/(watch\?v=|embed/|v/|playlist\?list=)|youtu\.be/)[\w\-_]+.*$"
)

# YouTube playlist URL validation regex
YOUTUBE_PLAYLIST_PATTERN = re.compile(
    r"^https?://(www\.)?youtube\.com/playlist\?list=([\w\-_]+).*$"
)


class YouTubeService:
    """Service for processing YouTube videos."""

    def __init__(self):
        pass

    def is_valid_youtube_url(self, url: str) -> bool:
        """
        Validate if URL is a valid YouTube URL (video or playlist).

        Args:
            url: URL to validate

        Returns:
            True if valid YouTube URL, False otherwise
        """
        return bool(YOUTUBE_URL_PATTERN.match(url.strip()))

    def is_playlist_url(self, url: str) -> bool:
        """
        Check if URL is a YouTube playlist URL.

        Args:
            url: URL to validate

        Returns:
            True if URL is a playlist, False if it's a single video
        """
        return bool(YOUTUBE_PLAYLIST_PATTERN.match(url.strip()))

    def extract_video_info(self, url: str) -> dict[str, Any]:
        """
        Extract video metadata without downloading.

        Args:
            url: YouTube URL

        Returns:
            Dictionary with video information

        Raises:
            HTTPException: If unable to extract video information
        """
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info
        except Exception as e:
            logger.error(f"Error extracting video info from {url}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to extract video information: {str(e)}",
            ) from e

    def extract_playlist_info(self, url: str) -> dict[str, Any]:
        """
        Extract playlist metadata and video list without downloading.

        Args:
            url: YouTube playlist URL

        Returns:
            Dictionary with playlist information including:
            - playlist_id: Playlist ID
            - playlist_title: Playlist title
            - playlist_uploader: Playlist creator
            - video_count: Number of videos
            - videos: List of video entries with URLs and basic info

        Raises:
            HTTPException: If unable to extract playlist information
        """
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",  # Extract video info without downloading
            "skip_download": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                if not info:
                    raise ValueError("No playlist information found")

                # Extract video entries
                entries = info.get("entries", [])
                videos = []

                for idx, entry in enumerate(entries):
                    if entry:  # Some entries might be None (unavailable videos)
                        video_id = entry.get("id")
                        if video_id:
                            videos.append(
                                {
                                    "video_id": video_id,
                                    "url": f"https://www.youtube.com/watch?v={video_id}",
                                    "title": entry.get("title", "Unknown"),
                                    "duration": entry.get("duration"),
                                    "uploader": entry.get("uploader"),
                                    "playlist_index": idx + 1,
                                }
                            )

                return {
                    "playlist_id": info.get("id"),
                    "playlist_title": info.get("title", "Unknown Playlist"),
                    "playlist_uploader": info.get("uploader") or info.get("channel"),
                    "playlist_description": info.get("description"),
                    "video_count": len(videos),
                    "videos": videos,
                }

        except Exception as e:
            logger.error(f"Error extracting playlist info from {url}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to extract playlist information: {str(e)}",
            ) from e

    def download_video(
        self,
        url: str,
        output_path: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> dict[str, Any]:
        """
        Download video from YouTube URL.

        Args:
            url: YouTube URL
            output_path: Directory to save downloaded file
            progress_callback: Optional callback for progress updates

        Returns:
            Dictionary with file path, filename, and video info

        Raises:
            HTTPException: If download fails
        """

        # Create progress hook function
        def progress_hook(d):
            if progress_callback and d.get("status") == "downloading":
                # Calculate progress percentage from downloaded_bytes and total_bytes
                total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded_bytes = d.get("downloaded_bytes", 0)

                if total_bytes and total_bytes > 0:
                    progress_percent = min(
                        int((downloaded_bytes / total_bytes) * 40) + 20, 60
                    )  # Map to 20-60% range
                    progress_callback(progress_percent, "Downloading video...")

        # Configure yt-dlp options for highest quality with web-compatible output
        ydl_opts = {
            # Download best H.264 quality for maximum browser compatibility
            # Prefer H.264 video codec over AV1 to ensure playback works across all browsers
            "format": "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/bestvideo[vcodec*=h264][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": os.path.join(output_path, "%(title)s.%(ext)s"),
            "restrictfilenames": True,  # Avoid special characters in filename
            "no_warnings": False,
            "extractaudio": False,
            "embed_subs": True,  # Embed subtitles if available
            "writesubtitles": False,  # Don't write separate subtitle files
            "writeautomaticsub": False,  # Don't write auto-generated subs
            "ignoreerrors": False,
            "no_playlist": True,  # Only download single video
            "max_filesize": 15 * 1024 * 1024 * 1024,  # 15GB limit (matches upload limit)
            # Ensure web-compatible MP4 output
            "merge_output_format": "mp4",
            # Use configured temp directory for yt-dlp cache and temporary files
            "cachedir": str(settings.TEMP_DIR / "yt-dlp-cache"),
            "paths": {"temp": output_path},  # Use the provided output_path for temp files
            # Anti-blocking measures for YouTube
            "extractor_args": {
                "youtube": {
                    "player_client": [
                        "android",
                        "web",
                    ],  # Try Android client first, fallback to web
                    "player_skip": ["webpage", "configs"],  # Skip unnecessary requests
                }
            },
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-us,en;q=0.5",
                "Sec-Fetch-Mode": "navigate",
            },
            "postprocessors": [
                {
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                }
            ],
        }

        # Add progress hook if callback is provided
        if progress_callback:
            ydl_opts["progress_hooks"] = [progress_hook]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first
                info = ydl.extract_info(url, download=False)

                # Check duration (optional limit)
                duration = info.get("duration")
                if duration and duration > 14400:  # 4 hours limit
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Video is too long. Maximum duration is 4 hours.",
                    )

                # Download the video
                ydl.download([url])

                # Find the downloaded file
                title = info.get("title", "video")
                ext = info.get("ext", "mp4")

                # Clean title for filename
                clean_title = re.sub(r"[^\w\-_\.]", "_", title)[:100]  # Limit length
                expected_filename = f"{clean_title}.{ext}"
                downloaded_file = os.path.join(output_path, expected_filename)

                # Find actual downloaded file (yt-dlp might change the name)
                if not os.path.exists(downloaded_file):
                    # Look for any video file in the directory
                    for file in os.listdir(output_path):
                        if file.endswith((".mp4", ".webm", ".mkv", ".avi")):
                            downloaded_file = os.path.join(output_path, file)
                            break
                    else:
                        raise FileNotFoundError("Downloaded file not found")

                return {
                    "file_path": downloaded_file,
                    "filename": os.path.basename(downloaded_file),
                    "info": info,
                }

        except yt_dlp.DownloadError as e:
            logger.error(f"yt-dlp download error for {url}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to download video: {str(e)}",
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error downloading {url}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error during download: {str(e)}",
            ) from e

    def _extract_technical_metadata(self, file_path: str) -> dict[str, Any]:
        """
        Extract technical metadata from downloaded file.

        Args:
            file_path: Path to the downloaded file

        Returns:
            Dictionary with technical metadata
        """
        try:
            # Use the existing metadata extraction service
            from app.tasks.transcription.metadata_extractor import extract_media_metadata
            from app.tasks.transcription.metadata_extractor import get_important_metadata

            raw_metadata = extract_media_metadata(file_path)
            if raw_metadata:
                important_metadata = get_important_metadata(raw_metadata)

                # Convert to format expected by MediaFile model
                return {
                    "content_type": raw_metadata.get("File:MIMEType", "video/mp4"),
                    "format": important_metadata.get("FileType"),
                    "video_codec": important_metadata.get("VideoCodec"),
                    "width": important_metadata.get("VideoWidth"),
                    "height": important_metadata.get("VideoHeight"),
                    "frame_rate": important_metadata.get("VideoFrameRate"),
                    "audio_channels": important_metadata.get("AudioChannels"),
                    "audio_sample_rate": important_metadata.get("AudioSampleRate"),
                    "duration": important_metadata.get("Duration"),
                }
            else:
                logger.warning("No metadata extracted, using fallback")
                return self._extract_basic_metadata(file_path)
        except Exception as e:
            logger.warning(f"Failed to extract technical metadata: {e}")
            return self._extract_basic_metadata(file_path)

    def _safe_frame_rate_eval(self, frame_rate_str: str) -> float:
        """
        Safely evaluate frame rate string like '30/1' or '29.97'.

        Args:
            frame_rate_str: Frame rate string from ffprobe

        Returns:
            Frame rate as float or None if invalid
        """
        try:
            if "/" in frame_rate_str:
                numerator, denominator = frame_rate_str.split("/")
                return float(numerator) / float(denominator)
            else:
                return float(frame_rate_str)
        except (ValueError, ZeroDivisionError):
            logger.warning(f"Invalid frame rate format: {frame_rate_str}")
            return None

    def _extract_basic_metadata(self, file_path: str) -> dict[str, Any]:
        """
        Fallback method to extract basic metadata using ffprobe.

        Args:
            file_path: Path to the media file

        Returns:
            Dictionary with basic metadata
        """
        try:
            import ffmpeg

            probe = ffmpeg.probe(file_path)
            format_info = probe.get("format", {})
            video_stream = next(
                (stream for stream in probe["streams"] if stream["codec_type"] == "video"),
                None,
            )
            audio_stream = next(
                (stream for stream in probe["streams"] if stream["codec_type"] == "audio"),
                None,
            )

            metadata = {
                "content_type": "video/mp4",  # Default
                "format": format_info.get("format_name"),
                "duration": float(format_info.get("duration", 0)),
            }

            if video_stream:
                metadata.update(
                    {
                        "video_codec": video_stream.get("codec_name"),
                        "width": video_stream.get("width"),
                        "height": video_stream.get("height"),
                        "frame_rate": self._safe_frame_rate_eval(video_stream.get("r_frame_rate"))
                        if video_stream.get("r_frame_rate")
                        else None,
                    }
                )

            if audio_stream:
                metadata.update(
                    {
                        "audio_channels": audio_stream.get("channels"),
                        "audio_sample_rate": audio_stream.get("sample_rate"),
                    }
                )

            return metadata

        except Exception as e:
            logger.warning(f"Failed to extract basic metadata: {e}")
            return {"content_type": "video/mp4"}

    def _prepare_youtube_metadata(self, url: str, youtube_info: dict[str, Any]) -> dict[str, Any]:
        """
        Prepare YouTube-specific metadata for storage.

        Args:
            url: Original YouTube URL
            youtube_info: Information extracted from yt-dlp

        Returns:
            Dictionary with YouTube metadata
        """
        return {
            "source": "youtube",
            "original_url": url,
            "youtube_id": youtube_info.get("id"),
            "youtube_title": youtube_info.get("title"),
            "youtube_description": youtube_info.get("description"),
            "youtube_uploader": youtube_info.get("uploader"),
            "youtube_upload_date": youtube_info.get("upload_date"),
            "youtube_duration": youtube_info.get("duration"),
            "youtube_view_count": youtube_info.get("view_count"),
            "youtube_like_count": youtube_info.get("like_count"),
            "youtube_thumbnail": youtube_info.get("thumbnail"),
            "youtube_tags": youtube_info.get("tags", []),
            "youtube_categories": youtube_info.get("categories", []),
        }

    def _download_youtube_thumbnail_sync(self, youtube_info: dict[str, Any], user_id: int) -> str:
        """
        Download YouTube thumbnail and upload to storage (synchronous version).

        Args:
            youtube_info: YouTube metadata from yt-dlp
            user_id: User ID for storage path

        Returns:
            Storage path of uploaded thumbnail or None if failed
        """
        try:
            # Get the best thumbnail URL from YouTube info
            thumbnail_url = None
            thumbnails = youtube_info.get("thumbnails", [])

            if not thumbnails and youtube_info.get("thumbnail"):
                # Fallback to single thumbnail URL
                thumbnail_url = youtube_info.get("thumbnail")
            else:
                # Find the highest quality thumbnail
                # YouTube provides multiple thumbnails, we want the highest resolution
                max_width = 0
                for thumb in thumbnails:
                    width = thumb.get("width", 0)
                    if width > max_width and thumb.get("url"):
                        max_width = width
                        thumbnail_url = thumb["url"]

                # Fallback to maxresdefault or hqdefault
                if not thumbnail_url and youtube_info.get("id"):
                    video_id = youtube_info["id"]
                    # Try maxresdefault first (1280x720), then hqdefault (480x360)
                    potential_urls = [
                        f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                        f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                        f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                    ]

                    # Test each URL to see which works
                    for test_url in potential_urls:
                        try:
                            response = requests.head(test_url, timeout=10)
                            if response.status_code == 200:
                                thumbnail_url = test_url
                                break
                        except:
                            continue

            if not thumbnail_url:
                logger.warning("No thumbnail URL found in YouTube metadata")
                return None

            # Download the thumbnail
            response = requests.get(thumbnail_url, timeout=30)
            response.raise_for_status()
            thumbnail_data = response.content

            if not thumbnail_data:
                logger.warning("Empty thumbnail data received")
                return None

            # Generate storage path (consistent with existing pattern)
            video_id = youtube_info.get("id", "unknown")
            storage_path = f"user_{user_id}/youtube_{video_id}/thumbnail.jpg"

            # Upload to storage
            upload_file(
                file_content=io.BytesIO(thumbnail_data),
                file_size=len(thumbnail_data),
                object_name=storage_path,
                content_type="image/jpeg",
            )

            logger.info(f"Successfully downloaded and uploaded YouTube thumbnail: {storage_path}")
            return storage_path

        except Exception as e:
            logger.error(f"Error downloading YouTube thumbnail: {e}")
            return None

    def process_youtube_url_sync(
        self,
        url: str,
        db: Session,
        user: User,
        media_file: MediaFile,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> MediaFile:
        """
        Process a YouTube URL by downloading the video and updating the MediaFile record (synchronous).

        Args:
            url: YouTube URL to process
            db: Database session
            user: User requesting the processing
            media_file: Pre-created MediaFile to update
            progress_callback: Optional callback for progress updates

        Returns:
            Updated MediaFile object

        Raises:
            HTTPException: If processing fails
        """
        if not self.is_valid_youtube_url(url):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid YouTube URL"
            )

        # Extract video info first to get YouTube ID
        logger.debug(f"Extracting video information for URL: {url}")
        video_info = self.extract_video_info(url)
        youtube_id = video_info.get("id")

        if not youtube_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not extract YouTube video ID",
            )

        # Create temporary directory for download in configured TEMP_DIR
        # This ensures the non-root container user has write permissions
        temp_dir = tempfile.mkdtemp(prefix="youtube_download_", dir=str(settings.TEMP_DIR))

        try:
            if progress_callback:
                progress_callback(15, "Preparing for download...")

            # Download the video using the already extracted info (this will use 20-60% progress range)
            logger.info(f"Starting YouTube download for URL: {url}")
            download_result = self.download_video(url, temp_dir, progress_callback)

            if progress_callback:
                progress_callback(65, "Video downloaded, processing metadata...")

            downloaded_file = download_result["file_path"]
            original_filename = download_result["filename"]
            youtube_info = video_info  # Use the info we already extracted

            # Get file stats
            file_stats = os.stat(downloaded_file)
            file_size = file_stats.st_size

            # Extract technical metadata from downloaded file first
            technical_metadata = self._extract_technical_metadata(downloaded_file)

            if progress_callback:
                progress_callback(75, "Uploading to storage...")

            # Generate unique storage path
            file_uuid = str(uuid.uuid4())
            file_extension = Path(downloaded_file).suffix
            storage_path = f"media/{user.id}/{file_uuid}{file_extension}"

            # Upload to MinIO
            logger.info(f"Uploading downloaded video to MinIO: {storage_path}")
            with open(downloaded_file, "rb") as f:
                file_content = io.BytesIO(f.read())
                upload_file(
                    file_content=file_content,
                    file_size=file_size,
                    object_name=storage_path,
                    content_type=technical_metadata.get("content_type", "video/mp4"),
                )

            if progress_callback:
                progress_callback(85, "Processing thumbnails...")

            # Download and upload YouTube thumbnail
            thumbnail_path = None
            try:
                thumbnail_path = self._download_youtube_thumbnail_sync(youtube_info, user.id)
                if thumbnail_path:
                    logger.debug(f"Successfully downloaded YouTube thumbnail: {thumbnail_path}")
                else:
                    logger.warning("Failed to download YouTube thumbnail, will generate from video")
                    # Fallback to generating thumbnail from video
                    thumbnail_path = generate_and_upload_thumbnail_sync(
                        user_id=user.id,
                        media_file_id=media_file.id,
                        video_path=downloaded_file,
                        timestamp=5.0,
                    )
            except Exception as e:
                logger.error(f"Error downloading YouTube thumbnail: {e}")
                # Fallback to generating thumbnail from video
                try:
                    thumbnail_path = generate_and_upload_thumbnail_sync(
                        user_id=user.id,
                        media_file_id=media_file.id,
                        video_path=downloaded_file,
                        timestamp=5.0,
                    )
                except Exception as fallback_error:
                    logger.error(f"Fallback thumbnail generation also failed: {fallback_error}")

            if progress_callback:
                progress_callback(95, "Finalizing and updating database...")

            # Prepare YouTube metadata
            youtube_metadata = self._prepare_youtube_metadata(url, youtube_info)

            # Update the existing MediaFile record
            media_file.filename = youtube_info.get("title", original_filename)[:255]  # Limit length
            media_file.storage_path = storage_path
            media_file.file_size = file_size
            media_file.content_type = technical_metadata.get("content_type", "video/mp4")
            media_file.duration = technical_metadata.get("duration") or youtube_info.get("duration")
            media_file.status = FileStatus.PENDING
            media_file.thumbnail_path = thumbnail_path

            # YouTube-specific metadata
            media_file.title = youtube_info.get("title")
            media_file.author = youtube_info.get("uploader")
            media_file.description = youtube_info.get("description")
            media_file.source_url = url  # Store original YouTube URL
            media_file.metadata_raw = youtube_metadata
            media_file.metadata_important = youtube_metadata

            # Technical metadata from extraction
            media_file.media_format = technical_metadata.get("format")
            media_file.codec = technical_metadata.get("video_codec")
            media_file.frame_rate = technical_metadata.get("frame_rate")
            media_file.resolution_width = technical_metadata.get("width")
            media_file.resolution_height = technical_metadata.get("height")
            media_file.audio_channels = technical_metadata.get("audio_channels")
            media_file.audio_sample_rate = technical_metadata.get("audio_sample_rate")

            # Save updated record to database
            db.commit()
            db.refresh(media_file)

            logger.info(f"Updated MediaFile record {media_file.id} for YouTube video")

            return media_file

        finally:
            # Clean up temporary files
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp directory {temp_dir}: {e}")

    def process_youtube_playlist_sync(
        self,
        url: str,
        db: Session,
        user: User,
        progress_callback: Optional[Callable[[int, str, dict], None]] = None,
    ) -> dict[str, Any]:
        """
        Process a YouTube playlist by extracting video list and creating placeholder MediaFile records.

        This method extracts the playlist information and creates MediaFile records for each video.
        Individual video downloads are handled by separate Celery tasks for parallel processing.

        Args:
            url: YouTube playlist URL
            db: Database session
            user: User requesting the processing
            progress_callback: Optional callback for progress updates (progress, message, data)

        Returns:
            Dictionary containing:
            - playlist_info: Playlist metadata
            - media_files: List of created MediaFile records
            - skipped_videos: List of videos that were skipped (duplicates or errors)

        Raises:
            HTTPException: If playlist extraction fails
        """
        if not self.is_playlist_url(url):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="URL is not a valid YouTube playlist",
            )

        # Extract playlist information
        logger.info(f"Extracting playlist information from: {url}")
        if progress_callback:
            progress_callback(10, "Extracting playlist information...", {})

        try:
            playlist_info = self.extract_playlist_info(url)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error extracting playlist info: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to extract playlist information: {str(e)}",
            ) from e

        video_count = playlist_info.get("video_count", 0)
        if video_count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Playlist is empty or contains no accessible videos",
            )

        logger.info(
            f"Found {video_count} videos in playlist: {playlist_info.get('playlist_title')}"
        )
        if progress_callback:
            progress_callback(
                20,
                f"Found {video_count} videos in playlist...",
                {"video_count": video_count, "playlist_title": playlist_info.get("playlist_title")},
            )

        # Create placeholder MediaFile records for each video
        created_media_files = []
        skipped_videos = []
        videos = playlist_info.get("videos", [])

        for idx, video_entry in enumerate(videos):
            try:
                video_id = video_entry.get("video_id")
                video_url = video_entry.get("url")
                video_title = video_entry.get("title", "Unknown")
                playlist_index = video_entry.get("playlist_index", idx + 1)

                # Calculate progress (20-90% range)
                progress = int(20 + (idx / video_count) * 70)
                if progress_callback:
                    progress_callback(
                        progress,
                        f"Processing video {idx + 1} of {video_count}: {video_title[:50]}...",
                        {
                            "current_video": idx + 1,
                            "total_videos": video_count,
                            "video_title": video_title,
                        },
                    )

                # Check for existing video with same YouTube ID
                from sqlalchemy import text

                existing_video = (
                    db.query(MediaFile)
                    .filter(
                        MediaFile.user_id == user.id,
                        text("metadata_raw->>'youtube_id' = :youtube_id"),
                    )
                    .params(youtube_id=video_id)
                    .first()
                )

                if existing_video:
                    logger.info(
                        f"Video already exists in library: {video_title} (YouTube ID: {video_id})"
                    )
                    skipped_videos.append(
                        {
                            "video_id": video_id,
                            "title": video_title,
                            "reason": "duplicate",
                            "existing_file_id": existing_video.id,
                        }
                    )
                    continue

                # Create placeholder MediaFile record
                placeholder_metadata = {
                    "youtube_id": video_id,
                    "youtube_url": video_url,
                    "title": video_title,
                    "processing": True,
                    "from_playlist": True,
                    "playlist_id": playlist_info.get("playlist_id"),
                    "playlist_title": playlist_info.get("playlist_title"),
                    "playlist_url": url,
                    "playlist_index": playlist_index,
                }

                media_file = MediaFile(
                    user_id=user.id,
                    filename=video_title[:255],
                    storage_path="",  # Will be set by background task
                    file_size=0,  # Will be set by background task
                    content_type="video/mp4",  # Default, will be updated
                    duration=video_entry.get("duration"),
                    status=FileStatus.PROCESSING,
                    title=video_title,
                    author=video_entry.get("uploader"),
                    source_url=video_url,
                    metadata_raw=placeholder_metadata,
                    metadata_important=placeholder_metadata,
                )

                db.add(media_file)
                db.flush()  # Flush to get the ID without committing

                created_media_files.append(media_file)
                logger.info(
                    f"Created placeholder MediaFile {media_file.id} for playlist video: {video_title}"
                )

            except Exception as e:
                logger.error(f"Error creating placeholder for video {video_title}: {e}")
                skipped_videos.append(
                    {
                        "video_id": video_entry.get("video_id"),
                        "title": video_entry.get("title", "Unknown"),
                        "reason": f"error: {str(e)}",
                    }
                )
                continue

        # Commit all placeholder records
        db.commit()

        # Refresh all created media files
        for media_file in created_media_files:
            db.refresh(media_file)

        if progress_callback:
            progress_callback(
                100,
                f"Playlist processing complete: {len(created_media_files)} videos queued",
                {
                    "created_count": len(created_media_files),
                    "skipped_count": len(skipped_videos),
                },
            )

        logger.info(
            f"Playlist processing complete: {len(created_media_files)} videos created, "
            f"{len(skipped_videos)} skipped"
        )

        return {
            "playlist_info": playlist_info,
            "media_files": created_media_files,
            "skipped_videos": skipped_videos,
            "created_count": len(created_media_files),
            "skipped_count": len(skipped_videos),
            "total_videos": video_count,
        }
