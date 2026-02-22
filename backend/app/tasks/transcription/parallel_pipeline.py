"""
Parallel Pipeline Execution

Runs WhisperX transcription and PyAnnote diarization concurrently using threads.
Both operations need only the audio array as input and are independent, making
them safe to parallelize.

VRAM requirements:
- Transcription (large-v3-turbo): ~6GB
- Diarization (PyAnnote v4): ~2-3GB
- Combined: ~9GB (safe for 12GB+ GPUs)

Enable with PIPELINE_MODE=parallel environment variable.
Requires 12GB+ VRAM. Falls back to sequential if insufficient.
"""

import logging
import os
import threading
import time
from typing import Any
from typing import Callable
from typing import Optional

logger = logging.getLogger(__name__)

# Minimum free VRAM (MB) required to run parallel mode
MIN_PARALLEL_VRAM_MB = 10_000


def get_pipeline_mode() -> str:
    """Get configured pipeline mode from environment.

    Returns:
        'parallel' or 'sequential'
    """
    return os.getenv("PIPELINE_MODE", "sequential").lower()


def can_run_parallel() -> bool:
    """Check if sufficient VRAM is available for parallel execution.

    Returns:
        True if parallel mode is safe to attempt.
    """
    try:
        import torch

        if not torch.cuda.is_available():
            logger.info("Parallel pipeline: CUDA not available, using sequential")
            return False

        free_vram = (
            torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated(0)
        ) / (1024**2)

        if free_vram < MIN_PARALLEL_VRAM_MB:
            logger.warning(
                f"Parallel pipeline: insufficient VRAM ({free_vram:.0f}MB free, "
                f"need {MIN_PARALLEL_VRAM_MB}MB), falling back to sequential"
            )
            return False

        logger.info(f"Parallel pipeline: {free_vram:.0f}MB VRAM available, proceeding")
        return True

    except Exception as e:
        logger.warning(f"Parallel pipeline: VRAM check failed ({e}), using sequential")
        return False


class ThreadSafeProgress:
    """Thread-safe wrapper for progress callbacks."""

    def __init__(self, callback: Optional[Callable] = None):
        self._callback = callback
        self._lock = threading.Lock()

    def report(self, progress: float, message: str) -> None:
        """Report progress in a thread-safe manner."""
        if self._callback:
            with self._lock:
                self._callback(progress, message)


class _StepResult:
    """Container for a pipeline step result with error tracking."""

    def __init__(self):
        self.result: Any = None
        self.error: Optional[Exception] = None
        self.duration_s: float = 0.0


def run_parallel_pipeline(
    whisperx_service: Any,
    audio_file_path: str,
    audio: Any,
    transcription_result: dict[str, Any],
    hf_token: Optional[str] = None,
    min_speakers: int = 1,
    max_speakers: int = 20,
    num_speakers: Optional[int] = None,
    progress: Optional[ThreadSafeProgress] = None,
    enable_overlap_detection: bool = True,
    overlap_min_duration: float = 0.25,
) -> tuple[dict[str, Any], Any]:
    """Run alignment/skip and diarization in parallel threads.

    Transcription has already been run (since alignment needs its output).
    This parallelizes the remaining independent steps:
    - Thread 1: Alignment (if enabled) - needs transcription_result + audio
    - Thread 2: Diarization - needs only audio

    Args:
        whisperx_service: WhisperXService instance
        audio_file_path: Path to audio file
        audio: Loaded audio numpy array (read-only, shared between threads)
        transcription_result: Result from transcription step
        hf_token: HuggingFace token for diarization models
        min_speakers: Minimum speakers hint
        max_speakers: Maximum speakers hint
        num_speakers: Exact speaker count (if known)
        progress: Thread-safe progress reporter

    Returns:
        Tuple of (aligned_result, diarize_segments)
    """
    enable_alignment = os.getenv("ENABLE_ALIGNMENT", "false").lower() == "true"

    align_step = _StepResult()
    diarize_step = _StepResult()

    def _run_alignment():
        """Thread target: run alignment or pass through."""
        try:
            step_start = time.perf_counter()

            if enable_alignment:
                if progress:
                    progress.report(0.50, "Aligning word-level timestamps")

                # Use separate CUDA stream for this thread
                try:
                    import torch

                    if torch.cuda.is_available():
                        stream = torch.cuda.Stream()
                        with torch.cuda.stream(stream):
                            align_step.result = whisperx_service._align_with_fallback(
                                transcription_result, audio
                            )
                        stream.synchronize()
                    else:
                        align_step.result = whisperx_service._align_with_fallback(
                            transcription_result, audio
                        )
                except ImportError:
                    align_step.result = whisperx_service._align_with_fallback(
                        transcription_result, audio
                    )

                logger.info(
                    f"TIMING: parallel align_transcription completed in "
                    f"{time.perf_counter() - step_start:.3f}s"
                )
            else:
                logger.info("TIMING: alignment SKIPPED (ENABLE_ALIGNMENT=false)")
                align_step.result = transcription_result

            align_step.duration_s = time.perf_counter() - step_start

        except Exception as e:
            align_step.error = e
            logger.error(f"Parallel alignment failed: {e}")

    def _run_diarization():
        """Thread target: run speaker diarization."""
        try:
            step_start = time.perf_counter()

            if progress:
                progress.report(0.55, "Analyzing speaker patterns")

            diarize_kwargs = dict(
                max_speakers=max_speakers,
                min_speakers=min_speakers,
                num_speakers=num_speakers,
                enable_overlap_detection=enable_overlap_detection,
                overlap_min_duration=overlap_min_duration,
            )

            # Use separate CUDA stream for this thread
            try:
                import torch

                if torch.cuda.is_available():
                    stream = torch.cuda.Stream()
                    with torch.cuda.stream(stream):
                        diarize_step.result = whisperx_service.perform_speaker_diarization(
                            audio, hf_token, **diarize_kwargs
                        )
                    stream.synchronize()
                else:
                    diarize_step.result = whisperx_service.perform_speaker_diarization(
                        audio, hf_token, **diarize_kwargs
                    )
            except ImportError:
                diarize_step.result = whisperx_service.perform_speaker_diarization(
                    audio, hf_token, **diarize_kwargs
                )

            diarize_step.duration_s = time.perf_counter() - step_start
            logger.info(
                f"TIMING: parallel perform_speaker_diarization completed in "
                f"{diarize_step.duration_s:.3f}s"
            )

        except Exception as e:
            diarize_step.error = e
            logger.error(f"Parallel diarization failed: {e}")

    # Launch both threads
    parallel_start = time.perf_counter()

    align_thread = threading.Thread(target=_run_alignment, name="pipeline-alignment")
    diarize_thread = threading.Thread(target=_run_diarization, name="pipeline-diarization")

    align_thread.start()
    diarize_thread.start()

    # Wait for both to complete
    align_thread.join()
    diarize_thread.join()

    parallel_elapsed = time.perf_counter() - parallel_start
    sequential_equivalent = align_step.duration_s + diarize_step.duration_s
    savings = sequential_equivalent - parallel_elapsed

    logger.info(
        f"TIMING: parallel pipeline completed in {parallel_elapsed:.3f}s "
        f"(alignment={align_step.duration_s:.3f}s, diarization={diarize_step.duration_s:.3f}s, "
        f"sequential_equivalent={sequential_equivalent:.3f}s, saved={savings:.3f}s)"
    )

    # Propagate errors
    if diarize_step.error:
        raise diarize_step.error
    if align_step.error:
        raise align_step.error

    return align_step.result, diarize_step.result
