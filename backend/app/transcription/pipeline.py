"""Main transcription pipeline orchestrator.

Coordinates: audio loading -> transcription -> diarization -> speaker
assignment -> dedup into a single process() call.
"""

import logging
import time
from typing import Any
from typing import Callable

from app.transcription.config import TranscriptionConfig
from app.transcription.model_manager import ModelManager

logger = logging.getLogger(__name__)


class TranscriptionPipeline:
    """Full transcription pipeline using faster-whisper + PyAnnote v4."""

    def __init__(self, config: TranscriptionConfig):
        self.config = config
        self.manager = ModelManager.get_instance()

    def process(
        self,
        audio_file_path: str,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> dict[str, Any]:
        """Full pipeline: audio -> transcribed, diarized, speaker-assigned segments.

        Args:
            audio_file_path: Path to the audio file (wav, mp3, etc).
            progress_callback: Optional callback(progress: float, message: str)
                for reporting progress. Progress values match the existing
                WhisperX pipeline range (0.42 -> 0.70).

        Returns:
            Dict with keys:
                "segments": list of segment dicts, each with
                    "text", "start", "end", "speaker", "words"
                "language": detected language code (str)
                "overlap_info": dict with count, duration, regions (if overlaps)
        """
        from app.utils.hardware_detection import detect_hardware
        from app.utils.vram_profiler import VRAMProfiler

        pipeline_start = time.perf_counter()
        profiler = VRAMProfiler()
        hw = detect_hardware()

        # Steps 1+2: Load audio and ensure model is warm in parallel
        self._report(progress_callback, 0.42, "Loading audio")
        import threading

        from app.transcription.audio import load_audio

        audio_result: list = [None]
        audio_error: list = [None]

        def _load_audio():
            try:
                audio_result[0] = load_audio(audio_file_path)
            except Exception as e:
                audio_error[0] = e

        # Start audio loading in background while ensuring model is warm
        audio_thread = threading.Thread(target=_load_audio, name="audio-load", daemon=True)
        audio_thread.start()
        transcriber = self.manager.get_transcriber(self.config)
        audio_thread.join()

        if audio_error[0]:
            raise audio_error[0]
        audio = audio_result[0]

        # Transcribe
        self._report(progress_callback, 0.43, "Running AI transcription")
        step_start = time.perf_counter()
        with profiler.step("transcription"):
            transcript = transcriber.transcribe(audio)
        logger.info(
            f"TIMING: transcription step completed in {time.perf_counter() - step_start:.3f}s"
        )

        if not transcript.get("segments"):
            logger.warning("Transcription produced no segments")
            return transcript

        # Step 3: Load diarizer — skip transcriber release if VRAM allows both
        self._report(progress_callback, 0.52, "Preparing speaker analysis")
        hw.log_vram_usage("after transcription, before diarizer load")
        total_vram_mb = self._get_total_vram_mb()
        if total_vram_mb >= 16_000:
            # Enough VRAM: keep transcriber warm for next task (saves ~4.7s)
            logger.info(
                "Keeping transcriber loaded (%dMB VRAM total, both models fit)",
                total_vram_mb,
            )
        else:
            # Small GPU: release transcriber first to free VRAM for diarizer
            self.manager.release_transcriber()
            hw.log_vram_usage("after transcriber release")

        # Step 4: Diarize with PyAnnote v4
        self._report(progress_callback, 0.55, "Analyzing speaker patterns")
        step_start = time.perf_counter()
        with profiler.step("diarization"):
            diarizer = self.manager.get_diarizer(self.config)
            diarize_df, overlap_info, native_embeddings = diarizer.diarize(audio)
        logger.info(
            f"TIMING: diarization step completed in {time.perf_counter() - step_start:.3f}s"
        )

        # Save raw GPU outputs for offline post-processing iteration
        self._save_intermediate(transcript, diarize_df, overlap_info, native_embeddings)

        # Step 5: Segment dedup BEFORE speaker assignment
        # Splits coarse VAD chunks (20-30s) into sentence-level segments (~3-5s)
        # so each sentence gets its own speaker assignment.
        if self.config.enable_dedup:
            step_start = time.perf_counter()
            from app.utils.segment_dedup import clean_segments

            original_count = len(transcript.get("segments", []))
            transcript["segments"] = clean_segments(transcript["segments"])
            logger.info(
                f"TIMING: segment_dedup completed in "
                f"{time.perf_counter() - step_start:.3f}s - "
                f"{original_count} -> {len(transcript['segments'])} segments"
            )

        # Step 6: Assign speakers to segments and words
        self._report(progress_callback, 0.65, "Assigning speakers to transcript")
        step_start = time.perf_counter()
        with profiler.step("speaker_assignment"):
            from app.transcription.speaker_assigner import assign_speakers

            result = assign_speakers(diarize_df, transcript)
        logger.info(
            f"TIMING: speaker assignment completed in {time.perf_counter() - step_start:.3f}s"
        )

        # Add overlap metadata
        if overlap_info.get("count", 0) > 0:
            result["overlap_info"] = overlap_info

        # Pass native speaker embeddings to downstream processing
        if native_embeddings:
            result["native_speaker_embeddings"] = native_embeddings

        # Save final result for comparison
        self._save_intermediate_result(result, "final_result")

        # Cleanup
        hw.log_vram_usage("before final pipeline cleanup")
        del diarize_df, audio
        hw.optimize_memory_usage()
        hw.log_vram_usage("after final pipeline cleanup")

        profiler.log_report()

        elapsed = time.perf_counter() - pipeline_start
        logger.info(
            f"TIMING: TranscriptionPipeline.process TOTAL completed in {elapsed:.3f}s - "
            f"{len(result.get('segments', []))} segments, "
            f"language={result.get('language', 'unknown')}"
        )

        return result

    @staticmethod
    def _save_intermediate(
        transcript: dict,
        diarize_df: Any,
        overlap_info: dict,
        native_embeddings: dict | None = None,
    ) -> None:
        """Save raw GPU outputs so post-processing can be iterated offline."""
        import json
        import os

        out_dir = os.environ.get("PIPELINE_DEBUG_DIR", "")
        if not out_dir:
            return

        os.makedirs(out_dir, exist_ok=True)
        logger.info(f"Saving intermediate pipeline data to {out_dir}")

        # Raw transcription (segments + words from faster-whisper)
        with open(os.path.join(out_dir, "raw_transcript.json"), "w") as f:
            json.dump(transcript, f, indent=2, default=str)

        # Diarization DataFrame
        diarize_df.to_json(
            os.path.join(out_dir, "raw_diarization.json"), orient="records", indent=2
        )

        # Overlap info
        with open(os.path.join(out_dir, "overlap_info.json"), "w") as f:
            json.dump(overlap_info, f, indent=2, default=str)

        # Native embeddings info
        if native_embeddings:
            emb_info = {label: {"dim": vec.shape[0]} for label, vec in native_embeddings.items()}
            with open(os.path.join(out_dir, "native_embeddings_info.json"), "w") as f:
                json.dump(emb_info, f, indent=2)

        logger.info(
            f"Saved: raw_transcript.json ({len(transcript.get('segments', []))} segments), "
            f"raw_diarization.json ({len(diarize_df)} rows), overlap_info.json"
        )

    @staticmethod
    def _save_intermediate_result(result: dict, name: str) -> None:
        """Save a processing result for comparison."""
        import json
        import os

        out_dir = os.environ.get("PIPELINE_DEBUG_DIR", "")
        if not out_dir:
            return

        path = os.path.join(out_dir, f"{name}.json")
        with open(path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        logger.info(f"Saved {name}.json ({len(result.get('segments', []))} segments)")

    @staticmethod
    def _get_total_vram_mb() -> int:
        """Return total GPU VRAM in MB, or 0 if no GPU."""
        try:
            import torch

            if torch.cuda.is_available():
                return int(torch.cuda.get_device_properties(0).total_mem / (1024**2))
        except Exception as e:
            logger.debug("Could not detect VRAM: %s", e)
        return 0

    @staticmethod
    def _report(
        callback: Callable[[float, str], None] | None,
        progress: float,
        message: str,
    ) -> None:
        if callback:
            callback(progress, message)
