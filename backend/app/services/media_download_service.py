"""
Media download service for downloading and processing media from various platforms.

This service handles all media URL-related operations including URL validation,
video downloading, metadata extraction, and integration with the media processing pipeline.
Supports YouTube, Vimeo, Twitter/X, TikTok, and 1800+ other platforms via yt-dlp.
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
from app.services.protected_media_providers import PROTECTED_MEDIA_PROVIDERS
from app.services.protected_media_providers import ProtectedMediaProvider
from app.utils.thumbnail import generate_and_upload_thumbnail_sync

logger = logging.getLogger(__name__)

# Authentication and access error patterns with user-friendly messages
AUTH_ERROR_PATTERNS = {
    "logged-in": "requires a logged-in account",
    "log in": "requires login",
    "sign in": "requires sign-in",
    "credentials": "requires authentication credentials",
    "cookies": "requires browser cookies for authentication",
    "private": "is private or restricted",
    "age": "is age-restricted and requires verification",
    "geo": "is not available in your region (geo-restricted)",
    "removed": "has been removed or is unavailable",
    "unavailable": "is currently unavailable",
    "blocked": "is blocked or restricted",
    "premium": "requires a premium subscription",
    "members only": "is members-only content",
    "subscriber": "requires a subscription",
}

# Platform-specific guidance messages
PLATFORM_GUIDANCE = {
    "vimeo": "Most Vimeo videos require authentication. Try YouTube or Dailymotion instead.",
    "instagram": "Instagram videos typically require login. Try a different platform.",
    "facebook": "Facebook videos often require authentication.",
    "twitter": "Some Twitter/X videos may require login to access.",
    "x": "Some X (Twitter) videos may require login to access.",
    "tiktok": "Some TikTok videos may be region-restricted or require authentication.",
    "linkedin": "LinkedIn videos require authentication.",
    "patreon": "Patreon videos require a subscription to access.",
    "onlyfans": "OnlyFans content requires a subscription.",
    "twitch": "Some Twitch VODs may be subscriber-only.",
}

# Recommended platforms for public video downloads (YouTube is most reliable)
RECOMMENDED_PLATFORMS = ["YouTube", "Dailymotion", "Twitter/X"]


def _detect_auth_error(error_message: str) -> tuple[bool, str]:
    """
    Detect if an error message indicates an authentication-related issue.

    Args:
        error_message: The error message from yt-dlp

    Returns:
        Tuple of (is_auth_error, matched_reason)
    """
    error_lower = error_message.lower()
    for pattern, reason in AUTH_ERROR_PATTERNS.items():
        if pattern in error_lower:
            return True, reason
    return False, ""


def _get_platform_from_error(error_message: str) -> str:
    """
    Try to extract platform name from error message or URL in the error.

    Args:
        error_message: The error message from yt-dlp

    Returns:
        Platform name or empty string
    """
    error_lower = error_message.lower()

    # Check for known platform names in the error
    platforms = [
        "vimeo",
        "instagram",
        "facebook",
        "twitter",
        "x.com",
        "tiktok",
        "linkedin",
        "patreon",
        "twitch",
        "youtube",
    ]
    for platform in platforms:
        if platform in error_lower:
            # Normalize x.com to twitter
            return "twitter" if platform == "x.com" else platform
    return ""


def create_user_friendly_error(error_message: str, url: str = "") -> str:
    """
    Create a user-friendly error message from a yt-dlp error.

    Detects authentication-related errors and provides helpful guidance
    about platform limitations.

    Args:
        error_message: The raw error message from yt-dlp
        url: The original URL (optional, for platform detection)

    Returns:
        User-friendly error message with guidance
    """
    is_auth_error, auth_reason = _detect_auth_error(error_message)

    # Try to detect platform from error message or URL
    platform = _get_platform_from_error(error_message)
    if not platform and url:
        platform = _get_platform_from_error(url)

    if is_auth_error:
        # Build user-friendly message
        if platform:
            platform_title = platform.title() if platform != "x" else "X (Twitter)"
            guidance = PLATFORM_GUIDANCE.get(platform.lower(), "")

            if guidance:
                return (
                    f"This {platform_title} video {auth_reason}. {guidance} "
                    f"For best results, try {', '.join(RECOMMENDED_PLATFORMS)}."
                )
            return (
                f"This {platform_title} video {auth_reason}. "
                f"For best results, try publicly accessible videos on "
                f"{', '.join(RECOMMENDED_PLATFORMS)}."
            )

        # Generic auth error without platform
        return (
            f"This video {auth_reason}. Some platforms restrict video downloads "
            f"to authenticated users. For best results, try publicly accessible "
            f"videos on {', '.join(RECOMMENDED_PLATFORMS)}."
        )

    # Not an auth error - return the original message but cleaned up
    # Remove common yt-dlp prefixes
    cleaned = error_message
    prefixes_to_remove = [
        "ERROR: ",
        "DownloadError: ",
        "[download] ",
        "[generic] ",
    ]
    for prefix in prefixes_to_remove:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]

    return cleaned


# Generic URL pattern - accepts any HTTP/HTTPS URL
GENERIC_URL_PATTERN = re.compile(r"^https?://.+$")

# YouTube URL validation regex - supports both videos and playlists
YOUTUBE_URL_PATTERN = re.compile(
    r"^https?://(www\.)?(youtube\.com/(watch\?v=|embed/|v/|playlist\?list=)|youtu\.be/)[\w\-_]+.*$"
)

# YouTube playlist URL validation regex
YOUTUBE_PLAYLIST_PATTERN = re.compile(
    r"^https?://(www\.)?youtube\.com/playlist\?list=([\w\-_]+).*$"
)


def _find_downloaded_file(output_path: str, clean_title: str, ext: str) -> str:
    """
    Find the downloaded file in the output directory.

    Args:
        output_path: Directory where file was downloaded
        clean_title: Cleaned title for expected filename
        ext: Expected file extension

    Returns:
        Path to the downloaded file

    Raises:
        FileNotFoundError: If no video file is found
    """
    expected_filename = f"{clean_title}.{ext}"
    downloaded_file = os.path.join(output_path, expected_filename)

    if os.path.exists(downloaded_file):
        return downloaded_file

    # Look for any video file in the directory (yt-dlp might change the name)
    for file in os.listdir(output_path):
        if file.endswith((".mp4", ".webm", ".mkv", ".avi")):
            return os.path.join(output_path, file)

    raise FileNotFoundError("Downloaded file not found")


def _resolve_thumbnail_url(media_info: dict[str, Any]) -> Optional[str]:
    """
    Resolve the best thumbnail URL from media metadata.

    Args:
        media_info: Media metadata from yt-dlp

    Returns:
        Best available thumbnail URL or None
    """
    thumbnails = media_info.get("thumbnails", [])

    # Fallback to single thumbnail URL if no thumbnails list
    if not thumbnails:
        return media_info.get("thumbnail")

    # Find the highest quality thumbnail
    max_width = 0
    thumbnail_url = None
    for thumb in thumbnails:
        width = thumb.get("width", 0)
        if width > max_width and thumb.get("url"):
            max_width = width
            thumbnail_url = thumb["url"]

    if thumbnail_url:
        return thumbnail_url

    # Fallback to standard YouTube thumbnail URLs if it's a YouTube video
    return _get_fallback_thumbnail_url(media_info.get("id"), media_info.get("extractor", ""))


def _get_fallback_thumbnail_url(video_id: Optional[str], extractor: str) -> Optional[str]:
    """
    Try standard thumbnail URLs as fallback for known platforms.

    Args:
        video_id: Video ID
        extractor: Platform extractor name

    Returns:
        Working thumbnail URL or None
    """
    if not video_id:
        return None

    # YouTube-specific fallback URLs
    if "youtube" in extractor.lower():
        potential_urls = [
            f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
        ]

        for test_url in potential_urls:
            try:
                response = requests.head(test_url, timeout=10)
                if response.status_code == 200:
                    return test_url
            except requests.exceptions.RequestException as e:
                logger.debug(f"Thumbnail URL test failed for {test_url}: {e}")

    return None


def _get_thumbnail_with_fallback(
    media_service: "MediaDownloadService",
    media_info: dict[str, Any],
    user_id: int,
    media_file_id: int,
    video_path: str,
) -> Optional[str]:
    """
    Get thumbnail from media source or generate from video as fallback.

    Args:
        media_service: MediaDownloadService instance
        media_info: Media metadata
        user_id: User ID
        media_file_id: Media file ID
        video_path: Path to downloaded video

    Returns:
        Thumbnail storage path or None
    """
    try:
        thumbnail_path = media_service._download_media_thumbnail_sync(media_info, user_id)
        if thumbnail_path:
            logger.debug(f"Successfully downloaded media thumbnail: {thumbnail_path}")
            return thumbnail_path
        logger.warning("Failed to download media thumbnail, will generate from video")
    except Exception as e:
        logger.error(f"Error downloading media thumbnail: {e}")

    # Fallback to generating thumbnail from video
    try:
        return generate_and_upload_thumbnail_sync(
            user_id=user_id,
            media_file_id=media_file_id,
            video_path=video_path,
            timestamp=5.0,
        )
    except Exception as fallback_error:
        logger.error(f"Fallback thumbnail generation also failed: {fallback_error}")
        return None


def _check_existing_youtube_video(db: Session, user_id: int, video_id: str) -> Optional[MediaFile]:
    """
    Check if a YouTube video already exists in the user's library.

    Args:
        db: Database session
        user_id: User ID
        video_id: YouTube video ID

    Returns:
        Existing MediaFile if found, None otherwise
    """
    from sqlalchemy import text

    return (
        db.query(MediaFile)
        .filter(
            MediaFile.user_id == user_id,
            text("metadata_raw->>'youtube_id' = :youtube_id"),
        )
        .params(youtube_id=video_id)
        .first()
    )


def _process_playlist_videos(
    db: Session,
    user_id: int,
    videos: list[dict[str, Any]],
    playlist_info: dict[str, Any],
    playlist_url: str,
    video_count: int,
    progress_callback: Optional[Callable[[int, str, dict], None]] = None,
) -> tuple[list[MediaFile], list[dict[str, Any]]]:
    """
    Process playlist videos and create placeholders.

    Args:
        db: Database session
        user_id: User ID
        videos: List of video entries from playlist
        playlist_info: Playlist metadata
        playlist_url: Original playlist URL
        video_count: Total video count for progress
        progress_callback: Optional progress callback

    Returns:
        Tuple of (created_media_files, skipped_videos)
    """
    created_media_files = []
    skipped_videos = []

    for idx, video_entry in enumerate(videos):
        video_id = video_entry.get("video_id")
        video_title = video_entry.get("title", "Unknown")

        # Report progress
        if progress_callback:
            progress = int(20 + (idx / video_count) * 70)
            progress_callback(
                progress,
                f"Processing video {idx + 1} of {video_count}: {video_title[:50]}...",
                {"current_video": idx + 1, "total_videos": video_count, "video_title": video_title},
            )

        # Check for existing video
        existing_video = _check_existing_youtube_video(db, user_id, video_id)
        if existing_video:
            logger.info(f"Video already exists in library: {video_title} (YouTube ID: {video_id})")
            skipped_videos.append(
                {
                    "video_id": video_id,
                    "title": video_title,
                    "reason": "duplicate",
                    "existing_file_id": existing_video.id,
                }
            )
            continue

        # Create placeholder
        try:
            video_entry["playlist_index"] = video_entry.get("playlist_index", idx + 1)
            media_file = _create_playlist_video_placeholder(
                db, user_id, video_entry, playlist_info, playlist_url
            )
            created_media_files.append(media_file)
            logger.info(
                f"Created placeholder MediaFile {media_file.id} for playlist video: {video_title}"
            )
        except Exception as e:
            logger.error(f"Error creating placeholder for video {video_title}: {e}")
            skipped_videos.append(
                {
                    "video_id": video_id,
                    "title": video_title,
                    "reason": f"error: {str(e)}",
                }
            )

    return created_media_files, skipped_videos


def _create_playlist_video_placeholder(
    db: Session,
    user_id: int,
    video_entry: dict[str, Any],
    playlist_info: dict[str, Any],
    playlist_url: str,
) -> MediaFile:
    """
    Create a placeholder MediaFile for a playlist video.

    Args:
        db: Database session
        user_id: User ID
        video_entry: Video entry from playlist
        playlist_info: Playlist metadata
        playlist_url: Original playlist URL

    Returns:
        Created MediaFile
    """
    video_id = video_entry.get("video_id")
    video_url = video_entry.get("url")
    video_title = video_entry.get("title", "Unknown")
    playlist_index = video_entry.get("playlist_index", 1)

    placeholder_metadata = {
        "youtube_id": video_id,
        "youtube_url": video_url,
        "title": video_title,
        "processing": True,
        "from_playlist": True,
        "playlist_id": playlist_info.get("playlist_id"),
        "playlist_title": playlist_info.get("playlist_title"),
        "playlist_url": playlist_url,
        "playlist_index": playlist_index,
    }

    media_file = MediaFile(
        user_id=user_id,
        filename=video_title[:255],
        storage_path="",
        file_size=0,
        content_type="video/mp4",
        duration=video_entry.get("duration"),
        status=FileStatus.PROCESSING,
        title=video_title,
        author=video_entry.get("uploader"),
        source_url=video_url,
        metadata_raw=placeholder_metadata,
        metadata_important=placeholder_metadata,
    )

    db.add(media_file)
    db.flush()

    return media_file


def _update_media_file_with_download_data(
    media_file: MediaFile,
    media_info: dict[str, Any],
    media_metadata: dict[str, Any],
    technical_metadata: dict[str, Any],
    storage_path: str,
    file_size: int,
    thumbnail_path: Optional[str],
    original_filename: str,
    source_url: str,
) -> None:
    """
    Update MediaFile record with downloaded media and technical metadata.

    Args:
        media_file: MediaFile to update
        media_info: Media video info from yt-dlp
        media_metadata: Prepared media metadata dict
        technical_metadata: Technical metadata from file
        storage_path: Storage path in MinIO
        file_size: File size in bytes
        thumbnail_path: Path to thumbnail
        original_filename: Original filename
        source_url: Original media URL
    """
    media_file.filename = media_info.get("title", original_filename)[:255]
    media_file.storage_path = storage_path
    media_file.file_size = file_size
    media_file.content_type = technical_metadata.get("content_type", "video/mp4")
    media_file.duration = technical_metadata.get("duration") or media_info.get("duration")
    media_file.status = FileStatus.PENDING
    media_file.thumbnail_path = thumbnail_path

    # Media-specific metadata
    media_file.title = media_info.get("title")
    media_file.author = media_info.get("uploader")
    media_file.description = media_info.get("description")
    media_file.source_url = source_url
    media_file.metadata_raw = media_metadata
    media_file.metadata_important = media_metadata

    # Technical metadata from extraction
    media_file.media_format = technical_metadata.get("format")
    media_file.codec = technical_metadata.get("video_codec")
    media_file.frame_rate = technical_metadata.get("frame_rate")
    media_file.resolution_width = technical_metadata.get("width")
    media_file.resolution_height = technical_metadata.get("height")
    media_file.audio_channels = technical_metadata.get("audio_channels")
    media_file.audio_sample_rate = technical_metadata.get("audio_sample_rate")


class MediaDownloadService:
    """Service for processing media from various platforms.

    Uses yt-dlp for public platforms and a pluggable registry of
    ProtectedMediaProvider implementations for authenticated sites
    (for example, internal corporate media portals).
    """

    def __init__(self):
        pass

    def _get_protected_provider(self, url: str) -> Optional[ProtectedMediaProvider]:
        """Return a protected media provider that can handle this URL, if any."""
        for provider in PROTECTED_MEDIA_PROVIDERS:
            try:
                if provider.can_handle(url):
                    return provider
            except Exception as e:
                logger.warning(
                    f"Protected media provider {provider.__class__.__name__} "
                    f"failed in can_handle for {url}: {e}"
                )
        return None

    def is_valid_media_url(self, url: str) -> bool:
        """
        Validate if URL is a valid media URL (any HTTP/HTTPS URL).

        Args:
            url: URL to validate

        Returns:
            True if valid media URL, False otherwise
        """
        return bool(GENERIC_URL_PATTERN.match(url.strip()))

    def is_youtube_url(self, url: str) -> bool:
        """
        Check if URL is a YouTube URL (for backward compatibility and special handling).

        Args:
            url: URL to check

        Returns:
            True if YouTube URL, False otherwise
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

    def extract_video_info(
        self,
        url: str,
        media_username: Optional[str] = None,
        media_password: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Extract video metadata without downloading.

        For generic public platforms this uses yt-dlp. For URLs handled by
        a ProtectedMediaProvider, it delegates to that provider's custom API-based logic.

        Args:
            url: Media URL
            media_username: Optional username for protected media sources
            media_password: Optional password for protected media sources
            
        Returns:
            Dictionary with video information

        Raises:
            HTTPException: If unable to extract video information
        """
        # Try protected media providers first (authenticated corporate sites, etc.)
        provider = self._get_protected_provider(url)
        if provider is not None:
            return provider.extract_info(
                url, username=media_username, password=media_password
            )

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info
        except yt_dlp.DownloadError as e:
            error_msg = str(e)
            logger.error(f"Error extracting video info from {url}: {error_msg}")
            # Create user-friendly error message
            user_friendly_error = create_user_friendly_error(error_msg, url)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to extract video information: {user_friendly_error}",
            ) from e
        except Exception as e:
            logger.error(f"Error extracting video info from {url}: {e}")
            user_friendly_error = create_user_friendly_error(str(e), url)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to extract video information: {user_friendly_error}",
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
        media_username: Optional[str] = None,
        media_password: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Download video from media URL.

        For public platforms uses yt-dlp; for URLs recognized by a
        ProtectedMediaProvider it delegates to that provider.

        Args:
            url: Media URL
            output_path: Directory to save downloaded file
            progress_callback: Optional callback for progress updates

        Returns:
            Dictionary with file path, filename, and video info

        Raises:
            HTTPException: If download fails
        """

        # First, try pluggable protected-media providers
        provider = self._get_protected_provider(url)
        if provider is not None:
            return provider.download(
                url,
                output_path,
                progress_callback=progress_callback,
                username=media_username,
                password=media_password,
            )

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
                clean_title = re.sub(r"[^\w\-_\.]", "_", title)[:100]
                downloaded_file = _find_downloaded_file(output_path, clean_title, ext)

                return {
                    "file_path": downloaded_file,
                    "filename": os.path.basename(downloaded_file),
                    "info": info,
                }

        except yt_dlp.DownloadError as e:
            error_msg = str(e)
            logger.error(f"yt-dlp download error for {url}: {error_msg}")
            # Create user-friendly error message
            user_friendly_error = create_user_friendly_error(error_msg, url)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to download video: {user_friendly_error}",
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error downloading {url}: {e}")
            user_friendly_error = create_user_friendly_error(str(e), url)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error during download: {user_friendly_error}",
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
            import ffmpeg  # type: ignore[import-untyped]

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

    def _prepare_media_metadata(self, url: str, media_info: dict[str, Any]) -> dict[str, Any]:
        """
        Prepare media-specific metadata for storage.

        Args:
            url: Original media URL
            media_info: Information extracted from yt-dlp

        Returns:
            Dictionary with media metadata
        """
        # Detect the source platform dynamically
        source = media_info.get("extractor", "unknown").lower()

        # Build metadata with platform-agnostic keys plus platform-specific ones
        metadata = {
            "source": source,
            "original_url": url,
            "video_id": media_info.get("id"),
            "title": media_info.get("title"),
            "description": media_info.get("description"),
            "uploader": media_info.get("uploader"),
            "upload_date": media_info.get("upload_date"),
            "duration": media_info.get("duration"),
            "view_count": media_info.get("view_count"),
            "like_count": media_info.get("like_count"),
            "thumbnail": media_info.get("thumbnail"),
            "tags": media_info.get("tags", []),
            "categories": media_info.get("categories", []),
        }

        # Add YouTube-specific fields for backward compatibility
        if "youtube" in source:
            metadata.update(
                {
                    "youtube_id": media_info.get("id"),
                    "youtube_title": media_info.get("title"),
                    "youtube_description": media_info.get("description"),
                    "youtube_uploader": media_info.get("uploader"),
                    "youtube_upload_date": media_info.get("upload_date"),
                    "youtube_duration": media_info.get("duration"),
                    "youtube_view_count": media_info.get("view_count"),
                    "youtube_like_count": media_info.get("like_count"),
                    "youtube_thumbnail": media_info.get("thumbnail"),
                    "youtube_tags": media_info.get("tags", []),
                    "youtube_categories": media_info.get("categories", []),
                }
            )

        return metadata

    def _download_media_thumbnail_sync(self, media_info: dict[str, Any], user_id: int) -> str:
        """
        Download media thumbnail and upload to storage (synchronous version).

        Args:
            media_info: Media metadata from yt-dlp
            user_id: User ID for storage path

        Returns:
            Storage path of uploaded thumbnail or None if failed
        """
        try:
            thumbnail_url = _resolve_thumbnail_url(media_info)

            if not thumbnail_url:
                logger.warning("No thumbnail URL found in media metadata")
                return None

            # Download the thumbnail
            response = requests.get(thumbnail_url, timeout=30)
            response.raise_for_status()
            thumbnail_data = response.content

            if not thumbnail_data:
                logger.warning("Empty thumbnail data received")
                return None

            # Generate storage path and upload
            video_id = media_info.get("id", "unknown")
            source = media_info.get("extractor", "media").lower()
            storage_path = f"user_{user_id}/{source}_{video_id}/thumbnail.jpg"

            upload_file(
                file_content=io.BytesIO(thumbnail_data),
                file_size=len(thumbnail_data),
                object_name=storage_path,
                content_type="image/jpeg",
            )

            logger.info(f"Successfully downloaded and uploaded media thumbnail: {storage_path}")
            return storage_path

        except Exception as e:
            logger.error(f"Error downloading media thumbnail: {e}")
            return None

    def process_media_url_sync(
        self,
        url: str,
        db: Session,
        user: User,
        media_file: MediaFile,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        media_username: Optional[str] = None,
        media_password: Optional[str] = None,
    ) -> MediaFile:
        """
        Process a media URL by downloading the video and updating the MediaFile record (synchronous).

        Args:
            url: Media URL to process
            db: Database session
            user: User requesting the processing
            media_file: Pre-created MediaFile to update
            progress_callback: Optional callback for progress updates

        Returns:
            Updated MediaFile object

        Raises:
            HTTPException: If processing fails
        """
        if not self.is_valid_media_url(url):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid media URL")

        # Extract video info first to get video ID
        logger.debug(f"Extracting video information for URL: {url}")
        video_info = self.extract_video_info(
            url,
            media_username=media_username,
            media_password=media_password,
        )
        video_id = video_info.get("id")

        if not video_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not extract video ID from URL",
            )

        # Create temporary directory for download in configured TEMP_DIR
        # This ensures the non-root container user has write permissions
        temp_dir = tempfile.mkdtemp(prefix="media_download_", dir=str(settings.TEMP_DIR))

        try:
            if progress_callback:
                progress_callback(15, "Preparing for download...")

            # Download the video using the already extracted info (this will use 20-60% progress range)
            logger.info(f"Starting media download for URL: {url}")
            download_result = self.download_video(
                url,
                temp_dir,
                progress_callback=progress_callback,
                media_username=media_username,
                media_password=media_password,
            )

            if progress_callback:
                progress_callback(65, "Video downloaded, processing metadata...")

            downloaded_file = download_result["file_path"]
            original_filename = download_result["filename"]
            media_info = video_info  # Use the info we already extracted

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

            # Download and upload media thumbnail with fallback
            thumbnail_path = _get_thumbnail_with_fallback(
                self, media_info, user.id, media_file.id, downloaded_file
            )

            if progress_callback:
                progress_callback(95, "Finalizing and updating database...")

            # Prepare media metadata and update the MediaFile record
            media_metadata = self._prepare_media_metadata(url, media_info)
            _update_media_file_with_download_data(
                media_file=media_file,
                media_info=media_info,
                media_metadata=media_metadata,
                technical_metadata=technical_metadata,
                storage_path=storage_path,
                file_size=file_size,
                thumbnail_path=thumbnail_path,
                original_filename=original_filename,
                source_url=url,
            )

            # Save updated record to database
            db.commit()
            db.refresh(media_file)

            logger.info(f"Updated MediaFile record {media_file.id} for media video")

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
        videos = playlist_info.get("videos", [])
        created_media_files, skipped_videos = _process_playlist_videos(
            db, user.id, videos, playlist_info, url, video_count, progress_callback
        )

        # Commit and refresh all placeholder records
        db.commit()
        for media_file in created_media_files:
            db.refresh(media_file)

        if progress_callback:
            progress_callback(
                100,
                f"Playlist processing complete: {len(created_media_files)} videos queued",
                {"created_count": len(created_media_files), "skipped_count": len(skipped_videos)},
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

    # Backward compatibility aliases
    def is_valid_youtube_url(self, url: str) -> bool:
        """Alias for is_valid_media_url for backward compatibility."""
        return self.is_valid_media_url(url)

    def process_youtube_url_sync(
        self,
        url: str,
        db: Session,
        user: User,
        media_file: MediaFile,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> MediaFile:
        """Alias for process_media_url_sync for backward compatibility."""
        return self.process_media_url_sync(url, db, user, media_file, progress_callback)

    def _prepare_youtube_metadata(self, url: str, youtube_info: dict[str, Any]) -> dict[str, Any]:
        """Alias for _prepare_media_metadata for backward compatibility."""
        return self._prepare_media_metadata(url, youtube_info)

    def _download_youtube_thumbnail_sync(self, youtube_info: dict[str, Any], user_id: int) -> str:
        """Alias for _download_media_thumbnail_sync for backward compatibility."""
        return self._download_media_thumbnail_sync(youtube_info, user_id)


# Backward compatibility alias
YouTubeService = MediaDownloadService
