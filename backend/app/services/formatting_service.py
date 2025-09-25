"""Formatting service for converting raw data to display-ready formats.

This service handles formatting dates, durations, status text, and other data
that was previously formatted on the frontend.

The service provides comprehensive data formatting including:
- Duration formatting (seconds to MM:SS, detailed formats)
- Date and time formatting with timezone handling
- File size formatting with appropriate units (B, KB, MB, GB)
- Status text and badge class generation for UI styling
- Speaker name resolution and display formatting
- Error categorization and suggestion generation
- Media file and transcript segment enrichment with computed fields
- File age calculation with human-readable relative time
- Processing time calculation and formatting

All formatting logic is centralized to ensure consistency across the application
and reduce frontend complexity while supporting both light and dark modes.

Key Features:
- Timezone-aware date/time handling
- Consistent duration formatting across MM:SS and detailed formats
- Intelligent file size formatting with appropriate precision
- Speaker name resolution with fallback handling
- Status badge CSS class generation for UI consistency
- Percentage calculations with safe division
- Cross-platform compatibility for time calculations

Example:
    Basic usage for formatting media file data:

    formatted_file = FormattingService.format_media_file(media_file, speakers)
    duration_str = FormattingService.format_duration(seconds)
    file_size_str = FormattingService.format_bytes_detailed(file_size)

Classes:
    FormattingService: Main service class providing all formatting methods.
"""

import logging
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Optional

from app.models.media import FileStatus
from app.models.media import MediaFile
from app.models.media import Speaker
from app.schemas.media import MediaFile as MediaFileSchema
from app.schemas.media import TranscriptSegment
from app.services.error_categorization_service import ErrorCategorizationService

logger = logging.getLogger(__name__)


class FormattingService:
    """Service for formatting data for frontend display."""

    @staticmethod
    def format_duration(seconds: Optional[float]) -> Optional[str]:
        """
        Format duration in seconds to MM:SS format.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string (e.g., "5:23") or None
        """
        if seconds is None or seconds <= 0:
            return None

        minutes = int(seconds // 60)
        remaining_seconds = int(seconds % 60)
        return f"{minutes}:{remaining_seconds:02d}"

    @staticmethod
    def format_duration_with_millis(seconds: Optional[float]) -> Optional[str]:
        """
        Format duration with milliseconds for timestamps.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string (e.g., "0:45.2") or None
        """
        if seconds is None or seconds < 0:
            return None

        minutes = int(seconds // 60)
        remaining_seconds = seconds % 60
        return f"{minutes}:{remaining_seconds:04.1f}"

    @staticmethod
    def format_upload_date(upload_time: Optional[datetime]) -> Optional[str]:
        """
        Format upload date for display.

        Args:
            upload_time: Upload datetime

        Returns:
            Formatted date string (e.g., "Oct 15, 2024") or None
        """
        if upload_time is None:
            return None

        return upload_time.strftime("%b %d, %Y")

    @staticmethod
    def format_status(status: FileStatus) -> str:
        """
        Format file status for display.

        Args:
            status: File status enum

        Returns:
            User-friendly status string
        """
        status_map = {
            FileStatus.PENDING: "Pending",
            FileStatus.PROCESSING: "Processing",
            FileStatus.COMPLETED: "Completed",
            FileStatus.ERROR: "Error",
            FileStatus.CANCELLING: "Cancelling",
            FileStatus.CANCELLED: "Cancelled",
            FileStatus.ORPHANED: "Needs Recovery",
        }
        return status_map.get(status, str(status))

    @staticmethod
    def create_speaker_summary(speakers: list[Speaker]) -> dict[str, Any]:
        """
        Create a summary of speakers for file listing.

        Args:
            speakers: List of Speaker objects

        Returns:
            Dictionary with speaker count and primary speakers
        """
        if not speakers:
            return {"count": 0, "primary_speakers": []}

        # Get display names, fallback to original names
        speaker_names = []
        for speaker in speakers[:3]:  # Only show first 3 speakers
            display_name = speaker.display_name or speaker.name
            speaker_names.append(display_name)

        return {"count": len(speakers), "primary_speakers": speaker_names}

    @staticmethod
    def format_media_file(
        media_file: MediaFile, speakers: Optional[list[Speaker]] = None
    ) -> MediaFileSchema:
        """
        Add formatted fields to a MediaFile object.

        Args:
            media_file: MediaFile object
            speakers: Optional list of speakers for the file

        Returns:
            MediaFileSchema with formatted fields
        """
        # Convert to schema
        file_data = MediaFileSchema.model_validate(media_file)

        # Add basic formatted fields
        file_data.formatted_duration = FormattingService.format_duration(media_file.duration)
        file_data.formatted_upload_date = FormattingService.format_upload_date(
            media_file.upload_time
        )
        file_data.formatted_file_age = FormattingService.format_file_age(media_file.upload_time)
        file_data.formatted_file_size = FormattingService.format_bytes_detailed(
            media_file.file_size
        )
        file_data.display_status = FormattingService.format_status(media_file.status)
        file_data.status_badge_class = FormattingService.get_status_badge_class(
            media_file.status.value
        )

        # Add error categorization for failed files
        if media_file.status == FileStatus.ERROR and hasattr(media_file, "last_error_message"):
            error_info = ErrorCategorizationService.get_error_info(media_file.last_error_message)
            file_data.error_category = error_info["category"]
            file_data.error_suggestions = error_info["suggestions"]
            file_data.is_retryable = error_info["is_retryable"]

        return file_data

    @staticmethod
    def format_transcript_segment(
        segment: Any, speaker_mapping: Optional[dict[str, str]] = None
    ) -> TranscriptSegment:
        """
        Add formatted fields to a TranscriptSegment.

        Args:
            segment: TranscriptSegment object
            speaker_mapping: Optional mapping of speaker labels to display names

        Returns:
            TranscriptSegment with formatted fields
        """
        # Security: Validate input segment
        if segment is None:
            raise ValueError("Segment cannot be None")

        # Convert to schema if needed (segment is a SQLAlchemy model, convert to Pydantic schema)
        try:
            segment_data = TranscriptSegment.model_validate(segment)
        except Exception as e:
            logger.error(f"Failed to validate segment data: {e}")
            raise ValueError(f"Invalid segment data: {e}") from e

        # Add formatted timestamps
        segment_data.formatted_timestamp = FormattingService.format_duration_with_millis(
            segment_data.start_time
        )
        segment_data.display_timestamp = FormattingService.format_duration_with_millis(
            segment_data.start_time
        )

        # Resolve speaker label and name
        # speaker_label ALWAYS contains the original speaker ID (e.g., "SPEAKER_01") for color consistency
        # resolved_speaker_name contains the display name for UI
        if segment_data.speaker:
            # Preserve original speaker ID in speaker_label
            segment_data.speaker_label = segment_data.speaker.name or "Unknown"
            # Set display name in resolved_speaker_name
            resolved_name = (
                segment_data.speaker.resolved_display_name
                or segment_data.speaker.display_name
                or segment_data.speaker.name
                or "Unknown"
            )
            segment_data.resolved_speaker_name = resolved_name
        elif speaker_mapping and hasattr(segment_data, "speaker_id"):
            # For segments without speaker objects, we can't preserve original ID
            # Use mapping for both fields as fallback
            resolved_name = speaker_mapping.get(str(segment_data.speaker_id), "Unknown")
            segment_data.speaker_label = resolved_name
            segment_data.resolved_speaker_name = resolved_name
        else:
            segment_data.speaker_label = "Unknown"
            segment_data.resolved_speaker_name = "Unknown"

        return segment_data

    @staticmethod
    def format_file_size(file_size: Optional[int]) -> Optional[str]:
        """
        Format file size in bytes to human-readable format.

        Args:
            file_size: File size in bytes

        Returns:
            Formatted file size string (e.g., "2.5 MB") or None
        """
        if file_size is None or file_size <= 0:
            return None

        # Convert to appropriate unit
        if file_size < 1024:
            return f"{file_size} B"
        elif file_size < 1024 * 1024:
            return f"{file_size / 1024:.1f} KB"
        elif file_size < 1024 * 1024 * 1024:
            return f"{file_size / (1024 * 1024):.1f} MB"
        else:
            return f"{file_size / (1024 * 1024 * 1024):.1f} GB"

    @staticmethod
    def format_speaker_name(speaker: Speaker) -> str:
        """
        Get the best display name for a speaker.

        Args:
            speaker: Speaker object

        Returns:
            Display name for the speaker
        """
        return speaker.display_name or speaker.name or "Unknown"

    @staticmethod
    def get_speaker_number(speaker_name: str) -> int:
        """
        Extract speaker number from SPEAKER_XX format for sorting.

        Args:
            speaker_name: Speaker name (e.g., "SPEAKER_01")

        Returns:
            Speaker number or 999 for unknown speakers
        """
        try:
            if speaker_name.startswith("SPEAKER_"):
                return int(speaker_name.split("_")[1])
        except (IndexError, ValueError):
            pass
        return 999  # Unknown speakers go to end

    @staticmethod
    def format_file_age(upload_time: Optional[datetime]) -> Optional[str]:
        """
        Format file age for display (e.g., "2 hours ago", "3 days ago").

        Args:
            upload_time: Upload datetime

        Returns:
            Formatted age string or None
        """
        if upload_time is None:
            return None

        # Security: Validate datetime is not in the future or too far in the past
        now = datetime.now(timezone.utc)

        # Ensure upload_time has timezone info
        if upload_time.tzinfo is None:
            upload_time = upload_time.replace(tzinfo=timezone.utc)

        # Security: Check for reasonable date range (not more than 100 years ago or in future)
        min_date = now.replace(year=now.year - 100)
        max_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        if upload_time < min_date:
            logger.warning(f"Upload time {upload_time} is more than 100 years ago, using fallback")
            return "Long ago"
        elif upload_time > max_date:
            logger.warning(f"Upload time {upload_time} is in the future, using fallback")
            return "Recently"

        diff = now - upload_time
        hours = diff.total_seconds() / 3600

        if hours < 1:
            minutes = int(diff.total_seconds() / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif hours < 24:
            hours_int = int(hours)
            return f"{hours_int} hour{'s' if hours_int != 1 else ''} ago"
        else:
            days = int(hours / 24)
            return f"{days} day{'s' if days != 1 else ''} ago"

    @staticmethod
    def format_detailed_duration(seconds: Optional[float]) -> Optional[str]:
        """
        Format duration with hours, minutes, and seconds for detailed display.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string (e.g., "1h 23m 45s") or None
        """
        if seconds is None or seconds <= 0:
            return None

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        remaining_seconds = int(seconds % 60)

        result = ""
        if hours > 0:
            result += f"{hours}h "
        if minutes > 0:
            result += f"{minutes}m "
        if remaining_seconds > 0 or not result:  # Always show seconds if nothing else
            result += f"{remaining_seconds}s"

        return result.strip()

    @staticmethod
    def format_bytes_detailed(file_size: Optional[int]) -> Optional[str]:
        """
        Enhanced file size formatting with more precision for larger files.

        Args:
            file_size: File size in bytes

        Returns:
            Formatted file size string with appropriate precision
        """
        if file_size is None or file_size <= 0:
            return None

        # Use 1024 as base for binary prefixes
        if file_size < 1024:
            return f"{file_size} B"
        elif file_size < 1024 * 1024:
            kb = file_size / 1024
            return f"{kb:.1f} KB" if kb < 10 else f"{int(kb)} KB"
        elif file_size < 1024 * 1024 * 1024:
            mb = file_size / (1024 * 1024)
            return f"{mb:.1f} MB" if mb < 10 else f"{int(mb)} MB"
        else:
            gb = file_size / (1024 * 1024 * 1024)
            return f"{gb:.2f} GB" if gb < 10 else f"{gb:.1f} GB"

    @staticmethod
    def get_status_badge_class(status: str) -> str:
        """
        Get CSS class for status badge styling.

        Args:
            status: File status string

        Returns:
            CSS class name for status styling
        """
        status_classes = {
            "completed": "status-completed",
            "processing": "status-processing",
            "pending": "status-pending",
            "error": "status-error",
            "cancelling": "status-cancelling",
            "cancelled": "status-cancelled",
            "orphaned": "status-orphaned",
        }
        return status_classes.get(status.lower(), "status-unknown")

    @staticmethod
    def calculate_percentage(value: float, total: float) -> float:
        """
        Calculate percentage with safe division.

        Args:
            value: The value to calculate percentage for
            total: The total value

        Returns:
            Percentage as float (0-100)
        """
        if total == 0 or value is None or total is None:
            return 0.0
        return min(100.0, max(0.0, (value / total) * 100))

    @staticmethod
    def format_processing_time(
        created_at: Optional[datetime], completed_at: Optional[datetime]
    ) -> Optional[str]:
        """
        Format the time taken to process a task.

        Args:
            created_at: Task creation time
            completed_at: Task completion time

        Returns:
            Formatted processing time or None
        """
        if not created_at:
            return None

        end_time = completed_at or datetime.now(timezone.utc)

        # Ensure timezone info
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        # Security: Validate reasonable time range
        duration_seconds = (end_time - created_at).total_seconds()

        # Negative duration indicates completion before creation (data error)
        if duration_seconds < 0:
            logger.warning(
                f"Negative duration detected: created_at={created_at}, completed_at={end_time}"
            )
            return "Unknown"

        # Extremely long durations (more than 7 days) might indicate stuck tasks
        max_duration = 7 * 24 * 3600  # 7 days in seconds
        if duration_seconds > max_duration:
            logger.warning(f"Unusually long processing time: {duration_seconds} seconds")
            return "More than 7 days"

        return FormattingService.format_detailed_duration(duration_seconds)
