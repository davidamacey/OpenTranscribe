# WhisperX Batch Size VRAM Profile — Phase B Study

**Date:** 2026-04-26
**Hardware:** NVIDIA RTX A6000 (49,140 MB NVML), CUDA 13.0, Driver 580.126.20
**Models tested:** large-v3-turbo, medium, small — all compute_type=int8_float16, beam_size=5
**Audio fixture:** 2.2h_7998s.wav (8005s, 244 MB)
**Measurement method:** NVML background poller at 100 ms intervals (captures CTranslate2
allocations that torch.cuda.memory_allocated() misses entirely)
**Script:** `backend/app/scripts/whisper_batch_diag.py`

---

## VRAM Baseline Decomposition

All sweeps were run inside the production celery-worker which pre-loads PyAnnote diarization
models at startup. The NVML baseline before Whisper loads therefore includes:

| Component | VRAM (MB) |
|-----------|-----------|
| CUDA context only | ~300 |
| PyAnnote diarization models (segmentation + embedding + wespeaker) | ~1,739 |
| **Total process baseline (all sweeps)** | **2,039** |

Whisper model footprint = `stable_before − 2039` (Whisper loaded, no inference yet):

| Model | stable_before MB | Model footprint MB |
|-------|-----------------|-------------------|
| large-v3-turbo | 3,371 | **1,332** |
| medium | 3,211 | **1,172** |
| small | 2,603 | **564** |

Peak activation overhead = `peak − stable_before` (encoder activations + KV cache during inference):
varies by batch size — see per-model tables below.

---

## Raw Results — large-v3-turbo

| batch_size | stable_before MB | peak MB | stable_after MB | wall_s | RTF   | status |
|-----------|-----------------|---------|-----------------|--------|-------|--------|
| 2         | 3363            | 3893    | 3445            | 106.6  | 0.013 | ok     |
| 4         | 3371            | 4341    | 3477            | 86.2   | 0.011 | ok     |
| 8         | 3371            | 5269    | 3477            | 75.3   | 0.009 | ok     |
| 12        | 3371            | 6197    | 3541            | 72.3   | 0.009 | ok     |
| 16        | 3371            | 7125    | 3509            | 73.5   | 0.009 | ok     |
| 24        | 3371            | 8981    | 3541            | 72.4   | 0.009 | ok     |
| 32        | 3371            | 10837   | 3541            | 71.2   | 0.009 | ok     |

Throughput **plateau at batch=8** (RTF 0.009 from bs=8 through bs=32).
VRAM increment above stable_before: ~928 MB per 8-unit step.

Raw CSV: `a6000_large-v3-turbo_2026-04-26.csv`

---

## Raw Results — medium

| batch_size | stable_before MB | peak MB | stable_after MB | wall_s | RTF   | status |
|-----------|-----------------|---------|-----------------|--------|-------|--------|
| 2         | 3203            | 3829    | 3285            | 209.4  | 0.026 | ok     |
| 4         | 3211            | 4181    | 3317            | 142.6  | 0.018 | ok     |
| 8         | 3211            | 5045    | 3317            | 106.7  | 0.013 | ok     |
| 12        | 3211            | 5973    | 3381            | 97.8   | 0.012 | ok     |
| 16        | 3211            | 6869    | 3317            | 89.2   | 0.011 | ok     |
| 24        | 3211            | 8629    | 3349            | 84.0   | 0.011 | ok     |
| 32        | 3211            | 10389   | 3349            | 83.8   | 0.011 | ok     |

Throughput **plateau at batch=24** (RTF 0.011 for bs=24 and bs=32).
VRAM increment above stable_before: ~864 MB per 8-unit step.

Raw CSV: `a6000_medium_2026-04-26.csv`

---

## Raw Results — small

| batch_size | stable_before MB | peak MB | stable_after MB | wall_s | RTF   | status |
|-----------|-----------------|---------|-----------------|--------|-------|--------|
| 2         | 2595            | 2933    | 2677            | 134.1  | 0.017 | ok     |
| 4         | 2603            | 3221    | 2709            | 92.4   | 0.011 | ok     |
| 8         | 2603            | 3797    | 2709            | 70.0   | 0.009 | ok     |
| 12        | 2603            | 4341    | 2709            | 64.1   | 0.008 | ok     |
| 16        | 2603            | 4885    | 2709            | 59.8   | 0.007 | ok     |
| 24        | 2603            | 6005    | 2741            | 57.8   | 0.007 | ok     |
| 32        | 2603            | 7157    | 2709            | 57.2   | 0.007 | ok     |

Throughput **plateau at batch=24** (RTF 0.007 for bs=24 and bs=32).
VRAM increment above stable_before: ~576 MB per 8-unit step (smaller encoder, smaller activations).

Raw CSV: `a6000_small_2026-04-26.csv`

---

## Key Findings (All Models)

### Finding 1: Each Model Has Its Own Throughput Saturation Point

| Model | Plateau batch | RTF at plateau | RTF at batch=2 | Speedup 2→plateau |
|-------|--------------|---------------|----------------|-------------------|
| large-v3-turbo | **8** | 0.009 | 0.013 | 1.44× |
| medium | **24** | 0.011 | 0.026 | 2.36× |
| small | **24** | 0.007 | 0.017 | 2.43× |

Larger models saturate earlier (fewer simultaneous batches needed to fill the GPU).
Smaller models keep improving up to batch=24 before plateauing.

### Finding 2: Whisper-Isolated VRAM Budget (Production Stack)

Peak VRAM with baseline (2039 MB) subtracted = Whisper activation overhead above process floor.
For hardware sizing at any GPU tier, use the full peak column — it already reflects production state.

### Finding 3: Safe Batch Ceiling by GPU Class — Production Stack (80% rule)

`peak_mb ≤ 0.80 × total_vram_mb`
Baseline 2039 MB (CUDA context + diarization) is included in all peak figures.

#### large-v3-turbo

| GPU VRAM | 80% threshold | Safe max batch | Peak at safe batch | Notes |
|----------|--------------|----------------|-------------------|-------|
| 4 GB (4,096) | 3,277 | **NOT SUPPORTED** | bs=2 peaks 3,893 MB — exceeds threshold | Use medium or small |
| 6 GB (6,144) | 4,915 | **4** | 4,341 MB | 574 MB headroom |
| 8 GB (8,192) | 6,554 | **8** | 5,269 MB | 1,285 MB headroom |
| 12 GB (12,288) | 9,830 | **16** | 7,125 MB | 2,705 MB headroom |
| 16 GB+ | — | **16** | 7,125 MB | plateau — no benefit above 16 |

#### medium

| GPU VRAM | 80% threshold | Safe max batch | Peak at safe batch | Notes |
|----------|--------------|----------------|-------------------|-------|
| 4 GB (4,096) | 3,277 | **NOT SUPPORTED** | bs=2 peaks 3,829 MB — exceeds threshold | Use small |
| 6 GB (6,144) | 4,915 | **4** | 4,181 MB | 734 MB headroom |
| 8 GB (8,192) | 6,554 | **8** | 5,045 MB | 1,509 MB headroom |
| 12 GB (12,288) | 9,830 | **16** | 6,869 MB | 2,961 MB headroom |
| 16 GB+ | — | **24** | 8,629 MB | plateau — bs=24 is safe on 12 GB+ |

#### small

| GPU VRAM | 80% threshold | Safe max batch | Peak at safe batch | Notes |
|----------|--------------|----------------|-------------------|-------|
| 4 GB (4,096) | 3,277 | **4** | 3,221 MB | 56 MB headroom (marginal — use 2 for safety) |
| 6 GB (6,144) | 4,915 | **12** | 4,341 MB | 574 MB headroom |
| 8 GB (8,192) | 6,554 | **16** | 4,885 MB | 1,669 MB headroom |
| 12 GB (12,288) | 9,830 | **24** | 6,005 MB | 3,825 MB headroom |
| 16 GB+ | — | **24** | 6,005 MB | plateau |

> **Note on 4 GB + small:** batch=4 peak is 3,221 MB vs 3,277 MB threshold — only 56 MB margin.
> Recommend batch=2 (2,933 MB, 344 MB headroom) for safety on 4 GB cards.

---

## Recommended Defaults by GPU + Model (hardware_detection.py)

| GPU VRAM | large-v3-turbo | medium | small |
|----------|---------------|--------|-------|
| 4 GB | NOT SUPPORTED | NOT SUPPORTED | 2 (safe) |
| 6 GB | 4 | 4 | 12 |
| 8 GB | 8 | 8 | 16 |
| 12 GB | 16 | 16 | 24 |
| 16 GB | 16 | 24 | 24 |
| 24 GB+ | 16 | 24 | 24 |

**Cap rationale:** Values are the throughput-plateau ceiling for each model/GPU combination.
Going above these adds VRAM cost with no speed benefit.

---

## Comparison with Diarization Phase A

| Metric | Diarization (embedding batch) | Whisper turbo | Whisper medium | Whisper small |
|--------|------------------------------|---------------|----------------|---------------|
| Throughput plateau | batch=16 | batch=8 | batch=24 | batch=24 |
| VRAM at plateau | ~1 GB | ~5.3 GB | ~6.9 GB | ~4.9 GB |
| VRAM increment / step | ~244 MB/8 | ~928 MB/8 | ~864 MB/8 | ~576 MB/8 |

---

## Phase B.2 — Remaining Next Steps

1. **Validate on RTX 3080 Ti (12 GB)** to confirm 12 GB thresholds with real hardware.
2. **Measure WER across batch sizes** — expected to be identical (batch size does not affect
   decoding outputs in faster-whisper's BatchedInferencePipeline), but should be verified.
3. **Update hardware_detection.py** to be model-aware — currently uses turbo thresholds for
   all models; add per-model branches using data from this study.
