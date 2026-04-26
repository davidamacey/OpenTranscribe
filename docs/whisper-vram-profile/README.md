# WhisperX Batch Size VRAM Profile — Phase B Study

**Date:** 2026-04-26
**Hardware:** NVIDIA RTX A6000 (49,140 MB NVML), CUDA 13.0, Driver 580.126.20
**Model:** large-v3-turbo, compute_type=int8_float16, beam_size=5
**Audio fixture:** 2.2h_7998s.wav (8005s, 244 MB)
**Measurement method:** NVML background poller at 100 ms intervals (captures CTranslate2
allocations that torch.cuda.memory_allocated() misses entirely)
**Script:** `backend/app/scripts/whisper_batch_diag.py`

---

## Raw Results

| batch_size | stable_before MB | peak MB | stable_after MB | wall_s | RTF   | status |
|-----------|-----------------|---------|-----------------|--------|-------|--------|
| 2         | 3363            | 3893    | 3445            | 106.6  | 0.013 | ok     |
| 4         | 3371            | 4341    | 3477            | 86.2   | 0.011 | ok     |
| 8         | 3371            | 5269    | 3477            | 75.3   | 0.009 | ok     |
| 12        | 3371            | 6197    | 3541            | 72.3   | 0.009 | ok     |
| 16        | 3371            | 7125    | 3509            | 73.5   | 0.009 | ok     |
| 24        | 3371            | 8981    | 3541            | 72.4   | 0.009 | ok     |
| 32        | 3371            | 10837   | 3541            | 71.2   | 0.009 | ok     |

VRAM baseline (NVML, before Whisper model load): **2039 MB**
(includes PyAnnote diarization models + CUDA context preloaded in celery-worker)

Whisper model footprint: stable_before − baseline = 3371 − 2039 = **1332 MB**

Raw CSV: `a6000_large-v3-turbo_2026-04-26.csv`

---

## Key Findings

### Finding 1: Throughput Saturates at batch=8

```
RTF (lower = faster):
batch=2:   0.013  ████████████░
batch=4:   0.011  ██████████░░░
batch=8:   0.009  █████████░░░░  ← plateau begins
batch=12:  0.009  █████████░░░░
batch=16:  0.009  █████████░░░░
batch=24:  0.009  █████████░░░░
batch=32:  0.009  █████████░░░░
```

Going from batch=8 to batch=32 yields **zero throughput improvement** (RTF 0.009 throughout).
batch=2 is 44% slower than the plateau; batch=4 is 22% slower.

This mirrors the diarization Phase A finding where embedding throughput saturated at batch=16.

### Finding 2: VRAM Scales ~928 MB per 8 Batch Units

```
peak VRAM above stable_before (3371 MB):
batch=2:  +522 MB   (encoder activations for 2 segments)
batch=4:  +970 MB
batch=8:  +1898 MB
batch=12: +2826 MB
batch=16: +3754 MB
batch=24: +5610 MB
batch=32: +7466 MB  ← current default: +7466 MB for zero extra speed vs batch=8
```

Linear scaling: approximately **+928 MB per 8-unit increment** in batch size.

### Finding 3: batch=32 Wastes 5568 MB vs batch=8

Current default on the A6000 (≥40 GB): batch=32, peak 10,837 MB.
Optimal choice on the A6000: batch=8, peak 5,269 MB.

Switching to batch=8 on the A6000 **frees 5568 MB** of VRAM with no speed cost.
That headroom is enough to run 5 additional concurrent PyAnnote diarization pipelines
(at ~1 GB each) — directly enabling the multi-file GPU parallelism described in
`docs/GPU_PIPELINE_OPTIMIZATION_PLAN.md`.

---

## Safe Batch Size by GPU Class (large-v3-turbo, int8_float16)

Constraint: `peak_whisper_mb ≤ total_vram_mb × 0.80`
(leaves 20% headroom for PyAnnote segmentation peak ~1–2 GB running immediately after)

| GPU Class | Total VRAM | 80% threshold | Safe max batch | Peak at safe batch | Headroom |
|-----------|-----------|--------------|---------------|-------------------|---------|
| 4 GB      | 4,096 MB  | 3,277 MB     | **NOT SUPPORTED** | 3,893 MB (bs=2) exceeds 80% | — |
| 6 GB      | 6,144 MB  | 4,915 MB     | **4**             | 4,341 MB           | 574 MB  |
| 8 GB      | 8,192 MB  | 6,554 MB     | **8**             | 5,269 MB           | 1,285 MB |
| 12 GB     | 12,288 MB | 9,830 MB     | **16**            | 7,125 MB           | 2,705 MB |
| 16 GB     | 16,384 MB | 13,107 MB    | **16**            | 7,125 MB           | 5,982 MB |
| 24 GB     | 24,576 MB | 19,661 MB    | **16**            | 7,125 MB (plateau) | 12,536 MB |
| 48 GB (A6000) | 49,140 MB | 39,312 MB | **16**        | 7,125 MB (plateau) | 32,187 MB |

**Recommended universal cap: batch=16** — same speed as batch=24/32, uses 3.7 GB less VRAM,
safe on all 12 GB+ GPUs with comfortable headroom for diarization.

**Note on 4 GB GPUs:** large-v3-turbo cannot run on 4 GB GPUs even at batch=2 (3,893 MB
peak exceeds the 3,277 MB 80% threshold). These GPUs require the `medium` model
(estimated ~2.5 GB peak at batch=4) or `small` (~1.8 GB peak). A follow-up sweep for
smaller models is needed — see Phase B.2 below.

---

## Comparison with Diarization Phase A

| Metric | Diarization (embedding batch) | Whisper (transcription batch) |
|--------|------------------------------|------------------------------|
| Throughput plateau | batch=16 | **batch=8** |
| VRAM at plateau | ~1 GB | ~5.3 GB (3.9 GB above baseline) |
| VRAM at current default | same (16 is the default) | 10.8 GB (batch=32) |
| Wasted VRAM at current default | 0 (already optimal) | **5.5 GB** |
| DER/accuracy change across batch | 0 (identical) | Not yet measured (expected 0) |

Diarization embedding was already pinned correctly by Phase A. Whisper transcription
batch needs to be capped at 16 (or lower for small GPUs).

---

## Phase B.2 — Next Steps

1. **Run sweep for `medium` and `small` models** to populate the 4–6 GB GPU rows:
   ```bash
   docker exec -it opentranscribe-celery-worker \
     python -m app.scripts.whisper_batch_diag \
       --audio /app/benchmark/test_audio/2.2h_7998s.wav \
       --model medium --batch-sizes 2,4,8,16,32 \
       --output /tmp/whisper_batch_medium.csv
   ```

2. **Run on RTX 3080 Ti (12 GB)** to validate the 12 GB thresholds with real hardware:
   ```bash
   CUDA_VISIBLE_DEVICES=1 docker exec -it opentranscribe-celery-worker \
     python -m app.scripts.whisper_batch_diag \
       --audio /app/benchmark/test_audio/1.0h_3758s.wav \
       --model large-v3-turbo --batch-sizes 2,4,8,12,16 \
       --output /tmp/whisper_batch_3080ti.csv
   ```

3. **Update `hardware_detection.py`** — already done based on these A6000 results.

4. **Measure WER (accuracy) across batch sizes** — expected to be identical (batch size
   does not affect decoding outputs in faster-whisper's BatchedInferencePipeline), but
   should be verified on a reference corpus.
