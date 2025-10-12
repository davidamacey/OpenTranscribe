import logging
import os
from pathlib import Path
from typing import Any

from app.utils.hardware_detection import detect_hardware

logger = logging.getLogger(__name__)


class WhisperXService:
    """Service for handling WhisperX transcription operations with cross-platform support."""

    def __init__(self, model_name: str = None, models_dir: str = None):
        # Add safe globals for PyTorch 2.6+ compatibility with PyAnnote
        # PyTorch 2.6+ changed torch.load() default to weights_only=True
        # PyAnnote models require ListConfig to be whitelisted
        try:
            import torch.serialization
            from omegaconf.listconfig import ListConfig

            torch.serialization.add_safe_globals([ListConfig])
            logger.debug("Added safe globals for PyTorch 2.6+ compatibility")
        except Exception as e:
            logger.warning(f"Could not add safe globals for torch.load: {e}")

        # Initialize hardware detection
        self.hardware_config = detect_hardware()

        # Model configuration
        self.model_name = model_name or os.getenv("WHISPER_MODEL", "medium.en")
        self.models_dir = models_dir or Path.cwd() / "models"

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
        if detected_device == "mps" and self.device == "cpu":
            logger.info(
                f"WhisperX initialized: model={self.model_name}, "
                f"detected_device={detected_device} (using CPU for WhisperX compatibility), "
                f"compute_type={self.compute_type}, batch_size={self.batch_size}"
            )
        else:
            logger.info(
                f"WhisperX initialized: model={self.model_name}, device={self.device}, "
                f"compute_type={self.compute_type}, batch_size={self.batch_size}"
            )

    def _apply_environment_optimizations(self):
        """Apply environment variable optimizations for the detected hardware."""
        env_vars = self.hardware_config.get_environment_variables()
        for key, value in env_vars.items():
            if key not in os.environ:  # Don't override existing settings
                os.environ[key] = value
                logger.debug(f"Set environment variable: {key}={value}")

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
        detected_device = self.hardware_config.device
        if detected_device == "mps" and self.device == "cpu":
            logger.info(
                f"Loading WhisperX model: {self.model_name} on {self.device} "
                f"(Apple Silicon detected, using CPU for WhisperX compatibility)"
            )
        else:
            logger.info(f"Loading WhisperX model: {self.model_name} on {self.device}")

        load_options = {
            "whisper_arch": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
            "language": "en",
        }

        # Add device-specific options
        if self.device == "cuda":
            # Always use device 0 since Docker maps the selected GPU to index 0
            load_options["device_index"] = 0

        model = whisperx.load_model(**load_options)

        # Load and transcribe audio
        logger.info(f"Transcribing audio file: {audio_file_path}")
        try:
            audio = whisperx.load_audio(audio_file_path)

            # Check if audio was loaded successfully and has content
            if audio is None or len(audio) == 0:
                raise ValueError("Audio file appears to be empty or corrupted")

            # Check for audio duration (very short files might be corrupted)
            # Use simple numpy-based duration calculation (no librosa needed)
            import numpy as np

            if isinstance(audio, np.ndarray):
                # Assume 16kHz sample rate (WhisperX default)
                duration = len(audio) / 16000
                if duration < 0.1:  # Less than 100ms
                    raise ValueError("Audio file is too short to contain meaningful content")

        except Exception as e:
            logger.error(f"Failed to load audio from {audio_file_path}: {str(e)}")
            if "No module named 'librosa'" in str(e):
                # Don't expose internal dependency issues to users
                raise ValueError(
                    "Audio file could not be processed. The file may be corrupted or in an unsupported format."
                ) from e
            raise ValueError(
                f"Unable to load audio content. The file may be corrupted, in an unsupported format, or contain no audio data: {str(e)}"
            ) from e

        try:
            transcription_result = model.transcribe(
                audio,
                batch_size=self.batch_size,
                task="translate",  # Always translate to English
            )

            # Validate transcription result
            if not transcription_result or "segments" not in transcription_result:
                raise ValueError("Transcription failed to produce valid output")

        except Exception as e:
            logger.error(f"Transcription failed for {audio_file_path}: {str(e)}")
            raise ValueError(
                f"Audio transcription failed. The file may contain no speech, be corrupted, or be in an unsupported format: {str(e)}"
            ) from e

        logger.info(
            f"Initial transcription completed with {len(transcription_result['segments'])} segments"
        )

        # Optimize memory usage based on device
        self.hardware_config.optimize_memory_usage()
        del model

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
        self.hardware_config.optimize_memory_usage()
        del align_model

        return aligned_result

    def perform_speaker_diarization(
        self, audio, hf_token: str = None, max_speakers: int = 10, min_speakers: int = 1
    ) -> dict[str, Any]:
        """
        Perform speaker diarization on audio.

        Args:
            audio: Loaded audio data
            hf_token: HuggingFace token for accessing models
            max_speakers: Maximum number of speakers
            min_speakers: Minimum number of speakers

        Returns:
            Diarization result

        Raises:
            RuntimeError: If cuDNN library compatibility issues occur
            ImportError: If WhisperX is not installed
        """
        try:
            import whisperx
        except ImportError as e:
            raise ImportError("WhisperX is not installed.") from e

        logger.info("Performing speaker diarization...")

        try:
            diarize_params = {"max_speakers": max_speakers, "min_speakers": min_speakers}

            # Use PyAnnote-compatible device configuration
            pyannote_config = self.hardware_config.get_pyannote_config()

            diarize_model = whisperx.diarize.DiarizationPipeline(
                use_auth_token=hf_token, device=pyannote_config["device"]
            )

            diarize_segments = diarize_model(audio, **diarize_params)
            return diarize_segments

        except Exception as e:
            error_msg = str(e)

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
        self, audio_file_path: str, hf_token: str = None, progress_callback=None
    ) -> dict[str, Any]:
        """
        Run the complete WhisperX pipeline: transcription, alignment, and diarization.

        Args:
            audio_file_path: Path to the audio file
            hf_token: HuggingFace token for speaker diarization
            progress_callback: Optional callback function for progress updates

        Returns:
            Complete processing result with speaker assignments
        """
        # Step 1: Transcribe (40% -> 50%)
        if progress_callback:
            progress_callback(0.42, "Running initial transcription")
        transcription_result, audio = self.transcribe_audio(audio_file_path)

        # Step 2: Align (50% -> 55%)
        if progress_callback:
            progress_callback(0.50, "Aligning word-level timestamps")
        aligned_result = self.align_transcription(transcription_result, audio)

        # Step 3: Diarize (55% -> 65%)
        if progress_callback:
            progress_callback(0.55, "Analyzing speaker patterns")
        diarize_segments = self.perform_speaker_diarization(audio, hf_token)

        # Step 4: Assign speakers (65% -> 70%)
        if progress_callback:
            progress_callback(0.65, "Assigning speakers to transcript")
        final_result = self.assign_speakers_to_words(diarize_segments, aligned_result)

        return final_result
