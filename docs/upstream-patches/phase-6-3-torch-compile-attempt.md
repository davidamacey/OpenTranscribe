# Phase 6.3 follow-up — `torch.compile` on Embedding ResNet

**Date**: 2026-04-23
**Outcome**: **REGRESSION — reverted.** Same variable-shape recompile storm that killed TRT EP also kills `torch.compile` when applied directly to the resnet submodule.

## Hypothesis (before the test)

- TRT EP microbench: embedding ResNet forward **4.9 ms** vs eager 10.46 ms = 2× (winning but not shippable due to shape rebuilds).
- `torch.compile` microbench on the same model: **default mode 7.79 ms (1.34×), max-autotune mode 7.02 ms (1.49×)**.
- Conclusion: slight win available via `torch.compile` with zero image bloat, no new runtime deps, fully within PyTorch.
- Plan: explicitly compile `self._embedding.model_.resnet` (which is what the hot path actually calls) in addition to the existing `model_` compile.

## Test

Ran 2.2h benchmark × 3 runs with `--torch-compile` enabled and the new `.resnet` compile addition:

| Run | Wall time |
|---|---:|
| 0 (includes compile) | ~250s |
| 1 (warm) | ~125s |
| 2 (warm) | **135.8s** |

Mean: **170.38s** (cv **35.1%** — unreliable due to compile cost on run 0).

### Per-stage breakdown (run 2, warm)

| Stage | Baseline (no compile) | With `.resnet` compile | Delta |
|---|---:|---:|---:|
| segmentation | ~5.1-5.2s | **8.57s** | **+65-68%** |
| embeddings | ~75.6-76.2s | **92.43s** | **+21-22%** |
| clustering_start | ~12.3s | 19.87s | +62% |
| reconstruction_start | ~2.3s | 4.38s | +90% |
| discrete_diarization | ~4.1s | 8.21s | +100% |
| **E2E** | ~100s | ~135s | **+35%** |

Every stage regressed — even the CPU-only clustering stage. This confirms it's not just compile overhead in a single call site; the whole pipeline is slower.

## Root cause (confirmed by observing CPU saturation)

Dynamo recompiles whenever it sees a **new input shape** (batch size, sequence length, etc.). The pipeline emits:

- Segmentation: batch sizes 32 + remainder (varies)
- Embedding: batch sizes 16 + remainder, with `num_frames` varying per chunk
- Multiple distinct shapes per scan

Each new shape → new guard check failure → fallback into `_torch_dynamo` recompile path. Recompile uses CPU (17 cores × 100% per the user's observation) while GPU sits idle. Even short recompiles (~1-5s each) × many shapes = cumulative stage regression across the whole pipeline.

**This is the same class of issue as the TRT EP rebuild storm in `phase-6-3-shape-profile-attempt.md`** — PyTorch's graph-compilation systems and NVIDIA's TRT both assume fixed shapes and punish variable-shape workloads.

### Why the other stages (clustering, reconstruct) also regressed

Suspect: torch.compile's guard check and potential recompile holds the Python GIL while the CPU-bound scipy + numpy stages try to run. The GIL contention between torch-compile workers and scipy stages serializes them.

## What was reverted

Reverted the explicit `self._embedding.model_.resnet = torch.compile(...)` line. Restored the prior Phase 2.1/6.1 behavior (compile `model_` and `segmentation.model` only). That prior state had measured noise-level impact (not a regression).

The `PYANNOTE_TORCH_COMPILE_MODE` env var was also removed — no point exposing a knob for a path that doesn't work.

## Lessons

1. **Microbench wins with fixed shapes do not generalize to variable-shape pipelines.** Both TRT EP and `torch.compile` hit the same wall. We saw 1.49× on the compile-time-fixed-shape ResNet; we saw **–30%** in the real pipeline on the same ResNet.
2. **Variable shape = compile-everything-on-first-call cost × N unique shapes.** For TRT: ~12s per shape × 30 shapes = 6+ min stall. For torch.compile: ~1-5s per shape × 30 shapes = 30-150s extra on first run, plus per-shape guard overhead forever after.
3. **Adding to the "stop chasing" list**:
   > 13. **`torch.compile(mode=default)` or `(max-autotune)` on pyannote embedding resnet** — regresses E2E 35% on 2.2h despite 1.49× microbench win. Variable batch shapes trigger recompile storms. Same class of issue as TRT EP rebuild storm. Only path forward is pad-to-fixed-shape at call site (invasive) or `dynamic=True` (would need testing).

## What's NOT blocked

The existing Phase 2.1/6.1 torch.compile wiring (default-off, `torch_compile=True` opt-in, compiles the parent `model_` only, not the hot `.resnet` path) **is still fine**. It was measured at noise-level impact prior — not a win, but also not a regression.

## What to try next

Given the last two TRT/compile attempts both died on variable shapes, the next productive move is **one of**:

- **A. Pad-to-fixed-shape at the embedding call site** (invasive, ~1-2 days of work). Embedding batch is already pinned at 16 by Phase A — the variable dim is `num_frames`. Padding num_frames to a fixed max (e.g., 500) would let TRT/compile see a single shape. Cost: ~3x wasted compute on short chunks.
- **B. `torch.compile(..., dynamic=True)`** — tells Dynamo to treat shapes as dynamic. Recompile-less but fewer optimization opportunities. Should spike this cheaply.
- **C. Accept Phase A + Phase 3 as the plateau** for pipeline-level optimizations on variable-shape pyannote-v4. Redirect effort to **Phase 5.4** (concurrent request ceiling — deployment-level 2-4× throughput win). Different dimension, same end-user benefit.

**My vote**: B (spike dynamic=True) first as cheap insurance; if it doesn't win, C (pivot to Phase 5.4). Ship what we have.
