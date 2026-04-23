# Phase 6.1 — `torch.compile` Enablement (feasibility memo)

**Status**: Feasibility analysis. **Recommended** as a 1-day commit.
**Projected impact**: 5-15% on segmentation + embedding stages on CUDA; 0-3% on MPS.
**Tier**: Tier 1 — default-on, automatic fallback, consumer-friendly.

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

**Ship.** 1-day commit: Dockerfile line + image rebuild + 3-run benchmark on 2.2h/4.7h. Low risk, automatic fallback, consumer-friendly (cache is persistent).

If measurement shows <3% gain across both stages, **keep the gcc change anyway** — it unlocks future ONNX/TensorRT export tooling that also needs the toolchain.

## Interaction with Phase 6.2 / 6.3

- Phase 6.2 (ONNX export) is compile-time, happens offline, no runtime gcc needed.
- Phase 6.3 (TensorRT plan) uses TensorRT's own compiler, not gcc.
- Phase 6.1 is complementary, not replaced by later phases. Keep it default-on.

## References

- Phase 2.1 plumbing: `pipelines/speaker_diarization.py:307-318`
- Inductor cache layout: `~/.cache/torch/inductor/`
- PyTorch 2.10 `torch.compile` docs: https://pytorch.org/docs/2.10/generated/torch.compile.html
