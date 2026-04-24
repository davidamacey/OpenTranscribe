# Phase 6.3 — Shape-Profile + Hybrid Mode Attempt

**Date**: 2026-04-23
**Outcome**: **Did not resolve the engine-rebuild storm.** TRT EP still compiles plans on CPU for >2 minutes even with min/opt/max shape-profile and segmentation ONNX disabled. GPU stays at 0% utilization while CPU sits at 17 cores × 100%. Killed.

## What was added

### `fork:pyannote/audio/onnx/runtime.py`

- New helper `_shapes_to_str()` to format shape maps as ORT's comma/x-joined strings.
- `_select_providers()` extended with optional `shape_profile={"min":{...}, "opt":{...}, "max":{...}}` argument; when present and `ENABLE_TENSORRT=1`, passes `trt_profile_min_shapes`, `trt_profile_opt_shapes`, `trt_profile_max_shapes` to the TRT EP.
- Two shape profile constants declared for the real call sites:
  - `_SEGMENTATION_SHAPE_PROFILE`: `input_values` from `(1, 1, 80000)` to `(32, 1, 160000)`.
  - `_EMBEDDING_SHAPE_PROFILE`: `fbank_features` from `(1, 50, 80)` to `(32, 500, 80)`; `weights` analogous.
- Both `ONNXSegmentationRuntime.__init__` and `ONNXEmbeddingRuntime.__init__` now pass their respective shape profile to `_select_providers()`.

### `fork:pyannote/audio/pipelines/speaker_diarization.py`

- New env vars `PYANNOTE_ONNX_SEG_ENABLED` and `PYANNOTE_ONNX_EMB_ENABLED` (both default to `"1"`). Allow hybrid modes: e.g. `PYANNOTE_ONNX_SEG_ENABLED=0` keeps segmentation on eager PyTorch while embedding goes through ONNX/TRT. This gives us a way to ship partial ONNX adoption without segmentation's op-coverage penalty.

## What was tested

Ran the 2.2h benchmark with:

```bash
PYANNOTE_USE_ONNX=1
ENABLE_TENSORRT=1
PYANNOTE_ONNX_SEG_ENABLED=0     # segmentation stays eager
TENSORRT_CACHE_DIR=/tmp/trt_cache
```

Observed during the run:

- Pipeline loaded in 4.0s (up from ~2s — ORT+TRT session init includes the initial TRT engine build trigger).
- Run 0 announced; then **CPU at 1707-1777%** (17 cores) for >2 minutes with no progress log.
- GPU utilization: **0%**, VRAM: 921 MB (stable).
- No "Done in..." line ever emitted.

Killed the container after 2 minutes. Baseline on this file is 100 seconds.

## Root cause (hypothesis, not fully proven)

ORT's TRT EP with a shape profile **should** build one engine plan covering all shapes within min/max. But one or more of:

1. **Partial last batches** in the pyannote embedding loop produce shapes outside `(B=16, num_frames=~200)`. If the last batch is, say, 7 chunks, and `num_frames` varies per chunk (depends on audio content after binarization), TRT may still see new shapes that fall inside the range but trigger per-shape optimization.
2. **ORT TRT EP's shape-profile contract is narrower than documented.** Some shapes within the range still trigger rebuilds; in practice we're seeing rebuild storms regardless of profile.
3. **Weights input shape varies** — the mask tensor `(B, num_frames_fbank)` is interpolated from the segmentation output; its `num_frames_fbank` dimension depends on audio content.
4. **Python-loop boundary**: each batch calls `session.run(...)` with fresh numpy arrays. Even if the *logical* shape is in range, the *physical* layout (strides, contiguity) may differ enough to invalidate engine caching.

Without deeper ORT TRT EP logging (which we haven't enabled), we can't distinguish these. The pragmatic finding: **the current integration does not work** with the observed pipeline shape pattern.

## Options that remain

Ordered by invasiveness:

### A. Pad all embedding calls to `(B=16, num_frames=fixed)` before hitting ONNX

Modify the embedding call site in `speaker_diarization.py:~750-780` to pad (and later un-pad with the weights mask) so TRT always sees identical shape. Cost: more code in the hot path, must preserve Phase A's adaptive-batch tuning. Benefit: TRT builds one plan, caches forever.

### B. Manual `trtexec`-built engine plan shipped with the image

Use NVIDIA's `trtexec` at image-build time to compile a plan for a specific (GPU arch, input shape) combination. Load the plan directly via the TensorRT Python API, bypassing ORT entirely. Not portable across GPU archs — one plan per SKU family. Fits our "server tier" narrative (Phase 6.3 memo), not consumer.

### C. Abandon TRT EP for embedding; use `torch.compile(mode="max-autotune")`

`torch.compile` in max-autotune mode does graph-level fusion similar to what TRT provides. Phase 6.1 already ships the gcc toolchain that unblocks it. Stays in PyTorch ecosystem; no ONNX/TRT dance. Needs measurement. Projected: similar magnitude to TRT's 2× on embedding microbench, but actual E2E unknown.

### D. Accept current state: TRT EP microbench unlocks are not production-shippable for pyannote-v4 yet

Document everything, land the existing code as opt-in scaffolding, move on to other phases.

## Recommendation

**Path C (torch.compile max-autotune)** is the cheapest next step. Zero image growth, no new runtime dependency, uses the gcc we already ship. 1-hour benchmark run compared against TRT EP microbench tells us whether the 2× win is PyTorch-native-achievable.

If C wins: ship torch.compile for embedding as a Phase 6.1.1 add-on, skip the TRT EP complexity.
If C doesn't win: revisit path A (padding) or accept path D.

## What was shipped despite the failure

The following changes are safe to leave in the codebase:

- Shape-profile plumbing in `_select_providers()` — zero cost when `ENABLE_TENSORRT` unset or no shape_profile passed.
- `_SEGMENTATION_SHAPE_PROFILE` / `_EMBEDDING_SHAPE_PROFILE` constants — make future TRT spike quicker.
- `PYANNOTE_ONNX_SEG_ENABLED` / `PYANNOTE_ONNX_EMB_ENABLED` env vars — useful for any future hybrid mode; default ON preserves prior behavior.

Correctness: these changes only activate when env vars are set. Default behavior (eager PyTorch) unchanged. Safe to commit.

## Adding to the "stop chasing as-is" list

**ORT TensorrtExecutionProvider for pyannote-v4 embedding path with shape-profile** joins:

> 12. **TRT EP with shape-profile on pyannote embedding call site** — compiles engine plans for >2 minutes on CPU (17-core × 100%) before any inference; GPU sits idle. Fixed-shape microbench wins 2× but real pipeline shape patterns trigger rebuild storms despite min/opt/max profile. Revisit only with padding-to-fixed-shape or via direct `trtexec`-compiled plan.

Also note the high CPU usage: **TRT plan compilation uses all available CPU cores at 100% for ~10-30s per plan**. For multi-pipeline deployments (25 concurrent pipelines per A6000 target), this would saturate the host while the GPU sits idle. Not production-friendly even if we solved the shape-profile issue.
