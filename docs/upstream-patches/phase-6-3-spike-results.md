# Phase 6.3 TensorRT Spike — Results

**Date**: 2026-04-23
**Outcome**: TRT EP unlocked microbenchmark win on embedding (2×), but E2E pipeline **fails due to engine-plan rebuild on variable batch shapes**. Shape-specialization work is the next blocker.

## What was tested (minimal-change approach, per user push-back)

Kept the existing `python:3.13-slim-trixie` base image. Added three things:

- `tensorrt>=10.16.0` to `requirements.txt` (linux x86_64 only, conditional).
- `LD_LIBRARY_PATH` in `Dockerfile.prod` extended with `site-packages/nvidia/cublas/lib` and `site-packages/tensorrt_libs` so ORT's TRT EP can `dlopen` its dependencies.
- `nvidia-cublas-cu12` (via existing pyTorch pip deps) provided `libcublas.so.12`.

Image size: **9.7 GB → 14.2 GB** (+4.5 GB, mostly `tensorrt` + CUDA libs).

## Microbenchmark — fixed-shape forwards (spike's headline numbers)

Tested via `scripts/onnx_benchmark_providers.py` with fixed batch shapes (segmentation 32×1×80000, embedding 16×200×80):

| Path | Segmentation ms/batch | Embedding ms/batch |
|---|---:|---:|
| **PyTorch eager CUDA** (baseline) | **7.9** | 9.6 |
| ORT CUDA EP | 31.7 (4.0× slower) | 9.8 (parity) |
| **ORT TensorRT EP** | **19.2** (2.4× slower) | **4.9** (**1.96× FASTER**) |
| ORT CPU EP | 134.4 (17× slower) | 184.8 (19× slower) |

First-call TRT build time: **~12.5 seconds for segmentation, ~7-8 seconds for embedding** (engine plans cached to `TENSORRT_CACHE_DIR` for subsequent runs).

Headline: **TRT EP is ~2× faster than eager PyTorch on the embedding ResNet.** Segmentation is still slower than eager because of partial op coverage (the `ModelImporter.cpp:739: Make sure input onnx::Gather_115 has Int64 binding` warning indicates some ops drop back to CUDA EP inside the TRT subgraph assignment).

## E2E pipeline test — FAILED (not a TRT bug, a shape-profile gap)

Ran `PYANNOTE_USE_ONNX=1` + `ENABLE_TENSORRT=1` on 2.2h pipeline. Normal run: ~100 seconds. TRT run: **still running after 20 minutes** — killed.

### Root cause (confirmed via container log inspection)

The pyannote pipeline calls `infer()` with **variable batch shapes**:

- Segmentation: batch sizes typically 32 but the *last batch of the scan* is often 1-31 items (remainder of the chunk count).
- Embedding: fixed batch size of 16 (Phase A pinned), so this one is actually stable.

TRT EP by default builds a new engine plan per unique input shape. Each new shape = ~12 seconds rebuild. With 30+ distinct shapes seen during a 2.2h segmentation scan, that's 6+ minutes of rebuild stalls before the actual inference begins. The engine cache *does* persist to disk, but *first run* on new shapes is unusable.

### The fix that unblocks this (documented, not implemented in this spike)

ORT's TRT EP accepts `trt_profile_min_shapes`, `trt_profile_opt_shapes`, `trt_profile_max_shapes` provider options. Setting these up-front lets TRT build **one plan covering all shape ranges**, amortizing the build cost:

```python
providers = [
    ("TensorrtExecutionProvider", {
        "device_id": 0,
        "trt_engine_cache_enable": True,
        "trt_engine_cache_path": "/var/cache/tensorrt",
        "trt_fp16_enable": False,
        # KEY: shape-profile gives TRT a single plan for the range of batch sizes
        # the pipeline will actually see.
        "trt_profile_min_shapes": "input_values:1x1x80000",
        "trt_profile_opt_shapes": "input_values:32x1x80000",
        "trt_profile_max_shapes": "input_values:32x1x80000",
    }),
    ...
]
```

Alternative: pre-build ahead-of-time (`trtexec` CLI during Docker build) and ship the pre-built plan in the image for *one specific GPU arch* (violates our "don't bake plans into images" rule).

## What's already shipped (safe, reversible)

Code + infra changes that are in the image now:

- `tensorrt` dependency in `requirements.txt`
- `LD_LIBRARY_PATH` extended so TRT EP can dlopen its deps
- `ENABLE_TENSORRT=1` gate in `fork:pyannote/audio/onnx/runtime.py::_select_providers()` — already wires TRT EP at the front of the provider list

**These changes don't affect production** unless `ENABLE_TENSORRT=1` is set. Production deployments still get eager PyTorch by default.

## What's NOT shipped (still in the "research" bucket)

- Full TRT EP integration for production use. Needs the shape-profile work above.
- Hybrid "TRT for embedding, eager for segmentation" mode. Would require a new env var
  `PYANNOTE_ONNX_MODE=embedding_only_trt` and a code branch in `_setup_phase6_onnx`.

## Next steps (priority order)

1. **Shape-profile the TRT providers** for segmentation + embedding. Expected: embedding runs cleanly (shapes already fixed), segmentation needs explicit min/opt/max shapes.
2. **Hybrid TRT embedding + eager segmentation**. Easier to ship first — segmentation stays known-good, only embedding gets the 2× win. Projected ~5-10% E2E improvement (embedding is 75s of 100s on 2.2h).
3. **Measure VRAM under TRT EP** — the spike didn't measure this. Must confirm we stay ≤1.15 GB per pipeline (relaxed invariant from Phase 6.3 memo).
4. **Pre-built engine plans per GPU arch** — only after (1-3) work, build `opentranscribe-tensorrt-plans:sm{86,89,90}` OCI artifacts in CI.

## Image-size tradeoff

The +4.5 GB from `tensorrt` is a lot. Worth revisiting:

- **Split Dockerfile**: `Dockerfile.prod` (default, no TRT, 9.7 GB) + `Dockerfile.prod.tensorrt` (with TRT, 14.2 GB, opt-in for AWS server deployments).
- **Pip extras**: use pip's optional-extras mechanism (`pip install pyannote-audio-fork[tensorrt]`) — but that's for library packages, not much help for Docker layers.
- **Stage-separated install**: install `tensorrt` only in a separate `tensorrt` stage, build layer can COPY from it if `ENABLE_TENSORRT=1`. Complex.

My vote: **split Dockerfile after TRT is actually validated end-to-end**. For now the +4.5 GB is spike cost; consumer deployments shouldn't pay it once the decision is made.

## Commits

- **Backend**: pending commit of `backend/Dockerfile.prod` + `backend/requirements.txt` + this memo.
- **Fork**: already has the TRT EP wiring in `pyannote.audio.onnx.runtime._select_providers` (commit `55820cdc`).
