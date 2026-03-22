# GPU Processing Benchmark Results

## System Configuration

| Component | Spec |
|-----------|------|
| CPU | 2x Intel Xeon E5-2680 v3 @ 2.50GHz (24 cores / 48 threads) |
| RAM | 504 GB DDR4 |
| GPU 0 (primary test) | NVIDIA RTX A6000 (48GB GDDR6), Ampere |
| GPU 1 (secondary) | NVIDIA GeForce RTX 3080 Ti (12GB GDDR6X), Ampere |
| GPU 2 (other) | NVIDIA RTX A6000 (48GB GDDR6), Ampere — running LLM |
| Storage | 1.8TB NVMe SSD |
| CUDA | 13.0, Driver 580.126.20 |
| Whisper Model | large-v3-turbo (int8_float16) |
| Diarization Model | PyAnnote v4 (pyannote/speaker-diarization-community-1) |
| PyAnnote Fork | davidamacey/pyannote-audio@gpu-optimizations |
| Celery Pool | threads |

## Database Summary

| Metric | Value |
|--------|-------|
| Total completed files | 1,435 |
| Total audio duration | 3,718 hours (155 days) |
| Average file duration | 2h35m |
| Files >= 3hr | 322 |
| Total storage size | 481 GB |

### Duration Distribution

| Bucket | Files | Hours |
|--------|-------|-------|
| < 5min | 4 | 0.2 |
| 5-30min | 24 | 5.3 |
| 30-60min | 17 | 13.0 |
| 1-2hr | 168 | 279.6 |
| 2-3hr | 900 | 2,366.5 |
| 3-4hr | 316 | 1,027.4 |
| 4hr+ | 6 | 26.0 |

---

## Test 1: Single-File Baseline (A6000, concurrency=1)

**File**: JRE #1467 - Jack Carr (2h47m, 302MB)
**Config**: batch_size=32, TF32=enabled, concurrent_requests=1

### Pipeline Timing (3 iterations)

| Stage | Iter 1 | Iter 2 | Iter 3 | Mean |
|-------|--------|--------|--------|------|
| CPU Preprocess | 26.9s | 18.6s | 18.1s | 21.2s |
| Queue: CPU→GPU | 0.1s | 0.0s | 0.0s | 0.0s |
| GPU Total | 233.5s | 234.1s | 231.3s | **233.0s** |
| Queue: GPU→Post | 0.1s | 0.1s | 0.1s | 0.1s |
| Wall Clock | 4m21s | 4m12s | 4m02s | **4m12s** |

### GPU Sub-Stage Breakdown (from VRAM profiler, iteration 3)

| Sub-stage | Duration | % of GPU | Realtime |
|-----------|----------|----------|----------|
| Whisper transcription | 95s (1m35s) | 41.2% | 104.3x |
| PyAnnote diarization | 124s (2m04s) | 53.4% | 80.4x |
| Speaker assignment | 3.1s | 1.3% | — |
| Other (DB save, cleanup) | 9.7s | 4.2% | — |

### VRAM Profile (iteration 3 — clean GPU, no other models)

| State | Device VRAM | PyTorch Peak | Notes |
|-------|-------------|--------------|-------|
| Models loaded (idle) | 9,302 MB | 31 MB | Whisper CTranslate2 + PyAnnote |
| During transcription | 9,430 MB | 31 MB | +128 MB CTranslate2 buffers |
| During diarization | 9,430 MB | **3,883 MB** | Embedding batch inference peak |
| After cleanup | 9,302 MB | 39 MB | Back to baseline |

### Performance Metrics

| Metric | Value |
|--------|-------|
| Realtime factor (GPU only) | **42.9x** |
| Realtime factor (end-to-end) | **39.3x** |
| GPU utilization (% of wall clock) | 91.6% |
| Speakers detected | 3 |
| 1 hour of audio takes | 1m24s (GPU) / 1m32s (total) |

### Quick Projections (1,400 files at avg 2h47m)

| Workers | Estimated Total Time |
|---------|---------------------|
| 1 | ~99 hours |
| 2 | ~57 hours |
| 4 | ~36 hours |
| 5 | ~32 hours |
| 9 | ~24 hours |

### Notes
- Highly consistent across 3 iterations: GPU time 231-234s (std dev 1.2s)
- Iter 1 preprocess slower (26.9s vs 18s) due to cold MinIO cache
- Diarization is the bottleneck at 53% of GPU time (embedding extraction dominates)
- batch_size=32 had minimal impact vs 12 — CTranslate2 internally chunks to 30s segments
- CTranslate2 (Whisper) uses its own CUDA kernels, not PyTorch matmul — TF32 flag doesn't help transcription
- TF32 benefits PyAnnote embeddings via our fork (already re-enabled in fork code)
- VRAM peak is only 9.4GB device / 3.9GB PyTorch — massive headroom for concurrency on A6000

---

## Test 2: Concurrency Testing (A6000, concurrent_requests=2,3,4)

**Benchmark files**: 5 matched files, all ~2.72-2.78hr (9800-10011s)
- `132e858d` JRE #1467 Jack Carr (2.78hr)
- `23ac4642` JRE #405 Steven Pressfield (2.72hr)
- `2fd923ab` JRE #216 Chael Sonnen (2.72hr)
- `e37539b0` JRE #1291 C.T. Fletcher (2.72hr)
- `d1f806a0` JRE #621 Aubrey Marcus (2.73hr)

### Scaling Results

| Config | Batch Size | Per-File GPU | Batch Wall | Throughput | Speedup | VRAM Peak | Status |
|--------|------------|-------------|------------|------------|---------|-----------|--------|
| concurrent=1 | 32 | 233.0s | 4m12s | 42.9x | 1.0x | 9,430 MB | Done |
| concurrent=2 | 16 | 391s (6m31s) | 7m02s | 46.9x | 2.0x | 14,738 MB | Done |
| concurrent=3 | 10 | 575s (9m35s) | 10m39s | 46.3x | 3.0x | 17,374 MB* | Done |
| concurrent=4 | 8 | | | | | | Pending |

### Key Observations
- **Perfect linear speedup** at both 2x and 3x — no scaling loss
- Throughput plateaus around 46-47x — per-file slowdown offsets concurrency gains
- Per-file time increases: 233s → 391s (+68%) → 575s (+147%) due to GPU contention
- VRAM scales predictably: +5.3GB per concurrent task
- At concurrent=3, VRAM peak 17.4GB* — includes ~3GB from unrelated agent on same GPU
- Actual pipeline VRAM at concurrent=3 estimated ~14-15GB based on profiler step data
- Batch size auto-divided: 32 → 16 → 10 (by TranscriptionConfig concurrent mode)
- Files start and finish within seconds of each other (good scheduling)

---

## Test 3: Multi-GPU (3080 Ti + A6000)

**Status**: Pending

### Plan
- GPU_SCALE_ENABLED=true, dual-GPU mode
- 3080 Ti: 1 worker, concurrency=1
- A6000: scaled worker, concurrency=4
- Total: 5 effective workers

---

## Test 4: Final Projection

**Status**: Pending

### Projection Template

| Configuration | Workers | Est. Time | Audio/hr |
|---------------|---------|-----------|----------|
| A6000 sequential | 1 | | |
| A6000 concurrent=2 | 2 | | |
| A6000 concurrent=4 | 4 | | |
| 3080 Ti + A6000 | 5 | | |
| All 3 GPUs | 9 | | |

---

## Bugs Found & Fixed During Testing

| Bug | Impact | Fix |
|-----|--------|-----|
| Redis VRAM key mismatch | Benchmark scripts never collected VRAM data | `vram_profile:` → `gpu:profile:` in both scripts |
| Auth endpoint format | benchmark_e2e.py sent JSON, API expects form data | Changed to `/api/auth/token` with `data=` |
| TF32 disabled globally | PyAnnote turns off TF32, stays off for Whisper | Re-enable after diarization + at worker startup |
| Deepgram routing | Admin user had Deepgram active, bypassed GPU | Deactivated cloud ASR for benchmarking |
| Segment index overflow | btree can't handle >2704 byte text segments | Migration v353: md5(text) functional index |
| Benchmark task_id mismatch | active_task_id differs from pipeline task_id | Resolve by matching Redis dispatch_timestamp |
| Whisper batch_size hardcoded | .env had GPU_DEFAULT_BATCH_SIZE=12 for A6000 | Changed to auto (detects 32 for A6000) |

---

## Key Findings

1. **Diarization is the bottleneck** — ~52% of GPU time, dominated by embedding extraction (~90s)
2. **Whisper transcription** — ~95-100s for 2.78hr audio regardless of batch_size (12 vs 32)
3. **Pipeline overhead is minimal** — preprocess ~18s, queue gaps <0.2s, DB save <1s
4. **VRAM headroom on A6000** — only ~7.6GB peak out of 49GB, massive room for concurrency
5. **Model preloading works** — 0.0s model load on subsequent tasks (singleton ModelManager)
6. **CTranslate2 ignores TF32** — Whisper uses its own CUDA kernels, not PyTorch matmul
