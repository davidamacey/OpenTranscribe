"""Audio loading for the transcription pipeline.

Uses faster_whisper.decode_audio() which is the same function WhisperX
calls internally via whisperx.load_audio().
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000


def load_audio(file_path: str) -> np.ndarray:
    """Load audio as 16kHz mono float32 numpy array.

    Args:
        file_path: Path to the audio file.

    Returns:
        Audio waveform as numpy array, shape (samples,).

    Raises:
        ValueError: If audio is empty, too short, or cannot be loaded.
    """
    from faster_whisper.audio import decode_audio

    logger.info(f"Loading audio: {file_path}")
    try:
        audio = decode_audio(file_path, sampling_rate=SAMPLE_RATE)
    except Exception as e:
        raise ValueError(
            f"Unable to load audio content. The file may be corrupted, "
            f"in an unsupported format, or contain no audio data: {e}"
        ) from e

    if audio is None or len(audio) == 0:
        raise ValueError("Audio file appears to be empty or corrupted")

    duration = len(audio) / SAMPLE_RATE
    if duration < 0.1:
        raise ValueError("Audio file is too short to contain meaningful content")

    logger.info(f"Audio loaded: {duration:.1f}s ({len(audio)} samples)")
    return audio
