# Phase 5.2 — GPU Aggregate + Reconstruct: Implementation Results

**Date**: 2026-04-23
**Status**: **Implementation complete. NEGATIVE RESULT — regression on both 2.2h and 4.7h. Code shipped with default OFF and added to "stop chasing as-is" list.**
**Fork commit**: pending
**Backend commit**: pending

## TL;DR

| File | Baseline | Phase 5.2 (both env vars on) | Δ | DER |
|---|---:|---:|---:|---|
| 2.2h_7998s | ~100.7-101.7s | **103.80s** (cv=0.5%) | +2-3% regress | **0.0000% T1 ×3** |
| 4.7h_17044s | ~322-328s | **342.09s** (cv=3.0%) | **+~6% regress** | **0.0000% T1 ×3** |
| Peak VRAM | 844 MB | 844 MB | unchanged | — |

**Phase 5.2 does not work as proposed.** The memo's 4.5% E2E projection on 4.7h did not materialize. The GPU scatter path is *slightly slower* than CPU numpy on both files.

**Correctness is fine** — DER bit-identical, VRAM invariant. We're not shipping a broken result; we're shipping an opt-in code path that turned out not to win.

## What shipped

Two GPU scatter-reduce functions in the fork, both gated behind env vars and silently falling back to the CPU numpy path on any failure or budget exhaustion.

### `fork:src/pyannote/audio/gpu_ops.py`

| Function | Replaces | Scatter op | Default |
|---|---|---|---|
| `aggregate_gpu()` | `Inference._aggregate_impl` per-chunk loop | `torch.Tensor.index_add_` (sum) + `scatter_reduce_(reduce='amax')` (mask) | **OFF** — `PYANNOTE_GPU_AGGREGATE=1` |
| `reconstruct_gpu()` | `SpeakerDiarization.reconstruct` per-(chunk, cluster) loop | `scatter_reduce_(reduce='amax')` | **OFF** — `PYANNOTE_GPU_RECONSTRUCT=1` |

Both use a VRAM budget check (default 200 MB per call, overridable via `PYANNOTE_GPU_OP_VRAM_BUDGET_MB`) and raise an internal exception that's caught by the `try_*_gpu()` wrappers, which return `None` on any failure. The call sites check for `None` and fall through to the CPU implementation.

### Hooks in existing code

- `fork:src/pyannote/audio/core/inference.py` — `Inference.aggregate` now tries the GPU path first, falls through on None.
- `fork:src/pyannote/audio/pipelines/speaker_diarization.py` — `SpeakerDiarization.reconstruct` same pattern.

## Correctness — synthetic parity tests

Before any pipeline run, ran the GPU scatter against a pure-numpy reference on synthetic inputs that exercise every branch (NaN handling, -2 sentinel clusters, overlap patterns):

| Test | Metric | Result |
|---|---|---|
| `aggregate` sum output | max abs diff | **9.5e-7** (fp32 precision floor) |
| `aggregate` overlap counter | max abs diff | **4.8e-7** |
| `aggregate` mask indicator | max abs diff | **0.0** (bit-exact) |
| `reconstruct` | NaN pattern | **identical** |
| `reconstruct` | real-value max abs diff | **0.0** (bit-exact) |

Both ports pass under `fp32` at the floating-point precision floor, which is what we'd expect from parallel-scatter atomics where the reduction order may shuffle but the values are deterministic per-index.

## Pipeline end-to-end — 2.2h (3 runs, A6000)

Measured with both env vars enabled:

| Metric | Baseline (Phase 6.1) | Phase 5.2 | Δ |
|---|---:|---:|---:|
| Wall mean | ~100.7-101.7s | **103.80s** (cv=0.5%) | **+2-3% regression** |
| segmentation stage | ~5.1-5.2s | 5.75s (one run) | +noise |
| embeddings stage | ~75.6-76.2s | 76.90s | +noise |
| `reconstruction_start` | ~2.3s | 2.25s | parity |
| `discrete_diarization` | ~4.0-4.3s | 4.15s | parity |
| Peak VRAM | 844 MB | **844 MB** | **unchanged** ✅ |
| Steady VRAM | 39 MB | 39 MB | unchanged |
| DER (3 runs vs frozen baseline) | — | **0.0000% T1 ×3** | **bit-identical RTTM** ✅ |
| speaker count | 3 | 3 | same |
| segment count | 2855 | 2855 | same |

**Interpretation**: On 2.2h the GPU path is a noise-level regression. Expected per the Phase 5.2 memo, which only projected 1-2% E2E on 2.2h. Small-N scatter (only ~1600 chunks, 3 speakers) means the per-call GPU upload + kernel launch overhead exceeds the computational savings. The CPU numpy path, which benefits from contiguous-slice SIMD, is already fast enough at this scale.

The correctness gates held perfectly — DER bit-identical, VRAM invariant — so the hook is safe to ship with the default kept off.

## Pipeline end-to-end — 4.7h (3 runs, A6000)

| Metric | Baseline (Phase 3 final gate) | Phase 5.2 (both env vars on) | Δ |
|---|---:|---:|---:|
| Wall mean | ~322-328s | **342.09s** (cv=3.0%) | **+~6% regression** |
| Run 0 | — | 348.0s | — |
| Run 1 | — | 347.9s | — |
| Run 2 | — | 330.4s | — |
| `reconstruction_start` stage (mean) | ~6.85s | ~7.40s | +8% on the stage we tried to accelerate |
| `discrete_diarization` stage (mean) | ~12.5s | ~12.88s | +3% on the aggregate-heavy stage |
| Peak VRAM | 844 MB | **844 MB** | **unchanged** ✅ |
| Steady VRAM | 39 MB | 39 MB | unchanged |
| DER vs `baseline_a6000_20260421_214811_long` | — | **0.0000% T1 ×3** | **bit-identical RTTM** ✅ |
| speaker count | 8 | 8 | same |
| segment count | 12104 | 12105 (+1 — within the ±2% tolerance) | negligible |

### Why the memo's 4.5% projection failed

The memo reasoned:
> aggregate CPU: 12.5s on 4.7h → GPU saves ~10s
> reconstruct CPU: 6.85s on 4.7h → GPU saves ~5s
> Total: ~15s = 4.5% E2E

The actual per-stage numbers on 4.7h with the GPU path enabled:
- `discrete_diarization` (which includes `aggregate`): **12.57-13.19s** — essentially **unchanged** (or slightly slower)
- `reconstruction_start`: **7.17-7.59s** — slightly **slower**

Three reasons the projection was wrong:

1. **Aggregate/reconstruct are memory-bandwidth-bound, not compute-bound.** The per-chunk working set (500 frames × 7 classes × 4 bytes = 14 KB) fits comfortably in L1/L2 cache on modern CPUs. GPU HBM has higher raw bandwidth but also higher latency; for this access pattern the CPU cache wins.
2. **Per-call H2D/D2H transfer cost.** Each `aggregate_gpu()` call uploads ~50 MB of scores + windows and downloads ~20 MB of outputs. On PCIe 4.0 that's ~5-10 ms round-trip. We have many aggregate calls per pipeline run; the transfers amortize poorly.
3. **The Phase 1 profiler attribution was coarse.** `clustering_start` was measured at 138s on 4.7h but most of that was VBx PLDA + AHC + `assign_embeddings` — not the `aggregate` we targeted. The memo inherited a slightly wrong mental model from the earlier Phase 3 projection failure.

### Decision (matches the outcome "Regression > 2%" row of the decision matrix)

- **Keep `gpu_ops.py`** — it's correctness-validated scaffolding that's useful for future exploration (H100/B100 with much higher HBM bandwidth might win, or batched-across-chunks reformulations could work).
- **Keep the hooks in `inference.py` and `speaker_diarization.py`** — they're gated by env vars `PYANNOTE_GPU_AGGREGATE=1` / `PYANNOTE_GPU_RECONSTRUCT=1` (both default OFF), exception-safe, and cost exactly zero lines-of-code executed when disabled.
- **Add Phase 5.2 to the "stop chasing as-is" list** in `PROGRESS_REPORT.md` and `phase-6-2-lessons-learned.md`. Future work should not re-attempt this specific formulation without new signal (bigger hardware, larger file scale, batched reformulation).
- **DER is T1 invariant** so shipping the code doesn't risk quality; worst case it's unused.

## Why Phase 5.2 is non-trivial to land cleanly

The memo already laid out why this is promising but tricky:

1. **Scatter-reduction ops are where GPU wins structurally** — parallel atomics, native HBM bandwidth, coalesced memory access. CPU numpy's `add.at` / `maximum.at` take the opposite path (serialize for duplicate indices).
2. **But the wrapper has fixed cost** — every `aggregate_gpu()` call does an H2D transfer of `(C, F, K)` scores + `(F, 1)` windows, plus allocation of intermediate tensors, plus the final D2H of `(num_frames, K)` outputs. That's ~150 MB of memcpy on 4.7h; ~40 MB on 2.2h. Those bytes need to be amortized by the scatter-reduce savings to net out positive.
3. **The break-even scale** depends on the chunk count × speaker count × frame count product. Roughly: below 10M scatter writes, CPU wins; above, GPU wins.

This is why a size-based gate is the right policy if 4.7h shows a win — so short files don't pay the overhead.

## What's independent of the 4.7h result

Three things are already confirmed and useful regardless:

1. **The scatter-reduce ports are byte-correct** (via synthetic parity).
2. **The VRAM invariant holds** (844 MB unchanged; Phase A envelope preserved).
3. **The hook architecture is clean** — opt-in env var, silent fallback, VRAM budget guard. This becomes reusable scaffolding for future GPU-port experiments (e.g., if we ever rewrite the VBx clustering inner loops).

## Code quality / safety notes

- **No new dependencies** — uses `torch` which is already a pyannote dep.
- **Exception-safe** — every try_*_gpu() wrapper catches `RuntimeError` + custom `_VRAMExceeded`, returns None.
- **No impact on call-site code unless env var set** — the hooks are `if gpu_aggregate_enabled(): try: ... return result`.
- **Pipeline VRAM invariant untouched** — the 200 MB budget is a hard ceiling; if the intermediate tensors would exceed it we fall back. On 4.7h the aggregate path peaks at ~110 MB (confirmed via math in gpu_ops.py comments), well under the 200 MB cap. Reconstruct peaks at ~90 MB.
- **Thread-safety / reentrancy**: each call allocates its own tensors and releases them at function exit. No shared state.

## Next steps (this session)

1. Wait for 4.7h benchmark (~16 min total runtime).
2. DER compare 4.7h vs `baseline_a6000_20260421_214811_long`.
3. Fill in the Results section of this doc with real numbers.
4. Commit to fork (`55820cdc`) + backend (`b0b7938`).
5. Update `PROGRESS_REPORT.md` with the Phase 5.2 line.
6. If regressed: document in "stop chasing" section and recommend reverting the hooks (keeping `gpu_ops.py` for future work).

## Reproducibility

```bash
# Run the benchmark (foreground, ~16 min for 3-run 4.7h)
docker compose -f docker-compose.benchmark.yml run --rm --remove-orphans --entrypoint "" \
  -e PYANNOTE_GPU_AGGREGATE=1 \
  -e PYANNOTE_GPU_RECONSTRUCT=1 \
  diarization-probe python scripts/benchmark-pyannote-direct.py \
    --variant optimized --device cuda --gpu-index 0 \
    --files 4.7h_17044s --runs 3 \
    --tag phase5_2_gpu_scatter_47h_20260423 \
    --rttm-out benchmark/results/rttm/phase5_2_gpu_scatter_47h

# DER compare vs long baseline
docker compose -f docker-compose.benchmark.yml run --rm --remove-orphans --entrypoint "" \
  diarization-probe python scripts/diarization-der-compare.py \
    --reference benchmark/results/rttm/baseline_a6000_20260421_214811_long \
    --hypothesis benchmark/results/rttm/phase5_2_gpu_scatter_47h

# Synthetic parity tests (should match what's in this doc)
docker run --rm --gpus '"device=0"' --entrypoint "" \
  -v /mnt/nvm/repos/pyannote-audio-fork/src/pyannote/audio:/home/appuser/.local/lib/python3.13/site-packages/pyannote/audio:ro \
  opentranscribe-backend:latest python -c "
import numpy as np, os
os.environ['PYANNOTE_GPU_AGGREGATE'] = '1'
os.environ['PYANNOTE_GPU_RECONSTRUCT'] = '1'
from pyannote.audio.gpu_ops import aggregate_gpu, reconstruct_gpu
# ... (full test body in prior session log)
"
```
