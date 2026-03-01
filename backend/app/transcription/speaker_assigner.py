"""Speaker assignment using WhisperX's diarize module.

Delegates to whisperx.diarize.assign_word_speakers() which computes
speaker-segment overlap via pandas vectorized operations.
"""

import pandas as pd


def assign_speakers(
    diarize_df: pd.DataFrame,
    transcript_result: dict,
) -> dict:
    """Assign speaker labels to transcript segments and words.

    Uses WhisperX's assign_word_speakers() which computes overlap between
    diarization intervals and transcript segments using pandas operations.

    fill_nearest=True ensures segments in small diarization gaps (e.g.,
    between speaker turns) get the nearest speaker instead of being
    left unassigned.

    Args:
        diarize_df: Diarization DataFrame with columns [segment, label, speaker, start, end].
        transcript_result: Dict with "segments" key containing transcript segments.

    Returns:
        Updated transcript_result with speaker assignments on segments and words.
    """
    from whisperx.diarize import assign_word_speakers

    return assign_word_speakers(diarize_df, transcript_result, fill_nearest=True)  # type: ignore[no-any-return]
