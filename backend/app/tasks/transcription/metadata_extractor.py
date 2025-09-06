import datetime
import json
import logging
import os
import subprocess
import sys
from typing import Any
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import exiftool
except ImportError:
    logging.warning("exiftool not found. Video metadata extraction will be limited.")


def get_important_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """
    Extract important metadata fields from the full metadata.

    Args:
        metadata: Dictionary of all metadata

    Returns:
        Dictionary of important metadata fields
    """
    field_mappings = {
        # Basic file info
        "FileName": ["File:FileName", "FileName", "SourceFile"],
        "FileSize": ["File:FileSize", "FileSize"],
        "MIMEType": ["File:MIMEType", "MIMEType"],
        "FileType": ["File:FileType", "FileType"],
        "FileTypeExtension": ["File:FileTypeExtension", "FileTypeExtension"],

        # Video specs
        "VideoFormat": ["QuickTime:VideoFormat", "VideoFormat", "Format"],
        "Duration": ["QuickTime:Duration", "Duration", "MediaDuration"],
        "FrameRate": ["QuickTime:FrameRate", "FrameRate"],
        "FrameCount": ["QuickTime:FrameCount", "FrameCount"],
        "VideoFrameRate": ["QuickTime:VideoFrameRate", "VideoFrameRate", "FrameRate"],
        "VideoWidth": ["QuickTime:ImageWidth", "File:ImageWidth", "ImageWidth", "Width"],
        "VideoHeight": ["QuickTime:ImageHeight", "File:ImageHeight", "ImageHeight", "Height"],
        "AspectRatio": ["QuickTime:AspectRatio", "AspectRatio"],
        "VideoCodec": ["QuickTime:CompressorID", "CompressorID", "VideoCodec", "Codec"],

        # Audio specs
        "AudioFormat": ["QuickTime:AudioFormat", "AudioFormat"],
        "AudioChannels": ["QuickTime:AudioChannels", "AudioChannels"],
        "AudioSampleRate": ["QuickTime:AudioSampleRate", "AudioSampleRate"],
        "AudioBitsPerSample": ["QuickTime:AudioBitsPerSample", "AudioBitsPerSample"],

        # Creation info
        "CreateDate": ["QuickTime:CreateDate", "CreateDate", "DateTimeOriginal"],
        "ModifyDate": ["QuickTime:ModifyDate", "ModifyDate"],
        "DateTimeOriginal": ["EXIF:DateTimeOriginal", "DateTimeOriginal"],

        # Device info
        "DeviceManufacturer": ["QuickTime:Make", "EXIF:Make", "Make", "DeviceManufacturer"],
        "DeviceModel": ["QuickTime:Model", "EXIF:Model", "Model", "DeviceModel"],

        # GPS info
        "GPSLatitude": ["EXIF:GPSLatitude", "GPSLatitude"],
        "GPSLongitude": ["EXIF:GPSLongitude", "GPSLongitude"],

        # Software used
        "Software": ["EXIF:Software", "Software"],

        # Content information
        "Title": ["QuickTime:Title", "Title"],
        "Artist": ["QuickTime:Artist", "Artist"],
        "Author": ["QuickTime:Author", "Author"],
        "Comment": ["QuickTime:Comment", "Comment"],
        "Description": ["QuickTime:Description", "Description"],
        "LongDescription": ["QuickTime:LongDescription", "LongDescription"],
        "HandlerDescription": ["QuickTime:HandlerDescription", "HandlerDescription"],
    }

    important_fields = {}

    # Extract values using the field mappings
    for field_name, possible_keys in field_mappings.items():
        for key in possible_keys:
            if key in metadata and metadata[key] is not None:
                important_fields[field_name] = metadata[key]
                break

    # Look for any additional fields that might be useful
    for key, value in metadata.items():
        if any(term in key.lower() for term in ["creator", "copyright", "language", "genre"]):
            important_fields[key] = value

    return important_fields


def extract_media_metadata(file_path: str) -> Optional[dict[str, Any]]:
    """
    Extract metadata from a media file using ExifTool.

    Args:
        file_path: Path to the media file

    Returns:
        Dictionary containing extracted metadata, or None if extraction failed
    """
    logger.info(f"Extracting metadata with ExifTool from {file_path}")
    extracted_metadata = {}

    # Try to use Python ExifTool library if available
    if "exiftool" in sys.modules:
        try:
            with exiftool.ExifToolHelper() as et:
                metadata_list = et.get_metadata(file_path)
                if metadata_list:
                    extracted_metadata = metadata_list[0]
                    logger.info(f"Successfully extracted {len(extracted_metadata)} metadata fields")
        except Exception as et_err:
            logger.warning(f"Error using Python ExifTool: {et_err}")

    # Fallback to command-line ExifTool if the Python library fails
    if not extracted_metadata:
        try:
            exif_process = subprocess.run(
                ["exiftool", "-json", "-n", file_path],
                capture_output=True,
                text=True,
                check=True
            )

            if exif_process.stdout:
                try:
                    metadata_list = json.loads(exif_process.stdout)
                    if metadata_list:
                        extracted_metadata = metadata_list[0]
                        logger.info(f"Successfully extracted {len(extracted_metadata)} metadata fields via subprocess")
                except json.JSONDecodeError as jde:
                    logger.warning(f"Error decoding ExifTool JSON output: {jde}")
        except (subprocess.SubprocessError, FileNotFoundError) as sp_err:
            logger.warning(f"Error running ExifTool subprocess: {sp_err}")

    return extracted_metadata if extracted_metadata else None


def update_media_file_metadata(media_file, extracted_metadata: dict[str, Any],
                              content_type: str, file_path: str) -> None:
    """
    Update a MediaFile object with extracted metadata.

    Args:
        media_file: SQLAlchemy MediaFile object
        extracted_metadata: Raw metadata from ExifTool
        content_type: MIME type of the file
        file_path: Path to the file for additional operations
    """
    important_metadata = get_important_metadata(extracted_metadata)

    # Store metadata
    media_file.metadata_raw = extracted_metadata
    media_file.metadata_important = important_metadata

    # Set basic file information
    media_file.file_size = os.path.getsize(file_path)
    media_file.media_format = important_metadata.get("FileType")

    # Video specific metadata
    if content_type.startswith(("video/", "image/")):
        media_file.resolution_width = important_metadata.get("VideoWidth") or important_metadata.get("ImageWidth")
        media_file.resolution_height = important_metadata.get("VideoHeight") or important_metadata.get("ImageHeight")
        media_file.frame_rate = important_metadata.get("VideoFrameRate") or important_metadata.get("FrameRate")
        media_file.codec = important_metadata.get("VideoCodec") or important_metadata.get("CompressorID")
        media_file.frame_count = important_metadata.get("FrameCount")

        if important_metadata.get("AspectRatio"):
            media_file.aspect_ratio = important_metadata.get("AspectRatio")

    # Audio specific metadata
    if content_type.startswith(("audio/", "video/")):
        media_file.audio_channels = important_metadata.get("AudioChannels")
        media_file.audio_sample_rate = important_metadata.get("AudioSampleRate")
        media_file.audio_bit_depth = important_metadata.get("AudioBitsPerSample")

    # Duration
    if important_metadata.get("Duration"):
        try:
            duration_value = float(important_metadata.get("Duration"))
            media_file.duration = duration_value
        except (ValueError, TypeError):
            logger.warning(f"Could not parse duration: {important_metadata.get('Duration')}")

    # Creation and modification dates
    if important_metadata.get("CreateDate"):
        try:
            create_date_str = important_metadata.get("CreateDate")
            if ":" in create_date_str and len(create_date_str) >= 10:
                if len(create_date_str) <= 19:  # No timezone
                    create_date_str = create_date_str.replace(":", "-", 2) + "+00:00"
                media_file.creation_date = datetime.datetime.fromisoformat(create_date_str)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse creation date: {important_metadata.get('CreateDate')}")

    if important_metadata.get("ModifyDate"):
        try:
            modify_date_str = important_metadata.get("ModifyDate")
            if ":" in modify_date_str and len(modify_date_str) >= 10:
                modify_date_str = modify_date_str.replace(":", "-", 2)
                if len(modify_date_str) <= 19:  # No timezone
                    modify_date_str += "+00:00"
                media_file.last_modified_date = datetime.datetime.fromisoformat(modify_date_str)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse modification date: {important_metadata.get('ModifyDate')}")

    # Device information
    media_file.device_make = important_metadata.get("DeviceManufacturer")
    media_file.device_model = important_metadata.get("DeviceModel")

    # Content information
    media_file.title = important_metadata.get("Title")
    media_file.author = important_metadata.get("Author") or important_metadata.get("Artist")
    media_file.description = (important_metadata.get("Description") or
                             important_metadata.get("Comment") or
                             important_metadata.get("LongDescription"))

    # Store both important and full metadata
    media_file.important_metadata = important_metadata
    media_file.metadata = extracted_metadata
