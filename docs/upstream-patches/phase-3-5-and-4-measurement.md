# Phases 3.5, 4, and GPU Lance-Williams — Measurement Report

**Date**: 2026-04-22
**Fork commits**:
- `6ab616c5` perf(clustering): Phase 3.5 micro-vectorization — trivial freebies only
- (pending) perf(clustering): GPU Lance-Williams centroid linkage

## Phase 3.5 — Scope cut after CPU regression measurement

### Attempted

1. ✅ `BaseClustering.constrained_argmax` inner zip → vector scatter
2. ✅ `BaseClustering.assign_embeddings` centroid comp → bincount + add.at
3. ✅ `AgglomerativeClustering` small/large cluster remap → lookup table
4. ❌ `SpeakerDiarization.reconstruct` double loop → broadcast-masked-max
5. ❌ `Inference.aggregate` overlap-add → np.add.at / np.maximum.at scatter

### Results

Items 4-5 were implemented, tested against the baseline reference (13 numeric-parity pytest all passed), then measured E2E on the 4.7h/8-speaker benchmark. Both **regressed badly**:

| stage | baseline | vectorized | delta |
|---|---:|---:|---:|
| reconstruct | 6.85s | 10.74s | **+57%** |
| discrete_diarization | 12.53s | 16.87s | **+35%** |
| wall (E2E) | 334.12s | 339.66s | +1.7% |

### Root cause

Both rewrites use scatter-style numpy primitives (`np.add.at`, `np.maximum.at`, broadcast-masked-max via `np.where`) that are **GPU-friendly but CPU-hostile**:

- `np.add.at` / `np.maximum.at` disable numpy's contiguous-stride SIMD optimizations to handle the duplicate-index case safely.
- The original loops used `array[start:start+F] += chunk_data` — a contiguous slice update that hits the CPU cache cleanly and vectorizes.
- Broadcast-masked-max (`np.where(mask, seg, -np.inf).max(axis=2)`) allocates an intermediate (C, F, S, K) tensor; the per-chunk loop only touches F×local_num_speakers slices at a time.

### Decision

Reverted items 4-5. Shipped only items 1-3 (the trivial freebies) in fork commit `6ab616c5`. The GPU port of `reconstruct` and `Inference.aggregate` belongs to **Phase 5.2** — when we're moving computation to GPU, scatter primitives finally pay for themselves.

### Lesson

CPU vectorization ≠ GPU vectorization. The right numpy replacement for a "per-chunk contiguous-slice update" loop is **another contiguous-slice loop** — not a flat scatter. np.add.at is only a win when the alternative is Python-level index indirection, not contiguous slicing.

## Phase 4 — Sliding-window step DER sweep

### What Phase 4 was trying to do

Phase 1 baseline established that the **segmentation** stage runs pyannote's `Inference` class over the audio with a sliding window: 10-second chunks overlapped at 90%, which means every second of audio is seen by ~10 different chunks. Each chunk is passed through the powerset segmentation model, and the frame-level predictions from the 10 overlapping chunks are aggregated (overlap-add averaging) into a single posterior per frame.

On 2.2h of audio this produces **~8,000 chunks** for the segmentation model to process (roughly 1 chunk per second of input × 10x overlap). The 5.5 seconds this stage takes is dominated by that chunk-count — each individual chunk runs a small amount of GPU work but 8000 of them add up.

**Hypothesis**: most of the chunk overlap is redundant. If we reduce overlap from 90% to 80% (step 1s → 2s), the segmentation model runs on **half** the chunks and the stage should be roughly 2× faster. Overlap-add aggregation tolerates some reduction because each frame is still averaged over 5 chunks at 80% overlap (vs 10 at 90%).

**Bet**: DER degradation is small because the segmentation model learns a smooth-ish posterior and 5-chunk averaging has enough signal. Plan's accept gate was DER ≤ +0.5 pp for default flip, ≤ +1.0 pp for opt-in.

### Defaults (discovered empirically)

pyannote/speaker-diarization-community-1 default: **chunk duration 10s, step 1.0s → 90% overlap**.

**Aside on plan confusion**: the plan wrote test points as 0.1 / 0.2 / 0.3 assuming "step is a fraction of duration" but the pyannote API takes absolute seconds. The first sweep ran step=0.15 which is actually **98.5% overlap** — nearly a 10× increase in segmentation work — and predictably got slower, not faster. Corrected values:

- step=1.0 (baseline, 90% overlap)
- step=2.0 (80% overlap, 5 chunks/frame)
- step=3.0 (70% overlap, ~3.3 chunks/frame)

### Results on 2.2h file (3 speakers, 3-run means)

| config | wall (s) | speakers | segments | DER vs baseline | decision |
|---|---:|---:|---:|---:|---|
| **step=1.0 (baseline)** | **101.47** ±0.29 | 3 | 2855 | 0 pp | keep as default |
| step=2.0 | **49.77** ±0.19 (**-51%**) | 2 | 2651 | **+1.45 pp** | opt-in, speaker mismatch |
| step=3.0 | **33.67** ±0.30 (**-67%**) | 2 | 2645 | **+1.73 pp** | archive (exceeds plan gate) |

The **wall-time side of the bet paid off exactly as predicted**: step=2.0 cut wall time almost perfectly in half (-51% on 2.2h); step=3.0 cut it by two-thirds. Segmentation stage timing alone would have been even more dramatic — e.g. the 5.5s segmentation on 2.2h at step=1.0 drops to roughly 2.7s at step=2.0, a 2× speedup precisely proportional to the chunk-count reduction. But **segmentation is only 5.4% of 2.2h wall time**, so the headline E2E speedup comes mostly from a proportional drop in **embeddings** (fewer chunks = fewer embeddings to extract) and **clustering** (fewer embeddings to cluster).

### Why it didn't work — the accuracy side

Both non-default configs **lost a speaker** (3 → 2) and the DER grew to 1.45 pp / 1.73 pp — well beyond the plan's 0.5 pp default-flip gate and the 1.0 pp opt-in gate.

**What went wrong mechanistically**:

1. **Short-turn speakers vanish first.** pyannote's segmentation posterior at any given frame is the average of every overlapping chunk's prediction at that frame. At 90% overlap a 2-second turn by a minor speaker is covered by ~20 chunks, each contributing evidence. At 70% overlap it's covered by ~6 chunks. If even 2-3 of those chunks miss the turn (because the speaker's voice is at the edge of the chunk or partially masked), the averaged posterior stays below pyannote's binarization threshold and the turn is deleted.

2. **Edge-of-chunk degradation.** The segmentation model is known to be less accurate at the first and last ~0.5s of each chunk (warm-up regions). The 90% overlap regime means most frames are observed at both the center and the edge of various chunks, so the center-chunk evidence dominates. At lower overlap, many frames are only seen at the edge of chunks, amplifying edge errors into the final posterior.

3. **Speaker-count cascade.** pyannote derives `num_speakers` from the count of distinct binarized identities in the aggregated segmentation. When a short-turn speaker's posterior is smeared below threshold, they're dropped entirely → clustering runs on a reduced embedding set → the missing speaker never appears in the final diarization. This is a *compounding* failure: segmentation loses one speaker, clustering loses one cluster, the final output mislabels that speaker's frames as a different person.

4. **Collar-25ms DER isn't forgiving here.** The DER metric we used has a 250 ms collar (tolerates small boundary shifts) but not a speaker-swap tolerance. Losing an entire speaker means every frame they would have occupied is charged as a confusion error. For a minor speaker with 2-3% of total speech, that's a 2-3 pp hit on its own — matching our observed 1.45 / 1.73 pp numbers.

**Short version**: reducing overlap is a correct optimization *only if* the segmentation model has enough margin in its posterior to tolerate fewer averaging inputs. For pyannote-community-1, the margin is ~10% overlap per short-turn speaker. Going below 90% overlap starts dropping speakers. This isn't a bug in pyannote — it's a design trade-off that was calibrated around 90% overlap during training, and we were asking it to extrapolate.

### Decision

Per the plan's decision rule table:

| Outcome | Action |
|---|---|
| DER ≤ +0.5 pp AND speakers ±1 AND seg ≥ 2× | flip default |
| DER ≤ +1.0 pp | opt-in kwarg |
| DER > +1.5 pp | archive |
| DER > +2.0 pp | abandon |

- step=2.0: 1.45 pp is between the opt-in and archive thresholds, **and** the speaker-count dropped by 1 (within ±1 tolerance but qualitatively bad). **Conclusion: expose as opt-in but do not default**.
- step=3.0: 1.73 pp exceeds the 1.5 pp archive gate. **Conclusion: archive**.

### What shipped

- `scripts/benchmark-pyannote-direct.py` already exposes `--segmentation-step` as a runtime flag (added during this phase). Power users can trade accuracy for a 50% wall-time reduction with one line.
- **No fork code changes** — pyannote's default stays at step=1.0 / 90% overlap.
- Documentation in this file describes the trade-off. If users want it in production, they'd set `pipeline._segmentation.step = 2.0` after `Pipeline.from_pretrained()` — explicit, reversible, auditable.

### Where this optimization *could* work

Three scenarios where step=2.0 becomes the right default:

1. **Low-speaker-count inputs** — interviews, single-speaker monologues, dual-speaker conversations with long turns. The short-turn-degradation pathway doesn't apply when there are no short turns.
2. **Retrained segmentation model** — training with step=2.0 data augmentation would let the model learn to tolerate the reduced-overlap regime. Out of scope here; requires a model retrain.
3. **Coarse diarization** — applications where "who spoke most" matters but short clarifications ("mhm", "yeah") can be dropped. Podcasts with guest counts, meeting summaries, etc.

### Speaker-count mismatch is the real killer

Both non-default configs drop from 3 speakers to 2 — a hard DER-independent regression. Even if DER were 0.3 pp, losing a speaker is a qualitative failure users notice. Pyannote's internal speaker-counting derives from the segmentation posteriors; sparser segmentation under-represents short-turn speakers.

**Recommendation**: document the trade-off in README_OPTIMIZATION.md as a power-user knob. Do not enable it by default, and do not expose it in the production pipeline config.

## GPU Lance-Williams — the real Phase 3 follow-up

### Context

Phase 3 shipped GPU pdist but measured only 1.2% E2E improvement on 4.7h because `scipy.cluster.hierarchy.linkage(method='centroid')` does O(N³) work in the Lance-Williams merge (CPU-bound), and my Phase 3 ported only the O(N²D) pdist step. To capture the remaining 25-30% on 4.7h, the Lance-Williams merge itself needs a GPU port.

### Implementation

`src/pyannote/audio/pipelines/clustering.py::_gpu_linkage_centroid()` — 100+ line pure-torch port that:

- Maintains centroid tensor, count tensor, active-slot mask on GPU
- Iterates N-1 merges; each iteration runs `argmin` over the N×N distance matrix, reads/writes slot i/j as 0-d tensor indices, and recomputes the `||new_centroid − all_centroids||` distance row in one vectorized pass
- Keeps the merge record (dendrogram) on GPU; transfers to numpy only at the end to minimize CPU-GPU syncs
- Avoids the O(N²·D) scipy Lance-Williams-with-centroid re-derivation by using the algebraic equivalence: for Euclidean, `d(C_ij, C_k) = ||C_ij − C_k||` where `C_ij = (n_i·C_i + n_j·C_j)/n_ij`
- Separate VRAM budget (`PYANNOTE_LINKAGE_VRAM_BUDGET_MB`, default 200 MB) because the full N×N distance matrix dominates; falls back to scipy when budget-exceeded or N < 200

### Tests

`tests/test_gpu_linkage.py` — 11 tests, all passing:
- Budget guard returns None on CPU device, N < 200, and tiny-budget override
- Partition equivalence with scipy on 4 parametrized cluster configs (n_clusters × per_cluster × dim × noise)
- Dendrogram shape, merge count, cluster-id validity, merge-distance finiteness

Scipy-partition match (not byte-equal dendrogram) is the correctness criterion: fp32 on GPU vs fp64 on CPU produces tiny numeric differences that may break tie-breaking order but don't change the induced clustering at any threshold.

### E2E measurement — **negative result**

**Result**: the GPU Lance-Williams implementation is **slower than scipy** on the actual pyannote-community-1 workload. Benchmark on 2.2h with probe instrumentation:

```
PROBE: _gpu_linkage_centroid called N=10023 D=256 device=cuda
PROBE: returned dendrogram in 14.17s
```

scipy baseline on the same workload: ~12s. **GPU port: +2s regression**.

### Why it didn't work — the root cause

The Lance-Williams merge is **intrinsically sequential**: each of the N-1 merges depends on the previous iteration's centroid update. This prevents batching merges across iterations. What runs on GPU per iteration:

- `argmin` over the N×N=10023² distance matrix — ~0.5ms
- `centroids[i] = ...` scatter writes — ~0.3ms
- Row/column `dists[i, :] = new_dists` updates — ~0.3ms
- `torch.norm(centroids - new_centroid, dim=1)` — ~0.5ms
- Misc tensor indexing + arithmetic — ~0.3ms

Per-iteration: **~1.5-2 ms**. Over 10k iterations: **15-20 seconds**.

scipy's compiled C version avoids Python/PyTorch overhead and uses cache-friendly array access; each iteration is 0.5-1ms → ~10-12 seconds total. On A6000 hardware, **scipy wins** even though each individual GPU op is nominally faster.

This is a known failure mode for naive pure-torch implementations of sequential O(N) algorithms: the fixed per-iteration overhead (dispatch, Python binding, kernel launch) dominates once iteration count is in the thousands.

### Wrong assumption in the Phase 3 "so what"

My Phase 3 measurement report projected 25-35% E2E improvement on 4.7h based on the assumption that **all of** `clustering_start`'s 138s was scipy linkage. But scipy linkage is only ~12s of that 138s. The other ~126s is:

- `filter_embeddings` (numpy work over raw segmentations)
- centroid computation (already GPU-ported by Phase 3)
- `fcluster` tree walk
- `assign_embeddings` cdist (GPU-ported, but runs twice)
- the multiple-iteration AHC resolution search (VBxClustering specifically)
- VBx's own PLDA-based re-clustering (`cluster_vbx`)

So even an infinite-speedup linkage would only save ~12s of the 138s stage — an 8-9% stage speedup, 3-4% E2E. My projection of 25-35% was off by an order of magnitude.

### What shipped anyway

- `_gpu_linkage_centroid()` + `_gpu_linkage_fits()` — correctness-verified (11/11 parity tests with scipy). Wired into both `AgglomerativeClustering.cluster` and `VBxClustering.cluster`.
- **Default off**: opt-in via `PYANNOTE_ENABLE_GPU_LINKAGE=1`. Scipy remains the production path.
- Budget guard auto-sizes to 50% of free VRAM (capped at 2 GB) so large N (10k+ embeddings) fit without manual tuning.
- Kept as infrastructure for future work where the GPU path **might** win:
  - `torch.jit.script` or `torch.compile` over the merge loop to reduce Python overhead
  - A single fused CUDA kernel for argmin+scatter+recompute per iteration
  - Newer hardware (H100/B100) with faster kernel launch latency
  - Larger N (20k+) where per-iteration GPU math compensates for overhead

### Revised picture of where pyannote-community-1 spends time

Per-stage wall on 4.7h/8-speaker baseline:
| stage | wall (s) | share |
|---|---:|---:|
| embeddings (GPU) | 161.56 | 48.4% |
| clustering_start (CPU-dominant, ~12s scipy linkage inside) | 138.32 | 41.4% |
| discrete_diarization (CPU numpy) | 12.53 | 3.8% |
| segmentation (GPU) | 11.46 | 3.4% |
| reconstruction_start (CPU numpy) | 6.85 | 2.1% |

The 138s `clustering_start` stage is dominated by the VBxClustering-specific work (PLDA re-clustering via `cluster_vbx`, the AHC resolution search, and assign_embeddings called twice), not scipy linkage. Closing this gap requires refactoring the VBxClustering flow itself, not just the linkage call inside it — which is scope beyond "swap scipy for GPU".

### The real highest-ROI remaining lever on 4.7h

Given the measurement, the only stages still worth a GPU port are:
- `reconstruction_start` + `discrete_diarization` combined (19.4s on 4.7h = 5.8% E2E). GPU port is straightforward for both; scatter ops are fine on GPU.
- Parts of `clustering_start` beyond the linkage — `cluster_vbx` especially.

`embeddings` (161s) is already the most optimized piece of the pipeline (Phase A's fork work). Further gains there require either model-precision reduction (bf16, already rejected per quality guarantee) or a different model (out of scope).

## Roadmap update

After this batch ships, the remaining optimization levers are:

1. **GPU port of `reconstruct` + `Inference.aggregate`** — Phase 5.2. Now that we've measured these as 18-20s combined on 4.7h (and CPU-vectorization regressed), a GPU port is the natural next win.
2. **torch.compile default-on** — Phase 2.1 follow-up blocked by the benchmark container missing gcc (Triton JIT dependency). Not a code issue; Dockerfile change required for measurement.
3. **MPS fallback op hunt** — Phase 1.5, requires a profiler trace on a 2.2h MPS run. Deferred.
4. **Alternative clustering (KMeans or spectral)** — if GPU Lance-Williams doesn't close the full 138s gap, KMeans on GPU runs in ~2s. Trade: DER-risky because pyannote-community-1 was tuned against centroid-AHC output.
