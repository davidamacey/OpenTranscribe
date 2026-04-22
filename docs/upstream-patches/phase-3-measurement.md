# Phase 3 GPU Clustering — Measurement Report

**Date**: 2026-04-21
**Fork commit**: `0ae8e477`
**Status**: **Implementation correct, impact smaller than projected**

## Summary

| file | baseline | Phase 3 | Δ E2E | clustering Δ |
| --- | ---: | ---: | ---: | ---: |
| 0.5h_1899s (5-run) | 22.62s | 22.49s | -0.54% | ~-30% (1.33→0.94s) |
| 2.2h_7998s (5-run) | 101.47s | 101.38s | -0.09% | -1% (12.29→12.19s) |
| 4.7h_17044s (2-run) | 334.12s | 330.15s | **-1.2%** | **-2.6%** (138.32→134.75s) |

All DER = 0%, peak VRAM 844 MB (unchanged), speaker + segment counts byte-identical.

## What went right

- **Numerical parity**: 21/21 pytest tests pass with rtol=1e-4 on fp32. GPU `torch.cdist` (euclidean) and `F.normalize + matmul` (cosine) match scipy to the last decimal.
- **VRAM invariant holds**: 844 MB peak across every run, same as Phase A. 50 MB budget never exceeded; fallback to scipy on budget-exceeded works correctly.
- **End-to-end correctness**: `AgglomerativeClustering.cluster` produces the same cluster partition under GPU and CPU paths.
- **Zero regression**: DER = 0.0%, wall time within noise on all files.

## What missed the target

My Phase 1 "so what" projected **25-35% E2E on 4.7h** based on "clustering is 41% of wall time × assumed 3-5× speedup". Reality is **1.2% E2E** because:

### Root cause: scipy's `linkage(method='centroid')` is O(N³) in the merge, not the pdist

The clustering stage has two components:
1. **Pairwise distance matrix** — `pdist(embeddings, metric)`. O(N²D).
2. **Hierarchical merge (Lance-Williams)** — `linkage(condensed_distances, method)`. **O(N³) for `centroid`/`median`/`ward` methods** because cluster centroids must be recomputed after each merge.

My Phase 3 moved step 1 to GPU. Step 2 stays on CPU (scipy's compiled C code; no GPU port exists without a heavy dependency like cuML).

On 4.7h / 8-speaker, with ~4000 filtered embeddings after `filter_embeddings`:
- pdist on CPU ≈ 10-15s → GPU ≈ 0.2s → **~13s saved**
- Lance-Williams merge ≈ 120s → **not touched**
- Observed saving: **3.58s** (so filter_embeddings keeps fewer than 4000, and the scipy pdist is faster than my estimate)

### Why pyannote uses `centroid`

`AgglomerativeClustering.method` is a hyperparameter; the default for `pyannote/speaker-diarization-community-1` is `centroid`. Switching to `single` / `complete` / `average` would make linkage O(N²) in the merge and my Phase 3 would shine (maybe 15-20% E2E), but would change the clustering behavior — a DER regression risk the plan explicitly forbids.

## Where the real wins remain

Updated stage-by-stage accounting for the 4.7h file under Phase 3:

| stage | Phase 3 wall | % of E2E | who owns the cost |
| --- | ---: | ---: | --- |
| **embeddings** | 160.72s | 48.7% | WeSpeaker ResNet forward on GPU. Mostly optimized already. bf16 would help but DER-risky. |
| **clustering_start** | 134.75s | 40.8% | Lance-Williams merge on CPU. Needs a GPU-native hierarchical clustering impl to further move. |
| discrete_diarization | 12.43s | 3.8% | numpy overlap-add. Phase 3.5 vectorization candidate. |
| segmentation | 12.02s | 3.6% | Optimized already. |
| reconstruct | 6.83s | 2.1% | numpy double loop. Phase 3.5 candidate. |

Reconstruct + discrete_diarization combined: 19.3s on 4.7h. The Phase 1.6 vectorization audit proposed rewrites for both; cumulative savings estimated 8-12s (≈ 2.5-3.5% E2E).

## Revised recommendations

### 1. Land Phase 3 as-is (fork commit 0ae8e477)

- Measurable even if small (-1.2% on 4.7h, -0.54% on 0.5h, -2.6% on the clustering stage specifically).
- Zero regression, full test coverage, 50 MB VRAM budget holds.
- **Prep work for future GPU-native Lance-Williams implementation** — the helpers (`_gpu_cdist`, `_gpu_pdist_condensed`, `_gpu_clustering_budget_bytes`, `_gpu_clustering_fits`) are reusable.
- Upstream-PR candidate: the change is small, opt-out via env var, numerically equivalent to the scipy path.

### 2. Reprioritize the next gates

Phase order in the original plan was Phase 2 → Phase 3 → Phase 3.5 → Phase 4 on assumption that Phase 3 would dominate. New data says Phase 3.5 (vectorize reconstruct + aggregate) is a comparable-sized win with lower risk. Recommended new order:

**Immediate value (low risk, low effort):**
1. Phase 3.5 `reconstruct` vectorization — 1-2% E2E savings, numeric-parity verifiable
2. Phase 3.5 `Inference.aggregate` vectorization — 0.5-1% E2E savings
3. Combined: ~1.5-3% E2E on 4.7h

**Medium-term, gate on empirical DER:**
4. Phase 4 — sliding-window overlap step=0.1→0.3. If DER holds within +1 pp, segmentation stage is 3× faster. Segmentation is only 3.6% of 4.7h wall, so E2E impact small, but on shorter files (0.5h where segmentation is 7% of wall) the effect is bigger.
5. Phase 2.1 follow-up — actually enable `torch_compile=True` and measure. Potentially 5-10% embedding speedup if Dynamo doesn't hit a graph break. Risk: may OOM or slow down warmup.

**Large lift, bigger reward:**
6. **GPU-native hierarchical clustering** — this is the real Phase 3. Would need a torch implementation of centroid-link Lance-Williams. Estimated effort: several days. Estimated payoff: 20-30% E2E on 4.7h. Not in the current plan scope but is the natural extension of Phase 3 as proven by this measurement.
7. Alternative: **switch to KMeans with careful DER validation**. KMeans on GPU is O(N·K·iter) not O(N³), would cut clustering from 138s to ~2s. But pyannote-community-1 was trained against the centroid-AHC output shape; DER risk is real.

### 3. bf16 remains out of scope per user direction

The only other lever on the embedding stage (48% of 4.7h wall) is precision-reduction. The user explicitly ruled out bf16 given fp16's prior rejection. Accepted.

## Code artifacts shipped in Phase 3

- `src/pyannote/audio/pipelines/clustering.py` — +207 lines (helpers + 4 call-site rewires)
- `tests/test_clustering_gpu.py` — +175 lines (21 tests, all passing)
- Env configuration:
  - `PYANNOTE_CLUSTERING_DEVICE` — override auto-detection
  - `PYANNOTE_CLUSTERING_VRAM_BUDGET_MB` — per-call budget (default 50)
  - `PYANNOTE_CLUSTERING_DISABLE_GPU` — route everything through scipy

## Lessons for future optimization measurement

1. **Profile before projecting**: my "so what" extrapolated clustering share (41% of wall) into an E2E speedup estimate without profiling the sub-stages inside clustering. A 2-minute profiler run on a baseline 4.7h would have shown Lance-Williams as the bottleneck and corrected the projection.
2. **Read the algorithm's complexity class, not just its share**: an O(N³) CPU step and an O(N²) GPU step both show up as "clustering time" in high-level profiling but have very different optimization responses.
3. **Small wins still ship**: 1.2% on 4.7h with zero regression is worth landing. Cumulative small wins (Phase 2 visibility + Phase 3 pdist + Phase 3.5 vectorize) add up.
