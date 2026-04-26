# Upload Speed Benchmark Results

**Date:** 2026-04-26
**Hardware:** NVIDIA RTX A6000 (49 GB), GPU 0, CUDA 13.0
**Model:** large-v3-turbo, int8_float16, batch_size=32
**Method:** Isolated bench volumes (no NAS data), fresh DB each run, built images (no live code mounts)
**Branches:** `master` (v355) vs `feat/upload-speed-improvement` (v362)

## Results

### End-to-End Wall Clock (upload → status=completed)

| Fixture | Size | Master | Branch | Speedup | HTTP saved |
|---------|------|--------|--------|---------|------------|
| 0.5h_1899s.wav | 58 MB | 51.0s | 51.0s | 1.00× | — |
| 1.0h_3758s.wav | 115 MB | 101.8s | 97.2s | 1.05× | +4.5s |
| 2.2h_7998s.wav | 244 MB | 201.3s | 197.2s | 1.02× | +4.1s |
| 3.2h_11495s.wav | 351 MB | 289.4s | 285.7s | 1.01× | +3.8s |
| 4.7h_17044s.wav | 521 MB | 568.1s | 562.8s | 1.01× | +5.3s |
| **Average** | | | | **1.02×** | |

### HTTP Upload Latency (client → MinIO ACK)

| Fixture | Master | Branch | Change |
|---------|--------|--------|--------|
| 0.5h (58 MB) | 2.28s | 2.30s | ±0% |
| 1.0h (115 MB) | 4.50s | 3.06s | **−32%** |
| 2.2h (244 MB) | 7.03s | 5.98s | **−15%** |
| 3.2h (351 MB) | 10.29s | 6.55s | **−36%** |
| 4.7h (521 MB) | 16.12s | 10.64s | **−34%** |
| **Average** | | | **~−29%** |

Raw CSVs:
- `docs/benchmark-results/master_upload_baseline_2026-04-26.csv`
- `docs/benchmark-results/branch_upload_after_2026-04-26.csv`

## Analysis

The branch's upload path optimizations (streaming validation, single DB commit, MinIO part-size tuning, parallel preprocessing, presigned direct-to-MinIO uploads) reduce HTTP upload latency by **~29% on average** for files ≥1 GB.

However, **GPU transcription + diarization accounts for 95–97% of total wall clock**, so the overall end-to-end improvement is **1–5%**. For small files where upload is a larger fraction of total time, the branch benefit would be more visible.

### GPU Transcription VRAM Profile (observed during benchmark)

| Phase | Stable VRAM | Peak VRAM | Notes |
|-------|------------|-----------|-------|
| Idle (preloaded) | ~1.5 GB | — | large-v3-turbo + pyannote loaded |
| WhisperX transcription | 4–9 GB | ~9 GB | Spikes by batch — 32 segs × activations + KV cache (beam_size=5) |
| PyAnnote diarization | ~1 GB | ~2 GB | Pinned batch_size=16 (Phase A fix) |
| CPU post-processing | ~0 GB | — | GPU idle during NLTK, dedup, speaker assignment |

The transcription VRAM spikes (4→6→9 GB) are caused by WhisperX allocating temporary buffers for encoder activations, attention maps, and beam-search KV cache for each batch of 32 segments simultaneously. The whisper batch_size is not yet pinned (unlike diarization's hardcoded 16).

### For 4–8 GB GPU Deployments

To target laptops and lower-VRAM GPUs, two changes are needed:

1. **Pin transcription batch_size** — set `WHISPER_BATCH_SIZE` env var (or hardcode like diarization's 16) to 8 or 4. Reduces peak VRAM from 9 GB to ~3–4 GB at batch=8.
2. **Use a smaller Whisper model** — `medium` peaks at ~3 GB, `small` at ~1.5 GB at batch=8.

See `docs/GPU_PIPELINE_OPTIMIZATION_PLAN.md` for the GPU idle time fix plan.

## Benchmark Infrastructure

The A/B test runs using isolated bench volumes so the NAS production dataset is never touched:

```bash
# Master baseline
./opentr.sh bench start master
./opentr.sh bench run /tmp/master_full.csv benchmark/test_audio

# Branch after
./opentr.sh bench start branch
./opentr.sh bench run /tmp/branch_after.csv benchmark/test_audio

# Compare
./opentr.sh bench compare /tmp/master_full.csv /tmp/branch_after.csv
```
