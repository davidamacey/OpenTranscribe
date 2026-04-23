# Phase 5.3 — MPS-Specific Optimization Feasibility (memo)

**Status**: Feasibility analysis. No code shipped.
**Projected impact**: 10-20% on MPS 2.2h if segmentation/embedding-stage MPS fallbacks are addressed. CUDA users unaffected.
**Dependency**: Requires a working MPS profiler (PyTorch 2.11+) or Xcode Instruments trace to move from speculation to targeted fixes.

## Context

Per Phase 1 baseline + Phase 1.5's profiler failure:

| stage | CUDA 2.2h | MPS 2.2h | MPS/CUDA |
|---|---:|---:|---:|
| segmentation | 5.52s | **19.22s** | 3.48× slower |
| embeddings | 75.27s | **152.28s** | 2.02× slower |
| (CPU stages win on MPS) | 19.05s | 6.83s | 0.36× |

MPS 2.2h total: 181.95s vs CUDA 101.47s → **1.79× slower end-to-end**. The 80-second gap is almost entirely in segmentation (+13.7s) and embeddings (+77s).

Phase A's MPS work addressed the biggest known win (native FFT in WeSpeaker, 4.46× fbank speedup). The remaining gap is smaller, structural, and suspected to be distributed across many small inefficiencies rather than one fixable hot spot.

## Candidate optimizations (code-inspection based; unverified)

### 5.3.A — Replace `std()` in stats pooling

**Location**: `pyannote/audio/models/blocks/pooling.py::StatsPool.forward` — `sequences.std(dim=-1, correction=1)`

**Observation**: MPS's `std` kernel is non-optimized per PyTorch issue tracker (~2× slower than CUDA). Equivalent using `sqrt(var)` is sometimes faster on MPS.

**Proposed**:
```python
mean = sequences.mean(dim=-1, keepdim=True)
var = ((sequences - mean) ** 2).mean(dim=-1)  # unbiased=False variant
std = torch.sqrt(var.clamp_min(1e-8))
```

**Expected speedup**: 0-15% on stats pooling. Unclear since PyTorch's `std` may have been improved in 2.10.

**Risk**: `correction=1` (Bessel's correction) changes the divisor; if the pooling layer was trained with Bessel's correction, switching to biased variance would produce slightly different embeddings. **DER regression likely** unless the model is retrained. **Do not ship without retraining.**

### 5.3.B — Pre-allocate workspace tensors in embedding forward

**Location**: `pyannote/audio/pipelines/speaker_diarization.py:~730-770` (the fast-path embedding loop).

**Observation**: The loop allocates `fbank`, `imasks`, `emb_tensor` per batch. On CUDA this is cheap (caching allocator); on MPS the allocator has higher per-allocation overhead.

**Proposed**: pre-allocate `fbank_buf`, `imask_buf` of the maximum expected batch shape at pipeline init; use `.copy_()` to reuse buffers.

**Expected speedup**: 2-5% on embedding stage (MPS only). Zero CUDA impact (CUDA allocator already caches).

**Risk**: low. Adds ~100 MB resident VRAM on MPS. Within unified-memory headroom.

### 5.3.C — Replace small-tensor `F.interpolate` with manual indexing

**Location**: Mask interpolation in `get_embeddings` (line ~740):
```python
imasks = F.interpolate(cur_mk.unsqueeze(1), size=num_frames, mode="nearest").squeeze(1)
```

**Observation**: `F.interpolate` with `mode="nearest"` on MPS has known launch-overhead issues for small tensors (batch=16, small spatial dims).

**Proposed**: Replace with manual index-broadcast:
```python
scale = cur_mk.shape[-1] / num_frames
idx = (torch.arange(num_frames, device=cur_mk.device) * scale).long()
imasks = cur_mk[:, idx]
```

**Expected speedup**: ~1% on embedding stage on MPS.

**Risk**: low. Numeric parity with nearest-neighbor interpolation is exact for `mode="nearest"`.

### 5.3.D — Profile-driven op-level audit (blocker: MPS profiler)

The three above are speculation based on PyTorch issue tracker chatter + code inspection. To justify implementing any of them, we need to *actually measure* which ops are slow. As Phase 1.5 documented, `torch.profiler` OOMs on MPS at realistic workload sizes.

**Workaround**: run a reduced-scope profiler on a 5-minute clip (1/24 of 2.2h). 36 GB profiler limit / 24 ≈ 1.5 GB required → fits.

**Alternative**: Xcode Instruments "Metal System Trace" schema, driven via `xctrace` CLI. This is Mac-native, doesn't go through torch.profiler at all, and captures GPU→CPU round trips. Would need a 30-minute setup session.

## Recommendation

**Defer all three micro-optimizations** until:
1. A working MPS profiler (either PyTorch 2.11+ or Xcode Instruments setup) is available, AND
2. An MPS user reports the 1.79× slowdown as a real workflow problem.

**Rationale**: MPS 2.2h at 182s = 44× realtime. That's fine for single-user workflows on a laptop/Mac Studio. The 80-second gap vs CUDA is expected hardware + driver cost, not broken code. Speculative optimizations without profile data risk regressing quality (see 5.3.A's `std` concern) or adding complexity for <5% gain.

## If MPS optimization becomes a priority

Ordered by ROI:

1. **Set up Xcode Instruments trace** — 30 min. Gives ground truth.
2. **Implement 5.3.B (preallocated buffers)** — 1 hour. Low risk, 2-5% gain.
3. **Implement 5.3.C (manual interpolation)** — 30 min. Low risk, ~1% gain.
4. **Investigate 5.3.A (std replacement)** — only if Instruments shows `std` is a hot op. Requires retraining if shipped.
5. **Deep dive on segmentation BatchNorm** — only if Instruments shows BN is hot. Options: fuse BN into conv (PyTorch `torch.fx`), switch to LayerNorm (model retrain required).

Total optimistic ceiling: 10-15% on MPS 2.2h = ~160s instead of 182s. Still 1.57× slower than CUDA 101s, so even "perfect" MPS optimization doesn't close the hardware gap.

## Final note

This memo is intentionally conservative. Based on Phase 1 data MPS is a usable platform already (DER matches CUDA exactly, VRAM behavior is predictable, wall time is acceptable for single-user workflows). The optimization candidates here are incremental polish, not structural wins. If there's a structural MPS optimization still on the table, it's more likely to live in Apple's MPS driver (out of our control) or in a PyTorch-level MPS backend rewrite (also out of our control).
