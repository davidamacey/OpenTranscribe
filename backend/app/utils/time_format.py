"""Shared timestamp formatting utilities.

Provides canonical implementations for timestamp formatting used across
the application (transcript segments, file endpoints, subtitle generation).
"""


def format_timestamp_simple(seconds: float) -> str:
    """Format seconds as MM:SS or H:MM:SS for display.

    Args:
        seconds: Time value in seconds.

    Returns:
        Formatted timestamp string (e.g. "3:45" or "1:03:45").
    """
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes >= 60:
        hours = minutes // 60
        minutes = minutes % 60
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_srt_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS,mmm for SRT subtitles.

    Args:
        seconds: Time value in seconds.

    Returns:
        Formatted SRT timestamp string (e.g. "00:03:45,123").
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
