#!/bin/bash
set -e

# Test Model Download Script
# Quick test of model download without full offline package build

echo "=== Testing Model Download ==="

# Load .env for HF token
if [ -f .env ]; then
    export HUGGINGFACE_TOKEN=$(grep "^HUGGINGFACE_TOKEN=" .env | cut -d'=' -f2)
fi

# Create test cache directory
TEST_CACHE="./test-model-cache"
rm -rf "$TEST_CACHE"
mkdir -p "$TEST_CACHE/huggingface"
mkdir -p "$TEST_CACHE/torch"

echo "Test cache directory: $TEST_CACHE"
echo ""

# Run model download in Docker container (runs as appuser, not root)
echo "Running model download..."
docker run --rm \
    --gpus all \
    -e HUGGINGFACE_TOKEN="${HUGGINGFACE_TOKEN}" \
    -e WHISPER_MODEL="base" \
    -e DIARIZATION_MODEL="pyannote/speaker-diarization-3.1" \
    -e USE_GPU="true" \
    -e COMPUTE_TYPE="float16" \
    -v "${TEST_CACHE}/huggingface:/home/appuser/.cache/huggingface" \
    -v "${TEST_CACHE}/torch:/home/appuser/.cache/torch" \
    -v "$(pwd)/scripts/download-models.py:/app/download-models.py" \
    -v "$(pwd)/test_videos:/app/test_videos:ro" \
    davidamacey/opentranscribe-backend:latest \
    python /app/download-models.py

echo ""
echo "=== Checking Downloaded Models ==="
echo ""

echo "HuggingFace cache:"
du -sh "$TEST_CACHE/huggingface"
find "$TEST_CACHE/huggingface" -name "*.bin" -o -name "*.safetensors" | wc -l
echo " model files found"
echo ""

echo "Torch cache:"
du -sh "$TEST_CACHE/torch"
find "$TEST_CACHE/torch" -name "*.bin" -o -name "pytorch_model.bin" | wc -l
echo " model files found"
echo ""

echo "PyAnnote models in torch cache:"
ls -la "$TEST_CACHE/torch/pyannote/" 2>/dev/null || echo "No pyannote directory found!"
echo ""

echo "PyAnnote subdirectories:"
find "$TEST_CACHE/torch/pyannote" -maxdepth 1 -type d 2>/dev/null | sort
echo ""

echo "PyAnnote model weight files:"
find "$TEST_CACHE/torch/pyannote" -name "pytorch_model.bin" 2>/dev/null
echo ""

echo "=== Test Complete ==="
