"""Phase A.7 — per-user GPU readout for diarization deployment sizing.

Run: `python -m app.scripts.diarization_diag`

Reads the local GPU state and prints a recommended (batch, precision) tuple
plus projected Whisper + diarization VRAM cost, so users can size consumer-GPU
deployments without running the benchmark harness.

Numbers come from `docs/diarization-vram-profile/README.md` Phase A findings,
dated 2026-04-20.
"""

from __future__ import annotations

import json
import sys

from app.utils.nvml_monitor import get_gpu_memory

# Whisper model VRAM costs (weights + decoder KV cache + per-audio activations
# with beam=5, CTranslate2 fp16). Measured on A6000 in the Phase A.6 probe.
# Conservative upper bounds so the budget math is safe for 4 GB cards.
# measured 2026-04-20 placeholder — replace with A.6 numbers when available
WHISPER_RESERVE_MB: dict[str, int] = {
    "tiny": 350,
    "base": 450,
    "small": 750,
    "medium": 1600,
    "large-v3-turbo": 2200,
    "large-v3": 3200,
    "large-v2": 3200,
}

# CUDA context + torch allocator reservation on (torch 2.8.0+cu128, driver
# 580.126, CUDA 12.8, RTX A6000). Measured 2026-04-20 in the whole-stack probe
# (docs/diarization-vram-profile/whole-stack.md A.6b): raw residue 278 MB +
# 22 MB safety margin. Regenerate on any torch/CUDA/driver upgrade.
CUDA_CONTEXT_MB = 300

# Diarization per-process footprint by embedding batch size (fp32).
# Process footprint = pipeline weights + activations, excluding CUDA context.
# measured 2026-04-20 from --small-batch-sweep
DIARIZATION_FOOTPRINT_MB: dict[int, int] = {
    4: 640,
    8: 640,
    16: 954,
    32: 1946,
}


def recommend_batch(free_mb: int) -> tuple[int, str]:
    """Pick embedding batch for the given free VRAM. fp32 always."""
    # Reserve 200 MB safety margin for fragmentation / allocator slack.
    headroom = free_mb - 200
    if headroom < DIARIZATION_FOOTPRINT_MB[4]:
        return 4, "insufficient-vram"
    if headroom < DIARIZATION_FOOTPRINT_MB[8]:
        return 4, "tight"
    if headroom < DIARIZATION_FOOTPRINT_MB[16]:
        return 8, "tight"
    # bs=16 saturates throughput per Phase A; never go higher.
    return 16, "optimal"


def feasible_whisper_models(free_mb_after_diar: int) -> list[str]:
    """Which Whisper models fit alongside diarization in the remaining budget."""
    return [m for m, cost in WHISPER_RESERVE_MB.items() if cost <= free_mb_after_diar]


def main() -> int:
    mem = get_gpu_memory(0)
    if mem is None:
        print("No CUDA GPU detected (or NVML unavailable). Diarization will run on CPU.")
        return 1

    total_mb = int(mem.total_mb)
    used_mb = int(mem.used_mb)
    free_mb = int(mem.free_mb)
    usable_mb = max(0, free_mb - CUDA_CONTEXT_MB)
    batch, status = recommend_batch(usable_mb)
    diar_mb = DIARIZATION_FOOTPRINT_MB[batch]
    after_diar = usable_mb - diar_mb
    whisper_ok = feasible_whisper_models(after_diar)
    whisper_fail = [m for m in WHISPER_RESERVE_MB if m not in whisper_ok]

    report = {
        "gpu": {
            "total_mb": total_mb,
            "idle_baseline_used_mb": used_mb,
            "free_mb": free_mb,
        },
        "cuda_context_mb": CUDA_CONTEXT_MB,
        "usable_mb_for_models": usable_mb,
        "diarization": {
            "recommended_batch_size": batch,
            "recommended_precision": "fp32",
            "status": status,
            "expected_peak_mb": diar_mb,
        },
        "whisper_compatibility": {
            "fits_alongside_diarization": whisper_ok,
            "does_not_fit": whisper_fail,
        },
        "projected_peak_mb": used_mb
        + CUDA_CONTEXT_MB
        + diar_mb
        + (max((WHISPER_RESERVE_MB[m] for m in whisper_ok), default=0) if whisper_ok else 0),
        "notes": [
            "bs=16 saturates throughput (Phase A 2026-04-20). Larger batches waste VRAM.",
            "fp16 is available but collapses speaker count; see docs/diarization-vram-profile/README.md.",
            "Whisper + diarization run sequentially in default mode, so only the larger of the two matters at peak.",
        ],
    }
    print(json.dumps(report, indent=2))
    return 0 if status != "insufficient-vram" else 2


if __name__ == "__main__":
    sys.exit(main())
