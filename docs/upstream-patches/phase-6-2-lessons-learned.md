# Phase 6.2 ONNX — Lessons Learned + Deployment Matrix

**Session date**: 2026-04-23
**Outcome**: Plumbing shipped (unit tests pass). GPU inference path is **not a win** via ONNX Runtime alone on pyannote v4 graphs. The analysis below explains why, what to pursue, and what to stop chasing.

## Executive summary

| Path | Status | Verdict |
|---|---|---|
| Export pipeline (`pyannote.audio.onnx.export`) | ✅ works | Ship. Segmentation 5.9 MB, embedding 26.5 MB. |
| Unit tests T1 (numeric parity) | ✅ 14 pass | Ship. Frame-class bit-exact on segmentation; cos ≥ 0.9999 on embedding. |
| Unit tests T2 (fbank parity) | ✅ 13 pass | Ship. Batched fbank matches vmap at ≤1e-5. |
| Layer 3 pipeline integration | ✅ works | Plumbing correct — ORT sessions load, forwards produce output. |
| **ORT CUDA EP** performance | ❌ **5-7× REGRESSION** | **Do not ship as-is.** |
| **ORT TensorRT EP** in current image | ❌ blocked by missing CUDA toolkit libs | Needs Phase 6.3 image rework. |
| ORT CPU EP performance | ⚠️ untested at pipeline level | Likely a win — ORT typically 2-3× vs eager PyTorch on CPU. |
| ORT CoreML EP on MPS | ⚠️ untested — needs Mac Studio run | Unknown — no blockers identified, worth testing. |

## What actually happens: the CUDA EP slowdown explained

### Root cause (the user's diagnostic question answered)

The pyannote segmentation-3.0 ONNX graph has 30+ op types, of which several have **no CUDA kernel in ONNX Runtime 1.25**:

| Op in main graph | Count | CUDA kernel in ORT? | Effect |
|---|---:|---|---|
| `LSTM` | 4 | Partial — falls back on certain attributes | ORT inserts `Memcpy` node before/after |
| `If` (control flow) | 1 | Yes, but subgraph ops must all be CUDA too | Contains Conv/Slice/Concat, subgraph gets placed on CPU, parent op downgrades |
| `Sin`, `Cos` | 2 each | Not in `CUDAExecutionProvider` as of 1.25 | Falls to CPU — these come from SincNet's parameterized sinc filters |
| `InstanceNormalization` | 4 | Yes but with train-mode leak warning | Slight drift, not a perf issue per se |

ORT's graph partitioner sees any op without a CUDA kernel, keeps it on CPU, and inserts `Memcpy` nodes to shuttle tensors between GPU and CPU. The pyannote segmentation graph ends up with **3 of these Memcpy insertions per forward**, documented in the warning:

```
Memcpy nodes are added to the graph sub_graph1 for CUDAExecutionProvider.
It might have negative impact on performance (including unable to run CUDA graph).
```

The runtime cost is that a single forward becomes:
1. Host → GPU transfer of input
2. GPU compute for some ops
3. GPU → Host transfer for LSTM
4. CPU compute for LSTM
5. Host → GPU transfer for downstream ops
6. GPU compute
7. ...repeat for each fallback op...
8. Final GPU → Host transfer

### Measured impact (onnx_benchmark_providers.py)

All on RTX A6000, segmentation graph, batch=32 × 5s chunks:

| Config | ms/batch | vs PyTorch eager |
|---|---:|---|
| PyTorch eager CUDA | **8.2** | baseline |
| ORT CUDA EP (plain `run`) | 47.5 | **5.8× slower** |
| ORT CUDA EP + `io_binding` | 32.4 | 4.0× slower |
| ORT CPU EP | (slower still; effective for CPU-only nodes) | n/a |
| ORT TensorRT EP | blocked — missing `libcublas.so.12` in image | n/a |

`io_binding` helps at the Python → ORT boundary (no `.cpu().numpy()` round trip at call site) but doesn't fix the *intra-graph* Memcpy nodes. Even with `io_binding`, ORT CUDA EP still inserts the internal Memcpy nodes and shuttles LSTM to CPU.

### End-to-end pipeline impact

Running the 2.2h benchmark with `PYANNOTE_USE_ONNX=1` and `ORT+CUDA EP` active, the pipeline ran for **28+ minutes before we killed it** (PyTorch eager baseline: 100s). That's consistent with the per-batch slowdown compounded across ~1600 segmentation chunks plus ~625 embedding calls.

## TensorRT EP as the GPU fix — and why it's Phase 6.3, not Phase 6.2

TensorRT **does** have kernels for LSTM, If (loops), Sin, Cos, InstanceNorm — all the ops that fall back in CUDA EP. So a TRT EP run would keep the entire graph on GPU.

But we couldn't test TRT EP in the Phase 6.2 image because:

1. `onnxruntime-gpu`'s bundled `libonnxruntime_providers_tensorrt.so` dynamically links against NVIDIA's `libnvinfer.so.10`. `pip install tensorrt` brings that library (verified 10.16.1.11 installs).
2. But `libonnxruntime_providers_cuda.so` *also* links against `libcublas.so.12` + `libcublasLt.so.12` — NVIDIA's **cuBLAS runtime libraries, part of the CUDA toolkit**.
3. Our `python:3.13-slim-trixie` base image has **none of the CUDA toolkit libs** — PyTorch brings its own bundled cuBLAS in `torch/lib/`, but ORT can't find them there.

Options to unblock TRT EP:

- **a. Switch base image to `nvidia/cuda:12.8.0-cudnn-runtime-ubuntu24.04`** — adds ~2 GB to image, provides full CUDA runtime including cuBLAS, cuBLASLt.
- **b. Use `nvcr.io/nvidia/pytorch:25.01-py3`** (what `Dockerfile.blackwell` uses) — already has everything, ~6 GB image.
- **c. Install CUDA runtime libs via pip** — `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 tensorrt`, then set `LD_LIBRARY_PATH` correctly. Lighter (~500 MB) but brittle.

All three are Phase 6.3 territory. Phase 6.2 as originally scoped ("ONNX via CUDA EP for consumers") is **not reachable** because ORT CUDA EP alone is slower than eager PyTorch for this graph.

## Answer to the deployment question

User question: *"if we do TensorRT can we deploy onto user machines without compiling for the GPU type?"*

**No — TensorRT engine plans are strictly per-GPU-architecture.** An engine plan built on A6000 (`sm_86`) won't run on RTX 4070 (`sm_89`) or H100 (`sm_90`). This is why Phase 6.3 specifies a **"build on first startup"** flow with per-arch caching.

**Setup-time implications for users:**

| Deployment target | TRT setup cost | Fix |
|---|---|---|
| User's Linux laptop (e.g., RTX 3080 Ti) | 6-13 min first run, cached thereafter | UI banner during build |
| Fresh Docker pull to a new VM | 6-13 min on first task | Pre-build plans in CI per-arch artifact |
| Mac (Apple Silicon) | **Not applicable** — no TensorRT on MPS | Use CoreML EP instead |
| Windows laptop | 6-13 min first run | Same as Linux |
| Older GPUs (< Turing / sm_75) | **TRT 10.x does not support** | Fall back to CUDA EP (slow) or eager PyTorch |

User question: *"TensorRT won't work on Mac MPS."*

**Correct.** TensorRT is NVIDIA-only. Apple Silicon path:
- Use ORT with **`CoreMLExecutionProvider`** — Apple's Core ML runtime.
- Convert ONNX → Core ML at install time (one-time, fast ~10s per model).
- Runs on Apple's Neural Engine / GPU / CPU depending on op availability.
- We already have the ONNX artifacts that CoreML EP can consume.

### The honest deployment matrix

| Platform | Best path | Why |
|---|---|---|
| Consumer Linux + NVIDIA GPU | **Eager PyTorch** (current) or TRT EP (Phase 6.3 build-on-first-run) | ORT CUDA EP alone is a regression |
| Consumer Mac (Apple Silicon) | ORT + CoreML EP | no TRT; CoreML EP handles LSTM natively |
| Consumer CPU-only (no GPU) | **ORT + CPU EP** | ORT historically 2-3× eager PyTorch on CPU — test to confirm |
| AWS g5 / dedicated server | ORT + TRT EP, Phase 6.3 + full CUDA image | biggest wins; accepts long first-run |
| Blackwell / DGX Spark | Same as above — `Dockerfile.blackwell` already has nvcr.io base | TRT EP loads cleanly in that image |

## Why Phase 6.2 is still worth the plumbing

Even though CUDA EP doesn't beat eager PyTorch, the Layer 1-3 code we shipped this session is the right foundation for:

1. **CPU-only deployments** — ORT CPU EP is usually 2-3× faster than eager PyTorch because ORT fuses kernels aggressively and doesn't need torch's autograd tape.
2. **MPS deployments** — CoreML EP is the only path to Apple's Neural Engine and our batched-fbank helper (no vmap) is required for any ONNX path.
3. **Phase 6.3** — TRT EP consumes the exact same ONNX artifacts we exported. The export pipeline, runtime wrapper, and pipeline integration carry over unchanged.

**What we would re-scope:**

- Previously: "Phase 6.2 = consumer GPU default via ONNX CUDA EP."
- Now: "Phase 6.2 = CPU / MPS path via ONNX; GPU path is Phase 6.3 via TensorRT."

## Things to stop chasing

Based on this session's measurements, the following are documented dead-ends — future sessions should not re-investigate without strong new signal:

1. **ORT CUDA EP as a pyannote-v4 accelerator.** The 5.8× slowdown is driven by `LSTM`, `If`, `Sin`, `Cos` lacking CUDA kernels in ORT 1.25 — a library-level gap, not an export-script gap. Upstream ORT would need to add these kernels. Not worth our time.
2. **`io_binding` alone as the CUDA EP fix.** Reduces Python-boundary overhead from 47.5 → 32.4 ms/batch but doesn't address intra-graph Memcpy. Still 4× slower than eager.
3. **Dynamo-based `torch.onnx.export` on WeSpeaker/segmentation in PyTorch 2.8.** Vmap in WeSpeaker is the blocker; dynamo fails in strict, non-strict, and draft modes. Revisit in PyTorch 2.11+ if vmap support lands.
4. **Full-pipeline ONNX export (end-to-end).** Diarization pipeline has pure-Python clustering, VBx, aggregation steps that are not exportable. Only segmentation + embedding models are viable candidates.
5. **TensorRT plans baked into Docker images.** Per-GPU-arch means one image can't serve multiple GPU types. Build-on-first-run + per-arch OCI artifacts is the only sane distribution model.
6. **bf16 / fp16 via ONNX quantization-aware export.** DER invariance excludes this round. Revisit only with a separate DER re-validation budget.

## Things to pursue

In priority order:

1. **Phase 5.2** (GPU aggregate + reconstruct) — independent of 6.x, projected 4.5% E2E, spec ready.
2. **Phase 5.4** (`GPU_CONCURRENT_REQUESTS` soak test) — independent, 2-4× throughput at deployment level.
3. **Phase 6.2 CPU/MPS validation** — confirm ORT+CPU EP is faster than eager CPU; test CoreML EP on M2 Max. Simple benchmark runs, no code changes.
4. **Phase 6.3 image rework** — switch backend base to `nvidia/cuda:12.8.0-cudnn-runtime` OR mirror `Dockerfile.blackwell`'s base. Enables TRT EP. Only needed if server-tier cloud batch becomes a priority.
5. **Phase 6.3 per-arch prebuilt-plan CI** — nightly GitHub Actions matrix on self-hosted runners; publish `opentranscribe-tensorrt-plans:sm{86,89,90}-vX.Y` artifacts. Only once (4) is done.

## What shipped this session

| Area | File | Purpose |
|---|---|---|
| Fork — runtime wrapper | `fork:pyannote/audio/onnx/__init__.py`, `runtime.py` | ORT session + batched fbank |
| Fork — export | `fork:pyannote/audio/onnx/export.py` | CLI export script, produces .onnx + metadata.json |
| Fork — pipeline integration | `fork:pyannote/audio/pipelines/speaker_diarization.py` (new `_setup_phase6_onnx`) | Monkey-patches infer + resnet + compute_fbank when `PYANNOTE_USE_ONNX=1` |
| Backend — image | `backend/Dockerfile.prod` | gcc/g++ + onnxruntime-gpu force-reinstall |
| Backend — requirements | `backend/requirements.txt` | `onnx`, `onnxruntime-gpu` deps |
| Backend — unit tests | `backend/tests/onnx/test_numeric_parity.py`, `test_fbank_parity.py`, `conftest.py` | T1 + T2 passing, 27 cases |
| Backend — diagnostic script | `scripts/onnx_benchmark_providers.py` | Reproducible CPU/CUDA/TRT EP benchmarks |
| Backend — artifacts | `models/onnx/segmentation.onnx`, `embedding.onnx` + `*.metadata.json` | Exported from our fork's weights |

## Reproducibility

Every diagnostic in this memo can be reproduced with:

```bash
# Export artifacts
docker run --rm --gpus '"device=0"' --entrypoint "" \
  --env-file .env \
  -v /mnt/nvm/repos/pyannote-audio-fork/src/pyannote/audio:/home/appuser/.local/lib/python3.13/site-packages/pyannote/audio:ro \
  -v $(pwd)/models/onnx:/out \
  -e HF_HOME=/tmp/hfcache \
  opentranscribe-backend:latest \
  bash -c 'mkdir -p /tmp/hfcache && python -m pyannote.audio.onnx.export --out-dir /out --device cpu --only both'

# Benchmark providers (this memo's numbers)
docker run --rm --gpus '"device=0"' --entrypoint "" \
  --env-file .env \
  -v /mnt/nvm/repos/transcribe-app/scripts:/app/scripts:ro \
  -v /mnt/nvm/repos/transcribe-app/models/onnx:/onnx:ro \
  opentranscribe-backend:latest \
  python /app/scripts/onnx_benchmark_providers.py --models-dir /onnx

# Run unit tests (T1 + T2)
docker run --rm --gpus '"device=0"' --entrypoint "" \
  --env-file .env \
  -v /mnt/nvm/repos/pyannote-audio-fork/src/pyannote/audio:/home/appuser/.local/lib/python3.13/site-packages/pyannote/audio:ro \
  -v /mnt/nvm/repos/transcribe-app/backend/tests/onnx:/tests/onnx:ro \
  -v /mnt/nvm/repos/transcribe-app/models/onnx:/onnx \
  -e PYANNOTE_ONNX_MODELS_DIR=/onnx \
  -e HF_HOME=/tmp/hfcache \
  opentranscribe-backend:latest \
  bash -c 'mkdir -p /tmp/hfcache && pip install --quiet --user pytest 2>&1 | tail -1 && cd /tests && python -m pytest onnx/ -v -p no:cacheprovider'
```
