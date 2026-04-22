# Per-Pipeline VRAM Budget Table (Phase 1.7)

**Measurement date**: 2026-04-21
**Hardware**: NVIDIA RTX A6000 (48 GB), torch 2.8.0+cu128, driver 580.126.20
**Fork commit**: `85858462` (gpu-optimizations branch)
**Model**: `pyannote/speaker-diarization-community-1` (v4)
**Sample rate**: 16 kHz mono float32
**Embedding batch size**: 16 (fixed per Phase A)

## Context

Phase A measured that per-pipeline peak stays around 1 GB with the fork's optimizations in place. This table decomposes that 1 GB into components so Phase 3 (GPU clustering) knows exactly how much headroom it has before the 1.05 GB invariant kicks in.

## Headline numbers (0.5h / 1899s / 4 speakers, 5-run mean)

| Metric | Value | Notes |
| --- | --- | --- |
| Overall peak | **844 MB** | `torch.cuda.max_memory_allocated`, process-private |
| Steady state (+2s) | **39 MB** | after `torch.cuda.empty_cache()` — models released |
| Baseline alloc pre-run | **0 MB** | fresh process, no residual |
| Reserved (pool) | **~50 MB** post-run | post-cache allocator pool |

The 844 MB peak is distributed across two stages, neither of which persists — the allocator returns to 39 MB after the pipeline releases the embedding model.

## Per-stage VRAM decomposition (0.5h file, 5-run mean)

Cumulative peak is monotonic within a single pipeline call. "Delta" is the stage's contribution over the cumulative peak reached at the previous stage boundary.

| Stage | Wall (s) | Cum peak (MB) | Delta (MB) | Attribution |
| --- | ---: | ---: | ---: | --- |
| `segmentation` | 1.3-1.9 | 437 | **+398-406** | Segmentation model weights (~100 MB) + chunk-batch activations (~300 MB) |
| `vram_cleanup_post_segmentation` | 0.1 | 437 | 0 | No-op for peak — internal `empty_cache` releases reserved, not peak |
| `speaker_counting` | 0.0 | 437 | 0 | CPU — pure numpy |
| `binarization` | 0.04-0.3 | 437 | 0 | CPU — in-place threshold |
| `embedding_chunk_extraction` | 0.16-0.20 | 437 | 0 | CPU — `waveform.unfold` + mask build |
| `embedding_inference_start` | 0.0 | 437 | 0 | Hook-only — no real work |
| **`embeddings`** | **17.5-18.1** | **844** | **+407** | WeSpeaker weights (~80 MB) + fbank + resnet activations + pinned transfer buffers + CUDA stream workspace |
| `vram_cleanup_post_embedding` | 0.02-0.03 | 844 | 0 | Peak counter doesn't decrease on `empty_cache` |
| `clustering_start` | 1.2-1.6 | 844 | 0 | **Pure CPU** (scipy `cdist` + `linkage`) — no GPU alloc |
| `clustering_done` | 0.0 | 844 | 0 | Hook-only |
| `reconstruction_start` | 0.56-0.63 | 844 | 0 | Pure CPU (numpy double loop — see vectorization-audit §1) |
| `discrete_diarization` | 0.98-1.06 | 844 | 0 | Pure CPU (overlap-add aggregation) |

## Budget for Phase 3 (GPU clustering)

Given the 1.05 GB ceiling (1 GB invariant + 5 % tolerance):

```
1050 MB  (ceiling)
- 844 MB  (current peak, dominated by embedding stage)
= 206 MB  headroom (headline)
```

But: by the time clustering runs, the embedding stage has **already completed** and the allocator has its peak locked in at 844 MB. `torch.cuda.empty_cache()` releases the reserved pool but does NOT reset the peak counter. So any additional allocation during clustering pushes the peak above 844 MB by whatever the clustering stage allocates.

**Effective budget for Phase 3 clustering tensors** = `1050 - 844 = 206 MB` **headline**, but we want a larger safety margin for:
- Sustained allocations across stages (MPS unified memory has less precise accounting)
- The concurrent-pipeline stress test where contention may inflate allocator overhead
- Future additions (Phase 3.5 `reconstruct` vectorization may temporarily allocate a 38 MB mask)

**Recommended budget**: **50 MB** default (`PYANNOTE_CLUSTERING_VRAM_BUDGET_MB=50`), exposed as env override.

## Memory cost per clustering-stage N (dim=256 fp32)

| N (embeddings) | Normalized copies (×2) | Pairwise full matrix (N²) | Pairwise condensed (N·(N−1)/2) | Within 50 MB budget? |
| ---: | ---: | ---: | ---: | :---: |
| 500 | 1 MB | 1 MB | 0.5 MB | Yes (2.5 MB) |
| 1000 | 2 MB | 4 MB | 2 MB | Yes (8 MB) |
| 2000 | 4 MB | 16 MB | 8 MB | Yes (28 MB) |
| 3000 | 6 MB | 36 MB | 18 MB | Tight (60 MB total) — **falls back** |
| 4000 | 8 MB | 64 MB | 32 MB | **Falls back** (104 MB) |
| 5000 | 10 MB | 100 MB | 50 MB | Falls back |

Typical diarization produces N=200-2000 embeddings even on 4.7h/21-speaker files (≈ chunks × active-speakers-per-chunk). The fallback guard is reached rarely but must exist.

**Fallback implementation**: Phase 3 helper `_gpu_clustering_fits(n, dim, device)` checks free VRAM via `torch.cuda.mem_get_info()` AND budget env; falls back to scipy CPU path if either is exhausted. Logs `logger.info` when triggered so tests can assert fallback was exercised (required by Phase 3 gate point 6).

## Updates needed when Phase 3 lands

After `torch.cdist` replaces scipy in clustering.py:
- `clustering_start` delta will rise from `+0 MB` to **some value** — measure and log here
- Overall peak must stay ≤ 1050 MB on all four reference files both devices
- Update this table with the post-Phase-3 column for comparison

## Concurrent-pipeline headroom

Assuming 1 GB per pipeline holds after Phase 3:

| GPU | Total VRAM | Whisper + baseline | Available | Max concurrent diarizations |
| --- | ---: | ---: | ---: | ---: |
| RTX A6000 (48 GB) | 48000 | ~6000 | 42000 | **~40** theoretical, 20-25 practical (per Phase A memory notes) |
| RTX 3080 Ti (12 GB) | 12000 | ~6000 | 6000 | ~5 (practical: 3-4) |
| Mac Studio M2 Max (32 GB unified) | 32000 | variable | variable | Measured separately; MPS accounting less precise |

This is the theoretical ceiling for **Phase 5.4 research memo** (backend concurrency). Not a commitment — practical ceiling depends on cuDNN per-stream workspace, thermal, and allocator fragmentation under sustained load.

## Measurement rigour note

All numbers above come from **5-run means** on fixed seed with `torch.cuda.synchronize()` before each timestamp. Coefficient of variation (cv) on wall time is < 3 %. Run-to-run VRAM peaks are identical (memory allocator is deterministic for fixed input shapes) — we report the single measured value rather than a distribution.

The 2.2h / 3.2h / 4.7h data will update this table once the long-file benchmark matrix completes (in-flight at time of writing — run ID `b4yfjy8a6`).
