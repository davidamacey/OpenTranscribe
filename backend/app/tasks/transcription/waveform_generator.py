"""
Waveform generation service for media files.

This module provides functionality to generate waveform visualization data
during the media processing pipeline.
"""

import logging
import subprocess
import json
import numpy as np
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Standard waveform resolutions for responsive design and device optimization
WAVEFORM_RESOLUTIONS = {
    'small': 500,   # Mobile phones, thumbnails, low-bandwidth
    'medium': 1000,  # Desktop standard, tablets
    'large': 2000    # High-DPI displays, detailed editing, large screens
}


class WaveformGenerator:
    """Generate waveform visualization data for audio/video files."""
    
    def __init__(self):
        """Initialize the waveform generator."""
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check that required dependencies (FFmpeg) are available."""
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True, timeout=10)
            subprocess.run(['ffprobe', '-version'], capture_output=True, check=True, timeout=10)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.error(f"FFmpeg not available: {e}")
            raise RuntimeError("FFmpeg is required for waveform generation but not available")
    
    def generate_waveform_data(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Generate waveform data for multiple resolutions optimized for different devices and screen sizes.
        
        Args:
            file_path: Path to the audio/video file
            
        Returns:
            Dictionary containing waveform data for all resolutions
        """
        try:
            # Generate waveforms for all standard resolutions
            waveform_cache = {}
            
            for resolution_name, samples in WAVEFORM_RESOLUTIONS.items():
                waveform_data = self._extract_single_waveform(file_path, samples)
                if waveform_data:
                    cache_key = f"waveform_{samples}"
                    waveform_cache[cache_key] = waveform_data
                    logger.debug(f"Generated {resolution_name} waveform: {samples} samples")
            
            # If we got at least one waveform, return the cache
            if waveform_cache:
                logger.info(f"Generated waveform data for {len(waveform_cache)} resolutions")
                return waveform_cache
            else:
                logger.warning(f"Failed to generate waveform data for {file_path}")
                return None
                
        except Exception as e:
            logger.error(f"Error generating waveform data: {e}")
            return None
    
    def _extract_single_waveform(self, file_path: str, target_samples: int) -> Optional[Dict[str, Any]]:
        """
        Extract waveform data for a single resolution.
        
        Args:
            file_path: Path to the audio/video file
            target_samples: Number of samples to return
            
        Returns:
            Dictionary containing waveform data and metadata
        """
        try:
            # First, get file duration and audio info using ffprobe
            probe_cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', 
                '-show_streams', file_path
            ]
            
            result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
            probe_data = json.loads(result.stdout)
            
            # Find audio stream
            audio_stream = None
            duration = 0.0
            sample_rate = 44100  # default
            
            for stream in probe_data.get('streams', []):
                if stream.get('codec_type') == 'audio':
                    audio_stream = stream
                    break
            
            if not audio_stream:
                logger.warning(f"No audio stream found in {file_path}")
                return None
            
            # Get duration and sample rate
            if 'duration' in probe_data.get('format', {}):
                duration = float(probe_data['format']['duration'])
            elif 'duration' in audio_stream:
                duration = float(audio_stream['duration'])
            
            if 'sample_rate' in audio_stream:
                sample_rate = int(audio_stream['sample_rate'])
            
            # Extract raw audio data using ffmpeg
            # Convert to mono, 16-bit PCM at 22050 Hz for waveform generation
            waveform_sample_rate = 22050
            
            # Build FFmpeg command with explicit duration if available
            ffmpeg_cmd = [
                'ffmpeg', '-i', file_path
            ]
            
            # Add duration flag to ensure we get the complete audio stream
            if duration > 0:
                # Add small buffer (0.5s) to ensure we don't cut off the end
                ffmpeg_cmd.extend(['-t', str(duration + 0.5)])
            
            ffmpeg_cmd.extend([
                '-f', 's16le',  # 16-bit little-endian
                '-acodec', 'pcm_s16le',
                '-ar', str(waveform_sample_rate),  # Sample rate for waveform
                '-ac', '1',  # Mono
                '-v', 'quiet',
                '-'  # Output to stdout
            ])
            
            logger.debug(f"FFmpeg command: {' '.join(ffmpeg_cmd)}")
            result = subprocess.run(ffmpeg_cmd, capture_output=True, check=True, timeout=300)
            
            # Convert bytes to numpy array
            audio_data = np.frombuffer(result.stdout, dtype=np.int16)
            
            if len(audio_data) == 0:
                logger.warning(f"No audio data extracted from {file_path}")
                return None
            
            # Debug: Log extracted audio info
            extracted_duration = len(audio_data) / waveform_sample_rate
            logger.info(f"FFmpeg extraction results: "
                       f"expected_duration={duration:.2f}s, "
                       f"extracted_duration={extracted_duration:.2f}s, "
                       f"audio_samples={len(audio_data)}, "
                       f"sample_rate={waveform_sample_rate}")
            
            # Validate extraction - warn if significantly different
            if duration > 0 and abs(extracted_duration - duration) > 1.0:
                logger.warning(f"Extracted duration ({extracted_duration:.2f}s) differs from expected ({duration:.2f}s)")
            
            # Convert to float and normalize
            audio_data = audio_data.astype(np.float32) / 32768.0
            
            # Calculate how many samples per target sample
            total_samples = len(audio_data)
            
            # Use the actual extracted duration for consistent sample distribution
            actual_duration = extracted_duration if extracted_duration > 0 else duration
            
            # Calculate samples per waveform point based on actual audio length
            if total_samples > target_samples:
                # Downsample: group audio samples into chunks
                chunk_size = total_samples / target_samples
                waveform = []
                
                for i in range(target_samples):
                    # Calculate chunk boundaries
                    start_idx = int(i * chunk_size)
                    end_idx = int((i + 1) * chunk_size)
                    
                    # Ensure we don't go out of bounds
                    end_idx = min(end_idx, total_samples)
                    
                    if start_idx < total_samples and start_idx < end_idx:
                        chunk = audio_data[start_idx:end_idx]
                        if len(chunk) > 0:
                            # Take RMS (root mean square) for better representation
                            rms_val = np.sqrt(np.mean(chunk ** 2))
                            waveform.append(rms_val)
                        else:
                            waveform.append(0.0)
                    else:
                        waveform.append(0.0)
            else:
                # Upsample: ensure we have enough points by interpolation
                # This shouldn't happen normally but handle gracefully
                logger.warning(f"Audio has fewer samples ({total_samples}) than target ({target_samples})")
                indices = np.linspace(0, total_samples - 1, target_samples)
                waveform = np.interp(indices, np.arange(total_samples), np.abs(audio_data)).tolist()
            
            # Ensure we have exactly target_samples
            if len(waveform) < target_samples:
                # Pad with zeros if needed (shouldn't happen with above logic)
                waveform.extend([0.0] * (target_samples - len(waveform)))
            elif len(waveform) > target_samples:
                waveform = waveform[:target_samples]
            
            # Normalize to 0-255 range for visualization
            if len(waveform) > 0 and max(waveform) > 0:
                max_val = max(waveform)
                waveform = [int(val / max_val * 255) for val in waveform]
            else:
                waveform = [0] * target_samples
            
            return {
                'waveform': waveform,
                'duration': actual_duration,  # Use the actual extracted duration
                'expected_duration': duration,  # Original expected duration
                'sample_rate': waveform_sample_rate,
                'samples': len(waveform),
                'original_sample_rate': sample_rate,
                'extracted_samples': total_samples,  # Total audio samples extracted
                'seconds_per_point': actual_duration / target_samples if target_samples > 0 else 0
            }
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error processing file {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error extracting waveform from {file_path}: {e}")
            return None