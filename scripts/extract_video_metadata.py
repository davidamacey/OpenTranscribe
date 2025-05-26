#!/usr/bin/env python3.11

"""
Script to extract metadata from video files using exiftool.
This helps us understand what metadata is available to improve
the OpenTranscribe application's metadata display.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

def run_exiftool(video_path: str, json_output: bool = True) -> Optional[Dict[str, Any]]:
    """
    Run exiftool on a video file and return the metadata.
    
    Args:
        video_path: Path to the video file
        json_output: Whether to return the output as JSON
        
    Returns:
        Dictionary of metadata if json_output is True, otherwise the raw output
    """
    try:
        cmd = ["exiftool"]
        if json_output:
            cmd.append("-j")
        cmd.append(video_path)
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        if json_output:
            # Parse JSON output
            metadata = json.loads(result.stdout)
            if metadata and isinstance(metadata, list):
                return metadata[0]  # exiftool returns a list with one item
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error running exiftool on {video_path}: {e}")
        print(f"stderr: {e.stderr}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing exiftool output as JSON: {e}")
        return None

def get_important_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract important metadata fields from the full metadata.
    
    Args:
        metadata: Dictionary of all metadata
        
    Returns:
        Dictionary of important metadata fields
    """
    important_fields = {
        # Basic file info
        "FileName": metadata.get("FileName"),
        "FileSize": metadata.get("FileSize"),
        "MIMEType": metadata.get("MIMEType"),
        "FileType": metadata.get("FileType"),
        "FileTypeExtension": metadata.get("FileTypeExtension"),
        
        # Video specs
        "VideoFormat": metadata.get("VideoFormat"),
        "Duration": metadata.get("Duration"),
        "DurationSeconds": metadata.get("Duration", "0").split()[0] if isinstance(metadata.get("Duration"), str) else None,
        "FrameRate": metadata.get("FrameRate"),
        "FrameCount": metadata.get("FrameCount"),
        "VideoFrameRate": metadata.get("VideoFrameRate"),
        "VideoWidth": metadata.get("ImageWidth"),
        "VideoHeight": metadata.get("ImageHeight"),
        "AspectRatio": metadata.get("AspectRatio"),
        "VideoCodec": metadata.get("CompressorID"),
        
        # Audio specs
        "AudioFormat": metadata.get("AudioFormat"),
        "AudioChannels": metadata.get("AudioChannels"),
        "AudioSampleRate": metadata.get("AudioSampleRate"),
        "AudioBitsPerSample": metadata.get("AudioBitsPerSample"),
        
        # Creation info
        "CreateDate": metadata.get("CreateDate"),
        "ModifyDate": metadata.get("ModifyDate"),
        "DateTimeOriginal": metadata.get("DateTimeOriginal"),
        
        # Device info
        "DeviceManufacturer": metadata.get("DeviceManufacturer"),
        "DeviceModel": metadata.get("DeviceModel"),
        "Make": metadata.get("Make"),
        "Model": metadata.get("Model"),
        
        # GPS info if available
        "GPSLatitude": metadata.get("GPSLatitude"),
        "GPSLongitude": metadata.get("GPSLongitude"),
        
        # Software used
        "Software": metadata.get("Software"),
    }
    
    # Include any other potentially useful fields
    for key, value in metadata.items():
        if any(term in key.lower() for term in ["author", "artist", "title", "comment", "description", "creator"]):
            important_fields[key] = value
    
    return important_fields

def process_videos_in_directory(directory_path: str) -> List[Dict[str, Any]]:
    """
    Process all video files in a directory and extract metadata.
    
    Args:
        directory_path: Path to the directory containing video files
        
    Returns:
        List of dictionaries containing metadata for each video
    """
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v']
    results = []
    
    # Get list of video files
    video_files = []
    for ext in video_extensions:
        video_files.extend(list(Path(directory_path).glob(f'*{ext}')))
    
    if not video_files:
        print(f"No video files found in {directory_path}")
        return results
    
    # Process each video file
    for video_path in video_files:
        print(f"Processing {video_path}...")
        metadata = run_exiftool(str(video_path))
        
        if metadata:
            important_metadata = get_important_metadata(metadata)
            results.append({
                "file": str(video_path),
                "important_metadata": important_metadata,
                "full_metadata": metadata
            })
            print(f"  - Found {len(metadata)} metadata fields")
        else:
            print(f"  - Failed to extract metadata")
    
    return results

def main():
    """Main function to run the script."""
    if len(sys.argv) > 1:
        directory_path = sys.argv[1]
    else:
        directory_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_videos")
    
    if not os.path.isdir(directory_path):
        print(f"Error: {directory_path} is not a valid directory")
        sys.exit(1)
    
    print(f"Extracting metadata from videos in {directory_path}...")
    results = process_videos_in_directory(directory_path)
    
    # Save results to a JSON file
    output_file = os.path.join(os.path.dirname(directory_path), "video_metadata.json")
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Metadata saved to {output_file}")
    
    # Print a summary
    print("\nSummary of available metadata fields:")
    for result in results:
        print(f"\n{result['file']}:")
        
        important_metadata = result['important_metadata']
        # Print duration, format, resolution if available
        duration = important_metadata.get('Duration', 'Unknown')
        video_format = important_metadata.get('VideoFormat', 'Unknown')
        resolution = f"{important_metadata.get('VideoWidth', '?')}x{important_metadata.get('VideoHeight', '?')}"
        
        print(f"  Duration: {duration}")
        print(f"  Format: {video_format}")
        print(f"  Resolution: {resolution}")
        print(f"  Creation Date: {important_metadata.get('CreateDate', 'Unknown')}")
        
        # Print all available fields as a quick reference
        print("  Available Fields:")
        non_empty_fields = {k: v for k, v in important_metadata.items() if v is not None}
        for key, value in non_empty_fields.items():
            print(f"    - {key}: {value}")

if __name__ == "__main__":
    main()
