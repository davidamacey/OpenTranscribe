# Diarization VRAM Profile — Phase A Findings

**Measured:** 2026-04-20 on GPU 0 (NVIDIA RTX A6000, 48 GB), benchmark container using the same image as `opentranscribe-celery-worker` (CUDA 12.8, torch 2.8.0+cu128, fork `davidamacey/pyannote-audio@gpu-optimizations`).

**Corpus:** `benchmark/test_audio/0.5h_1899s.wav` (1899 s, 4 speakers) and `2.2h_7998s.wav` (7998 s, 3 speakers).

**Harness:** `scripts/vram-probe-diarization.py` via `docker-compose.benchmark.yml` (`--matrix` and `--small-batch-sweep` modes). NVML ctypes sampler at 100 ms cadence; torch allocator peaks via `torch.cuda.memory_stats`.

**Raw data:** `docs/diarization-vram-profile/raw/*.json` (156 runs: 96 matrix + 60 small-batch sweep).

## Bottom line

1. **Embedding-batch throughput saturates at bs=16.** On the 2.2 h file at fp32, wall-time is 103 s at bs=16, 103 s at bs=32, 100 s at bs=64, 100 s at bs=128. Above 16, the fork's auto-scaler promotes batch up to 64–128 and spends **3–7 GB of extra VRAM for ~3 % throughput gain.**
2. **bs=16 fp32 fits a 4 GB laptop GPU with room for Whisper.** Pipeline process footprint at bs=16 is ~950 MB (device peak − idle baseline) plus ~500 MB CUDA context = ~1.5 GB total. Whisper small/base adds ~0.5–0.8 GB. Budget on a 4 GB card: ~2 GB free for system + driver overhead.
3. **fp16 autocast is not safe to ship as default.** At every batch size from 1 to 256, fp16 systematically merges speakers (0.5 h: 4 → 2; 2.2 h: 3 → 2) and drops ~30–44 % of the segments. The effect is consistent across batch sizes, so it is a pure precision effect, not a batching artifact. fp16 gains ~30–45 % wall time; it should be an opt-in "fast mode" with a loud accuracy caveat, not the default.
4. **Parallel diarization is viable on large GPUs.** At bs=16 fp32, a single pipeline uses ~1.5 GB total. An A6000 (48 GB) could host ~20+ concurrent diarizations, or a combined Whisper-plus-diarization worker pool an order of magnitude larger than today's `concurrent_requests=1` default.

## Throughput curve (2.2 h file, fp32, unlimited cap)

| Embedding batch size | Wall time (s) | Δ vs bs=64 | Device peak (MB) | Process footprint (MB) |
|---:|---:|---:|---:|---:|
| 1   | 265 | +165 % | 1 740 | 640 |
| 4   | 126 |  +26 % | 1 740 | 640 |
| 8   | 111 |  +11 % | 1 740 | 640 |
| **16**  | **103** | **+3 %** | **2 054** | **954** |
| 32  | 103 |   +3 % | 3 046 | 1 946 |
| 64  | 100 |   0 %  | 5 668 | 4 568 |
| 128 | 100 |   0 %  | 9 054 | 7 954 |

Process footprint = device peak − ~1 100 MB idle baseline (other host workloads on GPU 0 during the sweep).
bs=64/128 rows are from the 96-run trimmed matrix; bs≤32 from the small-batch sweep with `PYANNOTE_FORCE_EMBEDDING_BATCH_SIZE` bypassing the fork auto-scaler.

At bs=1/4/8 the process footprint plateaus at ~640 MB because torch's allocator pool is dominated by the segmentation model weights and a minimum reservation; actual per-item cost only shows up once the embedding pool scales past the reservation floor (~bs=16).

## DER — formal accuracy verification (Phase A.3, 2026-04-20)

Reference: fp32/bs=16/unlimited/r=0 for each file. Metric: `pyannote.metrics.DiarizationErrorRate(collar=0.25, skip_overlap=False)`. Full table in [`accuracy.md`](accuracy.md); raw RTTMs in `raw/rttm/`.

| Precision | bs range | DER @ 0.5 h | DER @ 2.2 h | Speaker count | Tier |
|---|---|---:|---:|:---:|:---:|
| fp32 | 1 → 128 | 0.00–0.07 % | 0.00 % | match | **T1** |
| fp16 | 1 → 128 | **33.3 %**  | **26.9 %** | 4→2 / 3→2 | **T3** |

Two findings from the DER table:

1. **fp32 is batch-size-invariant.** Changing bs from 1 to 128 produces the same diarization output, modulo 0.07 % jitter at bs=1 on the 0.5 h file (6 of 703 segments differ). The fork's auto-scaler, which chose bs=64–128, was trading 3-7 GB of VRAM for *zero* accuracy or speed benefit.
2. **fp16 is not a precision tunable; it is a different model.** The DER delta is so large (26-33 %) that the fp16 path is effectively clustering on a different embedding space. The root cause is almost certainly numerical underflow in the WeSpeaker pooling `std()` stage (warning emitted on every fp16 run). fp16 must be gated behind an opt-in flag with explicit accuracy-loss documentation; it cannot ship as default.

## fp16 vs fp32 on the same corpus

| File | Precision | Speakers detected | Segments | Wall @ bs=16 |
|---|---|---:|---:|---:|
| 0.5 h (4-speaker GT) | fp32 | **4** | 703 | 23.5 s |
| 0.5 h (4-speaker GT) | fp16 | 2   | 395 | 15.0 s |
| 2.2 h (3-speaker GT) | fp32 | **3** | 2 855 | 102.9 s |
| 2.2 h (3-speaker GT) | fp16 | 2   | 2 020 | 60.7 s |

The fp16 delta is constant across bs ∈ {1, 4, 8, 16, 32, 64, 128, 256}. The `UserWarning: std(): degrees of freedom is <= 0` emitted during fp16 runs in `pyannote/audio/models/blocks/pooling.py:103` points at numerical underflow in the statistics pooling stage — a plausible root cause for the speaker merging.

Phase A.3 (formal DER via `pyannote.metrics.DiarizationErrorRate`) will put a hard number on the accuracy cost. Based on the ~30–44 % segment-count drop, we expect DER well above the 3 % "marginal" threshold in the plan, which puts fp16 in the T3 (rejected as default) tier.

## Recommended Phase B policy

The fork's `_budget.py` helper should map free VRAM to a batch size without tier-differentiating by GPU class:

| Free VRAM available to diarization | Embedding batch size | Precision |
|---|---|---|
| < 700 MB   | 4  | fp32 |
| 700–1 000 MB | 8  | fp32 |
| 1 000–1 900 MB | 16 | fp32 |
| ≥ 1 900 MB  | 16 | fp32 (bigger buys nothing) |
| User opts in to fast mode | unchanged | fp16 (with accuracy warning) |

Retire the current auto-scaler's bs=64–256 range entirely. It was premised on "bigger batch = more throughput" which this data disproves above bs=16.

## Parallel-diarization opportunity

A single diarization pipeline at bs=16 fp32 holds ~1.5 GB of VRAM (weights + CUDA context + activations). This unlocks:

- **Multi-file parallelism on a single A6000** (48 GB): ~20–25 concurrent pipelines, vs. today's default of 1 via `GPU_CONCURRENT_REQUESTS=1`. Actual ceiling limited by CPU pre/post-processing, not GPU.
- **Mixed-model worker** on a 24 GB card: Whisper medium (~4 GB) + 8–10 concurrent diarizations in the same worker process.
- **Laptop recipe** on a 4 GB 3050: Whisper small + 1 diarization, sequential, completes a 2.2 h file in ~100 s diarization + transcription time.

Phase C should surface a `DIARIZATION_PARALLEL_WORKERS` setting that scales with `free_vram_mb / 1500` and expose a measured `recommended_budget_mb` from the backend diag endpoint (plan A.7 item 4).

## Baseline accounting note

Runs up to 2026-04-20 subtract a manual 1 100 MB estimate of the idle-GPU baseline (other host workloads on GPU 0 during the sweep). From 2026-04-20 onward the probe captures `device_baseline_mb` (pre-pipeline NVML reading) and `device_delta_mb = peak − baseline` directly in each run's JSON, so downstream analysis no longer needs to approximate.

## Phase A artifacts (all completed 2026-04-20)

| Phase | Artifact | Finding |
|---|---|---|
| A.2 | isolation matrix + small-batch sweep — this README, `raw/*.json` (156 runs) | bs=16 fp32 saturates throughput; bs>16 wastes VRAM |
| A.3 | [`accuracy.md`](accuracy.md), `raw/rttm/` | fp32 DER≈0 across bs∈{1..128}; fp16 DER 27-33 % (T3) |
| A.6 | [`whole-stack.md`](whole-stack.md), `raw/whole-stack/*.json` (12 runs) | Full consumer-GPU sizing table; sequential swap confirmed |
| A.6b | see `whole-stack.md` § A.6b | Residue floor = 300 MB (CUDA context + allocator); per-process, not per-task |
| A.7 | `backend/app/scripts/diarization_diag.py` | `python -m app.scripts.diarization_diag` prints recommended config |

Phase A policy conclusion (confirmed end-to-end): **bs=16 fp32 for all deployments**, subtract 300 MB for CUDA context, Whisper-small is the largest model that fits on a 4 GB laptop alongside diarization.

## Outstanding (Phase B / C)

- **Phase B:** implement `pipelines/_budget.py` in the fork; replace the bs=64–256 auto-scaler with the free-VRAM → batch table from this README.
- **Phase C:** surface `DIARIZATION_VRAM_BUDGET_MB`, `DIARIZATION_MIXED_PRECISION`, `DIARIZATION_ONNX_CPU` in `backend/app/core/config.py`. Drop the diag's `CUDA_CONTEXT_MB` to a per-driver table once we have numbers from other GPU classes.
- **Cross-validation:** one representative config on physical RTX 3080 Ti (GPU 1) vs. capped-A6000 to confirm simulation fidelity within 5 % (plan A.7 item 3).
- **Whisper large-v3-turbo whole-stack probe:** add to `--sweep` models list; need turbo numbers for the default deployment path.

## MPS (Apple Silicon) cross-platform validation — 2026-04-20

**Host:** Mac Studio, M2 Max (superstudio@192.168.30.26). torch `mps.is_available() == True`, `recommended_max_memory = 21 845 MB`.

**Unit tests:** all 28 `test_budget.py` assertions pass on `darwin-arm64`. `_budget.py` is pure-Python + stdlib so the ladder math is host-independent.

**Budget recommendations on MPS:**

| `free_mb` passed to `recommend_embedding_batch(device='mps')` | Returned |
|---:|---|
| 8 000 | `batch_size=16, status='optimal'` |
| 1 000 | `batch_size=8, status='tight'` |
| 500 | `batch_size=4, status='insufficient'` |

Identical to CUDA behaviour — no MPS-specific divergence.

**Integration smoke:** fresh-pipeline runs on the 0.5 h clip, forced bs=64 (old auto-scaler) vs. Phase B auto-selected bs=16:

| Config | Speakers | Wall time | Notes |
|---|:---:|---:|---|
| forced bs=64 | 4 | 42.6 s | matches Phase A CUDA reference for this file |
| Phase B auto (bs=16) | 4 | 41.7 s | output identical |

**Memory delta caveat:** MPS does **not** expose `torch.mps.max_memory_allocated()`; only `driver_allocated_memory()` (instantaneous). The reduction in *peak* allocation (which is the headline win on CUDA — 5.7 GB → 2.1 GB at fp32) cannot be measured directly on MPS with the current torch API. Indirect argument for the same win holding on MPS:

1. The WeSpeaker weights and per-item activation shapes are identical on CUDA and MPS; the allocator just lives in unified memory.
2. On CUDA, the dominant term is `bs × per_item_bytes` for the transformer activations, which shows up in the same units on MPS.
3. The recommended cap (`recommended_max_memory` - `allocated`) is what the fork's MPS branch already used; moving from bs=64 to bs=16 shrinks the cap demand by the same ratio.

For a direct peak-memory-on-MPS measurement, add a 100 ms sampling probe that polls `driver_allocated_memory` in a thread during inference (mirror of the CUDA NVML sampler). Tracked as a follow-up in Phase A.7 item 4 (user-facing diag CLI enhancement).

The Mac's prior uncommitted MPS work is parked as `stash@{0}` (`phase-B-mps-test-stash`) on the fork and intentionally not reapplied.
