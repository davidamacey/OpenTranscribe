# PyAnnote Fork Vectorization Audit (Phase 1.6)

Snapshot of remaining unvectorized hot paths in `davidamacey/pyannote-audio@gpu-optimizations` as of **2026-04-21**. Each finding includes file:line, current pattern, proposed vectorized pattern, expected speedup band, and VRAM delta. This list feeds Phase 3.5 (vectorization sweep commits).

## Ground rules

- **No API changes**: every refactor must preserve function signature, return shape/dtype, and numerical result within `rtol=1e-5` of the baseline.
- **No new deps**: pure numpy / torch.
- **DER invariance**: every change verified with the Phase 1 DER reference before shipping.
- **VRAM invariance**: per-change delta ≤ +10 MB (Phase 3.5 gate).

## Already vectorized (don't re-do)

| Location | Pattern | Note |
| --- | --- | --- |
| `speaker_diarization.py:527` | `waveform.unfold(1, window_samples, step_samples)` | Chunk extraction |
| `speaker_diarization.py:564-571` | `np.where` + `np.transpose` | Mask selection |
| `speaker_diarization.py:677` | `chunk_indices = torch.arange(...) // num_speakers` | Batch waveform gather |
| `speaker_diarization.py:548-553` | `np.nan_to_num` applied once to full tensor | Binary/clean data |
| `wespeaker/__init__.py:134-142` | Native MPS FFT via PyTorch 2.3+ | Phase A ship |

## Remaining hot-path findings

### 1. `SpeakerDiarization.reconstruct` — double Python loop

**Location**: `src/pyannote/audio/pipelines/speaker_diarization.py:831-843`

**Current**:
```python
for c, (cluster, (chunk, segmentation)) in enumerate(
    zip(hard_clusters, segmentations)
):
    for k in np.unique(cluster):
        if k == -2:
            continue
        clustered_segmentations[c, :, k] = np.max(
            segmentation[:, cluster == k], axis=1
        )
```

**Complexity**: `O(num_chunks × local_num_speakers × num_frames)` with Python-level iteration per (chunk, cluster).

**Observed cost**: smoke run on 0.5h/1899s showed `reconstruction_start + discrete_diarization` ≈ 1.6s. Scales ~linearly with duration → roughly 3-4s on 2.2h, 14-16s on 4.7h (21-speaker stress case).

**Proposed** (pure-numpy, no new deps):
```python
# cluster shape: (num_chunks, local_num_speakers), int8
# segmentation.data shape: (num_chunks, num_frames, local_num_speakers)
# target clustered_segmentations shape: (num_chunks, num_frames, num_clusters)

# Build a one-hot (num_chunks, local_num_speakers, num_clusters) mask
valid = cluster >= 0  # excludes -2 sentinel
one_hot = np.zeros(
    (num_chunks, local_num_speakers, num_clusters), dtype=np.float32
)
cc, ss = np.where(valid)
one_hot[cc, ss, cluster[cc, ss]] = 1.0

# Einsum: for each (chunk, frame, cluster), take max over speakers where
# one_hot[chunk, speaker, cluster] == 1. Equivalent to masked max.
# Use np.where + np.nanmax to avoid picking up zero-mask entries.
seg_data = segmentations.data  # (num_chunks, num_frames, local_num_speakers)
# Broadcast: (num_chunks, num_frames, local_num_speakers, num_clusters)
masked = np.where(
    one_hot[:, np.newaxis, :, :].astype(bool),
    seg_data[:, :, :, np.newaxis],
    -np.inf,
)
clustered = masked.max(axis=2)  # (num_chunks, num_frames, num_clusters)
clustered = np.where(
    np.any(one_hot, axis=1)[:, np.newaxis, :],
    clustered,
    np.nan,
)
clustered_segmentations = SlidingWindowFeature(clustered, segmentations.sliding_window)
```

**Memory note**: the intermediate `masked` tensor is `O(num_chunks × num_frames × local_num_speakers × num_clusters × 4 B)`. For a 4.7h/21-speaker case with `num_chunks≈500`, `num_frames≈150`, `local_num_speakers≈6`, `num_clusters≈21` that's ~38 MB — safe. For extreme cases add a chunked variant falling back to the loop when product exceeds 100 MB.

**Expected speedup**: 3-5× on reconstruction stage → ~1-2 % end-to-end on 4.7h.

**Risk**: low. Numeric parity test: `assert np.allclose(new_result.data, old_result.data, equal_nan=True, rtol=1e-5)`.

**Priority**: **High** (Phase 3.5 first commit).

---

### 2. `Inference.aggregate` — Python loop over chunks

**Location**: `src/pyannote/audio/core/inference.py:593-616`

**Current**:
```python
for chunk, score in scores:
    mask = 1 - np.isnan(score)
    np.nan_to_num(score, copy=False, nan=0.0)
    start_frame = frames.closest_frame(chunk.start + 0.5 * frames.duration)
    aggregated_output[start_frame : start_frame + num_frames_per_chunk] += (
        score * mask * hamming_window * warm_up_window
    )
    overlapping_chunk_count[...] += mask * hamming_window * warm_up_window
    aggregated_mask[...] = np.maximum(aggregated_mask[...], mask)
```

**Observed cost**: aggregation is called multiple times (once per segmentation hook → `__aggregate` at line 357, again in downstream reconstruction). Per-file total: ~0.5-2s on 0.5h, scaling to ~4-8s on 4.7h.

**Proposed** (pure-numpy):
```python
# scores.data shape: (num_chunks, num_frames_per_chunk, num_classes)
mask_all = ~np.isnan(scores.data)  # boolean, same shape
score_clean = np.where(mask_all, scores.data, 0.0).astype(np.float32)

# Pre-compute all start_frames in one pass using SlidingWindow arithmetic
# (SlidingWindow provides deterministic start offsets per chunk)
start_frames = frames.closest_frame(
    chunks.start + 0.5 * frames.duration +
    np.arange(num_chunks) * chunks.step
).astype(np.int64)

# Weight tensor (1, num_frames_per_chunk, 1)
weight = (hamming_window * warm_up_window).astype(np.float32)[np.newaxis, :, :]

# Weighted scores per chunk (num_chunks, num_frames_per_chunk, num_classes)
weighted_score = score_clean * mask_all.astype(np.float32) * weight
weighted_mask = mask_all.astype(np.float32) * weight

# Scatter-add into aggregated_output and overlapping_chunk_count
# Build index array: for each chunk c, rows [start_frames[c]:start_frames[c]+F]
frame_off = np.arange(num_frames_per_chunk)
# (num_chunks, num_frames_per_chunk) — indices into the global frame axis
global_idx = start_frames[:, None] + frame_off[None, :]

# Flatten to 1D for np.add.at
flat_idx = global_idx.reshape(-1)
flat_score = weighted_score.reshape(-1, num_classes)
flat_mask = weighted_mask.reshape(-1, num_classes)
flat_mask_presence = mask_all.reshape(-1, num_classes).astype(np.float32)

np.add.at(aggregated_output, flat_idx, flat_score)
np.add.at(overlapping_chunk_count, flat_idx, flat_mask)

# aggregated_mask is max (not sum) — use np.maximum.at (ufunc)
np.maximum.at(aggregated_mask, flat_idx, flat_mask_presence)
```

**Expected speedup**: 5-10× on aggregation stage (np.add.at is C-level) → ~1-2 % end-to-end.

**Caveat**: numeric drift — `np.add.at` accumulates in hash-bucket order, not in chunk order. For fp32 this is not order-invariant. Verify with `rtol=1e-4` rather than `1e-5`.

**Alternative** if drift exceeds rtol: use `scipy.sparse.coo_matrix` → `tocsr()` then accumulate row-by-row. Slightly slower but deterministic.

**Priority**: **Medium** (Phase 3.5 after reconstruction).

---

### 3. `BaseClustering.constrained_argmax` — inner zip loop

**Location**: `src/pyannote/audio/pipelines/clustering.py:128-141`

**Current**:
```python
hard_clusters = -2 * np.ones((num_chunks, num_speakers), dtype=np.int8)
for c, cost in enumerate(soft_clusters):
    speakers, clusters = linear_sum_assignment(cost, maximize=True)
    for s, k in zip(speakers, clusters):
        hard_clusters[c, s] = k
```

**Note**: the outer loop can't be vectorized (LSA is per-chunk). The inner `for s, k in zip(...)` is trivial:
```python
hard_clusters[c, speakers] = clusters
```

**Expected speedup**: <0.5 % end-to-end. Freebie: cleaner code, fewer Python-level ops.

**Priority**: **Trivial** (bundle with the other cleanups).

---

### 4. `BaseClustering.assign_embeddings` — centroids via list-comp

**Location**: `src/pyannote/audio/pipelines/clustering.py:183-187`

**Current**:
```python
centroids = np.vstack(
    [
        np.mean(train_embeddings[train_clusters == k], axis=0)
        for k in range(num_clusters)
    ]
)
```

**Proposed** (one `np.bincount` + one `np.add.at`, no Python loop):
```python
# train_embeddings: (N, D); train_clusters: (N,)
counts = np.bincount(train_clusters, minlength=num_clusters).astype(np.float32)
sums = np.zeros((num_clusters, train_embeddings.shape[1]), dtype=np.float32)
np.add.at(sums, train_clusters, train_embeddings)
centroids = sums / np.maximum(counts[:, None], 1.0)
```

**Expected speedup**: negligible for typical `num_clusters ≤ 30` but removes a Python loop on a correctness-critical path.

**Risk**: `np.add.at` ordering — same caveat as above. Verify with rtol=1e-6 on fixed-seed synthetic.

**Priority**: **Trivial**.

---

### 5. `AgglomerativeClustering.cluster` — large/small merge loop

**Location**: `src/pyannote/audio/pipelines/clustering.py:481`

**Current**:
```python
for small_k, large_k in enumerate(np.argmin(centroids_cdist, axis=0)):
    clusters[clusters == small_clusters[small_k]] = large_clusters[large_k]
```

**Proposed**:
```python
# Build a remap table: small_cluster_label -> large_cluster_label
nearest_large = large_clusters[np.argmin(centroids_cdist, axis=0)]
remap = np.arange(clusters.max() + 1)
remap[small_clusters] = nearest_large
clusters = remap[clusters]
```

**Expected speedup**: <0.2 s on long files but cleaner and avoids in-place iteration.

**Priority**: **Trivial**.

---

### 6. `AgglomerativeClustering.cluster` — dendrogram resolution search

**Location**: `src/pyannote/audio/pipelines/clustering.py:421-445`

**Current**: outer loop over iterations by `np.argsort(|dendrogram[:, 2] - threshold|)`, each iteration calls `fcluster` (a tree walk).

**Note**: inherently sequential — each iteration is a binary search-style refinement. `fcluster` itself is compiled C. Vectorization would require replacing the loop with a different algorithm (e.g. binary search over the sorted dendrogram array).

**Observed cost**: unknown without profiler data. Only triggered when `num_clusters` is specified AND `num_large_clusters != num_clusters`, which is a tuning path.

**Recommendation**: **profile first**. If > 2% of end-to-end on any benchmark file, binary search replacement is the right approach; otherwise skip.

**Priority**: **Defer** until Phase 1.5 profiler trace shows this is hot.

---

### 7. `Powerset.build_mapping` — one-time init loops

**Location**: `src/pyannote/audio/utils/powerset.py:102-108`

**Current**:
```python
for set_size in range(0, self.max_set_size + 1):
    for current_set in combinations(range(self.num_classes), set_size):
        mapping[powerset_k, current_set] = 1
        powerset_k += 1
```

**Frequency**: called **once per pipeline construction** — not in per-call hot path.

**Priority**: **Skip**. Even if vectorized, zero observable effect at pipeline runtime.

---

### 8. `Powerset.to_multilabel` / `forward` — already vectorized

**Location**: `src/pyannote/audio/utils/powerset.py:115-140`

Already pure torch (`torch.nn.functional.one_hot` + `torch.matmul`). No change needed.

---

## Summary Table

| # | Finding | Effort | Speedup | VRAM delta | Priority |
| --- | --- | --- | --- | --- | --- |
| 1 | `reconstruct` double loop | Medium | 3-5× stage / 1-2 % E2E | ≤40 MB (chunked fallback for stress) | **High** |
| 2 | `Inference.aggregate` loop | Low-Medium | 5-10× stage / 1-2 % E2E | 0 MB (CPU) | **Medium** |
| 3 | `constrained_argmax` zip loop | Trivial | <0.5 % | 0 | Trivial |
| 4 | `assign_embeddings` centroids | Trivial | <0.2 % | 0 | Trivial |
| 5 | Cluster remap loop | Trivial | <0.5 % | 0 | Trivial |
| 6 | AHC resolution search | High | Unknown | 0 | Defer (profile first) |
| 7 | `Powerset.build_mapping` | Low | 0 (one-time) | 0 | Skip |

## Phase 3.5 ship order

1. **`reconstruct` vectorization** — biggest single win on long files; add chunked fallback to respect the 50 MB budget.
2. **Trivial bundle** — items 3, 4, 5 in one commit. Free speedups + code cleanup.
3. **`Inference.aggregate` vectorization** — medium risk (float accumulation order); gate on `np.add.at` vs. dense matmul preference after prototyping both.
4. **Revisit item 6** after Phase 1.5 profiler trace lands.

## Caveat

Numbers above are algorithmic estimates. Actual speedup confirmed only after Phase 1.3 baseline lands and each change is benchmarked against it. Phase 3.5 gate: `≥5 % speedup on the relevant stage, DER unchanged, VRAM delta ≤ +10 MB`.
