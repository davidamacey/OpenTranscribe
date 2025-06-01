"""
Utility module for generating thumbnails from video files
"""
import os
import io
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Union, BinaryIO, Tuple

import ffmpeg
from fastapi import HTTPException, status

from app.services.minio_service import upload_file

logger = logging.getLogger(__name__)

def generate_thumbnail(
    video_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None, 
    timestamp: float = 1.0,
    size: Tuple[int, int] = (320, 180)  # 16:9 aspect ratio thumbnail
) -> Optional[Union[str, bytes]]:
    """
    Generate a thumbnail from a video file at the specified timestamp.
    
    Args:
        video_path: Path to the video file
        output_path: Path to save the thumbnail (optional)
        timestamp: Time in seconds to extract the thumbnail (default: 1s)
        size: Thumbnail dimensions as (width, height)
        
    Returns:
        If output_path is specified: The path to the saved thumbnail
        If output_path is None: The thumbnail as bytes
    """
    try:
        # Convert to string if Path object
        if isinstance(video_path, Path):
            video_path = str(video_path)
            
        width, height = size
        
        # Create a temporary file if no output path specified
        if output_path is None:
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                output_path = tmp.name
        
        # Generate thumbnail using ffmpeg
        (
            ffmpeg
            .input(video_path, ss=timestamp)
            .filter('scale', width, height)
            .output(str(output_path), vframes=1)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        
        # Return the path or read as bytes if no output_path was specified
        if output_path == tmp.name:
            with open(output_path, 'rb') as f:
                result = f.read()
            # Clean up the temporary file
            os.unlink(output_path)
            return result
        
        return output_path
        
    except ffmpeg.Error as e:
        logger.error(f"Error generating thumbnail with ffmpeg: {e.stderr.decode() if e.stderr else str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error generating thumbnail: {str(e)}")
        return None


async def generate_and_upload_thumbnail(
    user_id: int,
    media_file_id: int, 
    video_path: Union[str, Path],
    timestamp: float = 1.0
) -> Optional[str]:
    """
    Generate a thumbnail from a video file and upload it to storage.
    
    Args:
        user_id: User ID for storage path
        media_file_id: Media file ID for storage path
        video_path: Path to the video file
        timestamp: Time in seconds to extract the thumbnail
        
    Returns:
        The storage path of the uploaded thumbnail, or None if generation failed
    """
    try:
        # Generate thumbnail
        thumbnail_bytes = generate_thumbnail(video_path, timestamp=timestamp)
        
        if not thumbnail_bytes:
            logger.error(f"Failed to generate thumbnail for file {media_file_id}")
            return None
        
        # Generate storage path for thumbnail
        filename = Path(video_path).stem if isinstance(video_path, (str, Path)) else f"file_{media_file_id}"
        storage_path = f"user_{user_id}/file_{media_file_id}/thumbnail_{filename}.jpg"
        
        # Upload thumbnail to storage
        if os.environ.get('SKIP_S3', 'False').lower() != 'true':
            upload_file(
                file_content=io.BytesIO(thumbnail_bytes),
                file_size=len(thumbnail_bytes),
                object_name=storage_path,
                content_type="image/jpeg"
            )
        else:
            logger.info("Skipping S3 upload for thumbnail in test environment")
            
        return storage_path
        
    except Exception as e:
        logger.error(f"Error generating and uploading thumbnail: {str(e)}")
        return None
