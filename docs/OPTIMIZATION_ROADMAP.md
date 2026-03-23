# GPU Pipeline Optimization Roadmap

Discovered during performance benchmarking (March 22, 2026). Ordered by estimated impact and effort.

---

## Priority 1: High Impact, Medium Effort

### 1. Move speaker assignment + segment processing off GPU task to CPU postprocess

**What**: The GPU worker currently does 3-80s of CPU work (speaker assignment, sentence splitting, segment dedup, overlap marking, DB save) AFTER diarization completes but BEFORE releasing the GPU for the next task.

**Why it matters**: At 1,434 files, every second of GPU idle time multiplies. Average ~20s CPU work per file = 8 hours of GPU wasted across a full reprocessing run.

**Measured data**:
- 2.78hr file: 1.3s speaker assignment + 4.2s other = 5.5s GPU idle
- 4.7hr file: 80.9s speaker assignment (pre-optimization) + 5s other = 86s GPU idle
- Post-optimization (vectorized): 1.3s + 4.2s = 5.5s (fixed the worst case)

**Proposed fix**: GPU task returns raw transcription + diarization results immediately. CPU postprocess (`finalize_transcription`) handles all segment processing, speaker assignment, and DB writes.

**Risk**: Need to serialize diarization DataFrame and overlap info between stages. Data size is modest (~1-5MB per file).

**Recommendation**: **Do this.** The vectorized speaker assignment already cut the worst case from 80s to ~6s, but there's still 4-5s of GPU idle per file. At concurrent=8 with 1,434 files, that's ~2 hours of GPU time saved. The architectural boundary is also cleaner — GPU does GPU work, CPU does CPU work.

---

### 2. Separate VAD preprocessing to CPU preprocess stage

**What**: Silero VAD runs on CPU inside faster-whisper's `BatchedInferencePipeline`, blocking GPU inference start for 10-50s depending on file length. The GPU sits idle during VAD.

**Why it matters**: For a 4.7hr file, VAD takes ~50s on CPU before GPU transcription starts. With concurrent=8, all 8 files hit VAD simultaneously, slamming 48 CPU threads and keeping the GPU idle.

**Measured data**:
- 2.78hr file: ~20s VAD (hidden inside "transcription" timing)
- 4.7hr file: ~50s VAD
- GPU sits at 0% utilization during VAD phase

**Proposed fix**: Run Silero VAD in the CPU preprocess stage (stage 1). Pass VAD-segmented chunks to the GPU task. GPU starts inference immediately with no VAD delay.

**Challenge**: faster-whisper's `BatchedInferencePipeline.transcribe()` runs VAD internally. Would need to either:
1. Pre-compute VAD and pass segments to faster-whisper (may require forking faster-whisper)
2. Use Silero VAD directly and feed segments to the CTranslate2 model (bypass BatchedInferencePipeline)

**Recommendation**: **Research first, then implement.** The 10-50s per file at the beginning of each GPU task is real wasted time. At concurrent=8 with 1,434 files, this could save 5-10 hours. But it requires modifying the faster-whisper integration which is complex.

---

## Priority 2: Medium Impact, Low-Medium Effort

### 3. Add VAD dispatch jitter to prevent CPU thread stampede

**What**: When multiple files dispatch simultaneously (batch reprocessing), all hit Silero VAD at the same time, saturating all 48 CPU threads.

**Why it matters**: CPU contention during VAD could slow down individual file VAD time. The OS scheduler handles it, but cache thrashing and memory bandwidth contention are real.

**Proposed fix**: Add 1-5s random jitter to the preprocess task dispatch, or stagger file dispatches in `dispatch_batch_transcription()`.

**Recommendation**: **Easy win, do it.** Simple `time.sleep(random.uniform(0, 3))` in the preprocess task. Low risk, may improve throughput at high concurrency by 2-5%.

---

### 4. Run diarization during VAD to keep GPU utilized

**What**: Currently the pipeline runs: VAD (CPU) → Whisper (GPU) → PyAnnote (GPU). The GPU is idle during VAD. Could we start diarization (which runs on raw audio, not VAD output) while VAD runs on CPU?

**Why it matters**: Better GPU utilization, especially for long files where VAD takes 30-50s.

**Proposed fix**: Start PyAnnote diarization in a background thread immediately when the GPU task receives the audio. Meanwhile, run VAD on CPU. When both finish, run Whisper transcription on the VAD-filtered segments.

**Challenge**: This reorders the pipeline (diarization before transcription). Both results are independent — speaker assignment only happens after both complete. But it changes the VRAM profile since diarization and any concurrent Whisper tasks would overlap.

**Recommendation**: **Research but lower priority.** Only helps single-file throughput, not concurrent throughput. At concurrent=8+, the GPU is already fully utilized — overlapping VAD+diarization won't help because another file's transcription fills the GPU anyway. Best combined with item #2 (separate VAD).

---

### 5. Lazy torch import in CPU worker to avoid 1.4GB CUDA context

**What**: The CPU worker's main process creates a 1.4GB CUDA context just from `import torch` + `torch.cuda.is_available()`. With prefork concurrency=8, up to 8 children could each create their own context (11.2GB wasted).

**Why it matters**: Fixed with `PRELOAD_GPU_MODELS` env var for model loading, but the `import torch` at module level in several services still creates a CUDA context in the main process.

**Measured data**: 1,416 MiB per CPU worker main process. Stable, doesn't grow, but wasteful.

**Proposed fix**: Lazy-import torch only when actually needed. Guard all `import torch` in CPU worker services behind function-level imports rather than module-level.

**Recommendation**: **Low priority.** The 1.4GB is stable and the `PRELOAD_GPU_MODELS` fix prevents the 15-44GB leak. This is a cleanliness improvement, not a performance fix. Do it when touching these files for other reasons.

---

## Priority 3: Future Architecture

### 6. Per-task VRAM cleanup without disrupting concurrent tasks

**What**: After concurrent=10, PyTorch's CUDA allocator caches ~48GB of freed memory. `torch.cuda.empty_cache()` is process-wide — calling it would disrupt other concurrent tasks.

**Why it matters**: Cached memory prevents other applications (LLM, TTS) from using the GPU after a batch processing run.

**Proposed fix**:
1. Atomic counter tracking active GPU tasks — call `empty_cache()` only when count reaches 0
2. PyTorch 2.x `MemoryPool` for per-thread scoping (newer feature, may not be stable)
3. Periodic cleanup via Celery beat (every 5 min, only when GPU queue is empty)

**Recommendation**: **Implement option 1 (atomic counter).** Simple, safe, and handles the common case. When the last concurrent task finishes, clear the cache. If another task starts before cleanup, it reuses the cached memory anyway.

---

### 7. NVIDIA Triton Inference Server for dynamic batching

**What**: At high concurrency (10+), multiple threads each run independent batch_size=32 GPU inference, competing for SMs. Triton would consolidate all requests into optimal batches.

**Why it matters**: Could improve throughput at concurrent=10+ by 20-60% by eliminating SM contention and reducing kernel launch overhead.

**Measured data**: Throughput plateaus at 52-55x for concurrent=6-12. Triton's dynamic batching could push this higher.

**Proposed fix**: See `docs/TRITON_INFERENCE_RESEARCH.md` for full analysis. Phase 1: PyAnnote embeddings via Triton (biggest win, easiest). Phase 2: Evaluate TensorRT for Whisper. Phase 3: Full Triton pipeline.

**Recommendation**: **Future major feature.** Not needed now — the thread-based model works well up to concurrent=12 with perfect linear scaling. Triton adds infrastructure complexity. Evaluate when processing consistently exceeds 10 concurrent files or when multi-GPU coordination is needed.

---

## Already Fixed During Benchmarking

| Issue | Fix | Impact |
|-------|-----|--------|
| Speaker assignment O(n) Python loop | Vectorized numpy matmul in `speaker_assigner.py` | 80s → 6s for 4.7hr files (13x) |
| TF32 disabled after diarization | Re-enable in `pipeline.py` + `celery.py` | ~15-20% on Ampere+ |
| Batch_size auto-divided by concurrency | Removed division in `config.py` + `diarizer.py` | 49.2x → 54.6x throughput |
| CPU worker loaded GPU models at startup | `PRELOAD_GPU_MODELS=true` env var | 15GB → 0 GPU leak |
| Speaker clustering used GPU for small matrices | CPU threshold (n>=500) in `speaker_clustering_service.py` | 44GB → 0 GPU leak |
| Gender model loaded on GPU in CPU worker | `PRELOAD_GPU_MODELS` gate in `speaker_attribute_service.py` | 5.7GB → 0 GPU leak |
| Class-level `torch.device("cuda")` | `PRELOAD_GPU_MODELS` gate in `optimized_embedding_service.py`, `similarity_service.py` | CUDA context prevention |
| Segment index btree overflow | Alembic migration v353: `md5(text)` functional index | Fixed for segments >2704 bytes |
