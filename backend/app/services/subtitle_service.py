"""
Subtitle generation service for creating SRT files from transcript segments.
Handles movie-style formatting with proper line lengths and speaker labels.
Supports overlapping speech display where multiple speakers talk simultaneously.
"""

import re
import textwrap
from collections import defaultdict

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
    def _get_speaker_prefix(speaker_name: str | None) -> str:
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
    def _group_overlapping_segments(
        segments: list[TranscriptSegment],
    ) -> list[list[TranscriptSegment]]:
        """Group segments by overlap_group_id for merged display.

        Returns a list of segment groups. Non-overlapping segments are in
        single-element lists, while overlapping segments are grouped together.
        """
        overlap_groups: dict[str, list[TranscriptSegment]] = defaultdict(list)
        non_overlap_segments: list[tuple[int, TranscriptSegment]] = []

        # Separate overlapping and non-overlapping segments
        for idx, segment in enumerate(segments):
            if segment.overlap_group_id:
                overlap_groups[str(segment.overlap_group_id)].append(segment)
            else:
                non_overlap_segments.append((idx, segment))

        # Build result maintaining original order
        processed_overlap_ids: set[str] = set()
        result_with_positions: list[tuple[float, list[TranscriptSegment]]] = []

        for segment in segments:
            if segment.overlap_group_id:
                group_id = str(segment.overlap_group_id)
                if group_id not in processed_overlap_ids:
                    processed_overlap_ids.add(group_id)
                    group = overlap_groups[group_id]
                    # Use the earliest start time for positioning
                    min_start = min(float(s.start_time) for s in group)
                    result_with_positions.append((min_start, group))
            else:
                result_with_positions.append((float(segment.start_time), [segment]))

        # Sort by start time and return just the groups
        result_with_positions.sort(key=lambda x: x[0])
        return [group for _, group in result_with_positions]

    @staticmethod
    def _format_overlap_for_subtitle(
        segments: list[TranscriptSegment],
        speaker_map: dict[int, str],
        format_type: str = "srt",
    ) -> tuple[float, float, str]:
        """Format overlapping segments as a single subtitle cue with speaker labels.

        Returns (start_time, end_time, formatted_text).
        """
        # Get time range spanning all segments
        start_time = min(float(s.start_time) for s in segments)
        end_time = max(float(s.end_time) for s in segments)

        # Format each speaker's text with their label
        lines = []
        for segment in sorted(segments, key=lambda s: float(s.start_time)):
            speaker_name = (
                speaker_map.get(segment.speaker_id, "Unknown") if segment.speaker_id else "Unknown"  # type: ignore[call-overload]
            )
            text = str(segment.text).strip()
            lines.append(f"[{speaker_name}] {text}")

        return start_time, end_time, "\n".join(lines)

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
        text: str, speaker_name: str | None = None, format_type: str = "srt"
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
        speaker_name: str | None = None,
        format_type: str = "srt",
    ) -> list[tuple[float, float, str]]:
        """Split long transcript segments into properly timed subtitle chunks with speaker continuity."""
        text = str(segment.text).strip()
        duration = float(segment.end_time) - float(segment.start_time)

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
                    float(segment.start_time),
                    float(segment.start_time) + actual_duration,
                    formatted_subtitles[0],
                )
            ]

        # Handle multiple subtitle parts with proper timing distribution
        subtitle_parts: list[tuple[float, float, str]] = []
        total_chars = sum(len(subtitle) for subtitle in formatted_subtitles)

        current_time = float(segment.start_time)
        segment_end_time = float(segment.end_time)
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
            if end_time > segment_end_time:
                end_time = segment_end_time

            # Ensure minimum gap between subtitles for readability
            if i < len(formatted_subtitles) - 1:  # Not the last subtitle
                min_gap = 0.1  # 100ms gap
                if end_time + min_gap > segment_end_time:
                    end_time = segment_end_time - min_gap

            subtitle_parts.append((current_time, end_time, subtitle_text))
            current_time = end_time + 0.1  # Small gap between subtitles

            # Prevent overlapping with segment end
            if current_time >= segment_end_time:
                break

        return subtitle_parts

    @staticmethod
    def generate_webvtt_content(
        db: Session, media_file_id: int, include_speakers: bool = True
    ) -> str:
        """Generate WebVTT subtitle content from transcript segments.

        Handles overlapping speech by merging segments with the same overlap_group_id
        into a single subtitle cue with speaker labels on separate lines.
        """
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

        # Build speaker map for quick lookup
        speaker_map: dict[int, str] = {}
        if include_speakers:
            speaker_ids = {s.speaker_id for s in segments if s.speaker_id}
            speakers = db.query(Speaker).filter(Speaker.id.in_(speaker_ids)).all()
            for speaker in speakers:
                speaker_map[speaker.id] = (  # type: ignore[index]
                    str(speaker.display_name) if speaker.display_name else str(speaker.name)
                )

        # Group overlapping segments
        segment_groups = SubtitleService._group_overlapping_segments(segments)

        # Start WebVTT content
        webvtt_content = "WEBVTT\n\n"

        for group in segment_groups:
            if len(group) > 1:
                # Overlapping segments - merge into single cue
                start_time, end_time, text = SubtitleService._format_overlap_for_subtitle(
                    group, speaker_map, "webvtt"
                )
                start_timestamp = SubtitleService.format_timestamp(start_time).replace(",", ".")
                end_timestamp = SubtitleService.format_timestamp(end_time).replace(",", ".")

                webvtt_content += f"{start_timestamp} --> {end_timestamp}\n{text}\n\n"
            else:
                # Single segment - process normally
                segment = group[0]
                speaker_name = speaker_map.get(segment.speaker_id) if segment.speaker_id else None  # type: ignore[call-overload]

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
        """Generate SRT subtitle content from transcript segments.

        Handles overlapping speech by merging segments with the same overlap_group_id
        into a single subtitle cue with speaker labels on separate lines.
        """
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

        # Build speaker map for quick lookup
        speaker_map: dict[int, str] = {}
        if include_speakers:
            speaker_ids = {s.speaker_id for s in segments if s.speaker_id}
            speakers = db.query(Speaker).filter(Speaker.id.in_(speaker_ids)).all()
            for speaker in speakers:
                speaker_map[speaker.id] = (  # type: ignore[index]
                    str(speaker.display_name) if speaker.display_name else str(speaker.name)
                )

        # Group overlapping segments
        segment_groups = SubtitleService._group_overlapping_segments(segments)

        srt_content = []
        subtitle_index = 1

        for group in segment_groups:
            if len(group) > 1:
                # Overlapping segments - merge into single cue
                start_time, end_time, text = SubtitleService._format_overlap_for_subtitle(
                    group, speaker_map, "srt"
                )
                start_timestamp = SubtitleService.format_timestamp(start_time)
                end_timestamp = SubtitleService.format_timestamp(end_time)

                srt_entry = f"{subtitle_index}\n{start_timestamp} --> {end_timestamp}\n{text}\n"
                srt_content.append(srt_entry)
                subtitle_index += 1
            else:
                # Single segment - process normally
                segment = group[0]
                speaker_name = speaker_map.get(segment.speaker_id) if segment.speaker_id else None  # type: ignore[call-overload]

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
        output_path: str | None = None,
    ) -> str:
        """Generate SRT file and optionally save to disk."""
        srt_content = SubtitleService.generate_srt_content(db, media_file_id, include_speakers)

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(srt_content)

        return srt_content

    @staticmethod
    def format_timestamp_simple(seconds: float) -> str:
        """Convert seconds to simple MM:SS or HH:MM:SS format."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    @staticmethod
    def generate_txt_content(db: Session, media_file_id: int, include_speakers: bool = True) -> str:
        """Generate plain text transcript with timestamps and speaker labels.

        For overlapping speech, formats as:
        [00:02:15 - 00:02:20] OVERLAPPING SPEECH:
          Alice (00:02:15 - 00:02:18): That's a great idea but--
          Bob (00:02:16 - 00:02:20): I completely disagree!
        """
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

        # Build speaker map for quick lookup
        speaker_map: dict[int, str] = {}
        if include_speakers:
            speaker_ids = {s.speaker_id for s in segments if s.speaker_id}
            speakers = db.query(Speaker).filter(Speaker.id.in_(speaker_ids)).all()
            for speaker in speakers:
                speaker_map[speaker.id] = (  # type: ignore[index]
                    str(speaker.display_name) if speaker.display_name else str(speaker.name)
                )

        # Group overlapping segments
        segment_groups = SubtitleService._group_overlapping_segments(segments)

        txt_lines = []

        for group in segment_groups:
            if len(group) > 1:
                # Overlapping segments - format as special block
                group_start = min(float(s.start_time) for s in group)
                group_end = max(float(s.end_time) for s in group)

                start_ts = SubtitleService.format_timestamp_simple(group_start)
                end_ts = SubtitleService.format_timestamp_simple(group_end)

                txt_lines.append(f"[{start_ts} - {end_ts}] OVERLAPPING SPEECH:")

                for segment in sorted(group, key=lambda s: float(s.start_time)):
                    speaker_name = (
                        speaker_map.get(segment.speaker_id, "Unknown")  # type: ignore[call-overload]
                        if segment.speaker_id
                        else "Unknown"
                    )
                    seg_start = SubtitleService.format_timestamp_simple(float(segment.start_time))
                    seg_end = SubtitleService.format_timestamp_simple(float(segment.end_time))
                    text = str(segment.text).strip()

                    if include_speakers:
                        txt_lines.append(f"  {speaker_name} ({seg_start} - {seg_end}): {text}")
                    else:
                        txt_lines.append(f"  ({seg_start} - {seg_end}): {text}")

                txt_lines.append("")  # Empty line after overlap block
            else:
                # Single segment
                segment = group[0]
                speaker_name = (
                    speaker_map.get(segment.speaker_id, "Unknown")  # type: ignore[call-overload]
                    if segment.speaker_id
                    else "Unknown"
                )
                start_ts = SubtitleService.format_timestamp_simple(float(segment.start_time))
                end_ts = SubtitleService.format_timestamp_simple(float(segment.end_time))
                text = str(segment.text).strip()

                if include_speakers:
                    txt_lines.append(f"[{start_ts} - {end_ts}] {speaker_name}: {text}")
                else:
                    txt_lines.append(f"[{start_ts} - {end_ts}] {text}")

        return "\n".join(txt_lines)

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
            start_time = float(segment.start_time)
            end_time = float(segment.end_time)

            # Check for negative duration
            if end_time <= start_time:
                issues.append(f"Segment {i + 1}: Invalid duration (end <= start)")

            # Check for overlapping segments
            if start_time < prev_end:
                issues.append(f"Segment {i + 1}: Overlaps with previous segment")

            # Check for extremely short segments
            duration = end_time - start_time
            if duration < 0.1:  # Less than 100ms
                issues.append(f"Segment {i + 1}: Very short duration ({duration:.2f}s)")

            prev_end = end_time

        return issues
