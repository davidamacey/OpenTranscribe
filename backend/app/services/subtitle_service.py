"""
Subtitle generation service for creating SRT files from transcript segments.
Handles movie-style formatting with proper line lengths and speaker labels.
"""

import re
import textwrap
from typing import Optional

from sqlalchemy.orm import Session

from app.models.media import MediaFile
from app.models.media import Speaker
from app.models.media import TranscriptSegment


class SubtitleService:
    """Service for generating subtitle files from transcript data."""

    # Movie-style subtitle formatting constants (industry standards)
    MAX_LINE_LENGTH = 42  # Optimal for readability
    MAX_LINES_PER_SUBTITLE = 2
    MIN_DISPLAY_TIME = 1.0  # Minimum 1 second display time
    MAX_DISPLAY_TIME = 6.0  # Maximum 6 seconds display time
    READING_SPEED_WPM = 200  # Words per minute for subtitle timing
    MAX_CHARS_PER_SECOND = 20  # Maximum 20 characters per second for comfortable reading

    @staticmethod
    def format_timestamp(seconds: float) -> str:
        """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

    @staticmethod
    def calculate_optimal_display_time(text: str) -> float:
        """Calculate optimal display time based on text length and reading speed."""
        word_count = len(text.split())
        char_count = len(text)

        # Calculate time needed based on reading speed (words per minute)
        reading_time = (word_count / SubtitleService.READING_SPEED_WPM) * 60

        # Also check character-per-second limit (industry standard)
        chars_per_second_time = char_count / SubtitleService.MAX_CHARS_PER_SECOND

        # Use the longer of the two to ensure comfortable reading
        optimal_time = max(reading_time + 0.5, chars_per_second_time)

        # Apply min/max constraints
        optimal_time = max(optimal_time, SubtitleService.MIN_DISPLAY_TIME)
        return min(optimal_time, SubtitleService.MAX_DISPLAY_TIME)

    @staticmethod
    def _get_speaker_prefix(speaker_name: Optional[str]) -> str:
        """Get formatted speaker prefix from speaker name."""
        if not speaker_name or speaker_name.upper() == "UNKNOWN":
            return ""
        clean_name = speaker_name.strip()
        return f"{clean_name}: " if clean_name else ""

    @staticmethod
    def _wrap_text(text: str) -> list[str]:
        """Wrap text to subtitle line length constraints."""
        return textwrap.wrap(
            text,
            width=SubtitleService.MAX_LINE_LENGTH,
            break_long_words=False,
            break_on_hyphens=False,
        )

    @staticmethod
    def _create_subtitle_block(lines: list[str], speaker_prefix: str) -> str:
        """Create a subtitle block from lines, adding speaker prefix to first line."""
        block_lines = lines[: SubtitleService.MAX_LINES_PER_SUBTITLE]
        if speaker_prefix:
            block_lines[0] = f"{speaker_prefix}{block_lines[0]}"
        return "\n".join(block_lines)

    @staticmethod
    def _process_sentence(
        sentence: str,
        current_subtitle: str,
        speaker_prefix: str,
        formatted_subtitles: list[str],
    ) -> str:
        """Process a sentence and add to subtitles if needed. Returns updated current_subtitle."""
        if not current_subtitle:
            return sentence

        test_text = f"{current_subtitle} {sentence}"
        test_lines = SubtitleService._wrap_text(test_text)

        if len(test_lines) <= SubtitleService.MAX_LINES_PER_SUBTITLE:
            return test_text

        # Finalize current subtitle and start new one
        subtitle_lines = SubtitleService._wrap_text(current_subtitle)
        formatted_subtitles.append(
            SubtitleService._create_subtitle_block(subtitle_lines, speaker_prefix)
        )
        return sentence

    @staticmethod
    def _finalize_remaining_text(
        current_subtitle: str, speaker_prefix: str, formatted_subtitles: list[str]
    ) -> None:
        """Process remaining text into subtitle blocks."""
        if not current_subtitle:
            return

        subtitle_lines = SubtitleService._wrap_text(current_subtitle)
        for i in range(0, len(subtitle_lines), SubtitleService.MAX_LINES_PER_SUBTITLE):
            chunk = subtitle_lines[i : i + SubtitleService.MAX_LINES_PER_SUBTITLE]
            formatted_subtitles.append(
                SubtitleService._create_subtitle_block(chunk, speaker_prefix)
            )

    @staticmethod
    def format_text_for_subtitles(
        text: str, speaker_name: Optional[str] = None, format_type: str = "srt"
    ) -> list[str]:
        """Format text for movie-style subtitles with proper line breaks and speaker continuity."""
        # Clean the text
        text = re.sub(r"\s+", " ", text.strip())

        # Get speaker prefix
        speaker_prefix = SubtitleService._get_speaker_prefix(speaker_name)

        # If text with speaker prefix fits in one line, return as single subtitle
        full_text = f"{speaker_prefix}{text}"
        if len(full_text) <= SubtitleService.MAX_LINE_LENGTH:
            return [full_text]

        # For longer text, process sentences into subtitle blocks
        formatted_subtitles: list[str] = []
        sentences = re.split(r"(?<=[.!?])\s+", text)
        current_subtitle = ""

        for sentence in sentences:
            current_subtitle = SubtitleService._process_sentence(
                sentence, current_subtitle, speaker_prefix, formatted_subtitles
            )

        # Handle remaining text
        SubtitleService._finalize_remaining_text(
            current_subtitle, speaker_prefix, formatted_subtitles
        )

        return formatted_subtitles if formatted_subtitles else [full_text]

    @staticmethod
    def split_long_segment(
        segment: TranscriptSegment,
        speaker_name: Optional[str] = None,
        format_type: str = "srt",
    ) -> list[tuple[float, float, str]]:
        """Split long transcript segments into properly timed subtitle chunks with speaker continuity."""
        text = segment.text.strip()
        duration = segment.end_time - segment.start_time

        # Format text and handle multi-part subtitles
        formatted_subtitles = SubtitleService.format_text_for_subtitles(
            text, speaker_name, format_type
        )

        # If only one subtitle, return as-is
        if len(formatted_subtitles) == 1:
            optimal_duration = SubtitleService.calculate_optimal_display_time(text)
            actual_duration = min(duration, optimal_duration)
            return [
                (
                    segment.start_time,
                    segment.start_time + actual_duration,
                    formatted_subtitles[0],
                )
            ]

        # Handle multiple subtitle parts with proper timing distribution
        subtitle_parts = []
        total_chars = sum(len(subtitle) for subtitle in formatted_subtitles)

        current_time = segment.start_time
        for i, subtitle_text in enumerate(formatted_subtitles):
            # Calculate time allocation based on text length (proportional distribution)
            text_ratio = len(subtitle_text) / total_chars
            allocated_time = duration * text_ratio

            # Apply minimum and maximum display time constraints
            optimal_duration = SubtitleService.calculate_optimal_display_time(subtitle_text)
            actual_duration = min(
                max(allocated_time, SubtitleService.MIN_DISPLAY_TIME), optimal_duration
            )

            end_time = current_time + actual_duration

            # Ensure we don't exceed the original segment end time
            if end_time > segment.end_time:
                end_time = segment.end_time

            # Ensure minimum gap between subtitles for readability
            if i < len(formatted_subtitles) - 1:  # Not the last subtitle
                min_gap = 0.1  # 100ms gap
                if end_time + min_gap > segment.end_time:
                    end_time = segment.end_time - min_gap

            subtitle_parts.append((current_time, end_time, subtitle_text))
            current_time = end_time + 0.1  # Small gap between subtitles

            # Prevent overlapping with segment end
            if current_time >= segment.end_time:
                break

        return subtitle_parts

    @staticmethod
    def generate_webvtt_content(
        db: Session, media_file_id: int, include_speakers: bool = True
    ) -> str:
        """Generate WebVTT subtitle content from transcript segments."""
        # Get media file and transcript segments
        media_file = db.query(MediaFile).filter(MediaFile.id == media_file_id).first()
        if not media_file:
            raise ValueError(f"Media file with ID {media_file_id} not found")

        # Get all transcript segments ordered by start time
        segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.media_file_id == media_file_id)
            .order_by(TranscriptSegment.start_time)
            .all()
        )

        if not segments:
            raise ValueError("No transcript segments found for this media file")

        # Start WebVTT content
        webvtt_content = "WEBVTT\n\n"

        for segment in segments:
            speaker_name = None
            if include_speakers and segment.speaker_id:
                speaker = db.query(Speaker).filter(Speaker.id == segment.speaker_id).first()
                if speaker:
                    # Use display name if available, otherwise use original name
                    speaker_name = speaker.display_name or speaker.name

            # Split long segments into properly formatted subtitles for WebVTT
            subtitle_parts = SubtitleService.split_long_segment(segment, speaker_name, "webvtt")

            for start_time, end_time, text in subtitle_parts:
                # Format WebVTT timestamps (using dots instead of commas)
                start_timestamp = SubtitleService.format_timestamp(start_time).replace(",", ".")
                end_timestamp = SubtitleService.format_timestamp(end_time).replace(",", ".")

                # Add WebVTT cue
                webvtt_content += f"{start_timestamp} --> {end_timestamp}\n{text}\n\n"

        return webvtt_content

    @staticmethod
    def generate_srt_content(db: Session, media_file_id: int, include_speakers: bool = True) -> str:
        """Generate SRT subtitle content from transcript segments."""
        # Get media file and transcript segments
        media_file = db.query(MediaFile).filter(MediaFile.id == media_file_id).first()
        if not media_file:
            raise ValueError(f"Media file with ID {media_file_id} not found")

        # Get all transcript segments ordered by start time
        segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.media_file_id == media_file_id)
            .order_by(TranscriptSegment.start_time)
            .all()
        )

        if not segments:
            raise ValueError("No transcript segments found for this media file")

        srt_content = []
        subtitle_index = 1

        for segment in segments:
            speaker_name = None
            if include_speakers and segment.speaker_id:
                speaker = db.query(Speaker).filter(Speaker.id == segment.speaker_id).first()
                if speaker:
                    # Use display name if available, otherwise use original name
                    speaker_name = speaker.display_name or speaker.name

            # Split long segments into properly formatted subtitles
            subtitle_parts = SubtitleService.split_long_segment(segment, speaker_name, "srt")

            for start_time, end_time, text in subtitle_parts:
                # Format SRT entry
                start_timestamp = SubtitleService.format_timestamp(start_time)
                end_timestamp = SubtitleService.format_timestamp(end_time)

                srt_entry = f"{subtitle_index}\n{start_timestamp} --> {end_timestamp}\n{text}\n"
                srt_content.append(srt_entry)
                subtitle_index += 1

        return "\n".join(srt_content)

    @staticmethod
    def generate_srt_file(
        db: Session,
        media_file_id: int,
        include_speakers: bool = True,
        output_path: Optional[str] = None,
    ) -> str:
        """Generate SRT file and optionally save to disk."""
        srt_content = SubtitleService.generate_srt_content(db, media_file_id, include_speakers)

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(srt_content)

        return srt_content

    @staticmethod
    def validate_subtitle_timing(db: Session, media_file_id: int) -> list[str]:
        """Validate subtitle timing and return any issues found."""
        issues = []

        segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.media_file_id == media_file_id)
            .order_by(TranscriptSegment.start_time)
            .all()
        )

        prev_end = 0.0
        for i, segment in enumerate(segments):
            # Check for negative duration
            if segment.end_time <= segment.start_time:
                issues.append(f"Segment {i + 1}: Invalid duration (end <= start)")

            # Check for overlapping segments
            if segment.start_time < prev_end:
                issues.append(f"Segment {i + 1}: Overlaps with previous segment")

            # Check for extremely short segments
            duration = segment.end_time - segment.start_time
            if duration < 0.1:  # Less than 100ms
                issues.append(f"Segment {i + 1}: Very short duration ({duration:.2f}s)")

            prev_end = segment.end_time

        return issues
