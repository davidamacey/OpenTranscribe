# Phase 5.1 — CUDA Graphs for Embedding Forward (feasibility memo)

**Status**: Feasibility analysis. No code shipped.
**Projected impact**: ±0.5% E2E on A6000 at the current Phase-A configuration. Likely not worth the complexity.

## Context

The embedding stage runs `compute_fbank` + `resnet` forward on fixed-shape batches of `16 × 80000` samples (per Phase A's pinned `embedding_batch_size=16`). Each batch is one cuDNN forward + fbank FFT. On the 4.7h benchmark:

| stage | wall | batch count | ms/batch |
|---|---:|---:|---:|
| embeddings | 161.56s | ~625 | ~258 ms/batch |

The per-batch cost is dominated by actual GPU compute (ResNet + FFT), not kernel launch overhead. CUDA Graphs shines when **launch overhead ≫ kernel compute time**; that's not the regime here.

## What CUDA Graphs would do

`torch.cuda.graph(g)` captures a sequence of kernel launches into a replayable graph, amortizing:
- Python → C++ dispatch (~10–50 µs per op)
- CUDA driver API launch latency (~5–20 µs per kernel)
- cuDNN algorithm lookup (cached after first call, but still ~1–5 µs)

For the embedding forward, the graph would capture `compute_fbank(x) → ResNet(x) → stats pool`. Each batch has maybe 50–100 kernel launches; total launch overhead at 15 µs/kernel is 0.75–1.5 ms per batch.

On 625 batches of a 4.7h run, that's **~0.5–1s saved** out of 161s embedding = **~0.3–0.6% stage speedup / ~0.15–0.3% E2E**.

## Implementation complications

1. **Dynamic fbank shape**: `compute_fbank` pads sequences, so the output shape depends on input-chunk active-frame count. Graph capture requires identical tensor shapes on every replay. Would need pre-padding to a fixed max length (easy) or per-shape graph cache (higher complexity).

2. **FFT plan caching** (WeSpeaker internal): the fbank FFT is computed through `torch.fft.rfft`, which maintains a per-shape plan cache. Graph capture takes a snapshot of this cache; if a later replay triggers a re-plan, the graph becomes stale. Workaround: warmup one fixed-shape forward before capture so the plan is populated.

3. **Existing CUDA streams**: the fork's embedding pipeline uses a double-buffered prefetch pattern (`transfer_stream`, Phase A). CUDA Graphs can capture streams but the interaction with the prefetch is non-trivial — would need a redesign where the capture happens on the compute stream after prefetch completes.

4. **Error handling**: Graph replay raises an exception if any in-graph kernel fails, not just for the failing kernel. Debugging is harder.

## When it WOULD be worth doing

- Smaller batch sizes (bs=1-4) where launch overhead is a bigger fraction of per-batch time. Not our current config.
- Newer hardware (H100/B100) where raw kernel compute is faster (so launch overhead matters more relatively).
- Longer graphs (entire pipeline, not just one stage) where cumulative launch overhead adds up. Not achievable without significant refactoring because pyannote's pipeline has CPU work between GPU stages.

## Recommendation

**Do not implement.** The 0.15–0.3% E2E win doesn't justify the complexity, and the shape-invariance requirement would force us to abandon Phase A's variable-length-embedding optimization. Revisit if we move to H100-class hardware or shrink the embedding batch size.

## References

- [NVIDIA: CUDA Graphs](https://developer.nvidia.com/blog/cuda-graphs/)
- [PyTorch: torch.cuda.graph](https://pytorch.org/docs/stable/generated/torch.cuda.graph.html)
- Phase A embedding batch size analysis: `docs/diarization-vram-profile/README.md`
