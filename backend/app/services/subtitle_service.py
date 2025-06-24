"""
Subtitle generation service for creating SRT files from transcript segments.
Handles movie-style formatting with proper line lengths and speaker labels.
"""

import re
import textwrap
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.media import MediaFile, TranscriptSegment, Speaker


class SubtitleService:
    """Service for generating subtitle files from transcript data."""
    
    # Movie-style subtitle formatting constants
    MAX_LINE_LENGTH = 42  # Optimal for readability
    MAX_LINES_PER_SUBTITLE = 2
    MIN_DISPLAY_TIME = 1.0  # Minimum 1 second display time
    MAX_DISPLAY_TIME = 6.0  # Maximum 6 seconds display time
    READING_SPEED_WPM = 200  # Words per minute for subtitle timing
    
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
        # Calculate time needed based on reading speed
        reading_time = (word_count / SubtitleService.READING_SPEED_WPM) * 60
        # Add base time for short texts and cap at maximum
        optimal_time = max(reading_time + 0.5, SubtitleService.MIN_DISPLAY_TIME)
        return min(optimal_time, SubtitleService.MAX_DISPLAY_TIME)
    
    @staticmethod
    def format_text_for_subtitles(text: str, speaker_name: Optional[str] = None) -> List[str]:
        """Format text for movie-style subtitles with proper line breaks and speaker continuity."""
        # Clean the text
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
        
        # Format speaker name once
        speaker_prefix = ""
        if speaker_name and speaker_name.upper() != "UNKNOWN":
            # Format speaker name (remove SPEAKER_ prefix if present)
            clean_name = re.sub(r'^SPEAKER_\d+', '', speaker_name).strip()
            if clean_name:
                speaker_prefix = f"{clean_name}: "
        
        # If text with speaker prefix fits in one line, return as single subtitle
        full_text = f"{speaker_prefix}{text}"
        if len(full_text) <= SubtitleService.MAX_LINE_LENGTH:
            return [full_text]
        
        # For longer text, handle speaker continuity properly
        formatted_subtitles = []
        
        # Split text into sentences for better breaking points
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        current_subtitle = ""
        current_lines = []
        
        for sentence in sentences:
            # Check if we need to start a new subtitle
            if current_subtitle:
                # Test if adding this sentence would exceed limits
                test_text = f"{current_subtitle} {sentence}"
                test_lines = textwrap.wrap(
                    test_text, 
                    width=SubtitleService.MAX_LINE_LENGTH,
                    break_long_words=False,
                    break_on_hyphens=False
                )
                
                if len(test_lines) > SubtitleService.MAX_LINES_PER_SUBTITLE:
                    # Finalize current subtitle
                    subtitle_lines = textwrap.wrap(
                        current_subtitle,
                        width=SubtitleService.MAX_LINE_LENGTH,
                        break_long_words=False,
                        break_on_hyphens=False
                    )
                    
                    # Add speaker prefix only to first subtitle
                    if not formatted_subtitles and speaker_prefix:
                        subtitle_lines[0] = f"{speaker_prefix}{subtitle_lines[0]}"
                    
                    formatted_subtitles.append('\n'.join(subtitle_lines[:SubtitleService.MAX_LINES_PER_SUBTITLE]))
                    current_subtitle = sentence
                else:
                    current_subtitle = test_text
            else:
                current_subtitle = sentence
        
        # Handle remaining text
        if current_subtitle:
            subtitle_lines = textwrap.wrap(
                current_subtitle,
                width=SubtitleService.MAX_LINE_LENGTH,
                break_long_words=False,
                break_on_hyphens=False
            )
            
            # Add speaker prefix only to first subtitle if no previous subtitles
            if not formatted_subtitles and speaker_prefix:
                subtitle_lines[0] = f"{speaker_prefix}{subtitle_lines[0]}"
            
            # Split into multiple subtitles if needed
            for i in range(0, len(subtitle_lines), SubtitleService.MAX_LINES_PER_SUBTITLE):
                subtitle_chunk = subtitle_lines[i:i + SubtitleService.MAX_LINES_PER_SUBTITLE]
                formatted_subtitles.append('\n'.join(subtitle_chunk))
        
        return formatted_subtitles if formatted_subtitles else [full_text]
    
    @staticmethod
    def split_long_segment(
        segment: TranscriptSegment, 
        speaker_name: Optional[str] = None
    ) -> List[Tuple[float, float, str]]:
        """Split long transcript segments into properly timed subtitle chunks with speaker continuity."""
        text = segment.text.strip()
        duration = segment.end_time - segment.start_time
        
        # Format text and handle multi-part subtitles
        formatted_subtitles = SubtitleService.format_text_for_subtitles(text, speaker_name)
        
        # If only one subtitle, return as-is
        if len(formatted_subtitles) == 1:
            optimal_duration = SubtitleService.calculate_optimal_display_time(text)
            actual_duration = min(duration, optimal_duration)
            return [(segment.start_time, segment.start_time + actual_duration, formatted_subtitles[0])]
        
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
            actual_duration = min(max(allocated_time, SubtitleService.MIN_DISPLAY_TIME), optimal_duration)
            
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
    def generate_srt_content(
        db: Session, 
        media_file_id: int,
        include_speakers: bool = True
    ) -> str:
        """Generate SRT subtitle content from transcript segments."""
        # Get media file and transcript segments
        media_file = db.query(MediaFile).filter(MediaFile.id == media_file_id).first()
        if not media_file:
            raise ValueError(f"Media file with ID {media_file_id} not found")
        
        # Get all transcript segments ordered by start time
        segments = db.query(TranscriptSegment).filter(
            TranscriptSegment.media_file_id == media_file_id
        ).order_by(TranscriptSegment.start_time).all()
        
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
            subtitle_parts = SubtitleService.split_long_segment(segment, speaker_name)
            
            for start_time, end_time, text in subtitle_parts:
                # Format SRT entry
                start_timestamp = SubtitleService.format_timestamp(start_time)
                end_timestamp = SubtitleService.format_timestamp(end_time)
                
                srt_entry = f"{subtitle_index}\n{start_timestamp} --> {end_timestamp}\n{text}\n"
                srt_content.append(srt_entry)
                subtitle_index += 1
        
        return '\n'.join(srt_content)
    
    @staticmethod
    def generate_srt_file(
        db: Session, 
        media_file_id: int,
        include_speakers: bool = True,
        output_path: Optional[str] = None
    ) -> str:
        """Generate SRT file and optionally save to disk."""
        srt_content = SubtitleService.generate_srt_content(
            db, media_file_id, include_speakers
        )
        
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(srt_content)
        
        return srt_content
    
    @staticmethod
    def validate_subtitle_timing(
        db: Session, 
        media_file_id: int
    ) -> List[str]:
        """Validate subtitle timing and return any issues found."""
        issues = []
        
        segments = db.query(TranscriptSegment).filter(
            TranscriptSegment.media_file_id == media_file_id
        ).order_by(TranscriptSegment.start_time).all()
        
        prev_end = 0.0
        for i, segment in enumerate(segments):
            # Check for negative duration
            if segment.end_time <= segment.start_time:
                issues.append(f"Segment {i+1}: Invalid duration (end <= start)")
            
            # Check for overlapping segments
            if segment.start_time < prev_end:
                issues.append(f"Segment {i+1}: Overlaps with previous segment")
            
            # Check for extremely short segments
            duration = segment.end_time - segment.start_time
            if duration < 0.1:  # Less than 100ms
                issues.append(f"Segment {i+1}: Very short duration ({duration:.2f}s)")
            
            prev_end = segment.end_time
        
        return issues