#!/usr/bin/env python3
"""
Download all required AI models for OpenTranscribe offline packaging.

This script downloads:
- WhisperX models
- PyAnnote speaker diarization models
- Wav2Vec2 alignment models
- NLTK data files (punkt_tab tokenizer)
- Sentence-Transformers models (all-MiniLM-L6-v2)

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

def validate_gated_model_access():
    """Validate access to gated PyAnnote models before attempting download"""
    print_info("Validating access to gated PyAnnote models...")
    print_info("")

    try:
        from huggingface_hub import HfApi

        hf_token = os.environ.get("HUGGINGFACE_TOKEN")
        if not hf_token:
            return False, "No HuggingFace token provided"

        # List of REQUIRED gated models
        gated_models = [
            "pyannote/segmentation-3.0",
            "pyannote/speaker-diarization-3.1"
        ]

        api = HfApi()
        inaccessible_models = []
        access_errors = {}

        for model_id in gated_models:
            try:
                # Try to get model info - this will fail if user hasn't accepted the license
                model_info = api.model_info(model_id, token=hf_token)
                print_success(f"  ✓ Access confirmed: {model_id}")
            except Exception as e:
                error_msg = str(e)
                inaccessible_models.append(model_id)
                access_errors[model_id] = error_msg

                # Determine error type
                if "401" in error_msg or "Unauthorized" in error_msg:
                    print_error(f"  ✗ Access DENIED (401 Unauthorized): {model_id}")
                    print_error(f"     You have NOT accepted the model agreement!")
                elif "403" in error_msg or "Forbidden" in error_msg:
                    print_error(f"  ✗ Access DENIED (403 Forbidden): {model_id}")
                    print_error(f"     Token may not have required permissions")
                else:
                    print_error(f"  ✗ Cannot access: {model_id}")
                    print_error(f"     Error: {error_msg[:80]}")

        print_info("")

        if inaccessible_models:
            error_msg = f"Cannot access {len(inaccessible_models)} required gated model(s)"
            print_error("VALIDATION FAILED: Missing gated model access!")
            return False, (error_msg, access_errors)

        print_success("✅ All required gated models are accessible!")
        print_info("")
        return True, None

    except ImportError:
        # huggingface_hub might not be available, skip validation but warn
        print_info("  ⚠️  Skipping gated model validation (huggingface_hub not available)")
        print_info("  This is not recommended - validation may fail during download")
        print_info("")
        return True, None
    except Exception as e:
        # Unexpected error during validation - don't block but warn strongly
        print_error(f"  ⚠️  Could not validate gated models: {e}")
        print_info("  Proceeding anyway, but download may fail...")
        print_info("")
        return True, None

def validate_pyannote_download():
    """Validate that all expected PyAnnote models were downloaded to the torch cache"""
    torch_cache = Path.home() / ".cache" / "torch" / "pyannote"

    # Expected PyAnnote model directories
    expected_models = {
        "segmentation-3.0": "models--pyannote--segmentation-3.0",
        "speaker-diarization-3.1": "models--pyannote--speaker-diarization-3.1",
        "wespeaker-voxceleb": "models--pyannote--wespeaker-voxceleb-resnet34-LM"
    }

    validation_result = {
        "all_present": True,
        "models": {}
    }

    if not torch_cache.exists():
        validation_result["all_present"] = False
        for model_name in expected_models.keys():
            validation_result["models"][model_name] = False
        return validation_result

    for model_name, model_dir in expected_models.items():
        model_path = torch_cache / model_dir
        is_present = model_path.exists() and model_path.is_dir()
        validation_result["models"][model_name] = is_present
        if not is_present:
            validation_result["all_present"] = False

    return validation_result

def download_pyannote_models():
    """Download PyAnnote models by running full WhisperX pipeline (same as backend)"""
    print_header("Downloading PyAnnote Models")

    try:
        import whisperx
        import torch
        import numpy as np

        hf_token = os.environ.get("HUGGINGFACE_TOKEN")
        if not hf_token:
            print_error("HUGGINGFACE_TOKEN not set!")
            print_error("")
            print_error("A HuggingFace token is REQUIRED for speaker diarization models.")
            print_error("")
            print_error("To get your FREE token:")
            print_error("  1. Visit: https://huggingface.co/settings/tokens")
            print_error("  2. Click 'New token' and select 'Read' permissions")
            print_error("  3. Copy the token")
            print_error("")
            print_error("Then set it as an environment variable:")
            print_error("  export HUGGINGFACE_TOKEN=your_token_here")
            return {"pyannote": {"status": "failed", "error": "No HuggingFace token"}}

        # Validate access to gated models BEFORE attempting download
        has_access, access_result = validate_gated_model_access()
        if not has_access:
            print_error("")
            print_error("=" * 80)
            print_error("❌ GATED MODEL ACCESS DENIED - DOWNLOAD CANNOT PROCEED")
            print_error("=" * 80)
            print_error("")
            print_error("⚠️  YOUR TOKEN DOES NOT HAVE ACCESS TO REQUIRED PYANNOTE MODELS")
            print_error("")
            print_error("This means you have NOT accepted the model user agreements.")
            print_error("")
            print_error("╔════════════════════════════════════════════════════════════════════╗")
            print_error("║  REQUIRED ACTION: Accept BOTH model agreements on HuggingFace      ║")
            print_error("╚════════════════════════════════════════════════════════════════════╝")
            print_error("")
            print_error("Step 1: Visit the Segmentation Model page")
            print_error("   URL: https://huggingface.co/pyannote/segmentation-3.0")
            print_error("   → Look for the 'Agree and access repository' button")
            print_error("   → Click it to accept the terms")
            print_error("")
            print_error("Step 2: Visit the Speaker Diarization Model page")
            print_error("   URL: https://huggingface.co/pyannote/speaker-diarization-3.1")
            print_error("   → Look for the 'Agree and access repository' button")
            print_error("   → Click it to accept the terms")
            print_error("")
            print_error("Step 3: Wait 1-2 minutes for permissions to propagate")
            print_error("")
            print_error("Step 4: Run this script again:")
            print_error("   bash scripts/download-models.sh models")
            print_error("")
            print_error("=" * 80)
            print_error("")

            error_msg = access_result[0] if isinstance(access_result, tuple) else access_result
            return {"pyannote": {"status": "failed", "error": error_msg}}

        # Use default paths (same as backend) - let WhisperX/PyAnnote handle caching
        print_info("Using WhisperX full pipeline (same as backend) to download all models")
        print_info("Models will be cached to default locations (managed by WhisperX/PyAnnote)")

        # Detect device
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "float32"
        print_info(f"Using device: {device}")

        # Create synthetic audio (30 seconds of silence with some noise for testing)
        print_info("Creating synthetic test audio (30 seconds)...")
        sample_rate = 16000
        duration = 30  # 30 seconds

        # Generate audio with some speech-like characteristics
        # Use a simple sine wave pattern that mimics speech frequencies
        t = np.linspace(0, duration, sample_rate * duration)
        frequencies = [300, 500, 700]  # Speech-like frequencies
        audio = np.zeros_like(t)
        for freq in frequencies:
            audio += 0.1 * np.sin(2 * np.pi * freq * t)

        # Add some noise to make it more realistic
        audio += 0.05 * np.random.randn(len(t))

        # Normalize
        audio = audio.astype(np.float32)
        print_success("  Synthetic audio created")

        # Use WhisperX full pipeline (same as backend)
        print_info("Step 1/4: Audio ready...")
        print_success("  Audio prepared")

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
            max_speakers=20
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

        # Validate that all expected PyAnnote models were downloaded
        validation_result = validate_pyannote_download()
        if not validation_result["all_present"]:
            print_error("")
            print_error("=" * 70)
            print_error("WARNING: Some PyAnnote models may not have downloaded completely")
            print_error("=" * 70)
            print_error("")
            print_error("Expected models:")
            for model_name, present in validation_result["models"].items():
                status = "✓ Found" if present else "✗ Missing"
                print_error(f"  {status}: {model_name}")
            print_error("")
            print_error("If you encounter errors during transcription:")
            print_error("  1. Verify you accepted BOTH gated model agreements")
            print_error("  2. Run this script again to re-download models")
            print_error("")

        return {
            "pyannote": {
                "model": "pyannote/speaker-diarization-3.1",
                "status": "downloaded",
                "validation": validation_result
            }
        }

    except Exception as e:
        error_msg = str(e)
        print_error(f"Failed to download PyAnnote models: {error_msg}")

        # Check if this looks like a gated model access error
        if "cannot find the requested files" in error_msg.lower() or \
           "locate the file on the hub" in error_msg.lower() or \
           "403" in error_msg or \
           "401" in error_msg:
            print_error("")
            print_error("=" * 70)
            print_error("⚠️  THIS LOOKS LIKE A GATED MODEL ACCESS ERROR!")
            print_error("=" * 70)
            print_error("")
            print_error("This error usually means you haven't accepted the model agreements.")
            print_error("")
            print_error("You MUST accept BOTH PyAnnote gated model agreements:")
            print_error("")
            print_error("  1. Segmentation Model:")
            print_error("     https://huggingface.co/pyannote/segmentation-3.0")
            print_error("     → Click 'Agree and access repository'")
            print_error("")
            print_error("  2. Speaker Diarization Model:")
            print_error("     https://huggingface.co/pyannote/speaker-diarization-3.1")
            print_error("     → Click 'Agree and access repository'")
            print_error("")
            print_error("After accepting BOTH agreements:")
            print_error("  • Wait 1-2 minutes for permissions to propagate")
            print_error("  • Run this script again: bash scripts/download-models.sh models")
            print_error("")
            print_error("=" * 70)

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

def download_nltk_data():
    """Download NLTK data files required by transformers/whisperx"""
    print_header("Downloading NLTK Data")

    try:
        import nltk

        # Set NLTK data path to user's cache directory
        nltk_data_path = Path.home() / ".cache" / "nltk_data"
        nltk_data_path.mkdir(parents=True, exist_ok=True)

        # Add to NLTK's data path
        if str(nltk_data_path) not in nltk.data.path:
            nltk.data.path.insert(0, str(nltk_data_path))

        print_info(f"NLTK data path: {nltk_data_path}")

        # Download required NLTK data packages
        # punkt_tab is required by transformers/whisperx for tokenization
        required_packages = [
            'punkt_tab',       # Punkt tokenizer (new tabular format)
            'punkt',           # Punkt tokenizer (legacy format for compatibility)
            'averaged_perceptron_tagger_eng',  # POS tagger (may be needed by transformers)
        ]

        downloaded = []
        for package in required_packages:
            try:
                print_info(f"Downloading NLTK package: {package}")
                nltk.download(package, download_dir=str(nltk_data_path), quiet=False)
                downloaded.append(package)
                print_success(f"  Downloaded: {package}")
            except Exception as pkg_error:
                print_error(f"  Failed to download {package}: {pkg_error}")

        if downloaded:
            print_success(f"NLTK data downloaded successfully ({len(downloaded)} packages)")
        else:
            raise Exception("No NLTK packages were downloaded")

        return {
            "nltk": {
                "packages": downloaded,
                "path": str(nltk_data_path),
                "status": "downloaded"
            }
        }

    except Exception as e:
        print_error(f"Failed to download NLTK data: {e}")
        return {"nltk": {"status": "failed", "error": str(e)}}

def download_sentence_transformers():
    """Download sentence-transformers model for semantic search"""
    print_header("Downloading Sentence-Transformers Model")

    try:
        from sentence_transformers import SentenceTransformer

        model_name = "all-MiniLM-L6-v2"
        cache_path = Path.home() / ".cache" / "sentence-transformers"
        cache_path.mkdir(parents=True, exist_ok=True)

        print_info(f"Model: {model_name}")
        print_info(f"Cache path: {cache_path}")
        print_info("Loading sentence-transformers model (this will download if needed)...")

        # Load model (will download to cache if not present)
        model = SentenceTransformer(model_name, cache_folder=str(cache_path))

        # Test the model with a sample text to ensure it works
        test_embedding = model.encode("This is a test sentence.")
        print_info(f"  Embedding dimension: {len(test_embedding)}")

        print_success(f"Sentence-transformers model '{model_name}' downloaded successfully")

        # Clean up
        del model

        return {
            "sentence_transformers": {
                "model": model_name,
                "path": str(cache_path),
                "dimension": len(test_embedding),
                "status": "downloaded"
            }
        }

    except Exception as e:
        print_error(f"Failed to download sentence-transformers model: {e}")
        return {"sentence_transformers": {"status": "failed", "error": str(e)}}

def get_cache_info():
    """Get information about cached models"""
    # Use default paths (same as backend)
    hf_home = str(Path.home() / ".cache" / "huggingface")
    torch_home = str(Path.home() / ".cache" / "torch")
    nltk_home = str(Path.home() / ".cache" / "nltk_data")
    sent_home = str(Path.home() / ".cache" / "sentence-transformers")

    cache_dirs = {
        "huggingface": Path(hf_home),
        "torch": Path(torch_home),
        "nltk_data": Path(nltk_home),
        "sentence_transformers": Path(sent_home)
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
    results.update(download_nltk_data())
    results.update(download_sentence_transformers())

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
