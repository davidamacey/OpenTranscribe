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
    """Download PyAnnote models"""
    print_header("Downloading PyAnnote Models")

    try:
        from pyannote.audio import Pipeline

        hf_token = os.environ.get("HUGGINGFACE_TOKEN")
        if not hf_token:
            print_error("HUGGINGFACE_TOKEN not set!")
            return {"pyannote": {"status": "failed", "error": "No HuggingFace token"}}

        model_name = os.environ.get("DIARIZATION_MODEL", "pyannote/speaker-diarization-3.1")

        print_info(f"Model: {model_name}")
        print_info("Loading PyAnnote pipeline (this will download if needed)...")

        pipeline = Pipeline.from_pretrained(
            model_name,
            use_auth_token=hf_token
        )

        print_success(f"PyAnnote model '{model_name}' downloaded successfully")

        # Clean up
        del pipeline

        return {
            "pyannote": {
                "model": model_name,
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
    cache_dirs = {
        "huggingface": Path.home() / ".cache" / "huggingface",
        "torch": Path.home() / ".cache" / "torch"
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

    # Write manifest
    manifest_path = Path.home() / ".cache" / "model_manifest.json"
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
