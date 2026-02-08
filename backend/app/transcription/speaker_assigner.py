"""Thin wrapper around the existing fast_speaker_assignment module.

Provides a clean interface for the transcription pipeline while reusing
the interval-tree + NumPy speaker assignment implementation.
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def assign_speakers(
    diarize_df: pd.DataFrame,
    transcript_result: dict,
) -> dict:
    """Assign speaker labels to transcript segments and words.

    Uses the existing fast_speaker_assignment module (interval tree + NumPy,
    273x faster than WhisperX's implementation).

    fill_nearest=True ensures segments in small diarization gaps (e.g.,
    between speaker turns) get the nearest speaker instead of being
    left unassigned.

    Args:
        diarize_df: Diarization DataFrame with columns [segment, label, speaker, start, end].
        transcript_result: Dict with "segments" key containing transcript segments.

    Returns:
        Updated transcript_result with speaker assignments on segments and words.
    """
    from app.utils.fast_speaker_assignment import assign_word_speakers_fast

    return assign_word_speakers_fast(diarize_df, transcript_result, fill_nearest=True)
