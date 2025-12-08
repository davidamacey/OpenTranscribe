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
        model_name: str = None,
        models_dir: str = None,
        source_language: str = "auto",
        translate_to_english: bool = False,
    ):
        # Initialize hardware detection
        self.hardware_config = detect_hardware()

        # Model configuration
        self.model_name = model_name or os.getenv("WHISPER_MODEL", "large-v2")
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

            return transcription_result

        except Exception as e:
            logger.error(f"Transcription failed for {audio_file_path}: {str(e)}")
            raise ValueError(
                f"Audio transcription failed. The file may contain no speech, be corrupted, or be in an unsupported format: {str(e)}"
            ) from e

    def transcribe_audio(self, audio_file_path: str) -> dict[str, Any]:
        """
        Transcribe audio using WhisperX.

        Args:
            audio_file_path: Path to the audio file

        Returns:
            Dictionary containing transcription result
        """
        try:
            import whisperx
        except ImportError as e:
            raise ImportError(
                "WhisperX is not installed. Please install it with 'pip install whisperx'."
            ) from e

        # Load model with hardware-specific configuration
        self._log_model_loading()

        load_options = {
            "whisper_arch": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
        }

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

        return aligned_result

    def perform_speaker_diarization(
        self,
        audio,
        hf_token: str = None,
        max_speakers: int = 20,
        min_speakers: int = 1,
        num_speakers: int = None,
    ) -> dict[str, Any]:
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
                use_auth_token=hf_token, device=pyannote_config["device"]
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

            return diarize_segments

        except Exception as e:
            error_msg = str(e)

            # Detect HuggingFace gated model access errors (same checks as download scripts)
            if "401" in error_msg or "unauthorized" in error_msg.lower():
                logger.error(f"HuggingFace authentication error: {error_msg}")
                raise PermissionError(
                    "Cannot access PyAnnote speaker diarization models. "
                    "Your HuggingFace token does not have access to the required gated models. "
                    "You must accept BOTH model agreements on HuggingFace: "
                    "pyannote/segmentation-3.0 (https://huggingface.co/pyannote/segmentation-3.0) and "
                    "pyannote/speaker-diarization-3.1 (https://huggingface.co/pyannote/speaker-diarization-3.1). "
                    "After accepting both agreements, wait 1-2 minutes for permissions to propagate, "
                    "restart the application containers, and re-upload your file for transcription."
                ) from e

            # Detect 403 Forbidden errors
            if "403" in error_msg or "forbidden" in error_msg.lower():
                logger.error(f"HuggingFace permission error: {error_msg}")
                raise PermissionError(
                    "Access forbidden to PyAnnote models. "
                    "Your HuggingFace token may not have the required Read permissions, "
                    "or you have not accepted the gated model agreements. "
                    "Please verify your token has Read permissions at https://huggingface.co/settings/tokens "
                    "and accept both model agreements: pyannote/segmentation-3.0 and pyannote/speaker-diarization-3.1."
                ) from e

            # Detect generic Hub errors that indicate missing model access
            if (
                "cannot find the requested files" in error_msg.lower()
                or "locate the file on the hub" in error_msg.lower()
            ):
                logger.error(f"HuggingFace model access error: {error_msg}")
                raise PermissionError(
                    "Cannot download PyAnnote models from HuggingFace. "
                    "This usually means you have not accepted the gated model agreements. "
                    "Please accept both model agreements at https://huggingface.co/pyannote/segmentation-3.0 "
                    "and https://huggingface.co/pyannote/speaker-diarization-3.1, "
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

        Args:
            diarize_segments: Result from speaker diarization
            aligned_result: Aligned transcription result

        Returns:
            Final result with speaker assignments
        """
        try:
            import whisperx
        except ImportError as e:
            raise ImportError("WhisperX is not installed.") from e

        logger.info("Assigning speaker labels to transcript...")
        result = whisperx.assign_word_speakers(diarize_segments, aligned_result)
        return result

    def process_full_pipeline(
        self,
        audio_file_path: str,
        hf_token: str = None,
        progress_callback=None,
        min_speakers: int = 1,
        max_speakers: int = 20,
        num_speakers: int = None,
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
        # Step 1: Transcribe (40% -> 50%)
        if progress_callback:
            progress_callback(0.42, "Running initial transcription")
        transcription_result, audio = self.transcribe_audio(audio_file_path)

        # Step 2: Align (50% -> 55%) - with graceful fallback for unsupported languages
        if progress_callback:
            progress_callback(0.50, "Aligning word-level timestamps")

        try:
            aligned_result = self.align_transcription(transcription_result, audio)
        except Exception as e:
            # Alignment model not available for this language - use segment-level timestamps
            detected_lang = transcription_result.get("language", "unknown")
            logger.warning(
                f"Alignment model not available for language '{detected_lang}'. "
                f"Using segment-level timestamps (word-level timing disabled). Error: {e}"
            )
            # Fall back to transcription result without word alignment
            aligned_result = transcription_result

        # Step 3: Diarize (55% -> 65%)
        if progress_callback:
            progress_callback(0.55, "Analyzing speaker patterns")
        diarize_segments = self.perform_speaker_diarization(
            audio,
            hf_token,
            max_speakers=max_speakers,
            min_speakers=min_speakers,
            num_speakers=num_speakers,
        )

        # Step 4: Assign speakers (65% -> 70%)
        if progress_callback:
            progress_callback(0.65, "Assigning speakers to transcript")

        # Log VRAM before speaker assignment
        self.hardware_config.log_vram_usage("before assign_word_speakers")
        final_result = self.assign_speakers_to_words(diarize_segments, aligned_result)
        self.hardware_config.log_vram_usage("after assign_word_speakers")

        # CRITICAL: Force cleanup of diarize_segments and audio to free all VRAM
        # These objects may hold references to models internally
        self.hardware_config.log_vram_usage("before final WhisperX cleanup")
        logger.info("Final cleanup of WhisperX pipeline objects")
        del diarize_segments
        del aligned_result
        del audio
        self.hardware_config.optimize_memory_usage()
        self.hardware_config.log_vram_usage("after final WhisperX cleanup")
        logger.info("WhisperX pipeline cleanup completed")

        return final_result
