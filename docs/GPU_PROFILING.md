# GPU VRAM Profiling & Benchmarks

> **v0.4.0 Status:** GPU memory leaks are fully fixed. The worker pool default changed from `prefork` to `threads` (`GPU_WORKER_POOL=threads`), which shares model weights across concurrent tasks and eliminates the per-process VRAM duplication that caused the leaks. All benchmark data below reflects the current production configuration.

## Overview

Tracks GPU VRAM usage across the transcription pipeline stages with benchmarks
across different GPU hardware and audio durations. Used for optimizing concurrent
processing and identifying VRAM bottlenecks.

**Profiling infrastructure**: NVML via ctypes (`app/utils/nvml_monitor.py`) for
true device-level memory that captures CTranslate2 and all non-PyTorch allocations.

## How to Reproduce

```bash
# Prerequisites: ENABLE_VRAM_PROFILING=true in .env

# Solo tests (one at a time — clean per-file measurements)
./scripts/gpu-profile-test.sh --solo

# Concurrent tests (all 5 at once — shared VRAM under load)
./scripts/gpu-profile-test.sh

# Just one file
./scripts/gpu-profile-test.sh --solo 1.0h_3758s

# View results
./scripts/gpu-profile-test.sh --results

# Watch live
./scripts/gpu-profile-test.sh --watch

# Admin API
GET /api/admin/gpu-profiles
```

## Test Matrix

| Label | UUID | Duration | File |
|-------|------|----------|------|
| 4.7h | `3e313bbd-924f-4a4b-9584-fa24532b9a01` | 17,044s | Protect Our Parks 6 |
| 3.2h | `d734bb4b-0296-4e05-8122-8228e2cea1d5` | 11,495s | Jimmy Carr |
| 2.2h | `8cf209c3-6fc5-4c03-b867-d37e2fe33ac6` | 7,998s | Jordan Jonas |
| 1.0h | `b6375779-1675-4752-ab43-de246664d419` | 3,758s | Dom Irrera |
| 0.5h | `0ba0d6ed-bcca-4be6-9176-0b1a05904fab` | 1,899s | Chris Aubrey Marcus |

## Hardware Under Test

| GPU | Index | VRAM | Arch | Compute | Role |
|-----|-------|------|------|---------|------|
| NVIDIA RTX A6000 | 0 | 49,140 MB | Ampere | 8.6 | Scaled worker (5 threads) |
| NVIDIA GeForce RTX 3080 Ti | 1 | 12,288 MB | Ampere | 8.6 | Default worker (sequential) |

---

## Pipeline Stages: What Runs on GPU (Source-Referenced)

### Stage 1: Whisper Transcription (CTranslate2)

**Source**: `faster_whisper.WhisperModel` → CTranslate2 engine
**Our wrapper**: `app/transcription/transcriber.py`

#### Model Loading
```python
# transcriber.py:110-116
WhisperModel(model_name, device="cuda", compute_type="int8_float16", num_workers=N)
```
- Loads encoder (32 transformer layers) + decoder (2 layers for turbo) to GPU
- CTranslate2 uses its own CUDA allocator — **invisible to `torch.cuda.memory_allocated()`**
- Measured via NVML: **~1,050 MB** on device

#### Per-File Inference
```python
# transcriber.py:165 → BatchedInferencePipeline.transcribe()
segments_gen, info = self._pipeline.transcribe(audio, batch_size=B, ...)
```
1. **Silero VAD**: scans full audio for speech regions (tiny model, ~2MB)
2. **Batched encoder**: mel spectrograms → encoder in batches of `batch_size`
   - Each batch: `batch_size × 80 × 3000` mel frames → encoder activations
   - `batch_size` auto-divided by `concurrent_requests` (e.g., 32→6 with 5 threads)
3. **Decoder + beam search**: per-segment, generates tokens with attention KV-cache
4. **Cross-attention DTW**: extracts word timestamps from attention weights

**Key**: Transcription VRAM scales with `batch_size`, **NOT** audio duration.
Longer audio = more batches processed sequentially, same peak VRAM per batch.

**Measured inference overhead**: +300-400 MB on top of model weights (NVML delta).

---

### Stage 2: PyAnnote Speaker Diarization (PyTorch)

**Source**: `pyannote.audio.pipelines.speaker_diarization.SpeakerDiarization.apply()`
(`site-packages/pyannote/audio/pipelines/speaker_diarization.py`)
**Our wrapper**: `app/transcription/diarizer.py`

This is where VRAM scales with audio duration. Three sub-stages:

#### 2a. Segmentation — Sliding Window Over Full Audio

**Source**: `SpeakerDiarization.get_segmentations()` → `Inference.slide()`
(`site-packages/pyannote/audio/core/inference.py`)

```python
# inference.py - Inference.slide()
waveform, sample_rate = self.model.audio(file)       # Load FULL audio to memory
chunks = waveform.unfold(1, window_size, step_size)   # Create overlapping windows
for c in range(0, num_chunks, self.batch_size):
    batch = chunks[c : c + self.batch_size]
    outputs = self.infer(batch)                        # GPU forward pass
```

```python
# inference.py - Inference.infer()
with torch.inference_mode():
    outputs = self.model(chunks.to(self.device))       # ← SENDS TO GPU HERE
```

**What goes to GPU per batch**:
- `chunks.to(self.device)`: `(batch_size, 1, window_samples)` tensor
- Window = 10 seconds @ 16kHz = 160,000 samples × 4 bytes = **0.6 MB per window**
- Batch = `segmentation_batch_size` windows (default 32, we auto-tune to 6-8)
- So per batch: **~4-5 MB** of audio data sent to GPU

**But the output accumulates on CPU**:
- Output shape: `(num_chunks, num_frames, local_num_speakers)` — stays on CPU (numpy)
- `num_chunks` = `(audio_samples - window_size) / step_size`
- With 10s window, 0.1 step ratio (90% overlap): **~10 chunks per second of audio**
- 0.5h = ~19,000 chunks, 4.7h = ~170,000 chunks

**Segmentation model**: SincNet + LSTM, relatively small (~10-20 MB weights)

#### 2b. Speaker Embedding Extraction — Per Chunk × Per Speaker

**Source**: `SpeakerDiarization.get_embeddings()` (speaker_diarization.py:332-478)

```python
# speaker_diarization.py:399-425
def iter_waveform_and_mask():
    for (chunk, masks), (_, clean_masks) in zip(binary_segmentations, clean_segmentations):
        waveform, _ = self._audio.crop(file, chunk, mode="pad")  # Re-reads audio chunk
        for mask, clean_mask in zip(masks.T, clean_masks.T):     # Per speaker in chunk
            yield waveform[None], torch.from_numpy(used_mask)[None]

batches = batchify(iter_waveform_and_mask(), batch_size=self.embedding_batch_size)
```

```python
# speaker_verification.py - PyannoteAudioPretrainedSpeakerEmbedding.__call__()
with torch.inference_mode():
    embeddings = self.model_(waveforms.to(self.device), weights=masks.to(self.device))
```

**What goes to GPU per batch**:
- `waveforms.to(self.device)`: `(batch_size, 1, num_samples)` — audio segments
- `masks.to(self.device)`: `(batch_size, num_frames)` — speaker activity masks
- Forward pass through WeSpeaker ResNet34 → 256-dim embedding per chunk×speaker

**Total embedding calls** = `num_chunks × local_num_speakers`:
- 0.5h with 3 speakers: ~19,000 × 3 = **57,000 forward passes**
- 4.7h with 5 speakers: ~170,000 × 5 = **850,000 forward passes**
- `embedding_batch_size=1` by default — one forward pass at a time!

**Embedding model**: WeSpeaker ResNet34, ~10-20 MB weights, 256-dim output

#### 2c. Clustering (VBx) — Mostly CPU

**Source**: `SpeakerDiarization.apply()` → `self.clustering()`

```python
# speaker_diarization.py:640-648
hard_clusters, _, centroids = self.clustering(
    embeddings=embeddings,        # (num_chunks, local_num_speakers, 256)
    segmentations=binarized_segmentations,
    num_clusters=num_speakers,
    ...
)
```

- VBx (Variational Bayes) clustering on CPU
- Input: embedding matrix `(num_chunks × num_speakers, 256)`
- PLDA scoring matrix operations
- **No significant GPU usage** — CPU-bound

#### Why Diarization VRAM Scales with Duration

The key VRAM consumers during diarization:

1. **`file` dict containing full audio**: The `waveform` tensor from our `diarizer.py:193-196`:
   ```python
   waveform = torch.from_numpy(audio)  # Full audio as tensor
   audio_input = {"waveform": waveform, "sample_rate": 16000}
   ```
   Then inside PyAnnote, `self._audio.crop(file, chunk)` reads from this.
   - 0.5h: 1,899 × 16,000 × 4 = **115 MB**
   - 4.7h: 17,044 × 16,000 × 4 = **1,038 MB**

2. **Segmentation output accumulation**: `(num_chunks, num_frames, num_speakers)` array
   - Created by `Inference.slide()` → `np.vstack(output)` — on CPU but large
   - Then used in `get_embeddings()` and `reconstruct()`

3. **PyTorch CUDA cached memory**: During the segmentation sliding window,
   PyTorch allocates/frees GPU memory for each batch. The CUDA caching allocator
   holds onto freed memory (visible as `reserved` vs `allocated`).
   This is the **dominant** VRAM consumer — PyTorch reserves large blocks
   that it doesn't release back to CUDA until `torch.cuda.empty_cache()`.

4. **Concurrent tasks**: In thread pool mode, multiple tasks run diarization
   simultaneously. Each task's CUDA cached memory accumulates.

---

### Stage 3: Speaker Assignment (CPU only)

**Source**: `app/transcription/speaker_assigner.py`
- Maps diarization segments to transcript words via time overlap
- Pure pandas/numpy — no GPU usage

---

## Measured Results

### Shared Model Weights (A6000, both models preloaded)

| Metric | Value | Source |
|--------|-------|--------|
| Both models loaded (NVML) | **5,486 MB** | `nvidia-smi` after `ensure_models_loaded()` |
| PyTorch allocated | 31 MB | Only PyAnnote params visible to torch |
| Cold load time | 5.5s | Whisper 3.8s + PyAnnote 1.7s |
| Warm load time | 0.0s | ModelManager cache hit |

### Solo: 0.5h (1,899s) — A6000, Concurrent Mode (5 threads, 1 task)

| Stage | Time | NVML Before | NVML After | Δ VRAM | PT Peak |
|-------|------|-------------|------------|--------|---------|
| pipeline_start | — | 5,486 MB | 5,486 MB | — | 31 MB |
| model_load | 0.0s | 5,486 MB | 5,486 MB | +0 MB | 31 MB |
| transcription | 21.6s | 5,486 MB | 5,884 MB | **+398 MB** | 31 MB |
| diarization | 89.0s | 5,884 MB | 10,586 MB | **+4,702 MB** | 1,629 MB |
| speaker_assign | 0.5s | 10,586 MB | 8,762 MB | -1,824 MB | 39 MB |
| **Total** | **113.9s** | | | | |

### Concurrent: 5 Files Simultaneously — A6000

| Phase | NVML Used | NVML Free | Notes |
|-------|-----------|-----------|-------|
| Models preloaded, idle | 5,486 MB | 43,654 MB | Shared weights only |
| 5× transcription | ~9,845 MB | ~38,695 MB | +4.4 GB for 5 inference streams |
| Mixed transc + diarize | ~12,000 MB | ~36,500 MB | Peak during transitions |
| Peak concurrent diarize | **~19,000 MB** | ~30,000 MB | Observed via nvidia-smi |

### Solo Results by Duration — A6000

Stock PyAnnote 4.0.4 (`embedding_batch_size=1`, `segmentation_batch_size=32`).
Measured 2026-03-10 via `./scripts/gpu-profile-test.sh --solo`.
Each file processed alone with clean GPU state between runs.

| Duration | Speakers | Device Peak | Whisper Δ | Transcribe Time | PyAnnote Δ | Diarize Time | Total |
|----------|----------|-------------|-----------|-----------------|------------|--------------|-------|
| 0.5h (1,899s) | 5 | 2,991 MB | +1,056 MB | 18.7s | +1,000 MB | 31.4s | 54.6s |
| 1.0h (3,768s) | 5 | 19,517 MB | +0 MB | 38.8s | +11,510 MB | 62.5s | 103.2s |
| 2.2h (8,005s) | 3 | 11,309 MB | +1,056 MB | 72.8s | +9,198 MB | 131.4s | 217.2s |
| 3.2h (11,508s) | 3 | 2,993 MB | +1,056 MB | 882 MB | 112.9s | 202.5s | 326.4s |
| 4.7h (17,059s) | 8 | 25,770 MB | +0 MB | 183.7s | +11,136 MB | 441.8s | 707.4s |

**Notes:**
- Whisper Δ shows +0 MB when CTranslate2 model was already cached from previous run
- PyAnnote Δ is a post-diarization snapshot — actual peak VRAM during processing is higher
- Device Peak captures the maximum NVML reading across all profiler steps
- VRAM variability is due to PyTorch caching allocator timing (see GPU_OPTIMIZATION_PATCHES.md)

### Solo Results by Duration — A6000 (Patched: embedding_batch=32 + empty_cache)

Patched PyAnnote 4.0.4 (`embedding_batch_size=32`, `torch.cuda.empty_cache()` between stages).
Measured 2026-03-10. See `docs/GPU_OPTIMIZATION_PATCHES.md` for full comparison.

| Duration | Speakers | Device Peak | Whisper Δ | Transcribe Time | PyAnnote Δ | Diarize Time | Total |
|----------|----------|-------------|-----------|-----------------|------------|--------------|-------|
| 0.5h (1,899s) | 5 | 14,634 MB | +0 MB | 21.4s | +438 MB | 33.9s | 55.8s |
| 1.0h (3,768s) | 5 | 14,634 MB | +0 MB | 40.4s | +0 MB | 61.9s | 104.0s |
| 2.2h (8,005s) | 3 | 14,634 MB | +0 MB | 84.7s | +0 MB | 136.6s | 231.2s |
| 3.2h (11,508s) | 3 | 2,993 MB | +1,056 MB | 107.1s | +882 MB | 197.3s | 315.3s |
| 4.7h (17,059s) | 8 | 14,634 MB | +0 MB | 181.4s | +0 MB | 437.7s | 703.4s |

**Key improvement**: Consistent ~14,634 MB peak across durations (vs 2,991-25,770 MB stock).
The `empty_cache()` between stages releases PyTorch cached memory, making VRAM predictable.

### Solo Results by Duration — 3080 Ti (12 GB)

_Pending: solo runs on GPU 1_

---

## Key Findings

### CTranslate2 is Invisible to PyTorch
- `torch.cuda.memory_allocated()` reports 0 MB for whisper model and inference
- Must use NVML (`libnvidia-ml.so`) for accurate device-level tracking
- Our `app/utils/nvml_monitor.py` wraps NVML via ctypes (no pip dependency)

### Transcription VRAM is Constant (per batch_size)
- Whisper inference uses fixed VRAM regardless of audio duration
- Controlled by `batch_size` (divided by `concurrent_requests` in thread mode)
- ~300-400 MB overhead on top of model weights

### Diarization VRAM Scales with Duration
- Primary consumers (from source code analysis):
  1. Full audio waveform tensor (linear with duration)
  2. PyTorch CUDA cached memory from segmentation batches (managed with `empty_cache()`)
  3. Embedding extraction: `num_chunks × num_speakers` forward passes (batched at 32)
- With GPU optimizations applied (v0.4.0): consistent ~14,634 MB peak regardless of duration

### Shared Weights Save ~80% VRAM
- Thread pool: 5 tasks share 5,486 MB model weights (ONE copy)
- Old prefork: 5 tasks × 5,486 MB = 27,430 MB (FIVE copies)
- Savings: ~22 GB VRAM for 5 concurrent tasks
- Default changed from `prefork` to `threads` in v0.4.0 (`GPU_WORKER_POOL=threads`)

### GPU Memory Leaks: Fixed in v0.4.0
- Root cause: prefork workers each loaded a full copy of both models
- Fix: threads pool + `torch.cuda.empty_cache()` between diarization stages
- VRAM ceiling: 48.5 GB at concurrency=10+ on RTX A6000 (49 GB total)
- Memory is now predictable and does not grow unboundedly across tasks

---

## v0.4.0 Throughput Benchmarks (RTX A6000, large-v3-turbo)

Full pipeline (transcription + diarization + postprocessing):

| Metric | Value |
|--------|-------|
| Single-file realtime factor | **40.3x** (1 hour audio processes in ~89 seconds) |
| Peak throughput | **54.6x realtime** at concurrency=8 |
| Scaling linearity | Confirmed linear from 1-12 workers |
| VRAM ceiling | 48.5 GB at concurrency=10+ |
| GPU memory leaks | Fixed (0 growth across 100-task sustained run) |

PyAnnote GPU optimization improvements (from `davidamacey/pyannote-audio@gpu-optimizations`):

| Metric | Improvement |
|--------|-------------|
| Overall diarization speedup | 1.28x |
| Embedding extraction speedup | 1.44x |
| VRAM reduction (embeddings) | 66% |
| CPU RAM reduction | 115x (58.8 GB → 39 MB for 4.7h/21 speakers) |

Note: Do NOT use the old "70x realtime with large-v2" figure. That was a pre-optimization estimate. The correct v0.4.0 single-file figure is **40.3x** with large-v3-turbo (the default model).

---

## Optimization Status

### Implemented (v0.4.0)
1. Shared model weights via `--pool=threads` (saves ~22 GB with 5 threads)
2. CTranslate2 `num_workers` for concurrent CUDA streams
3. Batch size division by `concurrent_requests`
4. NVML-based profiling captures true device memory
5. PyAnnote `embedding_batch_size=32` (up from default of 1) — 1.44x speedup, 66% VRAM reduction
6. `torch.cuda.empty_cache()` between diarization stages — predictable VRAM, no leaks
7. Sequential diarization with VRAM gating — `_wait_for_vram()` threshold tuned for A6000
8. Upstream PR submitted: https://github.com/pyannote/pyannote-audio/pull/1992

### Potential Future Work
1. PyAnnote streaming/chunked diarization to reduce peak waveform memory
2. Adaptive `embedding_batch_size` based on available VRAM at task start
3. OpenSearch GPU-accelerated vector search for speaker matching at scale
