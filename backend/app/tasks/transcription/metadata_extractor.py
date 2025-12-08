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


# Invalid date patterns to reject (common in downloaded/processed videos)
_INVALID_DATE_PATTERNS = frozenset(
    [
        "0000:00:00 00:00:00",
        "0000-00-00 00:00:00",
        "1970:01:01 00:00:00",
        "1970-01-01T00:00:00",
        "0000:00:00",
        "0000-00-00",
        "1970:01:01",
        "1970-01-01",
    ]
)

# Common date format patterns in media metadata
_DATE_PATTERNS = [
    "%Y:%m:%d %H:%M:%S",  # ISO format: 2023:12:25 14:30:45
    "%Y:%m:%d %H:%M:%S%z",  # ISO with timezone: 2023:12:25 14:30:45+00:00
    "%Y-%m-%dT%H:%M:%S",  # Standard ISO: 2023-12-25T14:30:45
    "%Y-%m-%dT%H:%M:%SZ",  # ISO with timezone: 2023-12-25T14:30:45Z
    "%Y-%m-%dT%H:%M:%S%z",  # ISO with timezone: 2023-12-25T14:30:45+00:00
    "%Y:%m:%d",  # Date only: 2023:12:25
    "%Y-%m-%d",  # Date only: 2023-12-25
    "%Y",  # Year only (for MP3, etc.): 2023
]


def _parse_integer_date(date_int: int) -> Optional[datetime.datetime]:
    """Parse integer YYYYMMDD format (common in YouTube/platform videos)."""
    try:
        date_str = str(date_int)
        if len(date_str) != 8:
            return None
        year = int(date_str[0:4])
        month = int(date_str[4:6])
        day = int(date_str[6:8])
        return datetime.datetime(year, month, day, tzinfo=datetime.timezone.utc)
    except (ValueError, TypeError):
        return None


def _parse_with_patterns(date_str: str) -> Optional[datetime.datetime]:
    """Try parsing date string against common media metadata patterns."""
    for pattern in _DATE_PATTERNS:
        try:
            parsed_date = datetime.datetime.strptime(date_str.strip(), pattern)
            if parsed_date.tzinfo is None:
                parsed_date = parsed_date.replace(tzinfo=datetime.timezone.utc)
            return parsed_date
        except ValueError:
            continue
    return None


def _parse_quicktime_format(date_str: str) -> Optional[datetime.datetime]:
    """Fallback parser for QuickTime format dates."""
    try:
        if ":" not in date_str or len(date_str) < 10:
            return None
        create_date_str = date_str
        if len(create_date_str) <= 19:  # No timezone
            create_date_str = create_date_str.replace(":", "-", 2) + "+00:00"
        return datetime.datetime.fromisoformat(create_date_str)
    except (ValueError, TypeError):
        return None


def _parse_media_date(date_str: str) -> Optional[datetime.datetime]:
    """
    Parse various date formats commonly found in media file metadata.

    Args:
        date_str: Date string from metadata (can also be an integer for YYYYMMDD format)

    Returns:
        Parsed datetime object or None if parsing fails
    """
    if not date_str:
        return None

    # Handle integer YYYYMMDD format
    if isinstance(date_str, int):
        return _parse_integer_date(date_str)

    if not isinstance(date_str, str):
        return None

    # Reject obviously invalid dates
    if date_str.strip() in _INVALID_DATE_PATTERNS:
        return None

    # Try common date patterns
    result = _parse_with_patterns(date_str)
    if result:
        return result

    # Fallback: try QuickTime format
    result = _parse_quicktime_format(date_str)
    if result:
        return result

    raise ValueError(f"Unable to parse date format: {date_str}")


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
        "VideoWidth": [
            "QuickTime:ImageWidth",
            "File:ImageWidth",
            "ImageWidth",
            "Width",
        ],
        "VideoHeight": [
            "QuickTime:ImageHeight",
            "File:ImageHeight",
            "ImageHeight",
            "Height",
        ],
        "AspectRatio": ["QuickTime:AspectRatio", "AspectRatio"],
        "VideoCodec": ["QuickTime:CompressorID", "CompressorID", "VideoCodec", "Codec"],
        # Audio specs
        "AudioFormat": ["QuickTime:AudioFormat", "AudioFormat"],
        "AudioChannels": ["QuickTime:AudioChannels", "AudioChannels"],
        "AudioSampleRate": ["QuickTime:AudioSampleRate", "AudioSampleRate"],
        "AudioBitsPerSample": ["QuickTime:AudioBitsPerSample", "AudioBitsPerSample"],
        # Creation info
        "CreateDate": [
            "QuickTime:ContentCreateDate",  # YouTube and other platform videos
            "QuickTime:CreateDate",
            "CreateDate",
            "DateTimeOriginal",
            "File:FileCreateDate",
            "File:FileModifyDate",
            "XMP:CreateDate",
            "XMP:DateCreated",
            "XMP:DateTimeOriginal",
            "MP4:CreateDate",
            "MP4:CreationDate",
            "Matroska:DateUTC",
            "WebM:DateUTC",
            "AVI:DateTimeOriginal",
            "WMV:DateEncoded",
            "WAV:DateCreated",
            "MP3:Year",
            "FLAC:Date",
            "OGG:Date",
        ],
        "ModifyDate": ["QuickTime:ModifyDate", "ModifyDate", "File:FileModifyDate"],
        "DateTimeOriginal": ["EXIF:DateTimeOriginal", "DateTimeOriginal", "XMP:DateTimeOriginal"],
        # Device info
        "DeviceManufacturer": [
            "QuickTime:Make",
            "EXIF:Make",
            "Make",
            "DeviceManufacturer",
        ],
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
            # Using hardcoded exiftool command, not user input
            exif_process = subprocess.run(  # noqa: S603
                ["exiftool", "-json", "-n", file_path],  # noqa: S607
                capture_output=True,
                text=True,
                check=True,
            )

            if exif_process.stdout:
                try:
                    metadata_list = json.loads(exif_process.stdout)
                    if metadata_list:
                        extracted_metadata = metadata_list[0]
                        logger.info(
                            f"Successfully extracted {len(extracted_metadata)} metadata fields via subprocess"
                        )
                except json.JSONDecodeError as jde:
                    logger.warning(f"Error decoding ExifTool JSON output: {jde}")
        except (subprocess.SubprocessError, FileNotFoundError) as sp_err:
            logger.warning(f"Error running ExifTool subprocess: {sp_err}")

    return extracted_metadata if extracted_metadata else None


def _set_video_metadata(media_file, important_metadata: dict[str, Any]) -> None:
    """Set video-specific metadata fields on media_file."""
    media_file.resolution_width = important_metadata.get("VideoWidth") or important_metadata.get(
        "ImageWidth"
    )
    media_file.resolution_height = important_metadata.get("VideoHeight") or important_metadata.get(
        "ImageHeight"
    )
    media_file.frame_rate = important_metadata.get("VideoFrameRate") or important_metadata.get(
        "FrameRate"
    )
    media_file.codec = important_metadata.get("VideoCodec") or important_metadata.get(
        "CompressorID"
    )
    media_file.frame_count = important_metadata.get("FrameCount")
    if important_metadata.get("AspectRatio"):
        media_file.aspect_ratio = important_metadata.get("AspectRatio")


def _set_audio_metadata(media_file, important_metadata: dict[str, Any]) -> None:
    """Set audio-specific metadata fields on media_file."""
    media_file.audio_channels = important_metadata.get("AudioChannels")
    media_file.audio_sample_rate = important_metadata.get("AudioSampleRate")
    media_file.audio_bit_depth = important_metadata.get("AudioBitsPerSample")


def _set_duration(media_file, important_metadata: dict[str, Any]) -> None:
    """Parse and set duration from metadata."""
    duration = important_metadata.get("Duration")
    if not duration:
        return
    try:
        media_file.duration = float(duration)
    except (ValueError, TypeError):
        logger.warning(f"Could not parse duration: {duration}")


def _try_parse_creation_date_from_fields(media_file, important_metadata: dict[str, Any]) -> None:
    """Try to parse creation date from metadata fields."""
    creation_date_fields = ["CreateDate", "DateTimeOriginal", "ModifyDate"]
    for field_name in creation_date_fields:
        field_value = important_metadata.get(field_name)
        if not field_value or media_file.creation_date is not None:
            continue
        try:
            parsed_date = _parse_media_date(field_value)
            if parsed_date:
                media_file.creation_date = parsed_date
                logger.info(f"Successfully parsed creation date from {field_name}: {parsed_date}")
                return
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse {field_name}: {field_value} - {e}")


def _apply_creation_date_fallbacks(media_file, file_path: str) -> None:
    """Apply fallback chain for missing creation dates."""
    if media_file.creation_date is not None:
        return

    # First fallback: file system modification time
    try:
        if os.path.exists(file_path):
            file_mtime = os.path.getmtime(file_path)
            media_file.creation_date = datetime.datetime.fromtimestamp(
                file_mtime, tz=datetime.timezone.utc
            )
            logger.info(
                f"Using file system modification time as creation_date: {media_file.creation_date}"
            )
            return
    except Exception as e:
        logger.warning(f"Could not get file system modification time: {e}")

    # Final fallback: use upload_time
    if media_file.upload_time:
        media_file.creation_date = media_file.upload_time
        logger.info(f"Using upload_time as creation_date fallback: {media_file.creation_date}")


def _set_modification_date(media_file, important_metadata: dict[str, Any]) -> None:
    """Parse and set modification date from metadata."""
    modify_date = important_metadata.get("ModifyDate")
    if not modify_date:
        return
    try:
        media_file.last_modified_date = _parse_media_date(modify_date)
    except (ValueError, TypeError) as e:
        logger.warning(f"Could not parse modification date: {modify_date} - {e}")


def _set_content_info(media_file, important_metadata: dict[str, Any]) -> None:
    """Set device and content information fields."""
    media_file.device_make = important_metadata.get("DeviceManufacturer")
    media_file.device_model = important_metadata.get("DeviceModel")
    media_file.title = important_metadata.get("Title")
    media_file.author = important_metadata.get("Author") or important_metadata.get("Artist")
    media_file.description = (
        important_metadata.get("Description")
        or important_metadata.get("Comment")
        or important_metadata.get("LongDescription")
    )


def update_media_file_metadata(
    media_file, extracted_metadata: dict[str, Any], content_type: str, file_path: str
) -> None:
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

    # Video/image specific metadata
    if content_type.startswith(("video/", "image/")):
        _set_video_metadata(media_file, important_metadata)

    # Audio specific metadata
    if content_type.startswith(("audio/", "video/")):
        _set_audio_metadata(media_file, important_metadata)

    # Duration
    _set_duration(media_file, important_metadata)

    # Creation date with fallback chain
    _try_parse_creation_date_from_fields(media_file, important_metadata)
    _apply_creation_date_fallbacks(media_file, file_path)

    # Modification date
    _set_modification_date(media_file, important_metadata)

    # Device and content information
    _set_content_info(media_file, important_metadata)

    # Store both important and full metadata
    media_file.important_metadata = important_metadata
    media_file.metadata = extracted_metadata
