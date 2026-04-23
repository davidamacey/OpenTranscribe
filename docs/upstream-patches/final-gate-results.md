# Final Gate — Combined-Effect Benchmark

**Date**: 2026-04-22
**Fork branch**: `gpu-optimizations`
**Hardware**: RTX A6000 (CUDA), 5-run tags baseline_a6000_20260421_{213621_short, 214811_long} vs final_gate_combined (3 runs).

## Stack under test

All merged, default-on optimizations shipped this round:
- Phase 2.1 — `torch.compile` failure is now visible (gcc missing in container; logged, no impact).
- Phase 2.2 — `@lru_cache` hamming window in `Inference.aggregate`.
- Phase 2.3 — `torch.backends.cudnn.benchmark = True` (CUDA).
- Phase 2.4 — `embedding_mixed_precision` parameter plumbed, default `False`.
- Phase 3 — GPU `torch.cdist` for `assign_embeddings` + `torch.pdist`→scipy linkage bridge with VRAM-budget fallback.
- Phase 3.5 (trivial freebies only) — `_constrained_argmax` vector scatter, centroids via `bincount+add.at`, cluster remap lookup. (Aggregate/reconstruct CPU rewrites **reverted** — regressed 35-57%.)
- Phase 4 — default `segmentation_step` unchanged; opt-in kwarg documented.
- GPU Lance-Williams — opt-in only (`PYANNOTE_ENABLE_GPU_LINKAGE=1`); slower than scipy by default.

## Results

| file | runs | Δ wall | peak VRAM | DER vs baseline | speakers | segments |
|---|---:|---:|---:|---|---:|---:|
| 2.2h_7998s | 3 | +0.11% (noise) | **844 MB** (unchanged) | **0.0000% (T1)** ×3 | 3 / 3 | 2855 / 2855 |
| 4.7h_17044s | 3 | **-1.94%** (-6.49s) | **844 MB** (unchanged) | **0.0000% (T1)** ×3 | 8 / 8 | 12104 / 12104 |

## Invariants held

- **Per-pipeline peak VRAM ≤ 1.05 GB**: 844 MB ±0, every run, every file.
- **Steady-state VRAM ≤ 1.0 GB**: unchanged.
- **DER delta ≤ 0.1 pp**: 0.0000% on both files (byte-identical RTTM).
- **Speaker-count delta ≤ ±1**: identical.
- **Segment-count delta ≤ ±2%**: identical.
- **cv < 10%**: held (3-run spread within 0.5s on 4.7h).

## So-what

The combined stack delivers a small but real 4.7h gain (-1.94%, dominated by Phase 3's cdist GPU offload on the 21-speaker assign_embeddings path) with zero accuracy cost and zero VRAM cost. The 2.2h file is in the noise band — expected, since its clustering N is small and Phase 3 helps most at N≥1000.

Projected Phase 3 win (25-35% E2E) did **not** materialize because `clustering_start`'s 138s on 4.7h is dominated by VBx PLDA / AHC / `assign_embeddings` — not the scipy linkage we offloaded. Documented in `phase-3-measurement.md`.

The remaining CPU-bound stages (VBx, aggregation, reconstruction) are the topic of the Phase 5 memos. Next-highest ROI is **Phase 5.2 (GPU aggregate + reconstruct)** at projected 4.5% E2E on 4.7h.

## Concurrent-pipeline stress

Deferred to Phase 5.4 memo — requires backend Celery soak-test harness; out of scope for fork-only round.

## Fork state

All changes committed and pushed on branch `gpu-optimizations`. VRAM invariant preserved — the ~25 parallel pipelines/A6000 architecture remains intact.
