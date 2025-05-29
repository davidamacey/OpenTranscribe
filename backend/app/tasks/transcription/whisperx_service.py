import os
import logging
from pathlib import Path
from typing import Dict, Any
import torch

logger = logging.getLogger(__name__)


class WhisperXService:
    """Service for handling WhisperX transcription operations."""
    
    def __init__(self, model_name: str = "medium.en", models_dir: str = None):
        self.model_name = model_name
        self.models_dir = models_dir or Path.cwd() / "models"
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.compute_type = "float16" if self.device == "cuda" else "float32"
        self.batch_size = 16
        
        # Ensure models directory exists
        self.whisperx_model_directory = os.path.join(self.models_dir, "whisperx")
        os.makedirs(self.whisperx_model_directory, exist_ok=True)
        
        logger.info(f"WhisperX initialized: model={model_name}, device={self.device}")
    
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
        
        # Load model
        logger.info(f"Loading WhisperX model: {self.model_name}")
        model = whisperx.load_model(
            self.model_name,
            self.device,
            compute_type=self.compute_type,
            download_root=self.whisperx_model_directory,
            language="en"
        )
        
        # Load and transcribe audio
        logger.info(f"Transcribing audio file: {audio_file_path}")
        audio = whisperx.load_audio(audio_file_path)
        
        transcription_result = model.transcribe(
            audio,
            batch_size=self.batch_size,
            task="translate"  # Always translate to English
        )
        
        logger.info(f"Initial transcription completed with {len(transcription_result['segments'])} segments")
        
        # Free GPU memory
        if self.device == "cuda":
            gc.collect()
            torch.cuda.empty_cache()
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
        
        # Free GPU memory
        if self.device == "cuda":
            gc.collect()
            torch.cuda.empty_cache()
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
        
        diarize_model = whisperx.DiarizationPipeline(
            use_auth_token=hf_token,
            device=self.device
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
    
    def process_full_pipeline(self, audio_file_path: str, hf_token: str = None) -> Dict[str, Any]:
        """
        Run the complete WhisperX pipeline: transcription, alignment, and diarization.
        
        Args:
            audio_file_path: Path to the audio file
            hf_token: HuggingFace token for speaker diarization
            
        Returns:
            Complete processing result with speaker assignments
        """
        # Step 1: Transcribe
        transcription_result, audio = self.transcribe_audio(audio_file_path)
        
        # Step 2: Align
        aligned_result = self.align_transcription(transcription_result, audio)
        
        # Step 3: Diarize
        diarize_segments = self.perform_speaker_diarization(audio, hf_token)
        
        # Step 4: Assign speakers
        final_result = self.assign_speakers_to_words(diarize_segments, aligned_result)
        
        return final_result