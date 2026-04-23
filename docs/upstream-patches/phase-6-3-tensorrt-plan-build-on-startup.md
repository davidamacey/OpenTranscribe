# Phase 6.3 — TensorRT Engine Plans for Server Deployments (updated 2026-04-23)

**Status**: **UNBLOCKED**. Phase 6.2's ONNX-export path is validated; TensorRT EP consumes the same artifacts. 1-week investigation/commit once Phase 6.2 ships.
**Projected impact (fp32 only)**: 20-40% on segmentation, 15-25% on embeddings — stacked on top of Phase 6.2's ONNX gains.
**Tier**: Tier 3 — AWS / dedicated-GPU-server deployments, opt-in, not for consumer images.

## Why 6.3 is unblocked

See `phase-6-2-onnx-export-feasibility.md`. Key facts:

- **WeSpeaker ResNet-backbone export works cleanly** (`max_abs_diff=1.57e-05`, `cos≈0.99999994`).
- **Segmentation export produces frame-class-identical output** (zero mismatches out of 7k+ frames in the spike).
- The same `.onnx` artifacts that Phase 6.2 ships can be loaded by ONNX Runtime's `TensorrtExecutionProvider` with no further code changes — it's a provider-list change in the runtime wrapper.

```python
providers = [
    ("TensorrtExecutionProvider", {
        "trt_engine_cache_enable": True,
        "trt_engine_cache_path": "/home/appuser/.cache/tensorrt",
        "trt_fp16_enable": False,                   # fp32 — DER invariant
        "trt_max_workspace_size": 2 << 30,          # 2 GB
    }),
    "CUDAExecutionProvider",   # fallback if TRT plan build fails
    "CPUExecutionProvider",
]
```

On first inference with this provider list, ORT invokes TRT to build a hardware-specific engine plan (6-13 min), caches it to `trt_engine_cache_path`, and replays the cached plan on subsequent inference. No extra tooling.

## Architecture

### Deployment positioning (unchanged)

- **Consumer (Phase 6.2)**: ONNX with `CUDAExecutionProvider` (NVIDIA) / `CoreMLExecutionProvider` (Apple) / `CPUExecutionProvider` (airgapped). No first-run compile.
- **Server (Phase 6.3)**: ONNX with `TensorrtExecutionProvider` prepended. One-time 6-13 min build on first startup per unique GPU arch, cached thereafter.

### Cache layout

```
${MODEL_CACHE_DIR}/tensorrt/
├── sm_86_trt-10.3_cuda-12.8/      # A6000, A10G, A5000
│   ├── TensorrtExecutionProvider_TRTKernel_*.engine    # auto-named by ORT
│   └── TensorrtExecutionProvider_cache_.timestamp
├── sm_89_trt-10.3_cuda-12.8/      # RTX 40-series
├── sm_90_trt-10.3_cuda-12.8/      # H100, H200
└── build_metadata.json            # our own: fork SHA, pyannote HF revision
```

Cache key: `f"sm_{compute_capability}_trt-{trt_version}_cuda-{cuda_version}"`. If fingerprints don't match on boot (driver upgrade, TRT upgrade, fork update), rebuild.

### Opt-in gate

```bash
# backend/.env for AWS / server deployment
ENABLE_TENSORRT=true
PYANNOTE_USE_ONNX=true             # hard prerequisite
TENSORRT_CACHE_DIR=/var/cache/tensorrt  # persistent across container restarts
```

### Server-side prebuilt-plan OCI artifacts (optional optimization)

For Attevon AWS deployments, an nightly CI matrix job builds plans on each known GPU arch and publishes:

- `davidamacey/opentranscribe-tensorrt-plans:sm86-v1.0`  (A10G, A6000)
- `davidamacey/opentranscribe-tensorrt-plans:sm89-v1.0`  (RTX 40-series)
- `davidamacey/opentranscribe-tensorrt-plans:sm90-v1.0`  (H100)

Deployment pulls the matching artifact based on detected GPU arch. Skips the 6-13 min first-run build entirely. Phase 2 of 6.3.

## Test matrix

Built on top of Phase 6.2's matrix — this phase swaps the ORT provider and re-runs. All integration tests use the same canonical sample files as the rest of the project.

### Canonical sample inputs (unchanged from 6.2)

Same files in `benchmark/test_audio/`:
- `0.5h_1899s.wav`, `2.2h_7998s.wav`, `3.2h_11495s.wav`, `4.7h_17044s.wav`

### Phase T1-TRT — Numeric parity (TRT EP vs CUDA EP vs PyTorch eager)

| Model × Device × Provider | Input | Parity metric | Accept |
|---|---|---|---:|
| Seg × CUDA × TRT EP | `(2, 1, 160000)` random | frame-class mismatch vs PyTorch | 0% |
| Emb × CUDA × TRT EP | `(16, 200, 80)` random | `max_abs_diff`, cos similarity | ≤1e-3, ≥0.999 |

TRT EP tolerance is one order of magnitude looser than CUDA EP (1e-3 vs 1e-4) because TRT's fused kernels do accumulation in different order. Frame-class argmax must still be bit-exact for segmentation. Cosine threshold for embedding loosened from 0.9999 → 0.999 — still well above downstream clustering sensitivity.

**File**: extend `backend/tests/onnx/test_numeric_parity.py` with `--provider=trt` parameter.

### Phase T3-TRT — DER regression (same files as 6.2)

| File | Device | Runs | DER acceptance |
|---|---|---:|---|
| 0.5h_1899s | A6000 (sm_86) TRT EP | 3 | ≤0.1 pp vs Phase 6.2 baseline |
| 2.2h_7998s | A6000 TRT EP | 3 | ≤0.1 pp |
| 3.2h_11495s | A6000 TRT EP | 3 | ≤0.1 pp |
| 4.7h_17044s | A6000 TRT EP | 3 | ≤0.1 pp |
| 2.2h_7998s | 3080 Ti TRT EP (different arch — sm_86) | 3 | ≤0.1 pp (cross-arch validation) |

DER reference is Phase 6.2's ONNX baseline, **not PyTorch eager**. This isolates TRT-specific regression from ONNX-vs-eager drift (which 6.2 already validated).

### Phase T4-TRT — Speed vs Phase 6.2's ONNX CUDA EP baseline

| Metric | File | Device | Runs | Acceptance |
|---|---|---|---:|---|
| Segmentation stage wall | 2.2h, 4.7h | A6000 | 3 warm | ≥15% faster vs ONNX CUDA EP |
| Embedding stage wall | 2.2h, 4.7h | A6000 | 3 warm | ≥15% faster vs ONNX CUDA EP |
| End-to-end wall | 4.7h | A6000 | 3 warm | ≥5% E2E faster vs 6.2 baseline |
| First-run TRT build time | cold-start | A6000 | 1 | ≤15 min |
| Cache-hit inference init | warm-start | A6000 | 3 | ≤2s |

### Phase T5-TRT — VRAM / workspace (strict!)

TRT's workspace allocation is nontrivial and goes in our 844 MB envelope.

| Metric | File | Device | Acceptance |
|---|---|---|---|
| Peak VRAM during TRT build | first startup | A6000 | ≤ 2.5 GB peak (transient) |
| Peak VRAM at inference time | 4.7h | A6000 | **≤ 1.15 GB per pipeline** (100 MB TRT workspace allowance) |
| Steady-state VRAM (+2s after return) | 2.2h | A6000 | ≤ 1.0 GB |
| Build-phase doesn't interfere with other processes | GPU with 2+ TF processes | A6000 | no OOM |

**Critical**: the 1.05 GB invariant from every prior phase is **relaxed to 1.15 GB** here because TRT workspace lives in our envelope. If we can't stay under 1.15 GB, we bound `trt_max_workspace_size` downward until we fit.

### Phase T6-TRT — Concurrent + cross-arch

| Concurrency | Device | Acceptance |
|---|---|---|
| 4 pipelines | A6000 TRT EP | each ≤1.15 GB, no plan-cache races |
| 8 pipelines | A6000 TRT EP | same |
| Plan cache validity after image rebuild | A6000 | cache invalidated correctly (fork SHA changed) |
| Plan cache validity after driver upgrade | A6000 with manual nvidia-driver bump | cache invalidated correctly |

## Rollout plan (after Phase 6.2 ships)

1. **Provider integration** (1 day): add TRT EP option to the ONNX runtime wrapper from 6.2. Gate on `ENABLE_TENSORRT=true`.
2. **T1-TRT + T3-TRT** (2 days): parity + DER on A6000 + 3080 Ti.
3. **T4-TRT + T5-TRT** (2 days): speed and VRAM measurement. This phase decides go/no-go on the 1.15 GB relaxation.
4. **T6-TRT** (1 day): concurrent pipeline stress; confirm plan cache behavior.
5. **Nightly CI prebuilt-plan artifacts** (1-2 days, optional): GitHub Actions matrix on self-hosted runners with each arch; publish per-arch OCI artifacts.
6. **Flip `ENABLE_TENSORRT` default** (0.5 day) in server-only compose overlay, leave consumer default off.

Total: **6-8 days** of focused work after Phase 6.2 is merged.

## Risks

1. **TRT workspace memory eats into our 844 MB envelope** — T5-TRT will surface it early. Mitigation: bound `trt_max_workspace_size`. Accept 1.15 GB per pipeline as the new invariant for server tier only; consumer tier stays at 1.05 GB via Phase 6.2 CUDA EP.
2. **Build failures on rare GPU SKUs** — pre-Turing cards are TRT 10.x incompatible. Mitigation: `_tensorrt_supported(compute_capability)` check; fall back to CUDA EP.
3. **Plan cache corruption** across upgrades — T6-TRT validates driver/TRT version-stamped cache keys.
4. **ORT's TRT EP is a layer of abstraction** over raw TRT; some optimizations only reachable via direct `tensorrt.Builder` API. We explicitly accept that tradeoff (maintainability > last 5% of speed).
5. **fp32 constraint caps gains at 20-40%** per the original projection. The juicy 2-3× wins come from fp16/int8, which are DER-risky and excluded this round.

## Interaction with Phase 5.4 (concurrent-request ceiling)

Phase 5.4's soak-test plan assumes 844 MB per pipeline → 25 parallel on A6000. If T5-TRT relaxes the per-pipeline envelope to 1.15 GB, the ceiling drops to:
- `(48000 - 6000 [Whisper]) / 1150 ≈ 36` — still well above the current `GPU_CONCURRENT_REQUESTS_MAX=12` target.

Phase 5.4's existing recommendations and soak-test protocol remain valid; Phase 6.3 doesn't materially change them.

## Artifacts

- Reuse `scripts/spike-onnx-export-v2.py` — produces the ONNX inputs TRT EP will consume.
- (to come) `scripts/prebuild_tensorrt_plans.py` — one-shot script for CI to build per-arch plan artifacts.
- (to come) `backend/tests/onnx/test_tensorrt_*.py` — pytest suite for T1-TRT through T6-TRT.
- (to come) `docker-compose.tensorrt.yml` — optional compose overlay setting `ENABLE_TENSORRT=true`.
