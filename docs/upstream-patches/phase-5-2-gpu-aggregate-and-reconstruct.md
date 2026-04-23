# Phase 5.2 — GPU Port of `Inference.aggregate` + `SpeakerDiarization.reconstruct` (feasibility memo)

**Status**: Feasibility analysis. **Recommended** for a future session.
**Projected impact**: 4–6% E2E on 4.7h, 1–2% on 2.2h. Low DER risk.

## Context

Phase 3.5 attempted CPU-native vectorization of these two loops; both regressed 35–57% because numpy's scatter primitives (`np.add.at`, `np.maximum.at`) disable the contiguous-stride SIMD path that the original loops used. This memo scopes the **GPU port** — the natural next move now that CPU vectorization is confirmed to be the wrong approach.

Per Phase 1.7 baseline timing on 4.7h:
| stage | wall | share |
|---|---:|---:|
| discrete_diarization (CPU, uses Inference.aggregate) | 12.53s | 3.8% |
| reconstruction_start (CPU numpy) | 6.85s | 2.1% |
| **combined** | **19.38s** | **5.9%** |

If moved to GPU with ≥5× speedup per stage, saves ~15s → ~4.5% E2E on 4.7h.

## 5.2.A — GPU `Inference.aggregate`

### Current implementation

`core/inference.py::Inference.aggregate` iterates over chunks, computing:
```python
for chunk, score in scores:
    mask = 1 - np.isnan(score)
    np.nan_to_num(score, copy=False, nan=0.0)
    start_frame = frames.closest_frame(chunk.start + 0.5 * frames.duration)
    aggregated_output[start_frame:start_frame+F] += score * mask * hamming * warmup
    overlapping_chunk_count[start_frame:start_frame+F] += mask * hamming * warmup
    aggregated_mask[start_frame:start_frame+F] = np.maximum(
        aggregated_mask[start_frame:start_frame+F], mask
    )
```

### GPU rewrite

The key primitive is `torch.index_add_` (for sum) and `torch.scatter_reduce_(reduce='amax')` (for max). Both are native GPU ops with efficient parallel implementations — the problem that killed the CPU version (ufunc.at serializing for duplicate indices) is specifically what GPU scatter handles well.

```python
def aggregate_gpu(scores_data: torch.Tensor,  # (C, F, K) fp32 on device
                  start_frames: torch.Tensor,  # (C,) int64 on device
                  num_frames: int,
                  weight: torch.Tensor,        # (F, 1) fp32 on device
                  ):
    C, F, K = scores_data.shape
    mask = ~torch.isnan(scores_data)
    score_clean = torch.where(mask, scores_data, 0.0)

    # Global flat frame indices for scatter
    offsets = torch.arange(F, device=device)
    global_idx = (start_frames[:, None] + offsets[None, :]).reshape(-1)  # (C*F,)

    mask_f = mask.float()
    weighted_score = (score_clean * mask_f * weight).reshape(-1, K)
    weighted_mask = (mask_f * weight).reshape(-1, K)
    mask_presence = mask_f.reshape(-1, K)

    # Scatter-add — GPU parallel reduction over duplicate indices.
    agg_out = torch.zeros((num_frames, K), device=device, dtype=torch.float32)
    agg_out.index_add_(0, global_idx, weighted_score)

    overlap = torch.zeros_like(agg_out)
    overlap.index_add_(0, global_idx, weighted_mask)

    agg_mask = torch.zeros_like(agg_out)
    agg_mask.scatter_reduce_(0,
        global_idx.unsqueeze(1).expand(-1, K),
        mask_presence,
        reduce='amax',
    )

    return agg_out, overlap, agg_mask
```

### Why this is safe on GPU where it failed on CPU

| aspect | CPU (`np.add.at`) | GPU (`index_add_`) |
|---|---|---|
| duplicate index handling | serial atomic loop (slow) | parallel atomics (fast) |
| contiguous-stride optimization | DISABLED by scatter | N/A — GPU is already parallel |
| memory bandwidth | cache-miss per scatter | HBM parallel access |

The core reason: GPU atomics are designed for the duplicate-index case; CPU atomics are a fallback that disables the compiler's vectorizer.

### VRAM budget

For 4.7h with ~4000 chunks × 500 frames × 8 classes = 16 MB per intermediate tensor. Well under the 50 MB clustering budget. Non-issue.

### Correctness

Scipy parity verifiable with fixed-seed synthetic inputs. The GPU scatter_reduce_(reduce='amax') is not deterministic for duplicate indices; may produce slightly different ordering than numpy's np.maximum.at. For the max op this doesn't matter (max is commutative + associative). For the sum we care about ordering only at fp32 precision, where the worst case is ~1e-6 relative error per accumulation step.

### Expected speedup

On N=4000 chunks × 500 frames: CPU loop ~12s. GPU three-scatter ~1.5-2s (memory-bound on A6000 HBM). **~6-8× stage speedup**.

## 5.2.B — GPU `SpeakerDiarization.reconstruct`

### Current implementation

```python
for c, (cluster, (chunk, segmentation)) in enumerate(zip(hard_clusters, segmentations)):
    for k in np.unique(cluster):
        if k == -2: continue
        clustered_segmentations[c, :, k] = np.max(segmentation[:, cluster == k], axis=1)
```

### GPU rewrite via index_add / scatter_reduce

```python
def reconstruct_gpu(seg_data: torch.Tensor,       # (C, F, S) fp32 on device
                    hard_clusters: torch.Tensor,  # (C, S) int64 on device
                    num_clusters: int,
                    ):
    C, F, S = seg_data.shape
    # Build valid-cluster mask
    valid = hard_clusters >= 0  # (C, S)
    # Remap -2 sentinel to 0 safely (we mask below)
    clamped = hard_clusters.clamp_min(0)  # (C, S)

    # For each (c, f, s) with valid[c, s], contribute seg_data[c, f, s] to
    # output[c, f, clamped[c, s]] via max reduction.
    # Flatten: index into (C*num_clusters*F, ) buffer
    out = torch.full(
        (C, F, num_clusters),
        float('-inf'),
        device=device,
        dtype=torch.float32,
    )

    # Index tensor: (C, F, S) → global position (c, f, k) where k=clamped[c, s]
    c_idx = torch.arange(C, device=device)[:, None, None].expand(C, F, S)
    f_idx = torch.arange(F, device=device)[None, :, None].expand(C, F, S)
    k_idx = clamped[:, None, :].expand(C, F, S)
    valid_b = valid[:, None, :].expand(C, F, S)

    values = torch.where(valid_b, seg_data, float('-inf'))

    # scatter_reduce with amax
    flat_idx = (c_idx * (F * num_clusters) + f_idx * num_clusters + k_idx).reshape(-1)
    flat_values = values.reshape(-1)
    out_flat = out.reshape(-1)
    out_flat.scatter_reduce_(0, flat_idx, flat_values, reduce='amax', include_self=True)

    # Replace -inf with NaN (original returned NaN for empty slots)
    any_valid = valid.any(dim=1)  # (C, S) — which clusters appear in this chunk
    # ... (cluster-presence mask similar to before)
    result = torch.where(out != float('-inf'), out, float('nan'))
    return result
```

### VRAM budget

Intermediate `(C, F, S)` tensor = same size as `seg_data`. Flat scatter source `(C*F*S,)` small int64 → 4000 × 500 × 6 × 8 = 96 MB on worst case. Tight; may need chunking by C.

Alternative: reduce-by-groups pattern — since within each chunk, num_active_clusters ≤ local_num_speakers, can do per-chunk `torch.scatter_reduce` on a (F, num_clusters) buffer and batch in chunks of 32.

### Expected speedup

Similar reasoning to aggregate: 5-10× on the reconstruct stage = ~5-6s saved on 4.7h.

## Combined impact

On 4.7h:
- aggregate GPU: saves ~10s out of 12.5s = ~3% E2E
- reconstruct GPU: saves ~5s out of 6.9s = ~1.5% E2E
- **total: ~4.5% E2E on 4.7h**

On 2.2h:
- aggregate: saves ~3.5s out of 4.3s
- reconstruct: saves ~2s out of 2.4s
- **total: ~5.5% E2E on 2.2h**

## Risks

1. **Determinism**: `index_add_` and `scatter_reduce_` are non-deterministic on CUDA when duplicate indices contend. For sum the result is within 1 ULP; for max it's bitwise-identical.
2. **VRAM peaks**: Both rewrites temporarily allocate a CxFxSxK-ish tensor. For 4.7h/8-spk/6 local speakers worst case is ~100 MB — within the Phase A ceiling, but needs a chunked fallback for stress cases.
3. **Upstream-ability**: pyannote upstream may not have torch.scatter_reduce available on all versions. Would need a version guard.

## Recommendation

**Implement in a future session.** Estimated 1-2 days with correctness tests, VRAM validation, and benchmark measurement. This is the most promising remaining GPU-port target because the sequential-CPU-loop nature (which killed the Phase 3.5 CPU attempt) becomes a STRENGTH on GPU with scatter primitives.

The other stages aren't worth porting:
- `embeddings` (161s) already GPU-bound; further gains require model changes
- `clustering_start` (138s, of which ~12s is linkage) — Lance-Williams is the last CPU-native holdout and the GPU attempt showed it's not accelerate-able without fused CUDA kernels (Phase 5.1-like territory)
- `segmentation` (11s) already GPU-bound
