# Phase 6.1 — `torch.compile` Enablement (feasibility memo)

**Status**: **SHIPPED 2026-04-23**. Image change landed; default kept OFF pending broader wins.
**Measured impact on CUDA A6000, 2.2h, 3-run warm**: segmentation ~6-7% faster (5.52s → 5.11-5.16s), embeddings in noise (75.27s → 75.61-76.15s). **End-to-end unchanged** (~100s). DER 0.0000% (T1). VRAM 844 MB unchanged. First-run compile cost: ~68s (one-time, cached).
**Tier**: Tier 1 — opt-in via `torch_compile=True` kwarg, available but off by default. Primary value: unblocks Phase 6.2 (ONNX) + 6.3 (TensorRT) tooling which also need the toolchain.

## Context

Phase 2.1 wired `torch.compile` into the fork at `pipelines/speaker_diarization.py:307-318`. The gate fires on CUDA and MPS and calls `torch.compile(self._segmentation.model)` and `torch.compile(self._embedding)`. Phase 2.1 also replaced `except Exception: pass` with `logger.warning`.

**What we discovered:** the compile call succeeds but the first forward pass fails silently in our Docker container:

```
torch._inductor.exc.InductorError: BackendCompilerFailed:
backend='inductor' raised: FileNotFoundError: [Errno 2] No such file or directory: 'gcc'
```

Inductor generates C++ kernels for CPU fallback paths and C++ launcher code for Triton kernels. It shells out to the system C compiler. The production backend image (`backend/Dockerfile.blackwell`) uses `nvidia/cuda:...-runtime` which has no toolchain. PyTorch catches the error and falls back to eager, so the pipeline keeps running — but we get zero `torch.compile` benefit.

## Proposed change

### Dockerfile (single line, ~150 MB image growth)

```dockerfile
# backend/Dockerfile.blackwell
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    && rm -rf /var/lib/apt/lists/*
```

That's sufficient to unblock Inductor. No other changes.

### Cache layout

Inductor writes compiled kernels to `~/.cache/torch/inductor/`. Already inside the `MODEL_CACHE_DIR` volume mount path (`/home/appuser/.cache/torch/` is mapped to `${MODEL_CACHE_DIR}/torch/`). Cache persists across container restarts. **No separate cache infrastructure needed.**

### First-run behavior

- Segmentation model: ~60-120s compile (one-time per GPU + torch + driver combo).
- Embedding model: ~60-90s compile.
- Combined first-run delay: **~2-3 min**, blocking the first transcription task.
- Subsequent runs: cache hit, zero overhead.

### User-facing surfacing

If we want to avoid "is it frozen?" tickets:

```python
# backend/app/transcription/diarizer.py
logger.info("Optimizing models for this GPU (one-time, ~2-3 min)...")
# first forward pass
logger.info("Model optimization complete (cached for future runs).")
```

And emit a WebSocket progress update on the first run. Low-priority polish.

## Measurement plan

1. Baseline: current fork HEAD (compile silently disabled) on 2.2h + 4.7h A6000.
2. Rebuild backend image with gcc.
3. Restart worker; confirm `TORCH_LOGS=recompiles` shows `unique_graphs > 0`.
4. Run 3× on 2.2h (first run discarded for compile cost), 3× on 4.7h.
5. Accept if:
   - Segmentation stage ≥5% faster.
   - Embedding stage ≥5% faster.
   - DER unchanged (byte-identical RTTM).
   - Peak VRAM delta ≤ +100 MB (compile graph buffers).
   - cv < 10%.

## Risks

### 1. Shape specialization causing recompile storms

`torch.compile` specializes on tensor shapes. Pyannote's variable-length chunks can trigger recompiles on every unique shape. Mitigation: `torch.compile(model, dynamic=True)` or pre-pad to fixed shapes (Phase A's segmentation_batch_size=32 already enforces fixed shape for most batches).

**If recompile storms happen**: the log will show `dynamo.utils.counters["stats"]["unique_graphs"] > 10` and runtime will *regress*. Revert to `dynamic=True` or disable.

### 2. Image size growth

`gcc g++` adds ~150 MB to the backend image. Offset: the image is already ~8 GB (CUDA + PyTorch + WhisperX + pyannote). Marginal.

**Alternative**: `build-essential` is ~300 MB — don't use it, just `gcc g++`.

### 3. MPS — limited benefit

MPS Inductor backend is incomplete in PyTorch 2.10. Compile attempts on MPS often fall back to eager silently (different mechanism). Expected speedup on MPS: 0-3%. Leave the gate enabled — cost is zero when it falls back.

### 4. Airgapped deployments

Inductor caches compiled kernels to disk. For airgapped / offline installs: first-run compile still works (no network access required). Cache survives container rebuilds because of the volume mount.

### 5. Cold-start cost in CI / benchmarks

Benchmark harness must run 1 warmup + N measurement runs. Phase 1.1's harness already supports `--runs N` with the first run separable — document convention.

## Recommendation

**Shipped.** gcc+g++ added to `backend/Dockerfile.prod` runtime stage (~150 MB image growth). Warm-run measurement showed segmentation at the low end of the projected band (~6-7%) and embeddings in noise — net E2E is indistinguishable from baseline at measurement precision. **Default is kept OFF**: the `torch_compile` kwarg remains opt-in. The change still earns its keep because Phase 6.2 and 6.3 both require the toolchain for their export/compile pipelines.

## Actual measurements (2026-04-23, A6000, 2.2h, 3 runs after warmup)

| stage | baseline | with torch.compile | Δ |
|---|---:|---:|---:|
| segmentation | 5.52s | 5.11-5.16s | **-6.5 to -7.4%** |
| embeddings | 75.27s | 75.61-76.15s | +0.4 to +1.2% (noise) |
| clustering_start | 12.29s | 12.08-12.26s | unchanged |
| **E2E** | **~100s** | **100.7-101.7s** | **noise** |
| peak VRAM | 844 MB | 844 MB | 0 |
| DER | — | 0.0000% T1 ×3 | 0 |
| first-run compile cost | — | +68s | amortized over cache lifetime |

## Interaction with Phase 6.2 / 6.3

- Phase 6.2 (ONNX export) is compile-time, happens offline, no runtime gcc needed.
- Phase 6.3 (TensorRT plan) uses TensorRT's own compiler, not gcc.
- Phase 6.1 is complementary, not replaced by later phases. Keep it default-on.

## References

- Phase 2.1 plumbing: `pipelines/speaker_diarization.py:307-318`
- Inductor cache layout: `~/.cache/torch/inductor/`
- PyTorch 2.10 `torch.compile` docs: https://pytorch.org/docs/2.10/generated/torch.compile.html
