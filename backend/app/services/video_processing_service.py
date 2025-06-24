"""
Video processing service for embedding subtitles into video files using FFmpeg.
Handles various video formats and subtitle codecs with caching support.
"""

import os
import tempfile
import subprocess
import hashlib
from typing import Optional, Dict, Any, List
from pathlib import Path
from sqlalchemy.orm import Session

from app.services.minio_service import MinIOService
from app.services.subtitle_service import SubtitleService
from app.core.config import settings
from app.models.media import MediaFile


class VideoProcessingService:
    """Service for processing videos with embedded subtitles."""
    
    # Supported video formats and their optimal subtitle codecs
    SUPPORTED_FORMATS = {
        'mp4': {
            'subtitle_codec': 'mov_text',  # MP4 native subtitle format
            'container': 'mp4',
            'copy_codecs': True  # Copy video/audio streams without re-encoding
        },
        'mkv': {
            'subtitle_codec': 'srt',  # Matroska supports SRT natively
            'container': 'matroska',
            'copy_codecs': True
        },
        'webm': {
            'subtitle_codec': 'webvtt',  # WebM uses WebVTT
            'container': 'webm',
            'copy_codecs': True
        }
    }
    
    def __init__(self, minio_service: MinIOService):
        self.minio_service = minio_service
        self.cache_bucket = "processed-videos"
        self._ensure_cache_bucket()
    
    def _ensure_cache_bucket(self):
        """Ensure the cache bucket exists."""
        try:
            if not self.minio_service.client.bucket_exists(self.cache_bucket):
                self.minio_service.client.make_bucket(self.cache_bucket)
        except Exception as e:
            print(f"Warning: Could not create cache bucket: {e}")
    
    def _get_cache_key(
        self, 
        media_file_id: int, 
        format_type: str, 
        include_speakers: bool,
        transcript_hash: str
    ) -> str:
        """Generate cache key for processed video."""
        key_data = f"{media_file_id}_{format_type}_{include_speakers}_{transcript_hash}"
        return hashlib.sha256(key_data.encode()).hexdigest()
    
    def _get_transcript_hash(self, db: Session, media_file_id: int) -> str:
        """Generate hash of current transcript to detect changes."""
        srt_content = SubtitleService.generate_srt_content(db, media_file_id)
        return hashlib.sha256(srt_content.encode()).hexdigest()
    
    def _get_video_info(self, video_path: str) -> Dict[str, Any]:
        """Get video information using ffprobe."""
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            video_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            import json
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to get video info: {e}")
    
    def _detect_output_format(self, input_path: str, requested_format: Optional[str] = None) -> str:
        """Detect optimal output format based on input format and request."""
        if requested_format and requested_format.lower() in self.SUPPORTED_FORMATS:
            return requested_format.lower()
        
        # Auto-detect from input file extension
        input_ext = Path(input_path).suffix.lower().lstrip('.')
        
        # Map common formats to supported formats
        format_mapping = {
            'mp4': 'mp4',
            'm4v': 'mp4',
            'mov': 'mp4',
            'mkv': 'mkv',
            'webm': 'webm',
            'avi': 'mp4',  # Convert AVI to MP4
            'wmv': 'mp4',  # Convert WMV to MP4
        }
        
        return format_mapping.get(input_ext, 'mp4')  # Default to MP4
    
    def _embed_subtitles_ffmpeg(
        self,
        input_video_path: str,
        subtitle_content: str,
        output_path: str,
        format_type: str
    ) -> bool:
        """Embed subtitles into video using FFmpeg."""
        format_config = self.SUPPORTED_FORMATS[format_type]
        
        # Create temporary subtitle file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as srt_file:
            srt_file.write(subtitle_content)
            srt_path = srt_file.name
        
        try:
            # Build FFmpeg command
            cmd = [
                'ffmpeg',
                '-i', input_video_path,  # Input video
                '-i', srt_path,          # Input subtitle file
                '-c:v', 'copy',          # Copy video stream (no re-encoding)
                '-c:a', 'copy',          # Copy audio stream (no re-encoding)
                '-c:s', format_config['subtitle_codec'],  # Subtitle codec
                '-disposition:s:0', 'default',  # Make subtitles default
                '-y',  # Overwrite output file
                output_path
            ]
            
            # Add format-specific options
            if format_type == 'mp4':
                # MP4 specific options for better compatibility
                cmd.extend(['-movflags', '+faststart'])
            elif format_type == 'mkv':
                # Matroska specific options
                cmd.extend(['-f', 'matroska'])
            
            # Execute FFmpeg command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                raise Exception(f"FFmpeg failed: {result.stderr}")
            
            return True
            
        except subprocess.TimeoutExpired:
            raise Exception("Video processing timed out")
        except Exception as e:
            raise Exception(f"Failed to embed subtitles: {str(e)}")
        finally:
            # Clean up temporary subtitle file
            try:
                os.unlink(srt_path)
            except:
                pass
    
    def process_video_with_subtitles(
        self,
        db: Session,
        media_file_id: int,
        output_format: Optional[str] = None,
        include_speakers: bool = True,
        force_regenerate: bool = False
    ) -> str:
        """
        Process video with embedded subtitles and return MinIO path.
        
        Args:
            db: Database session
            media_file_id: ID of the media file
            output_format: Desired output format (mp4, mkv, webm)
            include_speakers: Whether to include speaker labels
            force_regenerate: Force regeneration even if cached version exists
            
        Returns:
            MinIO path to the processed video
        """
        # Get media file
        media_file = db.query(MediaFile).filter(MediaFile.id == media_file_id).first()
        if not media_file:
            raise ValueError(f"Media file {media_file_id} not found")
        
        # Generate transcript hash for cache validation
        transcript_hash = self._get_transcript_hash(db, media_file_id)
        
        # Determine output format
        with tempfile.NamedTemporaryFile() as temp_file:
            # Download original video to determine format
            self.minio_service.download_file(media_file.storage_path, temp_file.name)
            detected_format = self._detect_output_format(temp_file.name, output_format)
        
        # Check cache first
        cache_key = self._get_cache_key(media_file_id, detected_format, include_speakers, transcript_hash)
        cached_path = f"subtitled/{cache_key}.{detected_format}"
        
        if not force_regenerate:
            try:
                # Check if cached version exists
                self.minio_service.client.stat_object(self.cache_bucket, cached_path)
                return f"{self.cache_bucket}/{cached_path}"
            except:
                pass  # Cache miss, proceed with processing
        
        # Generate subtitle content
        subtitle_content = SubtitleService.generate_srt_content(
            db, media_file_id, include_speakers
        )
        
        if not subtitle_content.strip():
            raise ValueError("No subtitle content available for this media file")
        
        # Create temporary files for processing
        with tempfile.NamedTemporaryFile(suffix=f'.{detected_format}') as input_temp, \
             tempfile.NamedTemporaryFile(suffix=f'.{detected_format}') as output_temp:
            
            # Download original video
            self.minio_service.download_file(media_file.storage_path, input_temp.name)
            
            # Process video with subtitles
            success = self._embed_subtitles_ffmpeg(
                input_temp.name,
                subtitle_content,
                output_temp.name,
                detected_format
            )
            
            if not success:
                raise Exception("Failed to embed subtitles")
            
            # Upload processed video to cache
            self.minio_service.upload_file(
                output_temp.name,
                self.cache_bucket,
                cached_path,
                content_type=f"video/{detected_format}"
            )
        
        return f"{self.cache_bucket}/{cached_path}"
    
    def get_video_with_subtitles_url(
        self,
        db: Session,
        media_file_id: int,
        output_format: Optional[str] = None,
        include_speakers: bool = True,
        expires_in: int = 3600
    ) -> str:
        """
        Get presigned URL for video with embedded subtitles.
        
        Args:
            db: Database session
            media_file_id: ID of the media file
            output_format: Desired output format
            include_speakers: Whether to include speaker labels
            expires_in: URL expiration time in seconds
            
        Returns:
            Presigned URL for the processed video
        """
        processed_path = self.process_video_with_subtitles(
            db, media_file_id, output_format, include_speakers
        )
        
        # Extract bucket and object path
        bucket, object_path = processed_path.split('/', 1)
        
        return self.minio_service.get_presigned_url(
            bucket_name=bucket,
            object_name=object_path,
            expires=expires_in
        )
    
    def clear_cache_for_media_file(self, media_file_id: int):
        """Clear all cached processed videos for a media file."""
        try:
            # List all objects with the media file ID prefix
            objects = self.minio_service.client.list_objects(
                self.cache_bucket,
                prefix=f"subtitled/",
                recursive=True
            )
            
            # Filter objects that contain this media file ID
            for obj in objects:
                if f"_{media_file_id}_" in obj.object_name:
                    self.minio_service.client.remove_object(self.cache_bucket, obj.object_name)
                    
        except Exception as e:
            print(f"Warning: Failed to clear cache for media file {media_file_id}: {e}")
    
    def get_supported_formats(self) -> List[str]:
        """Get list of supported output formats."""
        return list(self.SUPPORTED_FORMATS.keys())
    
    def validate_format(self, format_type: str) -> bool:
        """Validate if format is supported."""
        return format_type.lower() in self.SUPPORTED_FORMATS