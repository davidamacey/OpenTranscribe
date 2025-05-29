import os
import tempfile
import logging
import ffmpeg
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)


def get_audio_file_extension(content_type: str, filename: str) -> str:
    """
    Determine the appropriate file extension based on content type and filename.
    
    Args:
        content_type: MIME type of the file
        filename: Original filename
        
    Returns:
        File extension string
    """
    file_ext = os.path.splitext(filename)[1]
    
    if not file_ext and content_type:
        mime_to_ext = {
            "audio/mpeg": ".mp3",
            "audio/mp3": ".mp3",
            "audio/wav": ".wav",
            "audio/wave": ".wav",
            "audio/x-wav": ".wav",
            "audio/webm": ".webm",
            "audio/ogg": ".ogg",
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "video/ogg": ".ogg"
        }
        file_ext = mime_to_ext.get(content_type, ".mp4")
    
    return file_ext


def extract_audio_from_video(video_path: str, output_path: str) -> None:
    """
    Extract audio from a video file using ffmpeg.
    
    Args:
        video_path: Path to the input video file
        output_path: Path for the output audio file
    """
    logger.info(f"Extracting audio from video file {video_path}")
    ffmpeg.input(video_path).output(
        output_path, 
        acodec="pcm_s16le", 
        ar="16000", 
        ac=1
    ).run(quiet=True)


def convert_audio_format(input_path: str, output_path: str) -> None:
    """
    Convert audio file to WAV format using ffmpeg.
    
    Args:
        input_path: Path to the input audio file
        output_path: Path for the output WAV file
    """
    logger.info(f"Converting audio to WAV format")
    ffmpeg.input(input_path).output(
        output_path, 
        acodec="pcm_s16le", 
        ar="16000", 
        ac=1
    ).run(quiet=True)


def prepare_audio_for_transcription(temp_file_path: str, content_type: str, 
                                  temp_dir: str) -> str:
    """
    Prepare audio file for transcription by extracting from video or converting format.
    
    Args:
        temp_file_path: Path to the temporary input file
        content_type: MIME type of the input file
        temp_dir: Temporary directory for processing
        
    Returns:
        Path to the prepared audio file
    """
    temp_audio_path = os.path.join(temp_dir, "audio.wav")
    
    if content_type.startswith("video/"):
        extract_audio_from_video(temp_file_path, temp_audio_path)
        return temp_audio_path
    else:
        # For audio files, convert to WAV format if needed
        file_ext = Path(temp_file_path).suffix.lower()
        if file_ext != ".wav":
            convert_audio_format(temp_file_path, temp_audio_path)
            return temp_audio_path
        else:
            return temp_file_path