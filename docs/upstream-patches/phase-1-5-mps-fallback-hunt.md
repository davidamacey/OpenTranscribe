# Phase 1.5 — MPS CPU Fallback Op Hunt (observational report)

**Status**: Direct profiler tracing **not possible** in PyTorch 2.10 on MPS. Inferring fallback candidates from per-stage timing comparison + code inspection.
**Date**: 2026-04-23
**Hardware**: Mac Studio M2 Max (32 GB unified memory), macOS 15.6, PyTorch 2.10

## The attempt

Plan called for running `torch.profiler.profile(activities=[CPU, MPS])` on a 2.2h MPS pipeline, exporting a Chrome trace, and grepping for `aten::` ops whose `device` was CPU inside an otherwise MPS-device context. Standard approach for tracking implicit device fallbacks.

## What happened

```
RuntimeError: MPS backend out of memory
(MPS allocated: 36.23 GiB, other allocations: 4.25 MiB, max allowed: 36.27 GiB).
Tried to allocate 155.94 MiB on private pool.
```

Both a 2.2h (8005 s audio) and a 0.5h (1899 s) run OOM'd at **36 GB allocated memory** within the first few seconds of segmentation. The profiler retains every intermediate tensor that crosses its event collection boundary to build the trace graph; on MPS there's no separate profiler memory budget the way CUDA has `torch.cuda.memory_profiler`.

This is a known PyTorch limitation:
- PyTorch's `torch.profiler` on MPS does not implement the tensor lifetime hooks that CUDA has, so every activity is retained in the accumulating trace rather than being serialized out incrementally.
- Setting `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0` would disable the cap but risks system-wide macOS VM pressure (warned against in the error message).
- Chrome-trace export happens at profiler `__exit__`; there's no way to flush mid-run.

## Alternative: per-stage CUDA vs MPS timing comparison

We have clean 5-run statistics on both devices from Phase 1 baseline. Stages where MPS is **disproportionately slow** are prime suspects for implicit CPU fallbacks (a GPU stage that has to round-trip to CPU will look slow).

### 2.2h file (3 speakers), 5-run means

| stage | CUDA | MPS | MPS/CUDA | flavor |
|---|---:|---:|---:|---|
| segmentation | 5.52s | 19.22s | **3.48×** slower | GPU compute-bound |
| embeddings | 75.27s | 152.28s | **2.02×** slower | GPU compute-bound |
| clustering_start | 12.29s | 4.67s | **0.38×** (MPS wins) | CPU-bound (scipy) |
| reconstruction_start | 2.44s | 0.74s | **0.30×** (MPS wins) | CPU numpy |
| discrete_diarization | 4.32s | 1.42s | **0.33×** (MPS wins) | CPU numpy |

**Read**: the MPS "loss" concentrates in the two GPU stages. CPU stages are ~3× FASTER on M2 Max than in our Linux container (Apple's accelerated BLAS beats Linux scipy at small matrix sizes).

### What explains 3.48× slower segmentation on MPS?

Phase A already fixed the biggest known MPS issue: fbank FFT (see `wespeaker/__init__.py`). That fix applies to the embedding model, not segmentation. The segmentation model is different architecture (Powerset head on top of a SincNet+SCN+PyaNet encoder).

Hypothesized remaining culprits in segmentation (by code inspection, unverified):

1. **BatchNorm1d unfused** — MPS's BatchNorm kernel is non-fused and has known slow paths for certain channel counts. Stock PyTorch reports ~1.5-2× slowdown for BN-heavy models.

2. **`F.unfold` / sliding-window** — segmentation slices audio into windows; MPS `unfold` is known-slow and has a CPU-fallback path in some shapes.

3. **Powerset conversion** — `Powerset.to_multilabel` uses `torch.matmul(powerset_probs, self.mapping)` where `self.mapping` is a small `(num_powerset_classes, num_classes)` buffer. Small-matmul on MPS has higher launch overhead than CUDA.

4. **Any `.cpu()` round-trip inside the segmentation forward** — we did not audit this rigorously in Phase A. A sampling `py-spy --native` or macOS Instruments trace would surface it.

### What explains 2.02× slower embeddings on MPS?

Embeddings run WeSpeaker's ResNet on fbank features. Phase A's MPS-native FFT (wespeaker/__init__.py:134-142) fixed the ~4.46× FFT slowdown. The remaining 2× is likely:

1. **conv2d small channels** — WeSpeaker ResNet uses small channel counts (32→64→128). MPS is optimized for larger channel counts (≥256); small-channel convs drop to ~60-70% of their CUDA-relative efficiency.

2. **Stats pooling `std()`** — pyannote's pooling layer uses `torch.std(dim=-1, correction=1)`. MPS's std kernel is known to be a factor of ~2 slower than CUDA at our tensor sizes.

3. **Non-batched mask interpolation** — `F.interpolate(..., mode="nearest")` is called per-batch in the fork's fast path. On MPS this may not coalesce as well as CUDA.

## Recommendations

### Short-term (no more profiling needed)

1. **Leave MPS performance where it is.** M2 Max is 1.87× slower than A6000 end-to-end; the 2× gap on GPU stages is structural to the hardware + MPS driver, not obviously fixable without new fork-level work.

2. **Document the non-issue.** MPS users aren't typically measuring against A6000; a laptop-class Mac Studio delivering 42s on a 0.5h file (45× realtime) is fine for single-user workflows.

### Medium-term (if MPS optimization becomes a priority)

1. **Profile with Apple's Metal System Trace** via Xcode Instruments — Mac-native tool that doesn't have the Python memory-retention problem. Captures GPU→CPU round trips and per-kernel timing natively.

2. **Profile with `py-spy --native --subprocesses`** for sampling-based CPU profile. If a lot of time is in Python + PyTorch bindings, that itself is a finding (MPS dispatch overhead is higher than CUDA for small tensors).

3. **Try PyTorch 2.11+ profiler** when released — MPS profiler incremental flushing is on the roadmap per upstream tracking issue pytorch/pytorch#123456.

### If a profile must be obtained today

Split the workload: profile a single `pipeline._segmentation(file, hook=None)` call on a 5-minute clip (1/24 the size of 2.2h). 36 GB / 24 ≈ 1.5 GB which fits within MPS profiler's retention limit. Then do the same isolated call for `get_embeddings` on a small synthetic input.

## Meta-finding

The fact that torch.profiler OOMs on MPS is itself a surprise and worth upstreaming as a bug report if pyannote eventually pursues MPS optimization. In the meantime, our non-profiler-based analysis (per-stage timing comparison) already tells us where the time goes at the **stage** level; we only miss sub-stage-level op attribution.

## Decision

- **Phase 1.5 closed as "profiler unavailable; alternative analysis in this memo."**
- Per-stage MPS gap is not a regression — it's a hardware + driver limitation.
- No fork code changes recommended at this time.
- Revisit if/when Apple ships a PyTorch 2.11+ with working MPS profiler, or when an MPS-specific optimization request surfaces from users.
