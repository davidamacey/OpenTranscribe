import whisperx
import gc
import torch
import argparse
import os
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main(audio_file_path: str, device_id: int, hf_token: str = None, output_dir: str = None):
    """
    Runs the WhisperX pipeline (transcription, alignment, diarization) on an audio file.

    Args:
        audio_file_path: Path to the input audio file.
        device_id: GPU device ID to use.
        hf_token: Hugging Face token for diarization. Diarization is skipped if None.
        output_dir: Directory to save transcription results. Defaults to audio file's directory.
    """
    # Set the specific GPU device
    if torch.cuda.is_available():
        if device_id >= torch.cuda.device_count():
            logger.error(f"GPU device ID {device_id} is not available. Max ID is {torch.cuda.device_count() - 1}.")
            logger.info(f"Available devices: {torch.cuda.device_count()}")
            logger.info("Please check your device_id or CUDA setup.")
            return
        os.environ["CUDA_VISIBLE_DEVICES"] = str(device_id)
        device = "cuda" # PyTorch will see the selected GPU as cuda:0
        logger.info(f"Attempting to use GPU device: {device_id} (PyTorch sees as cuda:0)")
    else:
        logger.warning("CUDA not available. Running on CPU. This will be very slow.")
        device = "cpu"

    audio_file = Path(audio_file_path)
    if not audio_file.is_file():
        logger.error(f"Audio file not found: {audio_file_path}")
        return

    if output_dir:
        output_path = Path(output_dir)
        try:
            output_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Could not create output directory {output_path}: {e}")
            return
    else:
        output_path = audio_file.parent

    batch_size = 16  # reduce if low on GPU mem
    compute_type = "float16"  # change to "int8" if low on GPU mem (may reduce accuracy)

    # Variables to hold models and results
    model = None
    model_a = None
    diarize_pipeline = None
    transcription_result = None
    audio_data = None

    try:
        logger.info(f"Loading audio from: {audio_file}")
        audio_data = whisperx.load_audio(str(audio_file))
    except Exception as e:
        logger.error(f"Error loading audio file {audio_file}: {e}")
        return

    # --- 1. Transcribe with original whisper (batched) ---
    try:
        logger.info("Loading Whisper model (large-v2)...")
        model = whisperx.load_model("large-v2", device, compute_type=compute_type)
        logger.info("Transcribing audio...")
        transcription_result = model.transcribe(audio_data, batch_size=batch_size)
        logger.info("Transcription (before alignment) complete.")
        with open(output_path / f"{audio_file.stem}_transcription_unaligned.txt", "w", encoding='utf-8') as f:
            for segment in transcription_result["segments"]:
                f.write(f"[{segment['start']:.2f}s - {segment['end']:.2f}s] {segment['text']}\n")
        logger.info(f"Unaligned transcription saved to {output_path / f'{audio_file.stem}_transcription_unaligned.txt'}")

    except Exception as e:
        logger.error(f"Error during transcription: {e}")
        return # Stop if transcription fails
    finally:
        if model:
            logger.info("Cleaning up Whisper model...")
            del model
            if device == "cuda": torch.cuda.empty_cache()
            gc.collect()

    if not transcription_result or "segments" not in transcription_result or not transcription_result["segments"]:
        logger.error("Transcription failed or produced no segments.")
        return

    # --- 2. Align whisper output ---
    try:
        logger.info("Loading alignment model...")
        model_a, metadata = whisperx.load_align_model(language_code=transcription_result["language"], device=device)
        logger.info("Aligning transcription...")
        transcription_result = whisperx.align(transcription_result["segments"], model_a, metadata, audio_data, device, return_char_alignments=False)
        logger.info("Alignment complete.")
        with open(output_path / f"{audio_file.stem}_transcription_aligned.txt", "w", encoding='utf-8') as f:
            for segment in transcription_result["segments"]:
                line = f"[{segment['start']:.2f}s - {segment['end']:.2f}s] {segment.get('text', '')}"
                if 'words' in segment:
                    line += "\n    Words: " + " ".join([f"{w.get('word','<NA>')}({w.get('start','?'):.2f}-{w.get('end','?'):.2f})" for w in segment.get('words', [])])
                f.write(line + "\n")
        logger.info(f"Aligned transcription saved to {output_path / f'{audio_file.stem}_transcription_aligned.txt'}")

    except Exception as e:
        logger.error(f"Error during alignment: {e}")
        # Proceed with unaligned segments for diarization if desired, or return
        return # For this script, stop if alignment fails as speaker assignment needs aligned words
    finally:
        if model_a:
            logger.info("Cleaning up alignment model...")
            del model_a
            if device == "cuda": torch.cuda.empty_cache()
            gc.collect()

    if not transcription_result or "segments" not in transcription_result or not transcription_result["segments"]:
        logger.error("Alignment failed or produced no segments.")
        return

    # --- 3. Assign speaker labels ---
    if not hf_token:
        logger.warning("Hugging Face token not provided. Skipping diarization and speaker assignment.")
        logger.info("Final result is the aligned transcription without speaker labels.")
    else:
        try:
            logger.info("Loading diarization model...")
            diarize_pipeline = whisperx.DiarizationPipeline(use_auth_token=hf_token, device=device)
            logger.info("Performing speaker diarization...")
            diarize_segments = diarize_pipeline(str(audio_file)) # Pass file path for pyannote's native handling
            # Or: diarize_segments = diarize_pipeline({"waveform": torch.from_numpy(audio_data).unsqueeze(0), "sample_rate": 16000})
            logger.info("Diarization complete.")
            with open(output_path / f"{audio_file.stem}_diarization_segments.txt", "w", encoding='utf-8') as f:
                f.write("Speaker | Segment_Start | Segment_End\n")
                for turn, _, speaker in diarize_segments.itertracks(yield_label=True):
                    f.write(f"{speaker} | {turn.start:.2f} | {turn.end:.2f}\n")
            logger.info(f"Diarization segments saved to {output_path / f'{audio_file.stem}_diarization_segments.txt'}")

            logger.info("Assigning word speakers...")
            result_final = whisperx.assign_word_speakers(diarize_segments, transcription_result)
            logger.info("Speaker assignment complete.")
            with open(output_path / f"{audio_file.stem}_transcription_final_speakers.txt", "w", encoding='utf-8') as f:
                for segment in result_final["segments"]:
                    speaker_label = segment.get('speaker', 'UNKNOWN')
                    line = f"[Speaker {speaker_label}] [{segment['start']:.2f}s - {segment['end']:.2f}s] {segment.get('text', '')}"
                    if 'words' in segment:
                        line += "\n    Words: " + " ".join([f"{w.get('word','<NA>')}(S:{w.get('speaker', '?')} {w.get('start','?'):.2f}-{w.get('end','?'):.2f})" for w in segment.get('words', [])])
                    f.write(line + "\n")
            logger.info(f"Final transcription with speakers saved to {output_path / f'{audio_file.stem}_transcription_final_speakers.txt'}")

        except Exception as e:
            logger.error(f"Error during diarization or speaker assignment: {e}")
        finally:
            if diarize_pipeline:
                logger.info("Cleaning up diarization model...")
                del diarize_pipeline
                if device == "cuda": torch.cuda.empty_cache()
                gc.collect()

    logger.info(f"WhisperX test script finished. Results are in {output_path.resolve()}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test script for WhisperX pipeline using specified GPU.")
    parser.add_argument("audio_file", type=str, help="Path to the audio file (e.g., test_videos/audio.mp3).")
    parser.add_argument("--device_id", type=int, default=2, help="GPU device ID to use (default: 2). Set by CUDA_VISIBLE_DEVICES.")
    parser.add_argument("--hf_token", type=str, default=os.environ.get("HF_TOKEN"),
                        help="Hugging Face token for diarization. Reads from HF_TOKEN env var if not set. Skips diarization if unavailable.")
    parser.add_argument("--output_dir", type=str, default=None,
                        help="Directory to save transcription results. Defaults to the audio file's directory.")

    args = parser.parse_args()

    if args.hf_token is None:
        logger.warning("Hugging Face token not provided via --hf_token argument or HF_TOKEN environment variable. Diarization and speaker assignment will be skipped.")

    main(args.audio_file, args.device_id, args.hf_token, args.output_dir)
