"""Per-GPU diarization sizing diagnostic.

Run: `python -m app.scripts.diarization_diag`

The diarization pipeline runs at a fixed ``embedding_batch_size = 16`` with a
measured ~1 GB peak VRAM footprint (fp32). This CLI reads the local GPU,
reports free VRAM, and prints how many concurrent diarization pipelines can
fit alongside a chosen Whisper model.

Numbers come from `docs/diarization-vram-profile/` (Phase A, 2026-04-20).
"""

from __future__ import annotations

import json
import sys

from app.utils.nvml_monitor import get_gpu_memory

# Measured on RTX A6000 at fp32 / bs=16 (Phase A.2 small-batch sweep).
# Upper-bound ceiling of process-footprint-over-baseline; keep conservative
# so sizing math stays safe on new driver/torch combinations.
DIARIZATION_FOOTPRINT_MB = 1100

# CUDA context + torch allocator residue per process. Measured in the Phase
# A.6 whole-stack probe (2026-04-20, torch 2.8.0+cu128, driver 580.126).
# Regenerate on any torch/CUDA/driver upgrade.
CUDA_CONTEXT_MB = 300

# Whisper peak VRAM during transcription (weights + decoder KV cache +
# activations). Conservative upper bounds from the Phase A.6 whole-stack
# probe on the 0.5 h reference clip; larger audio will not materially
# change the peak because Whisper processes in chunks.
WHISPER_PEAK_MB: dict[str, int] = {
    "tiny": 500,
    "base": 800,
    "small": 1800,
    "medium": 3400,
    "large-v3-turbo": 4400,
    "large-v3": 6500,
    "large-v2": 6500,
}


def feasible_whisper_models(free_mb_for_whisper: int) -> list[str]:
    return [m for m, cost in WHISPER_PEAK_MB.items() if cost <= free_mb_for_whisper]


def parallel_pipeline_count(free_mb: int, whisper_peak_mb: int) -> int:
    """How many diarization pipelines fit alongside one resident Whisper.

    Sequential mode (default) only needs Whisper *or* diarization resident,
    so the bottleneck is the larger of the two. In concurrent mode every
    extra pipeline adds one diarization footprint.
    """
    bottleneck = max(whisper_peak_mb, DIARIZATION_FOOTPRINT_MB)
    if free_mb < bottleneck:
        return 0
    remaining = free_mb - bottleneck
    return 1 + max(0, remaining // DIARIZATION_FOOTPRINT_MB)


def main() -> int:
    mem = get_gpu_memory(0)
    if mem is None:
        print("No CUDA GPU detected (or NVML unavailable). Diarization will run on CPU.")
        return 1

    total_mb = int(mem.total_mb)
    used_mb = int(mem.used_mb)
    free_mb = int(mem.free_mb)
    usable_mb = max(0, free_mb - CUDA_CONTEXT_MB)

    whisper_ok = feasible_whisper_models(max(0, usable_mb - DIARIZATION_FOOTPRINT_MB))
    whisper_fail = [m for m in WHISPER_PEAK_MB if m not in whisper_ok]

    parallel = {
        model: parallel_pipeline_count(usable_mb, peak) for model, peak in WHISPER_PEAK_MB.items()
    }

    report = {
        "gpu": {
            "total_mb": total_mb,
            "idle_baseline_used_mb": used_mb,
            "free_mb": free_mb,
        },
        "cuda_context_mb": CUDA_CONTEXT_MB,
        "usable_mb_for_models": usable_mb,
        "diarization": {
            "embedding_batch_size": 16,
            "precision": "fp32",
            "expected_peak_mb": DIARIZATION_FOOTPRINT_MB,
        },
        "whisper_compatibility": {
            "fits_alongside_diarization": whisper_ok,
            "does_not_fit": whisper_fail,
        },
        "parallel_diarization_pipelines": parallel,
        "notes": [
            "Embedding batch is pinned at 16 (Phase A 2026-04-20). Identical "
            "throughput to bs=128, ~1 GB peak VRAM.",
            "fp16 autocast is not used: DER collapses speaker count to T3 on "
            "the benchmark corpus. See docs/diarization-vram-profile/.",
            "Sequential mode (default) peaks at max(whisper, diarization); "
            "concurrent mode adds ~1 GB per extra diarization worker.",
        ],
    }
    print(json.dumps(report, indent=2))
    return 0 if whisper_ok else 2


if __name__ == "__main__":
    sys.exit(main())
