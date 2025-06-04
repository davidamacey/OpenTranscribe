import os
import logging
from pathlib import Path
from typing import Dict, Any
import torch

from app.utils.hardware_detection import detect_hardware

logger = logging.getLogger(__name__)


class WhisperXService:
    """Service for handling WhisperX transcription operations with cross-platform support."""
    
    def __init__(self, model_name: str = None, models_dir: str = None):
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
        
        logger.info(f"WhisperX initialized: model={self.model_name}, device={self.device}, "
                   f"compute_type={self.compute_type}, batch_size={self.batch_size}")
    
    def _apply_environment_optimizations(self):
        """Apply environment variable optimizations for the detected hardware."""
        env_vars = self.hardware_config.get_environment_variables()
        for key, value in env_vars.items():
            if key not in os.environ:  # Don't override existing settings
                os.environ[key] = value
                logger.debug(f"Set environment variable: {key}={value}")
    
    def transcribe_audio(self, audio_file_path: str) -> Dict[str, Any]:
        """
        Transcribe audio using WhisperX.
        
        Args:
            audio_file_path: Path to the audio file
            
        Returns:
            Dictionary containing transcription result
        """
        try:
            import whisperx
            import gc
        except ImportError:
            raise ImportError("WhisperX is not installed. Please install it with 'pip install whisperx'.")
        
        # Load model with hardware-specific configuration
        logger.info(f"Loading WhisperX model: {self.model_name} on {self.device}")
        
        load_options = {
            "whisper_arch": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
            "download_root": self.whisperx_model_directory,
            "language": "en"
        }
        
        # Add device-specific options
        if self.device == "cuda":
            load_options["device_index"] = int(os.getenv("GPU_DEVICE_ID", "0"))
        
        model = whisperx.load_model(**load_options)
        
        # Load and transcribe audio
        logger.info(f"Transcribing audio file: {audio_file_path}")
        audio = whisperx.load_audio(audio_file_path)
        
        transcription_result = model.transcribe(
            audio,
            batch_size=self.batch_size,
            task="translate"  # Always translate to English
        )
        
        logger.info(f"Initial transcription completed with {len(transcription_result['segments'])} segments")
        
        # Optimize memory usage based on device
        self.hardware_config.optimize_memory_usage()
        del model
        
        return transcription_result, audio
    
    def align_transcription(self, transcription_result: Dict[str, Any], audio) -> Dict[str, Any]:
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
            import gc
        except ImportError:
            raise ImportError("WhisperX is not installed.")
        
        logger.info("Loading alignment model...")
        align_model, align_metadata = whisperx.load_align_model(
            language_code=transcription_result["language"],
            device=self.device,
            model_name=None
        )
        
        logger.info("Aligning transcription for precise word timings...")
        aligned_result = whisperx.align(
            transcription_result["segments"],
            align_model,
            align_metadata,
            audio,
            self.device,
            return_char_alignments=False
        )
        
        # Optimize memory usage based on device
        self.hardware_config.optimize_memory_usage()
        del align_model
        
        return aligned_result
    
    def perform_speaker_diarization(self, audio, hf_token: str = None, 
                                  max_speakers: int = 10, min_speakers: int = 1) -> Dict[str, Any]:
        """
        Perform speaker diarization on audio.
        
        Args:
            audio: Loaded audio data
            hf_token: HuggingFace token for accessing models
            max_speakers: Maximum number of speakers
            min_speakers: Minimum number of speakers
            
        Returns:
            Diarization result
        """
        try:
            import whisperx
        except ImportError:
            raise ImportError("WhisperX is not installed.")
        
        logger.info("Performing speaker diarization...")
        
        diarize_params = {
            "max_speakers": max_speakers,
            "min_speakers": min_speakers
        }
        
        # Use PyAnnote-compatible device configuration
        pyannote_config = self.hardware_config.get_pyannote_config()
        
        diarize_model = whisperx.DiarizationPipeline(
            use_auth_token=hf_token,
            device=pyannote_config["device"]
        )
        
        diarize_segments = diarize_model(audio, **diarize_params)
        return diarize_segments
    
    def assign_speakers_to_words(self, diarize_segments, aligned_result: Dict[str, Any]) -> Dict[str, Any]:
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
        except ImportError:
            raise ImportError("WhisperX is not installed.")
        
        logger.info("Assigning speaker labels to transcript...")
        result = whisperx.assign_word_speakers(diarize_segments, aligned_result)
        return result
    
    def process_full_pipeline(self, audio_file_path: str, hf_token: str = None, progress_callback=None) -> Dict[str, Any]:
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