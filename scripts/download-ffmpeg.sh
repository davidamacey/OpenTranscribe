#!/bin/bash

# Download FFmpeg.wasm files for offline/self-hosted deployment
# Similar to how transcription models are cached locally

set -e

FFMPEG_VERSION="0.12.6"
CACHE_DIR="./frontend/public/ffmpeg"

echo "Downloading FFmpeg.wasm v${FFMPEG_VERSION} for offline use..."

# Create cache directory
mkdir -p "${CACHE_DIR}"

# Download core files from unpkg
echo "Downloading ffmpeg-core.js..."
curl -L "https://unpkg.com/@ffmpeg/core@${FFMPEG_VERSION}/dist/esm/ffmpeg-core.js" \
  -o "${CACHE_DIR}/ffmpeg-core.js"

echo "Downloading ffmpeg-core.wasm..."
curl -L "https://unpkg.com/@ffmpeg/core@${FFMPEG_VERSION}/dist/esm/ffmpeg-core.wasm" \
  -o "${CACHE_DIR}/ffmpeg-core.wasm"

echo "Downloading ffmpeg-core.worker.js..."
curl -L "https://unpkg.com/@ffmpeg/core@${FFMPEG_VERSION}/dist/esm/ffmpeg-core.worker.js" \
  -o "${CACHE_DIR}/ffmpeg-core.worker.js"

# Calculate file sizes
TOTAL_SIZE=$(du -sh "${CACHE_DIR}" | cut -f1)

echo ""
echo "✓ FFmpeg.wasm downloaded successfully!"
echo "  Location: ${CACHE_DIR}"
echo "  Total size: ${TOTAL_SIZE}"
echo ""
echo "To use local FFmpeg files:"
echo "  1. Set USE_LOCAL_FFMPEG=true in frontend/.env"
echo "  2. Files will be served from /ffmpeg/ path"
echo ""
