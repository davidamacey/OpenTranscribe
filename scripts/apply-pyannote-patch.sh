#!/usr/bin/env bash
# Apply/revert PyAnnote optimization patches inside the GPU worker container
#
# Supports multi-phase patching from the optimized fork:
#   - Phase 0 (legacy): embedding_batch_size + empty_cache only
#   - Phase 1-3 (full): All GPU optimizations from pyannote-audio-optimized fork
#
# Usage:
#   ./scripts/apply-pyannote-patch.sh status           # Show current patch state
#   ./scripts/apply-pyannote-patch.sh apply             # Apply full Phase 1-3 optimizations
#   ./scripts/apply-pyannote-patch.sh apply legacy      # Apply legacy (batch_size + empty_cache only)
#   ./scripts/apply-pyannote-patch.sh revert            # Restore stock PyAnnote files
#   ./scripts/apply-pyannote-patch.sh diff              # Show what the patch changes

set -euo pipefail

CONTAINER="${CONTAINER:-transcribe-app-celery-worker-gpu-scaled}"
SITE_PACKAGES="/home/appuser/.local/lib/python3.13/site-packages"
SD_FILE="$SITE_PACKAGES/pyannote/audio/pipelines/speaker_diarization.py"
SV_FILE="$SITE_PACKAGES/pyannote/audio/pipelines/speaker_verification.py"
INF_FILE="$SITE_PACKAGES/pyannote/audio/core/inference.py"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PATCHES_DIR="$REPO_ROOT/patches/pyannote"
FORK_DIR="$REPO_ROOT/reference_repos/pyannote-audio-optimized/src/pyannote/audio"
ORIG_DIR="$REPO_ROOT/reference_repos/pyannote-audio/src/pyannote/audio"

apply_full() {
  echo "=== Applying Phase 1-3 PyAnnote optimizations ==="
  echo ""

  local files_applied=0

  # speaker_diarization.py (Phase 2.1, 2.2, 2.3 + empty_cache)
  local fork_sd="$FORK_DIR/pipelines/speaker_diarization.py"
  if [[ -f "$fork_sd" ]]; then
    docker cp "$fork_sd" "$CONTAINER:$SD_FILE"
    echo "  [OK] speaker_diarization.py (vectorized chunks, masks, batch loop, empty_cache)"
    ((files_applied++))
  else
    echo "  [SKIP] speaker_diarization.py (fork file not found)"
  fi

  # speaker_verification.py (Phase 1.1: pinned memory)
  local fork_sv="$FORK_DIR/pipelines/speaker_verification.py"
  if [[ -f "$fork_sv" ]]; then
    docker cp "$fork_sv" "$CONTAINER:$SV_FILE"
    echo "  [OK] speaker_verification.py (pinned memory + non_blocking transfers)"
    ((files_applied++))
  else
    echo "  [SKIP] speaker_verification.py (fork file not found)"
  fi

  # inference.py (Phase 1.3: pinned memory for segmentation)
  local fork_inf="$FORK_DIR/core/inference.py"
  if [[ -f "$fork_inf" ]]; then
    docker cp "$fork_inf" "$CONTAINER:$INF_FILE"
    echo "  [OK] inference.py (pinned memory for segmentation)"
    ((files_applied++))
  else
    echo "  [SKIP] inference.py (fork file not found)"
  fi

  echo ""
  echo "  Applied $files_applied files. Restart the worker:"
  echo "    docker restart $CONTAINER"
}

apply_legacy() {
  echo "=== Applying legacy PyAnnote patch (batch_size + empty_cache only) ==="
  echo ""

  if [[ ! -f "$PATCHES_DIR/speaker_diarization.py.patched" ]]; then
    echo "ERROR: Patched file not found at $PATCHES_DIR/speaker_diarization.py.patched"
    exit 1
  fi

  docker cp "$PATCHES_DIR/speaker_diarization.py.patched" "$CONTAINER:$SD_FILE"

  echo "  Patch applied. Changes:"
  echo "    - embedding_batch_size: 1 -> 32"
  echo "    - torch.cuda.empty_cache() between stages"
  echo ""
  echo "  Restart the worker:"
  echo "    docker restart $CONTAINER"
}

revert_all() {
  echo "=== Reverting to stock PyAnnote ==="
  echo ""

  local files_reverted=0

  # Revert speaker_diarization.py
  local orig_sd="$ORIG_DIR/pipelines/speaker_diarization.py"
  if [[ -f "$orig_sd" ]]; then
    docker cp "$orig_sd" "$CONTAINER:$SD_FILE"
    echo "  [OK] speaker_diarization.py reverted"
    ((files_reverted++))
  elif [[ -f "$PATCHES_DIR/speaker_diarization.py.orig" ]]; then
    docker cp "$PATCHES_DIR/speaker_diarization.py.orig" "$CONTAINER:$SD_FILE"
    echo "  [OK] speaker_diarization.py reverted (from patches/)"
    ((files_reverted++))
  fi

  # Revert speaker_verification.py
  local orig_sv="$ORIG_DIR/pipelines/speaker_verification.py"
  if [[ -f "$orig_sv" ]]; then
    docker cp "$orig_sv" "$CONTAINER:$SV_FILE"
    echo "  [OK] speaker_verification.py reverted"
    ((files_reverted++))
  fi

  # Revert inference.py
  local orig_inf="$ORIG_DIR/core/inference.py"
  if [[ -f "$orig_inf" ]]; then
    docker cp "$orig_inf" "$CONTAINER:$INF_FILE"
    echo "  [OK] inference.py reverted"
    ((files_reverted++))
  fi

  echo ""
  echo "  Reverted $files_reverted files. Restart the worker:"
  echo "    docker restart $CONTAINER"
}

show_status() {
  echo "=== Current patch status ==="
  echo ""

  for label_file in "speaker_diarization:$SD_FILE" "speaker_verification:$SV_FILE" "inference:$INF_FILE"; do
    local label="${label_file%%:*}"
    local file="${label_file#*:}"

    local cache_count
    cache_count=$(docker exec "$CONTAINER" grep -c "empty_cache\|pin_memory\|unfold" "$file" 2>/dev/null || echo "0")
    echo "  $label: $cache_count optimization markers"
  done

  echo ""
  echo "  Fork dir: $FORK_DIR"
  echo "  Original: $ORIG_DIR"
}

show_diff() {
  echo "=== Optimization diff (fork vs stock) ==="
  echo ""
  for fname in "pipelines/speaker_diarization.py" "pipelines/speaker_verification.py" "core/inference.py"; do
    local orig="$ORIG_DIR/$fname"
    local fork="$FORK_DIR/$fname"
    if [[ -f "$orig" && -f "$fork" ]]; then
      local changes
      changes=$(diff "$orig" "$fork" | wc -l)
      echo "  $fname: $changes diff lines"
    fi
  done
  echo ""
  echo "  Full diff: diff -u reference_repos/pyannote-audio/src/ reference_repos/pyannote-audio-optimized/src/"
}

case "${1:-}" in
  apply)
    case "${2:-full}" in
      legacy) apply_legacy ;;
      *)      apply_full ;;
    esac
    ;;
  revert)  revert_all ;;
  status)  show_status ;;
  diff)    show_diff ;;
  *)
    echo "Usage: $0 {apply [full|legacy]|revert|status|diff}"
    echo ""
    show_status
    ;;
esac
