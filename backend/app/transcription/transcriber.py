"""Core transcription using faster-whisper BatchedInferencePipeline.

This is the key module: uses BatchedInferencePipeline.transcribe() with
word_timestamps=True to get batched speed (~76s for 3hr file) WITH
word-level timestamps (95% speaker accuracy). WhisperX hardcodes
word_timestamps off in its batched pipeline.
"""

import logging
import time

import numpy as np

from app.transcription.config import TranscriptionConfig

logger = logging.getLogger(__name__)


class Transcriber:
    """Faster-whisper BatchedInferencePipeline with native word timestamps."""

    def __init__(self, config: TranscriptionConfig):
        self.config = config
        self._model = None
        self._pipeline = None

    @property
    def is_loaded(self) -> bool:
        return self._pipeline is not None

    def load_model(self) -> None:
        """Load the WhisperModel and wrap it in BatchedInferencePipeline."""
        from faster_whisper import BatchedInferencePipeline
        from faster_whisper import WhisperModel

        step_start = time.perf_counter()

        logger.info(
            f"Loading faster-whisper model: {self.config.model_name}, "
            f"device={self.config.device}, compute_type={self.config.compute_type}"
        )

        self._model = WhisperModel(
            self.config.model_name,
            device=self.config.device,
            device_index=self.config.device_index,
            compute_type=self.config.compute_type,
        )
        self._pipeline = BatchedInferencePipeline(model=self._model)

        elapsed = time.perf_counter() - step_start
        logger.info(f"TIMING: transcriber model loaded in {elapsed:.3f}s")

    def transcribe(self, audio: np.ndarray) -> dict:
        """Batched transcription with word-level timestamps.

        Args:
            audio: Audio waveform as 16kHz mono float32 numpy array.

        Returns:
            Dict with keys:
                "segments": list of segment dicts, each with
                    "text", "start", "end", "words" (list of word dicts)
                "language": detected language code (str)
        """
        if not self.is_loaded:
            raise RuntimeError("Transcriber model not loaded. Call load_model() first.")

        step_start = time.perf_counter()

        task = "translate" if self.config.translate_to_english else "transcribe"
        language = self.config.source_language if self.config.source_language != "auto" else None

        logger.info(
            f"Transcribing: task={task}, language={language or 'auto'}, "
            f"batch_size={self.config.batch_size}, beam_size={self.config.beam_size}"
        )

        assert self._pipeline is not None, "Pipeline not initialized"
        segments_gen, info = self._pipeline.transcribe(
            audio,
            batch_size=self.config.batch_size,
            word_timestamps=True,
            beam_size=self.config.beam_size,
            task=task,
            language=language,
            vad_filter=True,
        )

        # Convert generator to list of dicts
        segments = []
        total_words = 0
        for seg in segments_gen:
            words = []
            if seg.words:
                for w in seg.words:
                    words.append(
                        {
                            "word": w.word,
                            "start": float(w.start),
                            "end": float(w.end),
                            "probability": float(w.probability),
                        }
                    )
                total_words += len(words)

            segments.append(
                {
                    "text": seg.text.strip(),
                    "start": float(seg.start),
                    "end": float(seg.end),
                    "words": words,
                }
            )

        elapsed = time.perf_counter() - step_start
        logger.info(
            f"TIMING: transcription completed in {elapsed:.3f}s - "
            f"{len(segments)} segments, {total_words} words with timestamps, "
            f"language={info.language}"
        )

        return {"segments": segments, "language": info.language}

    def unload_model(self) -> None:
        """Release model memory."""
        if self._pipeline is not None:
            del self._pipeline
            self._pipeline = None
        if self._model is not None:
            del self._model
            self._model = None
        logger.info("Transcriber model unloaded")
