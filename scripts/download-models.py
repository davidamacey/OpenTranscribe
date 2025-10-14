#!/usr/bin/env python3
"""
Download all required AI models for OpenTranscribe offline packaging.

This script downloads:
- WhisperX models
- PyAnnote speaker diarization models
- Wav2Vec2 alignment models

Models are cached to standard locations and a manifest is created.
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime

def print_header(text):
    """Print formatted header"""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def print_info(text):
    """Print info message"""
    print(f"ℹ️  {text}")

def print_success(text):
    """Print success message"""
    print(f"✅ {text}")

def print_error(text):
    """Print error message"""
    print(f"❌ {text}")

def download_whisperx_models():
    """Download WhisperX models"""
    print_header("Downloading WhisperX Models")

    try:
        import whisperx

        model_name = os.environ.get("WHISPER_MODEL", "large-v2")
        device = "cuda" if os.environ.get("USE_GPU", "true").lower() == "true" else "cpu"
        compute_type = os.environ.get("COMPUTE_TYPE", "float16")

        print_info(f"Model: {model_name}")
        print_info(f"Device: {device}")
        print_info(f"Compute type: {compute_type}")

        print_info("Loading WhisperX model (this will download if needed)...")
        model = whisperx.load_model(
            model_name,
            device=device,
            compute_type=compute_type
        )

        print_success(f"WhisperX model '{model_name}' downloaded successfully")

        # Clean up
        del model

        return {
            "whisperx": {
                "model": model_name,
                "device": device,
                "compute_type": compute_type,
                "status": "downloaded"
            }
        }

    except Exception as e:
        print_error(f"Failed to download WhisperX models: {e}")
        return {"whisperx": {"status": "failed", "error": str(e)}}

def download_pyannote_models():
    """Download PyAnnote models by running full WhisperX pipeline (same as backend)"""
    print_header("Downloading PyAnnote Models")

    try:
        import whisperx
        import torch

        hf_token = os.environ.get("HUGGINGFACE_TOKEN")
        if not hf_token:
            print_error("HUGGINGFACE_TOKEN not set!")
            return {"pyannote": {"status": "failed", "error": "No HuggingFace token"}}

        # Use default paths (same as backend) - let WhisperX/PyAnnote handle caching
        print_info("Using WhisperX full pipeline (same as backend) to download all models")
        print_info("Models will be cached to default locations (managed by WhisperX/PyAnnote)")

        # Detect device
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "float32"
        print_info(f"Using device: {device}")

        # Get test video path
        test_audio_path = "/app/test_videos/The Race to Develop Warp Drive and AI Passing the Turing Test.mp4"

        if not os.path.exists(test_audio_path):
            raise FileNotFoundError(f"Test video not found: {test_audio_path}")

        print_info(f"Test video: {test_audio_path}")

        # Use WhisperX full pipeline (same as backend)
        print_info("Step 1/4: Loading audio with WhisperX...")
        audio = whisperx.load_audio(test_audio_path)

        # Limit to first 60 seconds
        sample_rate = 16000
        max_samples = sample_rate * 60
        if len(audio) > max_samples:
            audio = audio[:max_samples]
        print_success("  Audio loaded")

        # Step 2: Transcribe (same as backend)
        print_info("Step 2/4: Running WhisperX transcription...")
        model = whisperx.load_model(
            os.environ.get("WHISPER_MODEL", "base"),
            device=device,
            compute_type=compute_type
        )
        result = model.transcribe(audio, batch_size=16 if device == "cuda" else 1)
        print_success("  Transcription completed")
        del model
        torch.cuda.empty_cache() if device == "cuda" else None

        # Step 3: Align (same as backend - downloads wav2vec2)
        print_info("Step 3/4: Aligning transcription (downloads wav2vec2)...")
        model_a, metadata = whisperx.load_align_model(
            language_code="en",
            device=device
        )
        result = whisperx.align(
            result["segments"],
            model_a,
            metadata,
            audio,
            device=device
        )
        print_success("  Alignment completed")
        del model_a
        torch.cuda.empty_cache() if device == "cuda" else None

        # Step 4: Diarize (same as backend - downloads PyAnnote models)
        print_info("Step 4/4: Running speaker diarization (downloads PyAnnote models)...")
        print_info("  This downloads: segmentation-3.0, embedding, wespeaker-voxceleb...")

        diarize_model = whisperx.diarize.DiarizationPipeline(
            use_auth_token=hf_token,
            device=device
        )

        diarize_segments = diarize_model(
            audio,
            min_speakers=1,
            max_speakers=10
        )

        print_success("  Diarization completed")
        print_success("  All PyAnnote model weights (.bin files) downloaded")

        # Verify models were downloaded to default torch cache
        torch_cache = Path.home() / ".cache" / "torch"
        if torch_cache.exists():
            model_files = list(torch_cache.rglob("*.bin")) + list(torch_cache.rglob("pytorch_model.bin"))
            print_info(f"  Verified {len(model_files)} model files in torch cache")

        # Clean up
        del diarize_model
        del audio
        torch.cuda.empty_cache() if device == "cuda" else None

        return {
            "pyannote": {
                "model": "pyannote/speaker-diarization-3.1",
                "status": "downloaded"
            }
        }

    except Exception as e:
        print_error(f"Failed to download PyAnnote models: {e}")
        return {"pyannote": {"status": "failed", "error": str(e)}}

def download_alignment_models():
    """Download Wav2Vec2 alignment models"""
    print_header("Downloading Alignment Models")

    try:
        import torch
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

        model_name = "facebook/wav2vec2-large-960h-lv60-self"

        print_info(f"Model: {model_name}")
        print_info("Loading Wav2Vec2 model (this will download if needed)...")

        processor = Wav2Vec2Processor.from_pretrained(model_name)
        model = Wav2Vec2ForCTC.from_pretrained(model_name)

        print_success(f"Alignment model '{model_name}' downloaded successfully")

        # Clean up
        del processor, model

        return {
            "alignment": {
                "model": model_name,
                "status": "downloaded"
            }
        }

    except Exception as e:
        print_error(f"Failed to download alignment models: {e}")
        return {"alignment": {"status": "failed", "error": str(e)}}

def get_cache_info():
    """Get information about cached models"""
    # Use default paths (same as backend)
    hf_home = str(Path.home() / ".cache" / "huggingface")
    torch_home = str(Path.home() / ".cache" / "torch")

    cache_dirs = {
        "huggingface": Path(hf_home),
        "torch": Path(torch_home)
    }

    info = {}
    total_size = 0

    for name, path in cache_dirs.items():
        if path.exists():
            size = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
            total_size += size
            info[name] = {
                "path": str(path),
                "size_bytes": size,
                "size_gb": round(size / (1024**3), 2)
            }
        else:
            info[name] = {
                "path": str(path),
                "exists": False
            }

    info["total_size_gb"] = round(total_size / (1024**3), 2)

    return info

def create_manifest(download_results):
    """Create manifest file with model information"""
    print_header("Creating Model Manifest")

    manifest = {
        "created_at": datetime.now().isoformat(),
        "models": download_results,
        "cache": get_cache_info(),
        "environment": {
            "whisper_model": os.environ.get("WHISPER_MODEL", "large-v2"),
            "diarization_model": os.environ.get("DIARIZATION_MODEL", "pyannote/speaker-diarization-3.1"),
            "use_gpu": os.environ.get("USE_GPU", "true"),
            "compute_type": os.environ.get("COMPUTE_TYPE", "float16")
        }
    }

    # Write manifest to HF_HOME directory (inside the cache dir, not parent)
    cache_base = os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))
    manifest_path = Path(cache_base) / "model_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    print_success(f"Manifest created at: {manifest_path}")
    print_info(f"Total model cache size: {manifest['cache']['total_size_gb']} GB")

    return manifest

def main():
    """Main execution"""
    print_header("OpenTranscribe Model Downloader")

    print_info("This script will download all required AI models")
    print_info("Models will be cached for offline packaging\n")

    # Check for required environment variables
    if not os.environ.get("HUGGINGFACE_TOKEN"):
        print_error("HUGGINGFACE_TOKEN environment variable not set!")
        print_info("Get your token at: https://huggingface.co/settings/tokens")
        sys.exit(1)

    results = {}

    # Download all models
    results.update(download_whisperx_models())
    results.update(download_pyannote_models())
    results.update(download_alignment_models())

    # Create manifest
    manifest = create_manifest(results)

    # Summary
    print_header("Download Summary")

    failed = [k for k, v in results.items() if v.get("status") == "failed"]
    succeeded = [k for k, v in results.items() if v.get("status") == "downloaded"]

    if failed:
        print_error(f"Failed to download: {', '.join(failed)}")
        for model in failed:
            print_error(f"  {model}: {results[model].get('error', 'Unknown error')}")
        sys.exit(1)

    print_success(f"Successfully downloaded {len(succeeded)} model(s)")
    print_success(f"Total cache size: {manifest['cache']['total_size_gb']} GB")

    print("\nCache locations:")
    for name, info in manifest['cache'].items():
        if name != "total_size_gb":
            print(f"  {name}: {info['path']} ({info.get('size_gb', 0)} GB)")

    print_success("\n✨ All models downloaded successfully!")

if __name__ == "__main__":
    main()
