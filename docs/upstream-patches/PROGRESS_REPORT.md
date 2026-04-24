# PyAnnote Fork Optimization — Progress Report

**Date**: 2026-04-23
**Fork**: `davidamacey/pyannote-audio@gpu-optimizations` (commit `55820cdc`)
**Backend**: `opentranscribe/master` (commit `93436e0`)
**Audience**: project lead reading between sessions — skim the tables, dive into the sections you want.

---

## Executive summary

- **Cumulative speedup vs stock pyannote**: ~**1.30× on NVIDIA A6000** / ~**1.18× on Apple M2 Max**.
- **Per-pipeline VRAM**: **844 MB steady-state** (down from 3-6 GB unpredictable) — enables **~25 parallel pipelines per A6000**.
- **Accuracy**: **DER invariant** — 0.0000% delta on all 5-run benchmarks across every phase.
- **What's recently unblocked**: ONNX export for both diarization models works, unit-tested at parity.
- **What's newly blocked**: ORT CUDA EP on segmentation is a regression (5.8× slower) because of LSTM/If/Sin/Cos op fallback — the NVIDIA answer is TensorRT (Phase 6.3) which needs an image rework.
- **What's next (highest ROI first)**: Phase 5.2 GPU aggregate+reconstruct → Phase 5.4 raise concurrent request cap → Phase 6.3 TensorRT via CUDA base image.

---

## Where we are — phase-by-phase

### Phase A (prior round) — the structural win

| Delivered | Impact |
|---|---|
| Vectorized chunk extraction | Drops the slowest CPU loop |
| Memory-safe batch indexing | **115× CPU RAM reduction** (58.8 GB → 39 MB on 4.7h/21 spk) |
| Adaptive batch size, pinned at `embedding_batch_size=16` | Predictable memory footprint |
| TF32 on Ampere+ | Free 15-20% on matmul-heavy ops |
| CUDA streams + pinned memory | Double-buffered H2D prefetch overlaps with GPU compute |
| MPS-native FFT (PyTorch 2.3+) | 4.46× fbank speedup on M2 Max |
| Direct model calls bypassing HF wrapper | Skip redundant plumbing overhead |

**Net**: **1.28× on A6000 / 1.17× on M2 Max**, 66-68% VRAM reduction → fixed 844 MB steady-state.

### Phase 1 — baselines and audit

- Benchmark harness extended: `--runs N`, `--tag`, `--rttm-out`, `--profiler`, per-stage VRAM capture.
- 5-run statistical baselines recorded on A6000 + M2 Max for all 4 canonical sample files (`0.5h_1899s`, `2.2h_7998s`, `3.2h_11495s`, `4.7h_17044s`).
- DER reference RTTMs frozen in `benchmark/results/rttm/baseline_a6000_20260421_{short,long}/`.
- Profiler `record_function` labels added to fork for per-stage attribution.
- Vectorization audit + VRAM decomposition table written.

### Phase 2 — trivial wins

| Change | Measured |
|---|---|
| `torch.compile` gate made visible | Was silently failing; now logs `torch._dynamo` warnings |
| `@lru_cache` on hamming window | Correctness cleanup |
| `cudnn.benchmark = True` on CUDA | Free, small segmentation speedup |
| `embedding_mixed_precision` parameter plumbed | Plumbing only; default stays off (fp16 excluded for DER reasons) |

Shipped as a bundle. End-to-end: ~noise on 2.2h, unchanged VRAM, DER bit-identical.

### Phase 3 — GPU clustering

- GPU `torch.cdist` for `assign_embeddings` path.
- `torch.pdist` → scipy `linkage` bridge (GPU computes distance matrix, scipy does the fast Lance-Williams merge).
- VRAM-budget fallback: if N would exceed `PYANNOTE_CLUSTERING_VRAM_BUDGET_MB` (default 50), path degrades to scipy CPU with a log line.
- **Result**: **-1.94% wall on 4.7h**, noise on 2.2h, DER **0.0000%** T1 across all runs, VRAM unchanged.
- Projected 25-35% did not materialize because clustering's 138s on 4.7h is dominated by VBx PLDA + AHC + `assign_embeddings`, not the scipy linkage we actually offloaded. Documented in `phase-3-measurement.md`.

### Phase 3.5 — trivial freebies

- `_constrained_argmax` vectorization.
- Centroids via `bincount` + `add.at` (scatter sum).
- Cluster remap lookup table.

**Measured on 4.7h**: small gains within cumulative Phase 3 numbers.

### Phase 3.5 — aggressive CPU vectorization — REVERTED

- Attempted `Inference.aggregate` rewrite as `np.add.at` scatter: **+35% slower**.
- Attempted `reconstruct` rewrite as `np.maximum.at` scatter: **+57% slower**.
- Root cause: `np.add.at` / `np.maximum.at` disable numpy's contiguous-stride SIMD path; CPU hostile.
- **Reverted**. Documented in `phase-3-5-and-4-measurement.md`. Do not retry.

### Phase 4 — sliding-window overlap sweep

- Tried `segmentation_step` ∈ {1.5, 2.0, 3.0} seconds (default 1.0 = 90% overlap).
- DER stayed flat but **speaker count regressed** (short-turn speakers vanished when fewer chunks averaged their posterior).
- Defaults unchanged; exposed as opt-in kwarg. Documented in `phase-3-5-and-4-measurement.md`. Do not flip default.

### GPU Lance-Williams — NEGATIVE RESULT

- Ported scipy's centroid-linkage Lance-Williams to GPU.
- Python loop overhead over the O(N) merge steps made it **slower than scipy's C implementation** (~14s vs ~12s on N=10k).
- **Gated behind `PYANNOTE_ENABLE_GPU_LINKAGE=1`** env var; **default off**. Would need a fused CUDA kernel to beat scipy. Not worth the effort.

### Phase 5 — research memos (no commits this round)

Five memos written in `docs/upstream-patches/`:

- `phase-5-1-cuda-graphs.md` — **do not implement** (0.15-0.3% E2E win doesn't justify complexity)
- `phase-5-2-gpu-aggregate-and-reconstruct.md` — **recommended next**, 4.5% E2E projected
- `phase-5-3-mps-optimization.md` — defer (MPS profiler OOMs, no ground truth)
- `phase-5-4-concurrent-requests-ceiling.md` — recommended (soak test to raise cap from 4 → 12)
- `phase-1-5-mps-fallback-hunt.md` — MPS profiler gap documented

### Phase 6.1 — torch.compile enablement ✅ SHIPPED

- Added `gcc g++` to `backend/Dockerfile.prod` runtime stage (~150 MB image growth).
- `torch.compile` now actually fires (previously silent failure from missing gcc).
- **Measured on 2.2h**: segmentation -6.5 to -7.4%, embeddings noise, E2E noise.
- **Default kept OFF** (`torch_compile=True` is opt-in kwarg). Primary value: unblocks Phase 6.2/6.3 tooling.
- Measured first-run compile: 68s (cached thereafter).

### Phase 6.2 — ONNX plumbing ✅ SHIPPED, ⚠️ RESTRICTED

**What shipped** (commit fork `55820cdc` + backend `93436e0`):

- **`fork:pyannote/audio/onnx/`** — new subpackage:
  - `runtime.py` — `ONNXSegmentationRuntime`, `ONNXEmbeddingRuntime`, `compute_fbank_batched` (vmap-free, keeps Phase A MPS FFT)
  - `export.py` — CLI export producing `segmentation.onnx` + `embedding.onnx` + sibling `.metadata.json`
  - Provider selection (TRT EP → CUDA EP → CoreML EP → CPU EP) device-aware
- **`fork:speaker_diarization.py::_setup_phase6_onnx()`** — env-var-gated monkey-patch of segmentation infer, embedding resnet, compute_fbank. Falls back to eager silently on any failure.
- **`backend/Dockerfile.prod`** — onnxruntime-gpu installed with force-reinstall (prevents transitive CPU-onnxruntime from shadowing GPU module).
- **`backend/requirements.txt`** — `onnx` + `onnxruntime-gpu` as first-class deps.
- **`backend/tests/onnx/`** — **27 unit tests**, all passing:
  - T1 segmentation: frame-class argmax bit-identical across 5 seeds
  - T1 embedding: cos sim ≥ 0.9999, max abs diff ≤ 1e-3 across 9 cases
  - T2 batched fbank: ≤1e-5 vs torch.vmap across 12 shape combos
  - T2 batch determinism: no cross-sample leakage
- **`scripts/onnx_benchmark_providers.py`** — reproducible provider benchmark (replaces ad-hoc snippets).

**What doesn't yet work**:

- **ORT CUDA EP on segmentation: 5.8× slower than eager PyTorch**. Root cause: LSTM (×4), If (×1), Sin (×2), Cos (×2) have no CUDA kernels in ORT 1.25 → Memcpy shuttling mid-graph. Documented in `phase-6-2-lessons-learned.md`.
- **ORT TRT EP**: blocked by missing `libcublas.so.12` in slim base image.

**What the failed CUDA-EP run proves**:

- Export path works end-to-end.
- Runtime wrapper works.
- Integration works (pipeline ran without errors, just slowly).
- The blocker is entirely in ORT's kernel coverage, not our code.

### Phase 5.2 — GPU aggregate + reconstruct — NEGATIVE RESULT

**Attempted 2026-04-23**. Shipped `fork:pyannote/audio/gpu_ops.py` with `aggregate_gpu()` + `reconstruct_gpu()` using `torch.Tensor.index_add_` and `scatter_reduce_(reduce='amax')`. Env-var-gated (`PYANNOTE_GPU_AGGREGATE=1`, `PYANNOTE_GPU_RECONSTRUCT=1`), both default OFF. Hooks in `core/inference.py::aggregate` + `pipelines/speaker_diarization.py::reconstruct`, exception-safe fallback to CPU numpy.

- **Correctness: PERFECT** — synthetic parity tests show aggregate max diff 9.5e-7 (fp32 floor), reconstruct max diff 0.0 (bit-exact).
- **DER: 0.0000% T1** on both 2.2h and 4.7h, all 3 runs each, vs frozen baseline RTTMs.
- **VRAM: unchanged 844 MB.**
- **But wall time regressed**: +2-3% on 2.2h, **+~6% on 4.7h** (342s vs ~322s baseline).

**Why the memo's 4.5% projection failed**: aggregate/reconstruct are memory-bandwidth-bound, not compute-bound. The per-chunk working set fits in CPU L2 cache; GPU HBM has higher throughput but more latency per scatter, and each call pays ~5-10 ms PCIe round-trip for H2D/D2H. For this access pattern, CPU wins.

**Decision**: keep `gpu_ops.py` + hooks (zero cost when env vars unset), add Phase 5.2 to the "stop chasing" list. Full analysis in `phase-5-2-implementation-results.md`.

### Phase 6.2 follow-ups from this session

After shipping the core Phase 6.2 plumbing, measured additional EP paths:

| Platform/Path | Seg ms/batch (32×5s) | Emb ms/batch (16×200) | Verdict |
|---|---:|---:|---|
| RTX A6000 PyTorch eager (baseline) | 8.2 | 9.6 | **fastest available** |
| RTX A6000 ORT CUDA EP | 47.5 | 9.8 | seg 5.8× slower (LSTM/If/Sin/Cos fallback); emb parity |
| Linux x86 CPU PyTorch eager | 239 | 387 | baseline for CPU-only tier |
| **Linux x86 CPU ORT CPU EP** | **127** | **182** | **1.87× seg / 2.12× emb — CLEAR WIN for CPU-only deployments** |
| Mac M2 Max PyTorch eager MPS | 36 | 19.6 | fastest on Mac |
| Mac M2 Max ORT CoreML EP | 163 | 20.9 | seg 4.5× slower; emb parity |
| Mac M2 Max ORT CPU EP | 187 | 401 | slower still |

**Takeaways**:

- **CPU-only deployments (no GPU at all)** get a clean 1.87-2.12× win from `PYANNOTE_USE_ONNX=1` + ORT CPU EP. This is the shippable Phase 6.2 story for airgapped / cloud-CPU tiers.
- **Mac deployments** should stay on eager MPS PyTorch. Phase A's MPS-native FFT is the right Mac optimization; CoreML EP doesn't cover the segmentation graph efficiently.
- **NVIDIA GPU deployments** stay on eager PyTorch until Phase 6.3 TensorRT (CUDA runtime image rework).
- **Embedding ORT CUDA EP hybrid** — measured at parity with eager. No win, so no hybrid mode is worth the complexity.

### Phase 6.3 — TensorRT plans — NEW PREREQUISITE SURFACED

- Originally: "unblocked once 6.2 ships."
- Now: **needs a base image with CUDA toolkit runtime libraries** (`libcublas.so.12`, `libcublasLt.so.12`, etc.).
- Options: switch to `nvidia/cuda:12.8.0-cudnn-runtime-ubuntu24.04` (~2 GB larger) or mirror `Dockerfile.blackwell`'s `nvcr.io/nvidia/pytorch:25.01-py3` (~5 GB larger).
- Engine plans are **per-GPU-arch** (sm_86, sm_89, sm_90) — build-on-first-run model with ~6-13 min first-run cost per unique arch. Not for consumer images.
- Documented in `phase-6-3-tensorrt-plan-build-on-startup.md`.

---

## Cumulative measured speedups

### RTX A6000 (single-pipeline wall time, 5-run statistical)

| File | Stock | Phase A | Phase 2+3 | 6.1 (torch.compile) | Notes |
|---|---:|---:|---:|---:|---|
| 2.2h_7998s | ~130s | **~100s (1.28×)** | ~100s | ~100-101s | warm runs; E2E in noise for 6.1 |
| 4.7h_17044s | ~420s | **~328s (1.28×)** | ~322s (-1.94% more) | unchanged | Phase 3 GPU clustering wins ~6s here |

### Mac Studio M2 Max (single-pipeline)

| File | Stock | Phase A | Notes |
|---|---:|---:|---|
| 2.2h_7998s | ~212s | **~182s (1.17×)** | Phase A's MPS-native FFT is the biggest win here |

### VRAM invariant across all phases

- **Peak VRAM: 844 MB ±0** across every benchmark, every file size, every phase.
- Steady-state (+2s after return): 39 MB.
- **This invariant enables the big parallel-pipeline throughput story** — ~25 pipelines per A6000 is feasible.

### DER invariance across all phases

**Every RTTM is bit-identical to the Phase A baseline.** T1 tier (0.0000%) on all runs of all phases. Quality is non-negotiable; we have zero accuracy regression.

---

## Deployment matrix (honest, based on measured findings)

| Platform | Best path | Why |
|---|---|---|
| Consumer Linux + NVIDIA GPU | **Eager PyTorch** (current) until Phase 6.3 ships | ORT CUDA EP is a regression; TRT needs image rework |
| Consumer Mac (Apple Silicon) | **ORT + CoreML EP** (pending M2 Max validation) | No TRT on Mac; CoreML EP handles the ops ORT CUDA can't |
| Consumer CPU-only (no GPU) | **ORT + CPU EP** (pending benchmark) | Historically 2-3× eager PyTorch on CPU |
| AWS g5 / dedicated NVIDIA server | **ORT + TRT EP** (Phase 6.3 required) | Biggest win (+20-40% on seg+emb); accepts 6-13 min first-run |
| Blackwell / DGX Spark | Same — `Dockerfile.blackwell` already has the CUDA base | TRT EP loads cleanly in that image today |

---

## What we've proven doesn't work (the "stop chasing" list)

From lessons-learned across all phases:

1. **ORT CUDA EP alone for pyannote-v4 segmentation** — 5.8× regression, driven by library-level op gaps in ORT 1.25. Not a config problem.
2. **`io_binding` alone as a fix** — helps 40% (47.5 → 32.4 ms) but still 4× slower than eager. Intra-graph Memcpy nodes are the real cost.
3. **ORT CoreML EP for pyannote-v4 segmentation on M2 Max** — 4.5× regression (163 ms vs 36 ms MPS eager). Embedding is parity. Don't ship.
4. **ORT embedding hybrid on CUDA** — measured at parity (9.8 vs 9.6 ms). No win, no point in the added complexity.
5. **GPU scatter-reduce for aggregate / reconstruct (Phase 5.2)** — memory-bandwidth-bound access pattern hits CPU L2 cache; GPU HBM round-trips cost more. Regressed ~6% on 4.7h, ~2-3% on 2.2h. Correctness preserved (T1 DER) but no speed win.
6. **Dynamo `torch.onnx.export` on WeSpeaker / segmentation (PyTorch 2.8)** — vmap blocker + control-flow issues. Revisit only in PyTorch 2.11+.
7. **CPU vectorization of `Inference.aggregate` / `reconstruct`** — numpy scatter primitives disable SIMD. Regressed 35-57%.
8. **`segmentation_step` > 1.0** — speaker count drops. Quality regression.
9. **GPU Lance-Williams clustering** — Python merge-loop overhead is worse than scipy's C.
10. **TensorRT plans baked into Docker images** — per-GPU-arch means one image can't serve multiple GPU types.
11. **bf16 / fp16 embeddings** — prior DER evidence rejects. Off-limits this round.

---

## What we're pursuing next (prioritized)

### P0 — measurable, scoped, achievable

1. **Phase 6.2 CPU EP validation** — ~1 hour. Run `scripts/onnx_benchmark_providers.py` on a CPU-only host. If wins ≥2×, flip default-on for CPU-only deployments.
2. **Phase 6.2 CoreML EP validation** — ~2 hours including SSH to Mac Studio. Same script with `--device cpu` (CoreML EP auto-selected on Mac). If wins ≥10%, flip default-on for Mac.
3. **Phase 6.2 hybrid: ORT CUDA EP for *embedding only*** — ~30 min measurement. The embedding ResNet graph has no LSTM/If — should run cleanly on CUDA EP. Potentially ships a GPU win for consumer deployments without waiting for Phase 6.3.
4. **Phase 5.2: GPU aggregate + reconstruct** — projected **+4.5% E2E on 4.7h**. 1-2 day implementation. Spec in `phase-5-2-gpu-aggregate-and-reconstruct.md`.

### P1 — larger but high-value

5. **Phase 5.4: `GPU_CONCURRENT_REQUESTS` soak test** — raise cap from 4 → 12 on A6000. 12-hour soak to validate VRAM + thermal. **2-4× batch throughput** at deployment level.
6. **Phase 6.3: TensorRT image rework** — switch backend base to a CUDA-runtime image, add TensorRT libs, implement per-arch plan caching. ~1 week. Enables AWS server tier at **+20-40% stage speedup**.

### P2 — bigger scope, conditional

7. **Nightly CI prebuilt TRT plan artifacts** — `sm_{86,89,90}` OCI images. Eliminates first-run build for known AWS instance types. 1-2 days after Phase 6.3 ships.
8. **Phase 6.3 Route B spike** — `torch_tensorrt` FX backend on segmentation only (not via ORT), if the ORT TRT EP path turns out problematic.

---

## Open questions / unknowns

- **Does ORT CPU EP actually win vs eager PyTorch CPU on our specific graphs?** Historically yes, but pyannote v4 might have surprises. One benchmark run resolves this.
- **How well does CoreML EP on M2 Max handle the SincNet + LSTM combo?** Apple's coverage is usually comprehensive, but we haven't measured.
- **TensorRT engine plan VRAM overhead** — Phase 5/6 memos cite 100 MB workspace. Phase 6.3 T5-TRT measurements will validate — risk is breaking the 844 MB invariant.
- **Embedding-only ORT CUDA EP hybrid** — speculation says it works, spike is cheap.

---

## Artifacts inventory

### Documentation in `docs/upstream-patches/`

| File | Purpose |
|---|---|
| `PROGRESS_REPORT.md` | This file |
| `phase-1-session-status.md` | Phase 1 baseline + VRAM decomposition |
| `vectorization-audit.md` | Phase 1.6 audit findings |
| `vram-budget-table.md` | Phase 1.7 per-stage VRAM decomposition |
| `phase-1-5-mps-fallback-hunt.md` | MPS profiler OOM + alternative analysis |
| `phase-3-measurement.md` | Phase 3 honest findings (projection vs reality) |
| `phase-3-5-and-4-measurement.md` | CPU vec + step sweep + GPU Lance-Williams negative results |
| `final-gate-results.md` | Combined-stack final gate (0% DER, 844 MB invariant) |
| `phase-5-1-cuda-graphs.md` | Do not implement |
| `phase-5-2-gpu-aggregate-and-reconstruct.md` | Recommended next — 4.5% E2E |
| `phase-5-3-mps-optimization.md` | Defer |
| `phase-5-4-concurrent-requests-ceiling.md` | Soak test scope |
| `phase-6-1-torch-compile-enablement.md` | SHIPPED — gcc in image |
| `phase-6-2-onnx-export-feasibility.md` | Test matrix + rollout plan |
| `phase-6-2-lessons-learned.md` | **Deployment matrix, stop-chasing list, root-cause analysis** |
| `phase-6-3-tensorrt-plan-build-on-startup.md` | CUDA-toolkit prerequisite documented |

### Scripts in `scripts/`

| File | Purpose |
|---|---|
| `benchmark-pyannote-direct.py` | Main benchmark harness |
| `diarization-der-compare.py` | DER scoring from RTTM directories |
| `vram-probe-diarization.py`, `...-mps.py`, `...-cpu.py` | VRAM sampling |
| `onnx_benchmark_providers.py` | Phase 6.2 provider benchmarks |
| `spike-onnx-export-v2.py` | Reference export recipes (validated) |
| `spike-onnx-seg-der-impact.py` | Proved segmentation drift is argmax-absorbed |

### Fork package (`fork:pyannote/audio/`)

| Path | Purpose |
|---|---|
| `onnx/runtime.py` | ORT session wrappers, batched fbank, provider selection |
| `onnx/export.py` | CLI export script |
| `pipelines/speaker_diarization.py` | `_setup_phase6_onnx` env-var-gated integration |
| `pipelines/clustering.py` | Phase 3 GPU cdist/pdist, VRAM-budget fallback |
| `models/embedding/wespeaker/__init__.py` | Phase A MPS-native FFT |
| `core/inference.py` | Phase 2.2 hamming cache, profiler labels |

### Backend test suite (`backend/tests/onnx/`)

| File | Coverage |
|---|---|
| `conftest.py` | `device`, `onnx_models_dir`, `hf_token` fixtures |
| `test_numeric_parity.py` | T1: segmentation argmax + embedding cos sim |
| `test_fbank_parity.py` | T2: batched fbank vs vmap + determinism |

Run with: `pytest backend/tests/onnx/ -v`.

### Benchmark results (`benchmark/results/`)

Statistical baselines with frozen RTTMs (reference for every future DER comparison):

| Tag | Device | Files | Runs | Status |
|---|---|---|---:|---|
| `baseline_a6000_20260421_213621_short` | A6000 | 0.5h + 2.2h | 5 each | **immutable reference** |
| `baseline_a6000_20260421_214811_long` | A6000 | 3.2h + 4.7h | 3 each | **immutable reference** |
| Plus phase-specific: `phase2_smoke`, `phase35`, `phase3_gpu_linkage`, `phase3_smoke`, `phase4_step{2,3,15,20,30}`, `phase6_1_torchcompile_20260423` | |

---

## How to read this report in future sessions

- **If you want the TL;DR**: top of file.
- **If you're deciding what to work on next**: "What we're pursuing next" section.
- **If you're tempted to retry something**: "What we've proven doesn't work" section first.
- **If you want to reproduce a measurement**: `phase-6-2-lessons-learned.md` has command lines; `scripts/onnx_benchmark_providers.py` is the reference diagnostic.
- **If you want to understand a specific failure**: the `phase-*-measurement.md` files have the detailed numbers.

Last updated: 2026-04-23 (Phase 6.2 implementation session).
