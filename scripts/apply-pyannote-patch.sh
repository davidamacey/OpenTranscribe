#!/usr/bin/env bash
# Apply/revert PyAnnote optimization patches inside the GPU worker container
#
# Patches are stored as files in patches/pyannote/ for reproducibility:
#   - speaker_diarization.py.orig    — stock PyAnnote 4.0.4
#   - speaker_diarization.py.patched — our optimized version
#   - embedding_batch_and_empty_cache.patch — unified diff
#
# Usage:
#   ./scripts/apply-pyannote-patch.sh status   # Show current patch state
#   ./scripts/apply-pyannote-patch.sh apply     # Copy patched file into container
#   ./scripts/apply-pyannote-patch.sh revert    # Restore original file in container
#   ./scripts/apply-pyannote-patch.sh diff      # Show what the patch changes

set -euo pipefail

CONTAINER="${CONTAINER:-transcribe-app-celery-worker-gpu-scaled}"
SITE_PACKAGES="/home/appuser/.local/lib/python3.13/site-packages"
SD_FILE="$SITE_PACKAGES/pyannote/audio/pipelines/speaker_diarization.py"
PATCHES_DIR="$(cd "$(dirname "$0")/../patches/pyannote" && pwd)"

apply_patch() {
  echo "=== Applying PyAnnote optimization patch ==="
  echo "  Source: $PATCHES_DIR/speaker_diarization.py.patched"
  echo "  Target: $CONTAINER:$SD_FILE"
  echo ""

  if [[ ! -f "$PATCHES_DIR/speaker_diarization.py.patched" ]]; then
    echo "ERROR: Patched file not found at $PATCHES_DIR/speaker_diarization.py.patched"
    exit 1
  fi

  docker cp "$PATCHES_DIR/speaker_diarization.py.patched" \
    "$CONTAINER:$SD_FILE"

  echo "  Patch applied. Changes:"
  echo "    - embedding_batch_size: 1 -> 32"
  echo "    - torch.cuda.empty_cache() between segmentation and embedding stages"
  echo "    - torch.cuda.empty_cache() between embedding and clustering stages"
  echo ""
  echo "  Restart the worker to pick up changes:"
  echo "    docker restart $CONTAINER"
}

revert_patch() {
  echo "=== Reverting to stock PyAnnote 4.0.4 ==="
  echo "  Source: $PATCHES_DIR/speaker_diarization.py.orig"
  echo "  Target: $CONTAINER:$SD_FILE"
  echo ""

  if [[ ! -f "$PATCHES_DIR/speaker_diarization.py.orig" ]]; then
    echo "ERROR: Original file not found at $PATCHES_DIR/speaker_diarization.py.orig"
    exit 1
  fi

  docker cp "$PATCHES_DIR/speaker_diarization.py.orig" \
    "$CONTAINER:$SD_FILE"

  echo "  Reverted. Restart the worker:"
  echo "    docker restart $CONTAINER"
}

show_status() {
  echo "=== Current patch status ==="
  echo ""

  # Check embedding_batch_size in container
  local emb_batch
  emb_batch=$(docker exec "$CONTAINER" grep "embedding_batch_size: int =" "$SD_FILE" | head -1 | xargs)
  echo "  Container embedding_batch_size: $emb_batch"

  local cache_count
  cache_count=$(docker exec "$CONTAINER" grep -c "empty_cache" "$SD_FILE" 2>/dev/null || echo "0")
  echo "  Container empty_cache() calls: $cache_count"

  echo ""
  echo "  Patch files:"
  echo "    Original: $PATCHES_DIR/speaker_diarization.py.orig"
  echo "    Patched:  $PATCHES_DIR/speaker_diarization.py.patched"
  echo "    Diff:     $PATCHES_DIR/embedding_batch_and_empty_cache.patch"
}

show_diff() {
  echo "=== Patch diff ==="
  echo ""
  if [[ -f "$PATCHES_DIR/embedding_batch_and_empty_cache.patch" ]]; then
    cat "$PATCHES_DIR/embedding_batch_and_empty_cache.patch"
  else
    echo "No patch file found. Generate with:"
    echo "  diff -u patches/pyannote/speaker_diarization.py.orig patches/pyannote/speaker_diarization.py.patched"
  fi
}

case "${1:-}" in
  apply)   apply_patch ;;
  revert)  revert_patch ;;
  status)  show_status ;;
  diff)    show_diff ;;
  *)
    echo "Usage: $0 {apply|revert|status|diff}"
    echo ""
    show_status
    ;;
esac
