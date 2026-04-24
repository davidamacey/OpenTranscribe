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
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Full pipeline: audio -> transcribed, diarized, speaker-assigned segments.

        Args:
            audio_file_path: Path to the audio file (wav, mp3, etc).
            progress_callback: Optional callback(progress: float, message: str)
                for reporting progress. Progress values match the existing
                WhisperX pipeline range (0.42 -> 0.70).
            task_id: Optional Celery task ID for VRAM profile storage.

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

        profiler.snapshot("pipeline_start")

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

        # Wait for VRAM before loading transcriber (concurrent mode)
        if self.config.concurrent_requests > 1:
            self._wait_for_vram(1500, "transcriber_load")

        with profiler.step("model_load_transcriber"):
            transcriber = self.manager.get_transcriber(self.config)
        audio_thread.join()

        if audio_error[0]:
            raise audio_error[0]
        audio = audio_result[0]

        profiler.snapshot("after_transcriber_loaded")

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

        if self.config.enable_diarization:
            result, diarize_df = self._run_diarization(
                audio,
                transcript,
                profiler,
                hw,
                progress_callback,
            )
        else:
            result, diarize_df = self._skip_diarization(transcript)

        # Save final result for comparison
        self._save_intermediate_result(result, "final_result")

        # Re-enable TF32 after diarization. PyAnnote's fix_reproducibility()
        # disables TF32 globally during segmentation. Our fork re-enables it for
        # embeddings, but it stays off after diarization completes. This ensures
        # subsequent Whisper runs benefit from Tensor Core acceleration (~15-20%
        # speedup on Ampere+ GPUs: RTX 3000+, A-series, RTX 4000+).
        if self.config.device == "cuda":
            import torch

            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True

        # Cleanup
        hw.log_vram_usage("before final pipeline cleanup")
        audio_duration = len(audio) / 16000 if audio is not None else 0.0
        if diarize_df is not None and len(diarize_df) > 0:
            import numpy as np

            num_speakers = int(np.unique(diarize_df.speaker).size)
        else:
            num_speakers = 1 if not self.config.enable_diarization else 0
        del diarize_df, audio
        hw.optimize_memory_usage()
        hw.log_vram_usage("after final pipeline cleanup")

        profiler.log_report()

        # Save profile to Redis for admin endpoint
        if task_id:
            profiler.save_to_redis(task_id, audio_duration, num_speakers)

        elapsed = time.perf_counter() - pipeline_start
        logger.info(
            f"TIMING: TranscriptionPipeline.process TOTAL completed in {elapsed:.3f}s - "
            f"{len(result.get('segments', []))} segments, "
            f"language={result.get('language', 'unknown')}"
        )

        return result

    def _run_diarization(
        self,
        audio: Any,
        transcript: dict,
        profiler: Any,
        hw: Any,
        progress_callback: Callable[[float, str], None] | None,
    ) -> tuple[dict, Any]:
        """Run PyAnnote diarization and assign speakers to segments."""
        # Step 3: Load diarizer — skip transcriber release if VRAM allows both
        self._report(progress_callback, 0.52, "Preparing speaker analysis")
        hw.log_vram_usage("after transcription, before diarizer load")
        total_vram_mb = self._get_total_vram_mb()

        profiler.snapshot("models_warm_no_inference")

        if self.config.concurrent_requests > 1:
            logger.info(
                "Concurrent mode (concurrent_requests=%d): keeping transcriber loaded",
                self.config.concurrent_requests,
            )
        elif total_vram_mb >= 16_000:
            logger.info(
                "Keeping transcriber loaded (%dMB VRAM total, both models fit)",
                total_vram_mb,
            )
        else:
            self.manager.release_transcriber()
            hw.log_vram_usage("after transcriber release")
            profiler.snapshot("diarizer_only_warm")

        if self.config.concurrent_requests > 1:
            self._wait_for_vram(2000, "diarization")

        # Step 4: Diarize with PyAnnote v4
        self._report(progress_callback, 0.55, "Analyzing speaker patterns")
        step_start = time.perf_counter()
        with profiler.step("diarization"):
            diarizer = self.manager.get_diarizer(self.config)
            diarize_df, overlap_info, native_embeddings = diarizer.diarize(audio)
        logger.info(
            f"TIMING: diarization step completed in {time.perf_counter() - step_start:.3f}s"
        )
        profiler.snapshot("after_diarization")

        self._save_intermediate(transcript, diarize_df, overlap_info, native_embeddings)

        # Step 5: Segment dedup BEFORE speaker assignment
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

        if overlap_info.get("count", 0) > 0:
            result["overlap_info"] = overlap_info
        if native_embeddings:
            result["native_speaker_embeddings"] = native_embeddings

        return result, diarize_df

    @staticmethod
    def _skip_diarization(transcript: dict) -> tuple[dict, None]:
        """Skip diarization and assign SPEAKER_00 to all segments."""
        logger.info("Diarization disabled — assigning SPEAKER_00 to all segments")
        from app.utils.segment_dedup import clean_segments

        transcript["segments"] = clean_segments(transcript["segments"])
        for seg in transcript.get("segments", []):
            seg["speaker"] = "SPEAKER_00"
            for word in seg.get("words", []):
                word["speaker"] = "SPEAKER_00"
        return transcript, None

    @staticmethod
    def _wait_for_vram(min_free_mb: int, stage: str, timeout: int = 120) -> None:
        """Block until device has enough free VRAM for the next stage.

        Used in concurrent mode to prevent OOM when multiple tasks run on
        the same GPU. Polls torch.cuda.mem_get_info() every 2 seconds.

        Args:
            min_free_mb: Minimum free device memory in MB to proceed.
            stage: Label for logging (e.g., "diarization").
            timeout: Maximum seconds to wait before proceeding anyway.
        """
        try:
            import torch

            if not torch.cuda.is_available():
                return

            deadline = time.perf_counter() + timeout
            while time.perf_counter() < deadline:
                free_mb = torch.cuda.mem_get_info(0)[0] / (1024**2)
                if free_mb >= min_free_mb:
                    return
                logger.info(
                    f"VRAM gate [{stage}]: {free_mb:.0f}MB free < {min_free_mb}MB required, "
                    f"waiting..."
                )
                time.sleep(2)

            free_mb = torch.cuda.mem_get_info(0)[0] / (1024**2)
            logger.warning(
                f"VRAM gate [{stage}]: timeout after {timeout}s, proceeding with "
                f"{free_mb:.0f}MB free (needed {min_free_mb}MB)"
            )
        except Exception as e:
            logger.debug(f"VRAM gate check skipped: {e}")

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

        # Diarization data
        with open(os.path.join(out_dir, "raw_diarization.json"), "w") as _f:
            json.dump(diarize_df.to_records(), _f, indent=2)

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
                return int(torch.cuda.get_device_properties(0).total_memory / (1024**2))
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
