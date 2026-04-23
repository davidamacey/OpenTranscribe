# CPU Diarization Feasibility Study — Plan

**Drafted:** 2026-04-20
**Motivation:** After Phase A/B/C/D optimizations, is CPU-only diarization now economically viable for cloud deployments where GPUs are expensive?
**Prior belief:** "CPU doesn't work" — whitepaper claim that PyAnnote diarization times out after 10 min on a 30-min file. Measured **before** the memory-safe batch-indexing patch (`f3614bf1`), so likely stale.

## Context from code review

- **Host CPU (for local benchmarks)**: Xeon E5-2680 v3 @ 2.5 GHz, Haswell microarchitecture (2014), 12 physical cores × 2 hyperthreads = 48 logical CPUs on a single socket. Older than modern cloud CPUs; projections below should be treated as a **pessimistic lower bound**.
- **Fork already has an ONNX CPU path**: `pipelines/speaker_diarization.py::_setup_onnx_cpu` at line 332 loads pre-converted ONNX segmentation models with optional INT8 quantization and monkey-patches the segmentation `.infer()` call. **Not currently wired into the backend.**
- **`scripts/preconvert-onnx-models.py` already exists** — one-time conversion of the pyannote segmentation checkpoint to ONNX (FP32 + INT8 variants) into `${MODEL_CACHE_DIR}/onnx/`.
- **`_budget.py` already handles CPU**: `recommend_embedding_batch(device='cpu')` returns `bs=1, status='cpu'` — no changes needed.
- **`onnxruntime` is NOT in `backend/requirements.txt`** — adding it is a CPU-only optional dependency we can gate on a `requirements-cpu.txt` extra.
- **Embedding (WeSpeaker ResNet34) is still pure torch on CPU**; only segmentation has an ONNX path. If embedding dominates on CPU, ONNX wins on segmentation won't move the needle much. Phase CPU.2 measures the split.

## What's changed that could help CPU

Three commits on the fork since the "CPU doesn't work" verdict:

1. **Memory-safe batch indexing** (`f3614bf1`): eliminated `all_chunks.repeat_interleave(num_speakers)` which allocated 59 GB of CPU RAM for a 4.7 h / 21-speaker file. Now uses lazy per-batch indexing. **Huge win for CPU where RAM is a hard constraint.**
2. **Budget ladder caps embedding batch at 16** (`f56b02ac` → `7ed7456` in backend): CPU uses bs=1 via `_budget`; code path is consistent, no auto-scaler confusion.
3. **ONNX CPU segmentation** is coded in the fork but has never been benchmarked end-to-end on long files post-optimization.

## Target hardware / cloud cost math

Local benchmarks will run in the existing `diarization-probe` container. Projections to cloud:

| Instance | Rough multiplier vs. local Xeon | $/hr on-demand |
|---|---:|---:|
| AWS c7i.4xlarge (8 vCPU Intel Platinum) | 2–3× faster per core | $0.71 |
| AWS c7g.4xlarge (8 vCPU Graviton 4) | ~2.5× faster per core | $0.57 |
| AWS m7i.4xlarge (16 vCPU Platinum) | 2× + more parallel | $0.81 |
| AWS g4dn.xlarge (4 vCPU + T4 16 GB GPU) | GPU reference baseline | $0.53 |
| Local Xeon (baseline for these tests) | 1× | — |

**CPU breakeven rule of thumb** (on-demand pricing):
```
cpu_wall / gpu_wall < (gpu_$/hr / cpu_$/hr) × parallel_jobs_per_vm
```
With c7i @ $0.71 + 2 concurrent jobs: CPU wins if slowdown < ~1.5× GPU.
With c7i + 4 concurrent jobs: CPU wins if slowdown < ~3× GPU.
Graviton is cheaper per hour but ARM-architecture caveats (no Intel MKL path).

## Phases

### Phase CPU.1 — Infrastructure smoke (~45 min)

**Goal:** prove the code path loads without error on a tiny file.

1. Add `onnxruntime>=1.18` to a new `backend/requirements-cpu.txt` (don't touch prod `requirements.txt` yet).
2. Build a `diarization-probe-cpu` compose service derived from the benchmark image + the CPU requirements layer (or pip-install at runtime into the existing image for this first pass).
3. Run `scripts/preconvert-onnx-models.py` once to cache ONNX models into `${MODEL_CACHE_DIR}/onnx/`.
4. Write `scripts/vram-probe-diarization-cpu.py` — mirrors `vram-probe-diarization.py` but samples process RSS (via `/proc/self/status`) at 100 ms and forces `device='cpu'`. Three modes: `torch-only`, `onnx-seg`, `onnx-seg-int8`.
5. Run one 30-second synthetic clip (or short slice of the existing reference). If it completes and detects at least one speaker, pass.

**Pass criterion:** 30 s clip completes in < 3 min in any mode.
**Abort if:** torch can't import on CPU, ONNX load fails, or wall time > 5 min on 30 s.

### Phase CPU.2 — Duration sweep (~2–3 hours)

**Goal:** characterize realtime factor (RTF = wall_s / audio_s) and peak RAM across audio durations. Kill the study early if RTF is hopeless.

**Matrix:**

| Audio | Duration | Purpose |
|---|---:|---|
| synthetic-30s | 30 s | baseline |
| `0.5h_1899s.wav` first 2 min slice | 120 s | short-file viability |
| `0.5h_1899s.wav` first 5 min slice | 300 s | medium-file scaling |
| full `0.5h_1899s.wav` | 1899 s | full-file stress |

**× 3 configs:** `torch-only`, `onnx-seg-fp32`, `onnx-seg-int8`
**× 3 thread counts:** `num_threads = 4, 8, 12` (Haswell tends to scale worst past physical core count)

**Early-abort rules (cascade):**
- 30 s takes > 3 min wall → abort, not viable
- 120 s takes > 10 min → abort, don't bother with longer files
- 300 s takes > 20 min → skip 1899 s for that config, note best-case RTF only
- Peak RSS > 16 GB at any point → note, continue; cloud VMs have ≥ 32 GB

**Metrics per run (JSON, compatible with existing analysis scripts):**
- `wall_s`, `segmentation_s`, `embedding_s`, `clustering_s` (from pipeline `hook` callbacks)
- `rss_peak_mb`, `rss_baseline_mb`
- `num_speakers_detected`, `num_segments`
- `realtime_factor = wall_s / audio_duration_s`
- `config` (torch-only / onnx-fp32 / onnx-int8)
- `num_threads`

### Phase CPU.3 — Accuracy check (~15 min, only if CPU.2 produced ≥1 viable config)

**Goal:** confirm CPU output matches GPU reference.

- Run best-config from CPU.2 on `0.5h_1899s.wav`
- Dump RTTM, compute DER vs. the committed `raw/rttm/0.5h_1899s__cap-unl__bs-16__mp-off__r0.rttm`
- Reuses `scripts/diarization-der.py` as-is.

**Pass criterion:** DER ≤ 1 %, speaker count matches (4 on this file).

### Phase CPU.4 — Large-file extrapolation (~2 hours worst case, only if CPU.2 viable)

**Goal:** confirm long-file scaling is linear, not superlinear.

- Run best-config on `2.2h_7998s.wav` (Phase A second reference)
- Assert RTF within 1.3× of the 1899 s RTF (linear scaling tolerance)
- Assert peak RAM doesn't grow super-linearly with duration

Superlinear scaling would indicate a clustering-cost explosion with speaker count; the memory-safe batch indexing patch should prevent this but we've never run it to completion on CPU.

### Phase CPU.5 — Whisper-on-CPU sanity check (optional, ~30 min)

**Goal:** whole-stack viability. Diarization isn't the only component; transcription has to fit too.

- Adapt `whole-stack-vram-probe.py` for CPU: Whisper `tiny`/`base`/`small` with CTranslate2 int8 on `0.5h_1899s.wav`
- Compute combined-stack RTF: `(whisper_wall + diar_wall) / audio_duration`
- Data point for the cost model; not a pass/fail gate.

## Decision matrix at end of CPU.2

| Best RTF observed | Recommendation |
|---:|---|
| ≥ 1.0× (realtime) | **Ship it.** CPU is viable; make it default for ≤ 6 GB GPU tier. |
| 0.5× – 1.0× | **Ship as opt-in.** Good for batch/overnight. GPU remains default. |
| 0.2× – 0.5× | **Document only.** Close cost-model analysis before enabling. |
| < 0.2× | **CPU remains infeasible.** Update whitepaper with the measured floor; close the question. |

## Deliverables

Two commits, one PR's worth of work:

1. `feat(diarization): add CPU probe harness + ONNX CPU wiring` — new `scripts/vram-probe-diarization-cpu.py`, `backend/requirements-cpu.txt`, compose service / runtime-install path for `onnxruntime`.
2. `docs(diarization): Phase CPU findings` — new `docs/diarization-vram-profile/cpu.md` with RTF + RAM tables, cloud-cost analysis, decision recommendation; `CLAUDE.md` update if CPU becomes a supported tier.

## Out of scope for this plan

- Auto-routing diarization to CPU on GPU-less machines (follow-up, conditional on CPU.2 passing).
- Optimizing the embedding path for CPU (e.g., porting WeSpeaker ResNet to ONNX) — large effort, only worth doing if segmentation is already not the bottleneck per the CPU.2 breakdown.
- MPS-as-fallback when MPS unavailable on macOS — Mac Studio testing is separate.

## Biggest unknown

Whether WeSpeaker embedding on CPU hits superlinear RAM with long files. The memory-safe batch indexing patch *should* have fixed this — CPU.2's 1899 s run is what confirms or denies it.

## Total time / risk

- **Total wall time:** 4–6 hours, mostly unattended.
- **Escape hatches built in:** every phase has early-abort criteria so we don't burn a day on a dead path.
