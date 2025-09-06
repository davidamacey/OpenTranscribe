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

import httpx
import yt_dlp
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session

from app.models.media import FileStatus
from app.models.media import MediaFile
from app.models.user import User
from app.services.minio_service import upload_file
from app.tasks.transcription import transcribe_audio_task
from app.utils.thumbnail import generate_and_upload_thumbnail

logger = logging.getLogger(__name__)

# YouTube URL validation regex
YOUTUBE_URL_PATTERN = re.compile(
    r'^https?://(www\.)?(youtube\.com/(watch\?v=|embed/|v/)|youtu\.be/)[\w\-_]+.*$'
)


class YouTubeService:
    """Service for processing YouTube videos."""

    def __init__(self):
        pass

    def is_valid_youtube_url(self, url: str) -> bool:
        """
        Validate if URL is a valid YouTube URL.

        Args:
            url: URL to validate

        Returns:
            True if valid YouTube URL, False otherwise
        """
        return bool(YOUTUBE_URL_PATTERN.match(url.strip()))

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
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info
        except Exception as e:
            logger.error(f"Error extracting video info from {url}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to extract video information: {str(e)}"
            )

    def download_video(self, url: str, output_path: str) -> dict[str, Any]:
        """
        Download video from YouTube URL.

        Args:
            url: YouTube URL
            output_path: Directory to save downloaded file

        Returns:
            Dictionary with file path, filename, and video info

        Raises:
            HTTPException: If download fails
        """
        # Configure yt-dlp options for highest quality with web-compatible output
        ydl_opts = {
            # Download best H.264 quality for maximum browser compatibility
            # Prefer H.264 video codec over AV1 to ensure playback works across all browsers
            'format': 'bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/bestvideo[vcodec*=h264][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
            'restrictfilenames': True,  # Avoid special characters in filename
            'no_warnings': False,
            'extractaudio': False,
            'embed_subs': True,  # Embed subtitles if available
            'writesubtitles': False,  # Don't write separate subtitle files
            'writeautomaticsub': False,  # Don't write auto-generated subs
            'ignoreerrors': False,
            'no_playlist': True,  # Only download single video
            'max_filesize': 15 * 1024 * 1024 * 1024,  # 15GB limit (matches upload limit)
            # Ensure web-compatible MP4 output
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first
                info = ydl.extract_info(url, download=False)

                # Check duration (optional limit)
                duration = info.get('duration')
                if duration and duration > 14400:  # 4 hours limit
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Video is too long. Maximum duration is 4 hours."
                    )

                # Download the video
                ydl.download([url])

                # Find the downloaded file
                title = info.get('title', 'video')
                ext = info.get('ext', 'mp4')

                # Clean title for filename
                clean_title = re.sub(r'[^\w\-_\.]', '_', title)[:100]  # Limit length
                expected_filename = f"{clean_title}.{ext}"
                downloaded_file = os.path.join(output_path, expected_filename)

                # Find actual downloaded file (yt-dlp might change the name)
                if not os.path.exists(downloaded_file):
                    # Look for any video file in the directory
                    for file in os.listdir(output_path):
                        if file.endswith(('.mp4', '.webm', '.mkv', '.avi')):
                            downloaded_file = os.path.join(output_path, file)
                            break
                    else:
                        raise FileNotFoundError("Downloaded file not found")

                return {
                    'file_path': downloaded_file,
                    'filename': os.path.basename(downloaded_file),
                    'info': info
                }

        except yt_dlp.DownloadError as e:
            logger.error(f"yt-dlp download error for {url}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to download video: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Unexpected error downloading {url}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error during download: {str(e)}"
            )

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
            from app.tasks.transcription.metadata_extractor import (
                extract_media_metadata,
            )
            from app.tasks.transcription.metadata_extractor import (
                get_important_metadata,
            )

            raw_metadata = extract_media_metadata(file_path)
            if raw_metadata:
                important_metadata = get_important_metadata(raw_metadata)

                # Convert to format expected by MediaFile model
                return {
                    'content_type': raw_metadata.get('File:MIMEType', 'video/mp4'),
                    'format': important_metadata.get('FileType'),
                    'video_codec': important_metadata.get('VideoCodec'),
                    'width': important_metadata.get('VideoWidth'),
                    'height': important_metadata.get('VideoHeight'),
                    'frame_rate': important_metadata.get('VideoFrameRate'),
                    'audio_channels': important_metadata.get('AudioChannels'),
                    'audio_sample_rate': important_metadata.get('AudioSampleRate'),
                    'duration': important_metadata.get('Duration'),
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
            if '/' in frame_rate_str:
                numerator, denominator = frame_rate_str.split('/')
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
            format_info = probe.get('format', {})
            video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
            audio_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'audio'), None)

            metadata = {
                'content_type': 'video/mp4',  # Default
                'format': format_info.get('format_name'),
                'duration': float(format_info.get('duration', 0)),
            }

            if video_stream:
                metadata.update({
                    'video_codec': video_stream.get('codec_name'),
                    'width': video_stream.get('width'),
                    'height': video_stream.get('height'),
                    'frame_rate': self._safe_frame_rate_eval(video_stream.get('r_frame_rate')) if video_stream.get('r_frame_rate') else None
                })

            if audio_stream:
                metadata.update({
                    'audio_channels': audio_stream.get('channels'),
                    'audio_sample_rate': audio_stream.get('sample_rate'),
                })

            return metadata

        except Exception as e:
            logger.warning(f"Failed to extract basic metadata: {e}")
            return {'content_type': 'video/mp4'}

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
            'source': 'youtube',
            'original_url': url,
            'youtube_id': youtube_info.get('id'),
            'youtube_title': youtube_info.get('title'),
            'youtube_description': youtube_info.get('description'),
            'youtube_uploader': youtube_info.get('uploader'),
            'youtube_upload_date': youtube_info.get('upload_date'),
            'youtube_duration': youtube_info.get('duration'),
            'youtube_view_count': youtube_info.get('view_count'),
            'youtube_like_count': youtube_info.get('like_count'),
            'youtube_thumbnail': youtube_info.get('thumbnail'),
            'youtube_tags': youtube_info.get('tags', []),
            'youtube_categories': youtube_info.get('categories', []),
        }

    async def _download_youtube_thumbnail(
        self,
        youtube_info: dict[str, Any],
        user_id: int
    ) -> str:
        """
        Download YouTube thumbnail and upload to storage.

        Args:
            youtube_info: YouTube metadata from yt-dlp
            user_id: User ID for storage path

        Returns:
            Storage path of uploaded thumbnail or None if failed
        """
        try:
            # Get the best thumbnail URL from YouTube info
            thumbnail_url = None
            thumbnails = youtube_info.get('thumbnails', [])

            if not thumbnails and youtube_info.get('thumbnail'):
                # Fallback to single thumbnail URL
                thumbnail_url = youtube_info.get('thumbnail')
            else:
                # Find the highest quality thumbnail
                # YouTube provides multiple thumbnails, we want the highest resolution
                max_width = 0
                for thumb in thumbnails:
                    width = thumb.get('width', 0)
                    if width > max_width and thumb.get('url'):
                        max_width = width
                        thumbnail_url = thumb['url']

                # Fallback to maxresdefault or hqdefault
                if not thumbnail_url and youtube_info.get('id'):
                    video_id = youtube_info['id']
                    # Try maxresdefault first (1280x720), then hqdefault (480x360)
                    potential_urls = [
                        f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                        f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                        f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                    ]

                    # Test each URL to see which works
                    for test_url in potential_urls:
                        try:
                            async with httpx.AsyncClient() as client:
                                response = await client.head(test_url, timeout=10)
                                if response.status_code == 200:
                                    thumbnail_url = test_url
                                    break
                        except:
                            continue

            if not thumbnail_url:
                logger.warning("No thumbnail URL found in YouTube metadata")
                return None

            # Download the thumbnail
            async with httpx.AsyncClient() as client:
                response = await client.get(thumbnail_url, timeout=30)
                response.raise_for_status()
                thumbnail_data = response.content

            if not thumbnail_data:
                logger.warning("Empty thumbnail data received")
                return None

            # Generate storage path (consistent with existing pattern)
            video_id = youtube_info.get('id', 'unknown')
            storage_path = f"user_{user_id}/youtube_{video_id}/thumbnail.jpg"

            # Upload to storage
            upload_file(
                file_content=io.BytesIO(thumbnail_data),
                file_size=len(thumbnail_data),
                object_name=storage_path,
                content_type="image/jpeg"
            )

            logger.info(f"Successfully downloaded and uploaded YouTube thumbnail: {storage_path}")
            return storage_path

        except Exception as e:
            logger.error(f"Error downloading YouTube thumbnail: {e}")
            return None

    async def process_youtube_url(
        self,
        url: str,
        db: Session,
        user: User
    ) -> MediaFile:
        """
        Process a YouTube URL by downloading the video and creating a MediaFile record.

        Args:
            url: YouTube URL to process
            db: Database session
            user: User requesting the processing

        Returns:
            Created MediaFile object

        Raises:
            HTTPException: If processing fails
        """
        if not self.is_valid_youtube_url(url):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid YouTube URL"
            )

        # Create temporary directory for download
        temp_dir = tempfile.mkdtemp(prefix="youtube_download_")

        try:
            # Download the video
            logger.info(f"Starting YouTube download for URL: {url}")
            download_result = self.download_video(url, temp_dir)

            downloaded_file = download_result['file_path']
            original_filename = download_result['filename']
            youtube_info = download_result['info']

            # Get file stats
            file_stats = os.stat(downloaded_file)
            file_size = file_stats.st_size

            # Extract technical metadata from downloaded file first
            technical_metadata = self._extract_technical_metadata(downloaded_file)

            # Generate unique storage path
            file_uuid = str(uuid.uuid4())
            file_extension = Path(downloaded_file).suffix
            storage_path = f"media/{user.id}/{file_uuid}{file_extension}"

            # Upload to MinIO
            logger.info(f"Uploading downloaded video to MinIO: {storage_path}")
            with open(downloaded_file, 'rb') as f:
                file_content = io.BytesIO(f.read())
                upload_file(
                    file_content=file_content,
                    file_size=file_size,
                    object_name=storage_path,
                    content_type=technical_metadata.get('content_type', 'video/mp4')
                )

            # Download and upload YouTube thumbnail
            thumbnail_path = None
            try:
                thumbnail_path = await self._download_youtube_thumbnail(
                    youtube_info, user.id
                )
                if thumbnail_path:
                    logger.info(f"Successfully downloaded YouTube thumbnail: {thumbnail_path}")
                else:
                    logger.warning("Failed to download YouTube thumbnail, will generate from video")
                    # Fallback to generating thumbnail from video
                    thumbnail_path = await generate_and_upload_thumbnail(
                        user_id=user.id,
                        media_file_id=0,  # Will be updated after DB save
                        video_path=downloaded_file,
                        timestamp=5.0
                    )
            except Exception as e:
                logger.error(f"Error downloading YouTube thumbnail: {e}")
                # Fallback to generating thumbnail from video
                try:
                    thumbnail_path = await generate_and_upload_thumbnail(
                        user_id=user.id,
                        media_file_id=0,
                        video_path=downloaded_file,
                        timestamp=5.0
                    )
                except Exception as fallback_error:
                    logger.error(f"Fallback thumbnail generation also failed: {fallback_error}")

            # Prepare YouTube metadata
            youtube_metadata = self._prepare_youtube_metadata(url, youtube_info)

            # Create MediaFile record
            media_file = MediaFile(
                user_id=user.id,
                filename=youtube_info.get('title', original_filename)[:255],  # Limit length
                storage_path=storage_path,
                file_size=file_size,
                content_type=technical_metadata.get('content_type', 'video/mp4'),
                duration=technical_metadata.get('duration') or youtube_info.get('duration'),
                status=FileStatus.PENDING,
                thumbnail_path=thumbnail_path,  # Add thumbnail path

                # YouTube-specific metadata
                title=youtube_info.get('title'),
                author=youtube_info.get('uploader'),
                description=youtube_info.get('description'),
                source_url=url,  # Store original YouTube URL
                metadata_raw=youtube_metadata,
                metadata_important=youtube_metadata,

                # Technical metadata from extraction
                media_format=technical_metadata.get('format'),
                codec=technical_metadata.get('video_codec'),
                frame_rate=technical_metadata.get('frame_rate'),
                resolution_width=technical_metadata.get('width'),
                resolution_height=technical_metadata.get('height'),
                audio_channels=technical_metadata.get('audio_channels'),
                audio_sample_rate=technical_metadata.get('audio_sample_rate'),
            )

            # Save to database
            db.add(media_file)
            db.commit()
            db.refresh(media_file)

            logger.info(f"Created MediaFile record {media_file.id} for YouTube video")

            # Thumbnail is already properly set from YouTube's official thumbnail
            # No need to regenerate with media file ID since we're using YouTube video ID

            # Start transcription task
            try:
                transcribe_audio_task.delay(media_file.id)
                logger.info(f"Started transcription task for MediaFile {media_file.id}")
            except Exception as e:
                logger.error(f"Failed to start transcription task: {e}")
                # Don't fail the whole process if task scheduling fails

            return media_file

        finally:
            # Clean up temporary files
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.info(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp directory {temp_dir}: {e}")
