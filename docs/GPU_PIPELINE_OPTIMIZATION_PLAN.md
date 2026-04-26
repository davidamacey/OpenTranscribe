# GPU Pipeline Optimization Plan

**Discovered:** 2026-04-26 during upload-speed A/B benchmark
**Status:** Documented — not yet implemented
**Priority:** Medium (affects throughput and low-VRAM GPU support)

## Problem 1: GPU Idle During CPU Post-Processing

### Observation

During transcription, `nvtop` shows the GPU going idle for extended periods while the CPU
runs post-processing steps. The current task execution order is fully sequential:

```
GPU: [transcription] [diarization] [idle.............] [idle...]
CPU: [idle.........] [idle.......] [NLTK split] [dedup] [speaker assign] [DB write]
```

The GPU waits for the entire CPU post-processing chain before it can release the task and
accept the next file from the queue. On a 4.7h file, CPU post-processing takes ~10–15s,
during which the GPU (and next queued file) sit idle.

### Root Cause

The Celery `gpu_transcribe` task is a single monolithic function:
`backend/app/tasks/transcription/core.py`. It calls `pipeline.process()` then
`postprocess()` (NLTK split → dedup → speaker assignment → DB write) before returning.
No other file can start until this returns.

### Proposed Fix: Split GPU and CPU Stages into Separate Celery Tasks

Break `gpu_transcribe` into two chained tasks:

```
gpu_transcribe        → [transcription + diarization] → emits result dict
cpu_postprocess       → [NLTK + dedup + speaker assign + DB write] (CPU queue)
```

With Celery's `chain()`, `cpu_postprocess` runs on the CPU worker concurrently with the
NEXT file's `gpu_transcribe` on the GPU worker. This fully overlaps CPU post-processing
of file N with GPU processing of file N+1:

```
GPU: [transcribe N] [diarize N] [transcribe N+1] [diarize N+1] ...
CPU:                            [postproc N    ] [postproc N+1] ...
```

### Expected Benefit

- Removes ~5–15s GPU idle per file (CPU post-processing time)
- For a batch of 10 files, this saves ~1–2 min total
- More significant as file count grows (linear savings per file)
- Improves GPU utilization from ~90% → ~97%+ for consecutive uploads

### Implementation Notes

- New Celery task `cpu_postprocess` on the existing `cpu` queue (no GPU needed)
- `gpu_transcribe` returns the raw transcript + diarization result as a dict
- `cpu_postprocess` receives that dict and runs NLTK, dedup, speaker_assignment, DB write
- Use `celery.chain(gpu_transcribe.s(...), cpu_postprocess.s())` at dispatch time
- Progress notifications must be emitted from each task's stage, not just at end of chain
- The `file_pipeline_timing` instrumentation (v360 migration) tracks stage boundaries;
  add `cpu_postprocess_start` and `cpu_postprocess_end` markers

### Files to Change

- `backend/app/tasks/transcription/core.py` — split into gpu + cpu halves
- `backend/app/tasks/transcription/dispatch.py` — chain tasks instead of single task
- `backend/app/tasks/transcription/postprocess.py` — move to CPU task
- `backend/app/tasks/transcription/notifications.py` — emit from each stage

---

## Problem 2: WhisperX Transcription Batch VRAM Spikes

### Observation

During transcription of large files, GPU VRAM spikes from the ~1.5 GB idle baseline to
4–9 GB in waves. The pattern matches batch processing — each batch of 32 segments
simultaneously allocates encoder activations + attention maps + beam-search KV cache
(beam_size=5, 32 segments × 5 beams × N layers).

Diarization is stable at ~1 GB because its embedding batch was pinned to 16 in Phase A
(`SpeakerDiarizer.EMBEDDING_BATCH_SIZE = 16`). Whisper batch_size is currently
auto-selected (defaults to 32 on CUDA) and is NOT pinned.

### Impact

- RTX A6000 (49 GB): no issue, spikes handled
- RTX 3080 Ti (12 GB): marginal at batch=32 for large models
- 8 GB GPU (laptop): OOM crash at batch=32 with large-v3-turbo
- 6 GB GPU: requires medium model + batch=8 or smaller
- 4 GB GPU: requires small model + batch=4

### Proposed Fix: Pin Whisper Batch Size by GPU VRAM Budget

Add a VRAM-aware batch size resolver in `TranscriptionConfig`:

```python
WHISPER_VRAM_BUDGET_MB = {
    "large-v3-turbo":  {"32": 9000, "16": 5000, "8": 3000, "4": 2000},
    "large-v3":        {"32": 11000, "16": 6000, "8": 4000, "4": 2500},
    "medium":          {"32": 5000, "16": 3000, "8": 2000, "4": 1500},
    "small":           {"32": 3000, "16": 2000, "8": 1500, "4": 1000},
}

def _resolve_batch_size(model_name: str, available_vram_mb: int) -> int:
    budgets = WHISPER_VRAM_BUDGET_MB.get(model_name, {})
    for batch in [32, 16, 8, 4]:
        if budgets.get(str(batch), 9999) <= available_vram_mb * 0.85:
            return batch
    return 4  # safe fallback
```

Alternatively, expose `WHISPER_BATCH_SIZE` as an env/DB config with a safe default of 8
(works on 6 GB GPUs with large-v3-turbo without OOM).

### Files to Change

- `backend/app/tasks/transcription/core.py` — resolve batch size at startup
- `backend/app/core/config.py` — add `WHISPER_BATCH_SIZE` env var
- `backend/app/transcription/pipeline.py` — pass batch_size to WhisperX
- `backend/alembic/versions/` — add `asr.whisper_batch_size` system setting (optional)

---

## Problem 3: No GPU Concurrency Between Transcription and Diarization Stages

### Observation

Within a single file's processing, transcription and diarization are strictly sequential.
Transcription finishes, then diarization begins. During diarization's segmentation phase
(~8–12s), the GPU is lightly loaded. The two models (Whisper and PyAnnote) do not overlap.

### Future Opportunity

PyAnnote's segmentation (neural segmentation model) could overlap with the final Whisper
decoding if the audio is chunked. This is a significant refactor (requires streaming the
Whisper output chunks to PyAnnote incrementally) and is listed here as a future research
item, not a near-term task.

---

## Summary Table

| Item | Effort | VRAM Impact | Throughput Impact |
|------|--------|------------|-------------------|
| Pin whisper batch_size | Small | High (enables 4–8 GB GPUs) | Slight decrease at batch<32 |
| GPU↔CPU task split | Medium | None | +5–15% on batches |
| Whisper/PyAnnote overlap | Large | None | +10–20% single file |

Tackle in order: batch_size pin first (enables deployment on more hardware), then GPU/CPU
task split (throughput), then whisper/pyannote overlap (research).
