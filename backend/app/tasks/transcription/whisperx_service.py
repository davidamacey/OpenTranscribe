import logging
import os
from pathlib import Path
from typing import Any

# Note: PyTorch 2.6+ compatibility patch (weights_only=False) is applied in
# app/core/celery.py at module level, BEFORE any ML libraries are imported
from app.utils.hardware_detection import detect_hardware

logger = logging.getLogger(__name__)


class WhisperXService:
    """Service for handling WhisperX transcription operations with cross-platform support."""

    def __init__(
        self,
        model_name: str | None = None,
        models_dir: str | None = None,
        source_language: str = "auto",
        translate_to_english: bool = False,
    ):
        # Initialize hardware detection
        self.hardware_config = detect_hardware()

        # Model configuration
        self.model_name = model_name or os.getenv("WHISPER_MODEL", "large-v3-turbo")
        self.models_dir = models_dir or Path.cwd() / "models"

        # Language configuration
        self.source_language = source_language
        self.translate_to_english = translate_to_english

        # Hardware-optimized settings
        whisperx_config = self.hardware_config.get_whisperx_config()
        self.device = whisperx_config["device"]
        self.compute_type = whisperx_config["compute_type"]
        self.batch_size = whisperx_config["batch_size"]

        # Additional optimizations
        self._apply_environment_optimizations()

        # Ensure models directory exists
        self.whisperx_model_directory = os.path.join(self.models_dir, "whisperx")
        os.makedirs(self.whisperx_model_directory, exist_ok=True)

        # Validate configuration
        is_valid, validation_msg = self.hardware_config.validate_configuration()
        if not is_valid:
            logger.warning(f"Hardware validation failed: {validation_msg}")

        # Log hardware details
        detected_device = self.hardware_config.device
        lang_info = f"source_language={self.source_language}, translate_to_english={self.translate_to_english}"
        if detected_device == "mps" and self.device == "cpu":
            logger.info(
                f"WhisperX initialized: model={self.model_name}, "
                f"detected_device={detected_device} (using CPU for WhisperX compatibility), "
                f"compute_type={self.compute_type}, batch_size={self.batch_size}, {lang_info}"
            )
        else:
            logger.info(
                f"WhisperX initialized: model={self.model_name}, device={self.device}, "
                f"compute_type={self.compute_type}, batch_size={self.batch_size}, {lang_info}"
            )

    def _apply_environment_optimizations(self):
        """Apply environment variable optimizations for the detected hardware."""
        env_vars = self.hardware_config.get_environment_variables()
        for key, value in env_vars.items():
            if key not in os.environ:  # Don't override existing settings
                os.environ[key] = value
                logger.debug(f"Set environment variable: {key}={value}")

    def _log_model_loading(self) -> None:
        """Log model loading with device-specific messaging."""
        detected_device = self.hardware_config.device
        if detected_device == "mps" and self.device == "cpu":
            logger.info(
                f"Loading WhisperX model: {self.model_name} on {self.device} "
                f"(Apple Silicon detected, using CPU for WhisperX compatibility)"
            )
        else:
            logger.info(f"Loading WhisperX model: {self.model_name} on {self.device}")

    def _load_and_validate_audio(self, audio_file_path: str):
        """
        Load audio file and validate it has content.

        Args:
            audio_file_path: Path to the audio file

        Returns:
            Loaded audio data as numpy array

        Raises:
            ValueError: If audio cannot be loaded or is invalid
        """
        import whisperx

        logger.info(f"Transcribing audio file: {audio_file_path}")
        try:
            audio = whisperx.load_audio(audio_file_path)
            self._validate_audio_content(audio)
            return audio
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to load audio from {audio_file_path}: {str(e)}")
            self._raise_audio_load_error(e)

    def _validate_audio_content(self, audio) -> None:
        """Validate that audio data has meaningful content."""
        import numpy as np

        if audio is None or len(audio) == 0:
            raise ValueError("Audio file appears to be empty or corrupted")

        if isinstance(audio, np.ndarray):
            # Assume 16kHz sample rate (WhisperX default)
            duration = len(audio) / 16000
            if duration < 0.1:  # Less than 100ms
                raise ValueError("Audio file is too short to contain meaningful content")

    def _raise_audio_load_error(self, original_error: Exception) -> None:
        """Raise appropriate error message for audio loading failures."""
        error_msg = str(original_error)
        if "No module named 'librosa'" in error_msg:
            # Don't expose internal dependency issues to users
            raise ValueError(
                "Audio file could not be processed. The file may be corrupted or in an unsupported format."
            ) from original_error
        raise ValueError(
            f"Unable to load audio content. The file may be corrupted, in an unsupported format, or contain no audio data: {error_msg}"
        ) from original_error

    def _run_transcription(self, model, audio, audio_file_path: str) -> dict[str, Any]:
        """Run transcription on loaded audio and validate results."""
        try:
            # Determine task: "translate" outputs English, "transcribe" keeps original language
            task = "translate" if self.translate_to_english else "transcribe"
            logger.info(
                f"Running transcription with task='{task}' "
                f"(translate_to_english={self.translate_to_english})"
            )

            transcription_result = model.transcribe(
                audio,
                batch_size=self.batch_size,
                task=task,
            )

            if not transcription_result or "segments" not in transcription_result:
                raise ValueError("Transcription failed to produce valid output")

            # Log detected language
            detected_lang = transcription_result.get("language", "unknown")
            logger.info(f"Transcription detected language: {detected_lang}")

            return transcription_result  # type: ignore[no-any-return]

        except Exception as e:
            logger.error(f"Transcription failed for {audio_file_path}: {str(e)}")
            raise ValueError(
                f"Audio transcription failed. The file may contain no speech, be corrupted, or be in an unsupported format: {str(e)}"
            ) from e

    def transcribe_audio(self, audio_file_path: str) -> tuple[dict[str, Any], Any]:
        """
        Transcribe audio using WhisperX.

        Args:
            audio_file_path: Path to the audio file

        Returns:
            Tuple of (transcription_result dict, audio data)
        """
        try:
            import whisperx
        except ImportError as e:
            raise ImportError(
                "WhisperX is not installed. Please install it with 'pip install whisperx'."
            ) from e

        # Load model with hardware-specific configuration
        self._log_model_loading()

        # Override compute_type from env if set (e.g., int8_float16 for speed)
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", self.compute_type)

        load_options = {
            "whisper_arch": self.model_name,
            "device": self.device,
            "compute_type": compute_type,
        }

        # Override beam_size and other asr_options from env
        asr_options = {}
        beam_size = os.getenv("WHISPER_BEAM_SIZE", "").strip()
        if beam_size:
            asr_options["beam_size"] = int(beam_size)
            logger.info(f"Using custom beam_size={beam_size}")

        if asr_options:
            load_options["asr_options"] = asr_options

        # Add language hint if specified (helps accuracy even when translating)
        # "auto" means let Whisper detect the language automatically
        if self.source_language != "auto":
            load_options["language"] = self.source_language
            logger.info(f"Using source language hint: {self.source_language}")
        else:
            logger.info("Using automatic language detection")

        # Add device-specific options
        if self.device == "cuda":
            # Always use device 0 since Docker maps the selected GPU to index 0
            load_options["device_index"] = 0

        logger.info(
            f"Loading WhisperX model: compute_type={compute_type}, "
            f"beam_size={asr_options.get('beam_size', 5)}"
        )
        model = whisperx.load_model(**load_options)

        # Load and validate audio
        audio = self._load_and_validate_audio(audio_file_path)

        # Run transcription
        transcription_result = self._run_transcription(model, audio, audio_file_path)

        logger.info(
            f"Initial transcription completed with {len(transcription_result['segments'])} segments"
        )

        # Optimize memory usage based on device
        self.hardware_config.log_vram_usage("after transcription, before cleanup")
        del model
        self.hardware_config.optimize_memory_usage()
        self.hardware_config.log_vram_usage("after transcription model deleted")

        return transcription_result, audio

    def transcribe_with_word_timestamps(self, audio_file_path: str) -> tuple[dict[str, Any], Any]:
        """
        Transcribe audio using faster-whisper directly with native word timestamps.

        This bypasses WhisperX's batched pipeline to use faster-whisper's built-in
        cross-attention-based word timing (DTW alignment). No separate wav2vec2
        model needed. Trade-off: sequential processing (no batching) but gets
        word-level timestamps in a single pass.

        Uses WhisperX's VAD for chunking, then processes each chunk with
        faster-whisper's native word_timestamps=True.

        Args:
            audio_file_path: Path to the audio file

        Returns:
            Tuple of (transcription_result dict with word timestamps, audio data)
        """
        import time as time_mod

        step_start = time_mod.perf_counter()

        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise ImportError("faster-whisper is required.") from e

        self._log_model_loading()

        # Load audio via WhisperX (ensures correct format/sample rate)
        audio = self._load_and_validate_audio(audio_file_path)

        # Load faster-whisper model directly (not WhisperX's pipeline wrapper)
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", self.compute_type)
        beam_size = int(os.getenv("WHISPER_BEAM_SIZE", "5"))

        logger.info(
            f"Loading faster-whisper model directly: {self.model_name}, "
            f"compute_type={compute_type}, beam_size={beam_size}"
        )
        fw_model = WhisperModel(
            self.model_name,
            device=self.device,
            device_index=0 if self.device == "cuda" else 0,
            compute_type=compute_type,
        )

        model_load_time = time_mod.perf_counter() - step_start
        logger.info(f"TIMING: faster-whisper model loaded in {model_load_time:.3f}s")

        # Use WhisperX's VAD to get speech segments (same chunking as batched mode)
        vad_start = time_mod.perf_counter()
        import torch
        from whisperx.vads.pyannote import Pyannote
        from whisperx.vads.pyannote import load_vad_model

        vad_pipeline = load_vad_model(device=self.device)
        waveform = torch.from_numpy(audio).unsqueeze(0)
        vad_result = vad_pipeline({"waveform": waveform, "sample_rate": 16000})

        # Merge into ~30s chunks (same as WhisperX default)
        vad_segments = Pyannote.merge_chunks(
            vad_result,
            chunk_size=30,
            onset=0.500,
            offset=0.363,
        )
        del vad_pipeline, waveform
        self.hardware_config.optimize_memory_usage()

        vad_time = time_mod.perf_counter() - vad_start
        logger.info(
            f"TIMING: VAD completed in {vad_time:.3f}s - {len(vad_segments)} speech segments"
        )

        # Transcribe each VAD chunk with word_timestamps=True
        transcribe_start = time_mod.perf_counter()
        sample_rate = 16000
        all_segments = []
        total_words = 0

        task = "translate" if self.translate_to_english else "transcribe"
        language = self.source_language if self.source_language != "auto" else None

        detected_language = language
        for chunk_idx, vad_seg in enumerate(vad_segments):
            chunk_start = vad_seg["start"]
            chunk_end = vad_seg["end"]

            # Extract audio chunk
            f1 = int(chunk_start * sample_rate)
            f2 = int(chunk_end * sample_rate)
            audio_chunk = audio[f1:f2]

            # Transcribe with native word timestamps
            segments_gen, info = fw_model.transcribe(
                audio_chunk,
                beam_size=beam_size,
                word_timestamps=True,
                task=task,
                language=detected_language,
                vad_filter=False,  # We already did VAD
            )

            # Detect language from first chunk
            if chunk_idx == 0 and detected_language is None:
                detected_language = info.language
                logger.info(f"Detected language: {detected_language}")

            # Process segments, adjusting timestamps to absolute positions
            for seg in segments_gen:
                words = []
                if seg.words:
                    for w in seg.words:
                        words.append(
                            {
                                "word": w.word,
                                "start": float(round(chunk_start + w.start, 3)),
                                "end": float(round(chunk_start + w.end, 3)),
                                "probability": float(round(w.probability, 3)),
                            }
                        )
                    total_words += len(words)

                all_segments.append(
                    {
                        "text": seg.text,
                        "start": float(round(chunk_start + seg.start, 3)),
                        "end": float(round(chunk_start + seg.end, 3)),
                        "words": words,
                    }
                )

        transcribe_time = time_mod.perf_counter() - transcribe_start
        total_time = time_mod.perf_counter() - step_start
        logger.info(
            f"TIMING: native word_timestamps transcription completed in {transcribe_time:.3f}s "
            f"- {len(all_segments)} segments, {total_words} words with timestamps"
        )
        logger.info(
            f"TIMING: transcribe_with_word_timestamps TOTAL {total_time:.3f}s "
            f"(model_load={model_load_time:.3f}s, vad={vad_time:.3f}s, "
            f"transcribe={transcribe_time:.3f}s)"
        )

        # Clean up model
        self.hardware_config.log_vram_usage("after native transcription, before cleanup")
        del fw_model
        self.hardware_config.optimize_memory_usage()
        self.hardware_config.log_vram_usage("after native transcription model deleted")

        transcription_result = {
            "segments": all_segments,
            "language": detected_language or "en",
            "word_timestamps_native": True,
        }

        return transcription_result, audio

    def align_transcription(self, transcription_result: dict[str, Any], audio) -> dict[str, Any]:
        """
        Align transcription with precise word-level timestamps.

        Args:
            transcription_result: Result from initial transcription
            audio: Loaded audio data

        Returns:
            Aligned transcription result
        """
        try:
            import whisperx
        except ImportError as e:
            raise ImportError("WhisperX is not installed.") from e

        logger.info("Loading alignment model...")
        align_model, align_metadata = whisperx.load_align_model(
            language_code=transcription_result["language"],
            device=self.device,
            model_name=None,
        )

        use_batched = os.getenv("USE_BATCHED_ALIGNMENT", "false").lower() == "true"

        if use_batched:
            from app.utils.batched_alignment import align_batched

            logger.info("Aligning transcription using BATCHED wav2vec2 inference...")
            aligned_result = align_batched(
                transcription_result["segments"],
                align_model,
                align_metadata,
                audio,
                self.device,
                return_char_alignments=False,
            )
        else:
            logger.info("Aligning transcription for precise word timings...")
            aligned_result = whisperx.align(
                transcription_result["segments"],
                align_model,
                align_metadata,
                audio,
                self.device,
                return_char_alignments=False,
            )

        # Optimize memory usage based on device
        self.hardware_config.log_vram_usage("after alignment, before cleanup")
        del align_model
        self.hardware_config.optimize_memory_usage()
        self.hardware_config.log_vram_usage("after alignment model deleted")

        return aligned_result  # type: ignore[no-any-return]

    def perform_speaker_diarization(
        self,
        audio,
        hf_token: str | None = None,
        max_speakers: int = 20,
        min_speakers: int = 1,
        num_speakers: int | None = None,
    ) -> Any:
        """
        Perform speaker diarization on audio.

        Args:
            audio: Loaded audio data
            hf_token: HuggingFace token for accessing models
            max_speakers: Maximum number of speakers (default: 20, can be increased to 50+ for large conferences)
            min_speakers: Minimum number of speakers
            num_speakers: Exact number of speakers (if known, overrides min/max)

        Returns:
            Diarization result

        Raises:
            RuntimeError: If cuDNN library compatibility issues occur
            PermissionError: If HuggingFace token doesn't have access to gated PyAnnote models
            ImportError: If WhisperX is not installed
        """
        try:
            import whisperx
        except ImportError as e:
            raise ImportError("WhisperX is not installed.") from e

        logger.info(
            f"Performing speaker diarization with min_speakers={min_speakers}, max_speakers={max_speakers}, num_speakers={num_speakers}"
        )

        try:
            diarize_params = {"max_speakers": max_speakers, "min_speakers": min_speakers}
            if num_speakers is not None:
                diarize_params["num_speakers"] = num_speakers
                logger.info(f"Using exact speaker count: {num_speakers}")
            logger.info(f"Diarization parameters: {diarize_params}")

            # Use PyAnnote-compatible device configuration
            pyannote_config = self.hardware_config.get_pyannote_config()

            diarize_model = whisperx.diarize.DiarizationPipeline(
                token=hf_token, device=pyannote_config["device"]
            )

            diarize_segments = diarize_model(audio, **diarize_params)

            # CRITICAL: Clean up diarization model immediately to free VRAM
            # This model uses ~2-3 GB and must be deleted before speaker embedding extraction
            self.hardware_config.log_vram_usage("after diarization, before cleanup")
            logger.info("Cleaning up diarization model to free GPU memory")
            del diarize_model
            self.hardware_config.optimize_memory_usage()
            self.hardware_config.log_vram_usage("after diarization model deleted")
            logger.info("Diarization model cleanup completed")

            return diarize_segments  # type: ignore[no-any-return]

        except Exception as e:
            error_msg = str(e)

            # Detect HuggingFace gated model access errors (same checks as download scripts)
            if "401" in error_msg or "unauthorized" in error_msg.lower():
                logger.error(f"HuggingFace authentication error: {error_msg}")
                raise PermissionError(
                    "Cannot access PyAnnote speaker diarization models. "
                    "Your HuggingFace token does not have access to the required gated model. "
                    "You must accept the model agreement on HuggingFace: "
                    "pyannote/speaker-diarization-community-1 (https://huggingface.co/pyannote/speaker-diarization-community-1). "
                    "After accepting the agreement, wait 1-2 minutes for permissions to propagate, "
                    "restart the application containers, and re-upload your file for transcription."
                ) from e

            # Detect 403 Forbidden errors
            if "403" in error_msg or "forbidden" in error_msg.lower():
                logger.error(f"HuggingFace permission error: {error_msg}")
                raise PermissionError(
                    "Access forbidden to PyAnnote models. "
                    "Your HuggingFace token may not have the required Read permissions, "
                    "or you have not accepted the gated model agreement. "
                    "Please verify your token has Read permissions at https://huggingface.co/settings/tokens "
                    "and accept the model agreement: pyannote/speaker-diarization-community-1."
                ) from e

            # Detect generic Hub errors that indicate missing model access
            if (
                "cannot find the requested files" in error_msg.lower()
                or "locate the file on the hub" in error_msg.lower()
            ):
                logger.error(f"HuggingFace model access error: {error_msg}")
                raise PermissionError(
                    "Cannot download PyAnnote models from HuggingFace. "
                    "This usually means you have not accepted the gated model agreement. "
                    "Please accept the model agreement at https://huggingface.co/pyannote/speaker-diarization-community-1, "
                    "wait 1-2 minutes for permissions to propagate, then restart the application and try again."
                ) from e

            # Detect cuDNN library compatibility issues
            if "libcudnn" in error_msg.lower():
                raise RuntimeError(
                    "CUDA cuDNN library compatibility error detected. This indicates a version "
                    "mismatch between PyTorch and CTranslate2. The system requires all packages "
                    "to use cuDNN 9 for CUDA 12.8 compatibility. "
                    f"Technical details: {error_msg}"
                ) from e

            # Detect general CUDA errors
            if "cuda" in error_msg.lower() or "gpu" in error_msg.lower():
                raise RuntimeError(
                    f"GPU processing error during speaker diarization: {error_msg}"
                ) from e

            # Re-raise other exceptions
            raise

    def assign_speakers_to_words(
        self, diarize_segments, aligned_result: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Assign speaker labels to words in the transcription.

        Uses our optimized fast_speaker_assignment module instead of WhisperX's
        slow implementation. The original WhisperX assign_word_speakers() takes
        60-90 seconds for large files due to O(n*m) pandas operations per word.
        Our implementation uses interval trees and NumPy vectorization for 15-30x speedup.

        Args:
            diarize_segments: Result from speaker diarization (pandas DataFrame)
            aligned_result: Aligned transcription result

        Returns:
            Final result with speaker assignments
        """
        import os

        logger.info("Assigning speaker labels to transcript...")

        # Fast implementation using interval tree + NumPy (128x faster than WhisperX)
        # Set USE_FAST_SPEAKER_ASSIGNMENT=false to fall back to WhisperX if issues
        use_fast_assignment = os.getenv("USE_FAST_SPEAKER_ASSIGNMENT", "true").lower() == "true"

        if use_fast_assignment:
            from app.utils.fast_speaker_assignment import assign_word_speakers_fast

            logger.info("Using fast speaker assignment (interval tree + NumPy)")
            result = assign_word_speakers_fast(diarize_segments, aligned_result)
        else:
            try:
                import whisperx
            except ImportError as e:
                raise ImportError("WhisperX is not installed.") from e

            logger.info("Using WhisperX speaker assignment (legacy)")
            result = whisperx.assign_word_speakers(diarize_segments, aligned_result)

        return result  # type: ignore[no-any-return]

    def _report_progress(self, callback, progress: float, message: str) -> None:
        """Report progress if callback is provided."""
        if callback:
            callback(progress, message)

    def _align_with_fallback(self, transcription_result: dict, audio: Any) -> dict[str, Any]:
        """Align transcription with fallback for unsupported languages."""
        try:
            return self.align_transcription(transcription_result, audio)
        except Exception as e:
            detected_lang = transcription_result.get("language", "unknown")
            logger.warning(
                f"Alignment model not available for language '{detected_lang}'. "
                f"Using segment-level timestamps (word-level timing disabled). Error: {e}"
            )
            return transcription_result

    def _handle_overlapping_speech(
        self,
        overlaps: list[dict[str, float]],
        overlap_count: int,
    ) -> None:
        """
        Log overlapping speech detection from PyAnnote v4 diarization.

        Overlap regions are detected natively by PyAnnote v4 and passed through
        in overlap_info for downstream processing by mark_overlapping_segments().
        """
        if overlap_count > 0:
            total_duration = sum(o["end"] - o["start"] for o in overlaps)
            logger.info(
                f"Detected {overlap_count} overlapping regions "
                f"(total duration: {total_duration:.2f}s)"
            )

    def _add_overlap_metadata(
        self,
        final_result: dict[str, Any],
        overlap_count: int,
        overlap_duration: float,
        overlaps: list[dict[str, float]],
    ) -> None:
        """Add overlap metadata to result if overlaps were detected."""
        if overlap_count > 0:
            final_result["overlap_info"] = {
                "count": overlap_count,
                "duration": overlap_duration,
                "regions": overlaps,
            }

    def process_full_pipeline(
        self,
        audio_file_path: str,
        hf_token: str | None = None,
        progress_callback=None,
        min_speakers: int = 1,
        max_speakers: int = 20,
        num_speakers: int | None = None,
    ) -> dict[str, Any]:
        """
        Run the complete WhisperX pipeline: transcription, alignment, and diarization.

        Args:
            audio_file_path: Path to the audio file
            hf_token: HuggingFace token for speaker diarization
            progress_callback: Optional callback function for progress updates
            min_speakers: Minimum number of speakers (hint)
            max_speakers: Maximum number of speakers (hint)
            num_speakers: Exact number of speakers (if known, overrides min/max)

        Returns:
            Complete processing result with speaker assignments
        """
        import time

        from app.utils.vram_profiler import VRAMProfiler

        pipeline_start = time.perf_counter()
        profiler = VRAMProfiler()

        # Step 1: Transcribe (40% -> 50%)
        import os

        use_native_word_ts = os.getenv("USE_NATIVE_WORD_TIMESTAMPS", "false").lower() == "true"

        self._report_progress(progress_callback, 0.42, "Running initial transcription")
        step_start = time.perf_counter()
        if use_native_word_ts:
            logger.info("Using native word timestamps mode (faster-whisper direct)")
            with profiler.step("transcription_native_word_ts"):
                transcription_result, audio = self.transcribe_with_word_timestamps(audio_file_path)
        else:
            with profiler.step("transcription"):
                transcription_result, audio = self.transcribe_audio(audio_file_path)
        logger.info(
            f"TIMING: transcribe_audio completed in {time.perf_counter() - step_start:.3f}s"
        )

        from .parallel_pipeline import ThreadSafeProgress
        from .parallel_pipeline import can_run_parallel
        from .parallel_pipeline import get_pipeline_mode
        from .parallel_pipeline import run_parallel_pipeline

        pipeline_mode = get_pipeline_mode()
        use_parallel = pipeline_mode == "parallel" and can_run_parallel()

        if use_parallel:
            # Parallel mode: alignment and diarization run concurrently in threads
            logger.info("Using PARALLEL pipeline mode (alignment + diarization concurrent)")
            progress_wrapper = ThreadSafeProgress(progress_callback) if progress_callback else None
            step_start = time.perf_counter()
            with profiler.step("parallel_align_and_diarize"):
                aligned_result, diarize_segments = run_parallel_pipeline(
                    whisperx_service=self,
                    audio_file_path=audio_file_path,
                    audio=audio,
                    transcription_result=transcription_result,
                    hf_token=hf_token,
                    min_speakers=min_speakers,
                    max_speakers=max_speakers,
                    num_speakers=num_speakers,
                    progress=progress_wrapper,
                )
            logger.info(
                f"TIMING: parallel align+diarize completed in {time.perf_counter() - step_start:.3f}s"
            )
        else:
            # Sequential mode: alignment then diarization (default)
            logger.info(f"Using SEQUENTIAL pipeline mode (PIPELINE_MODE={pipeline_mode})")

            # Step 2: Align (50% -> 55%) - optional, disabled by default for performance
            # Word-level timestamps from alignment are not persisted to DB or used by any
            # downstream feature (search, frontend seek, speaker assignment all use segment-level).
            # Enable with ENABLE_ALIGNMENT=true if word-level highlighting is needed.
            # Skip alignment if native word timestamps are enabled (already have word timing)
            enable_alignment = os.getenv("ENABLE_ALIGNMENT", "false").lower() == "true"
            if use_native_word_ts:
                enable_alignment = False
                logger.info(
                    "TIMING: alignment SKIPPED (native word timestamps already provide word timing)"
                )

            if enable_alignment:
                self._report_progress(progress_callback, 0.50, "Aligning word-level timestamps")
                step_start = time.perf_counter()
                with profiler.step("alignment"):
                    aligned_result = self._align_with_fallback(transcription_result, audio)
                logger.info(
                    f"TIMING: align_transcription completed in {time.perf_counter() - step_start:.3f}s"
                )
            else:
                logger.info("TIMING: alignment SKIPPED (ENABLE_ALIGNMENT=false)")
                aligned_result = transcription_result

            # Step 3: Diarize (55% -> 65%)
            self._report_progress(progress_callback, 0.55, "Analyzing speaker patterns")
            step_start = time.perf_counter()
            with profiler.step("diarization"):
                diarize_segments = self.perform_speaker_diarization(
                    audio,
                    hf_token,
                    max_speakers=max_speakers,
                    min_speakers=min_speakers,
                    num_speakers=num_speakers,
                )
            logger.info(
                f"TIMING: perform_speaker_diarization completed in {time.perf_counter() - step_start:.3f}s"
            )

        # Extract overlap info from PyAnnote v4 diarization before speaker assignment
        # diarize_segments is a DataFrame with attrs for overlap info
        overlaps = diarize_segments.attrs.get("overlaps", [])
        overlap_count = diarize_segments.attrs.get("overlap_count", 0)

        # Step 4: Assign speakers (65% -> 70%)
        self._report_progress(progress_callback, 0.65, "Assigning speakers to transcript")
        self.hardware_config.log_vram_usage("before assign_word_speakers")
        step_start = time.perf_counter()
        with profiler.step("speaker_assignment"):
            final_result = self.assign_speakers_to_words(diarize_segments, aligned_result)
        logger.info(
            f"TIMING: assign_word_speakers (WhisperX) completed in {time.perf_counter() - step_start:.3f}s"
        )
        self.hardware_config.log_vram_usage("after assign_word_speakers")

        # Step 4b: Segment dedup (when alignment is disabled)
        # Without alignment, WhisperX returns both coarse VAD-chunked segments AND
        # fine-grained subsegments, creating duplicates. Clean them up.
        # Can be explicitly disabled with ENABLE_SEGMENT_DEDUP=false for A/B testing.
        enable_alignment = os.getenv("ENABLE_ALIGNMENT", "false").lower() == "true"
        enable_dedup = os.getenv("ENABLE_SEGMENT_DEDUP", "true").lower() == "true"
        if not enable_alignment and enable_dedup:
            from app.utils.segment_dedup import clean_segments

            step_start = time.perf_counter()
            original_count = len(final_result.get("segments", []))
            final_result["segments"] = clean_segments(final_result["segments"])
            logger.info(
                f"TIMING: segment_dedup completed in {time.perf_counter() - step_start:.3f}s "
                f"- {original_count} -> {len(final_result['segments'])} segments"
            )
        elif not enable_alignment and not enable_dedup:
            logger.info("TIMING: segment_dedup SKIPPED (ENABLE_SEGMENT_DEDUP=false)")

        # Step 5: Log overlapping speech detection (70% -> 75%)
        step_start = time.perf_counter()
        self._handle_overlapping_speech(overlaps, overlap_count)
        logger.info(
            f"TIMING: _handle_overlapping_speech completed in {time.perf_counter() - step_start:.3f}s"
        )

        # Add overlap metadata to result
        self._add_overlap_metadata(
            final_result, overlap_count, diarize_segments.attrs.get("overlap_duration", 0), overlaps
        )

        # CRITICAL: Force cleanup of diarize_segments and audio to free all VRAM
        self.hardware_config.log_vram_usage("before final WhisperX cleanup")
        logger.info("Final cleanup of WhisperX pipeline objects")
        del diarize_segments
        del aligned_result
        del audio
        self.hardware_config.optimize_memory_usage()
        self.hardware_config.log_vram_usage("after final WhisperX cleanup")

        # Log VRAM profiling report
        profiler.log_report()

        pipeline_elapsed = time.perf_counter() - pipeline_start
        logger.info(
            f"TIMING: run_pipeline_with_diarization TOTAL completed in {pipeline_elapsed:.3f}s"
        )

        return final_result
