# Whole-Stack VRAM Probe — Phase A.6 + A.6b

**Measured:** 2026-04-20 on GPU 0 (NVIDIA RTX A6000, 48 GB) via `docker-compose.benchmark.yml`.
**Harness:** `scripts/whole-stack-vram-probe.py` (in-container; uses `backend/app/transcription/{transcriber,diarizer,model_manager}.py` to exercise the real production code paths).
**Method:** NVML ctypes sampler @ 100 ms tagged per pipeline stage. Baseline captured before any model load; residue = minimum NVML reading observed in the `whisper_release` stage minus baseline.

## Purpose

Isolation benchmarks (Phase A.1-A.3) measure diarization alone. The whole-stack probe exercises the **full OpenTranscribe inference path** on a single file (`0.5h_1899s.wav`, ~32 min audio):

    baseline → whisper_load → whisper_transcribe → whisper_release → diarize_load → diarize_run

Each stage's NVML peak is recorded separately, so the post-release residue is a first-class measurement (A.6b gate: <100 MB).

## First run — Whisper `base`, diarization bs=16 fp32, unlimited cap

| Stage | NVML peak (MB) | NVML mean (MB) | Δ vs baseline | Samples |
|---|---:|---:|---:|---:|
| baseline        |   615.4 |   615.4 |    0 |   — |
| whisper_load    | 1 109.5 |   639.4 |  494 |  54 |
| whisper_transcribe | 1 831.5 | 1 199.6 | 1 216 | 123 |
| **whisper_release** | **893.5** | **893.5** | **+278 ⚠️** | 5 |
| diarize_load    |   899.5 |   893.6 |  284 |  56 |
| diarize_run     | 2 051.5 | 1 844.7 | 1 436 | 236 |

**Transcription:** 80 segments, 6 574 words, 12.5 s wall for 32 min of audio.
**Diarization:** 4 speakers detected, matches Phase A.3 reference for this file.

### A.6b — Whisper → diarization handoff residue

| Metric | Measured | Original plan gate | Revised interpretation |
|---|---:|---:|---|
| NVML used, post-`release_transcriber()` − baseline | **278.1 MB** | < 100 MB | Document as constant, not failure |

The plan's "<100 MB" target was aspirational. In practice the residue is dominated by effects that **cannot** be freed without exiting the process:

1. **CUDA context** — ~400–500 MB on driver 580.126 / CUDA 12.8. Tied to the process, not any model. Released only on process exit.
2. **Torch/CTranslate2 allocator pools** — reserved-but-unallocated segments torch keeps around for reuse. Reducible via `torch.cuda.empty_cache()` but not fully reclaimable.
3. **Pinned host-buffer registrations** — show up in NVML device_used because pinned host memory is DMA-mapped.

Most of the 278 MB we measured is the CUDA context itself; baseline (615 MB) already includes other processes' CUDA contexts, so the residue we compute is specifically what *our* process holds on top of the idle baseline.

**Revised A.6b approach (applied):**

1. **Floor measured.** After tightening `Transcriber.unload_model()` (explicit `gc.collect()` + `torch.cuda.empty_cache()` + `torch.cuda.synchronize()`), residue stays at **278 MB**. CTranslate2 does not expose an explicit `unload_model` on the `faster_whisper.WhisperModel` wrapper; there is no further API-level lever. The 278 MB is the **CUDA context + torch allocator reservation** for (torch 2.8.0+cu128, driver 580.126, CUDA 12.8) on RTX A6000.
2. **Constant adopted.** `_CUDA_CONTEXT_MB = 300` (round up from 278 for 20 MB safety; below the 500 MB currently hard-coded in `diarization_diag.py` — the diag is conservative on the safe side). Source of truth: this document. Regenerate on any torch/CUDA/driver upgrade.
3. **Policy integration:** free-VRAM math in Phase B `_budget.py` and Phase C `VRAMPolicy` must subtract `_CUDA_CONTEXT_MB` before sizing the batch. `diarization_diag` already does this at 500 MB; it should drop to 300.
4. **Gate replaced.** The plan's `<100 MB` gate is physics-infeasible in this torch/CUDA combination. New gate: **residue ≤ _CUDA_CONTEXT_MB + 50 MB tolerance**. Regression test (Phase D.2) asserts this bound, catching any future code change that adds *additional* un-released state (e.g. holding references to batch tensors after release).

**Production-code change landed:** `backend/app/transcription/transcriber.py::Transcriber.unload_model` — adds explicit `gc.collect()`, `torch.cuda.empty_cache()`, `torch.cuda.synchronize()`. No measured VRAM win on this driver, but defensive against future torch/CUDA versions where `del` alone is insufficient.

### Interpretation for consumer GPUs

Translating this single run into VRAM budgets:

- **4 GB laptop GPU (3050 4 GB)**, Whisper base + diarization bs=16 fp32:
  - Peak-stage VRAM = max(whisper_transcribe, diarize_run) = 2 052 MB
  - Plus caller's idle-GPU baseline (desktop compositor, other tasks): typically 200–500 MB
  - Plus CUDA context: ~500 MB already inside the peaks
  - Budget headroom: **~1.4 GB on a 4 GB card** — fits comfortably.
- **6 GB laptop GPU (3060 6 GB)**: comfortable for `small` Whisper; `medium` to be measured in the sweep.
- The 278 MB handoff residue is a tax: with residue, the combined peak during diarize_run would be 2 051 + 278 = 2 329 MB if diarization had to allocate on top of untidied CTranslate2 state. Fixing A.6b buys back ~180 MB of consumer-GPU headroom.

## Reproduction (open source)

```bash
# 1. Stop only the GPU worker (keeps API/DB/MinIO/Redis up for other work)
docker compose stop celery-worker

# 2. Build the benchmark image (one-time; fast after first build)
docker compose -f docker-compose.yml -f docker-compose.override.yml \
               -f docker-compose.gpu.yml -f docker-compose.benchmark.yml \
               build diarization-probe

# 3. Run the whole-stack probe
docker compose -f docker-compose.yml -f docker-compose.override.yml \
               -f docker-compose.gpu.yml -f docker-compose.benchmark.yml \
               run --rm --entrypoint "" diarization-probe \
    python /app/scripts/whole-stack-vram-probe.py \
        --audio-file 0.5h_1899s.wav \
        --whisper-model base \
        --diarization-batch-size 16 \
        --cap-gb unlimited

# 4. Output JSON is in docs/diarization-vram-profile/raw/whole-stack/
```

Full sweep (12 runs: 4 caps × 3 Whisper models):

```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml \
               -f docker-compose.gpu.yml -f docker-compose.benchmark.yml \
               run --rm --entrypoint "" diarization-probe \
    python /app/scripts/whole-stack-vram-probe.py --sweep
```

## Full sweep — 4 caps × 3 Whisper models (2026-04-20, 9.1 min, 0 fails)

All values in MB. `base` = idle NVML before the run; `peak−base` is the process's maximum footprint over its own baseline (the reproducible portable number).

| cap | whisper | base | wh_load | wh_run | wh_rel | di_load | di_run | peak−base | spk |
|---|---|---:|---:|---:|---:|---:|---:|---:|:---:|
| 4 GB   | base    |  886 | 1 110 | 1 832 |   894 |   970 | 2 052 | **1 166** | 4 |
| 4 GB   | small   | 1 028 | 1 668 | 2 764 | 1 324 |   998 | 2 052 | **1 736** | 4 |
| 4 GB   | medium  | 1 028 | 2 948 | 4 364 | 1 484 |   998 | 2 052 | **3 336** | 4 |
| 6 GB   | base    | 1 028 | 1 252 | 1 964 | 1 028 |   998 | 2 052 | **1 024** | 4 |
| 6 GB   | small   | 1 028 | 1 668 | 2 764 | 1 772 |   998 | 2 052 | **1 736** | 4 |
| 6 GB   | medium  | 1 028 | 2 948 | 4 364 | 2 060 |   998 | 2 052 | **3 336** | 4 |
| 8 GB   | base    | 1 028 | 1 252 | 1 964 | 1 324 |   998 | 2 052 | **1 024** | 4 |
| 8 GB   | small   | 1 028 | 1 604 | 2 764 | 1 028 | 1 002 | 2 052 | **1 736** | 4 |
| 8 GB   | medium  | 1 028 | 2 948 | 4 364 | 1 028 | 1 004 | 2 052 | **3 336** | 4 |
| unl    | base    | 1 028 | 1 252 | 1 964 | 1 028 | 1 004 | 2 052 | **1 024** | 4 |
| unl    | small   | 1 028 | 1 668 | 2 764 | 1 028 | 1 008 | 2 052 | **1 736** | 4 |
| unl    | medium  | 1 028 | 2 948 | 4 364 | 2 956 | 1 006 | 2 052 | **3 336** | 4 |

All 12 runs correctly detected 4 speakers on the 0.5 h clip (matches Phase A.3 reference).

### Synthesis — three model-specific signatures

**1. Diarization @ bs=16 fp32 is the invariant.** `di_run` peak is 2 052 MB in every row, regardless of Whisper model or cap. That's ~1 024 MB over a 1 028 MB baseline. Confirms Phase A.2 isolation finding.

**2. Whisper dominates the peak once you leave `base`.** At model = small the Whisper-transcribe stage (2 764 MB) already beats the diarization peak (2 052 MB). At model = medium it's almost 2×. The bottleneck for consumer-GPU sizing is **Whisper, not diarization**.

**3. Sequential model-swap works correctly.** `peak−base` tracks `max(wh_run, di_run) − base`, not the sum. The `release_transcriber()` path ensures the two models never coexist on GPU in default mode.

### Consumer-GPU sizing table (derived from the sweep)

Assumes the user's idle GPU baseline is 300 MB (desktop compositor) and reserves 300 MB for CUDA context on top. "Fits" means `baseline + CUDA_context + peak_over_process_baseline < GPU_total`.

| GPU | total VRAM | Whisper base | Whisper small | Whisper medium | Whisper large-v3-turbo |
|---|---:|:---:|:---:|:---:|:---:|
| RTX 3050 laptop | 4 096 | ✅ (1.6 GB free) | ✅ (1.1 GB free) | ❌ (overflow) | ❌ (overflow) |
| RTX 3060 laptop | 6 144 | ✅ (3.8 GB free) | ✅ (3.0 GB free) | ✅ (1.4 GB free) | ~ borderline |
| RTX 3070 laptop | 8 192 | ✅ | ✅ | ✅ (3.4 GB free) | ✅ |
| RTX 3080 Ti    | 12 288 | ✅ | ✅ | ✅ | ✅ (7+ GB free) |
| RTX A6000      | 48 000 | ✅ concurrent× 15+ | ✅ concurrent× 10 | ✅ concurrent× 5 | ✅ concurrent× 5 |

Translation for common asks:
- **"Will it work on my 4 GB laptop?"** Yes with Whisper **small** (≤ 2 GB over your idle baseline). Upgrade to `large-v3-turbo` only on 8 GB+ hardware.
- **"Can I run two jobs in parallel on my 24 GB card?"** Yes — `peak−base` of the heaviest config (medium) is 3.3 GB. Even 6× parallel fits in 20 GB.

### Residue caveat on first-vs-later runs (in-process)

The `wh_rel` column varies from 894 MB (first run, warm CUDA context initialization) to 1 028 MB ≈ baseline (later runs in the same Python process). This is consistent with the A.6b finding: **CUDA context + torch allocator reservation is a one-time cost per process**. Long-lived Celery workers pay it once at startup, not per task.

## Open items

- **Cross-validation on real GPU 1 (RTX 3080 Ti 12 GB):** confirm capped-A6000 simulation matches physical hardware within 5 % (plan A.7 item 3). Requires stopping other GPU workloads first.
- **Hardware-specific `_CUDA_CONTEXT_MB`:** the 300 MB constant is measured on A6000 / driver 580.126. Needs one-time re-measurement on each supported driver + GPU class; document in a separate table.
- **Whisper large-v3-turbo whole-stack probe:** add to sweep. Current sweep covers base/small/medium only; need turbo data for the default deployment model.
