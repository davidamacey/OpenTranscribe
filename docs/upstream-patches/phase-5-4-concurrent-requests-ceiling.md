# Phase 5.4 — Backend `GPU_CONCURRENT_REQUESTS` Ceiling (feasibility memo)

**Status**: Feasibility analysis. **Recommended** for a dedicated soak-test session.
**Projected impact**: 2–4× end-to-end throughput on RTX A6000 for batch-style workloads.

## Context

Phase A validated that the fork holds per-pipeline peak VRAM at **844 MB ±0 across every test file size and every run**. With a 48 GB A6000 and the 6 GB Whisper baseline still resident, that leaves ~42 GB of free VRAM — enough in theory for **20+ concurrent diarization pipelines** per GPU.

The backend's `GPU_CONCURRENT_REQUESTS` currently caps at 4 per the `config._auto_concurrent()` formula:

```python
def _auto_concurrent() -> int:
    total_vram_mb = torch.cuda.get_device_properties(0).total_memory / (1024**2)
    return min(4, (int(total_vram_mb) - 6000) // 1000)
```

The formula assumes 1000 MB per task + 6000 MB reserved for Whisper, and hard-caps at 4. With Phase A's measured 844 MB per task, the 1000 MB provision is right-sized but the hard cap of 4 leaves ~75% of A6000 idle on batch workloads.

## Proposed change

**Minimal, reversible**: raise the hard cap to 12 and add an env override:

```python
def _auto_concurrent() -> int:
    total_vram_mb = torch.cuda.get_device_properties(0).total_memory / (1024**2)
    env_max = int(os.environ.get("GPU_CONCURRENT_REQUESTS_MAX", "12"))
    # Reserve 6 GB for Whisper + 1 GB per concurrent task (with Phase A's 844 MB
    # per pipeline + 150 MB headroom for allocator fragmentation).
    capacity = (int(total_vram_mb) - 6000) // 1000
    return max(1, min(env_max, capacity))
```

On A6000: `(48000 - 6000) // 1000 = 42`, clamped to `min(12, 42) = 12`.
On RTX 3080 Ti (12 GB): `(12000 - 6000) // 1000 = 6`, clamped to `min(12, 6) = 6`.
Backward compatible: the env var default of 12 is higher than the old 4, so small GPUs still get their VRAM-based ceiling.

## Risks

### 1. cuDNN workspace per-stream

Each concurrent CUDA stream maintains its own cuDNN workspace (~60–200 MB depending on algorithm). With 12 concurrent streams that's up to 2.4 GB of workspace. Phase A measured this with `concurrent=1`; soak tests at `concurrent=8+` are needed before raising the default.

**Mitigation**: benchmark `concurrent ∈ {4, 6, 8, 10, 12}` and measure peak VRAM per-pipeline. If it grows above 1.2 GB at `concurrent=12`, lower the cap.

### 2. Thermal throttling under sustained load

A6000 TDP is 300 W. Sustained 12-way concurrent diarization may push temps toward thermal limits over a multi-hour batch. Observed in Phase A brief runs, not characterized under sustained load.

**Mitigation**: 12-hour soak test at `concurrent=12` with `nvidia-smi` temperature logging. If clocks drop, lower the cap.

### 3. Allocator fragmentation under long runs

PyTorch's allocator is page-based; sustained allocation/deallocation of variable-size tensors can fragment the reserved pool. Phase A only saw steady-state 39 MB (one process); multi-process is untested.

**Mitigation**: set `PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:128` or similar. Measure over 12-hour soak.

### 4. Celery worker memory isolation

Each concurrent task runs in the same Celery worker process with separate CUDA streams. Python GIL will serialize CPU work; if CPU stages (clustering, reconstruct) don't release the GIL, we'd see less than expected throughput.

**Mitigation**: profile wall-time distribution under concurrent=8. If CPU stages block, consider per-worker-process concurrency instead of per-worker-thread.

### 5. Contention on host→device transfers

The H→D transfer stream (Phase A's double-buffered prefetch) may become a bottleneck at high concurrency. PCIe 4.0 × 16 = 32 GB/s; 12 pipelines × 16 × 80000 samples × 4 bytes = ~60 MB per batch → ~2 ms transfer at full bandwidth. Non-trivial if batches arrive back-to-back.

**Mitigation**: measure PCIe utilization during soak. If >80%, reduce concurrent by 1-2.

## Soak test protocol

1. Start backend with `GPU_CONCURRENT_REQUESTS=12`.
2. Enqueue 50 diarization tasks through the Celery worker (mix of 0.5h / 2.2h / 4.7h).
3. Monitor `nvidia-smi --query-gpu=memory.used,temperature.gpu,utilization.gpu --format=csv --loop-ms=1000 > soak.log`.
4. Accept criteria:
   - Peak VRAM ≤ 40 GB (80% of 48 GB on A6000)
   - Per-pipeline peak (process-level) ≤ 1.2 GB
   - No temperature clock drops observed
   - All 50 tasks complete without OOM
   - Combined throughput > 6× single-pipeline rate (at least 50% scaling efficiency)

## Recommendation

Run the soak test in a dedicated session. The code change is trivial (5 lines in `config.py`); the risk is validating production stability. For A6000-dedicated deployments, the upside is substantial (2-4× batch throughput). For shared deployments (A6000 also running LLM, Whisper, etc.), the existing `concurrent=4` is likely still right.

## Measurement gaps to close first

1. **Per-process peak VRAM at concurrent=8 and concurrent=12** — only measured at concurrent=1 in Phase A.
2. **Thermal behavior under 12-hour sustained load** — untested.
3. **PCIe utilization during concurrent H→D transfers** — untested.

Each ~1 day of soak + analysis. Worth doing if/when batch workloads become a significant fraction of production traffic.
