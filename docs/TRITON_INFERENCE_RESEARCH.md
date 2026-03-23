# Triton Inference Server Research

## Problem Statement

At high GPU concurrency (10+ files), the current thread-based model sharing shows diminishing returns. Each thread runs its own inference independently, competing for GPU SMs. A centralized inference server with dynamic batching could consolidate GPU work across all concurrent files into optimal batches.

## Current Architecture

```
Thread 1: [VAD → Whisper(batch=32) → PyAnnote(batch=32)] ──┐
Thread 2: [VAD → Whisper(batch=32) → PyAnnote(batch=32)] ──┤── All on same GPU
Thread N: [VAD → Whisper(batch=32) → PyAnnote(batch=32)] ──┘   (SM contention)
```

Each thread independently submits batch=32 to the GPU. With 10 threads, that's 10 separate kernel launches competing for SM time.

## Proposed Architecture (Triton)

```
Thread 1: [VAD → request] ──┐                              ┌── [response → postprocess]
Thread 2: [VAD → request] ──┤── Triton Server ──┤── [response → postprocess]
Thread N: [VAD → request] ──┘   (dynamic batch) └── [response → postprocess]
                                    │
                                    ▼
                              Single GPU batch
                              (batch=320 in one pass)
```

## Model Compatibility

| Model | Framework | Triton Support | Export Path | Priority |
|-------|-----------|---------------|-------------|----------|
| PyAnnote Embeddings (WeSpeaker) | PyTorch | Native | TorchScript or ONNX | HIGH — 53% of GPU time |
| PyAnnote Segmentation | PyTorch | Native | TorchScript or ONNX | MEDIUM — 3% of GPU time |
| Silero VAD | PyTorch | Native | ONNX (already available) | LOW — runs on CPU |
| Whisper (CTranslate2) | Custom CUDA | Not direct | See alternatives below | HIGH but complex |

### Whisper on Triton — Options

1. **TensorRT-LLM Whisper**: NVIDIA has official Whisper TensorRT support in `TensorRT-LLM` repo. Fastest option but requires model conversion and TRT engine build per GPU architecture.

2. **ONNX Runtime**: Export Whisper to ONNX, run via Triton's ONNX backend. Moderate speed, broad compatibility.

3. **Custom CTranslate2 Backend**: Write a Triton backend wrapper around CTranslate2. Preserves current int8_float16 quantization and custom CUDA kernels. Most work but keeps existing performance characteristics.

4. **faster-whisper-server**: Existing project that wraps faster-whisper in an OpenAI-compatible API server. Not Triton but provides request batching. Could be a simpler intermediate step.

## Expected Impact

### Where Triton Helps Most
- **Embedding extraction** (53% of GPU time): 10 files × batch_size=32 = 320 chunks could be batched into a single forward pass instead of 10 separate ones. Expected 2-4x throughput improvement at high concurrency.
- **Segmentation**: Smaller model, less impact but still benefits from consolidated batching.

### Where Triton Helps Less
- **Whisper transcription** (41% of GPU time): CTranslate2 already has efficient CUDA kernels. The batched pipeline internally manages GPU scheduling. Triton overhead might offset gains unless using TensorRT.
- **Low concurrency (1-4)**: Current thread model works perfectly with linear scaling. Triton adds latency overhead that isn't worth it at low concurrency.

## Implementation Complexity

| Approach | Effort | Risk | Expected Speedup |
|----------|--------|------|-----------------|
| PyAnnote embeddings only via Triton | Medium | Low | 20-30% at conc=10+ |
| Full PyAnnote (seg + embed) via Triton | Medium-High | Low | 25-35% at conc=10+ |
| Whisper TensorRT-LLM | High | Medium | 30-50% at conc=10+ |
| Full pipeline via Triton | Very High | High | 40-60% at conc=10+ |
| faster-whisper-server (intermediate) | Low | Low | 10-15% at conc=10+ |

## Existing Projects & References

- **NVIDIA Triton**: https://github.com/triton-inference-server/server
- **TensorRT-LLM Whisper**: https://github.com/NVIDIA/TensorRT-LLM/tree/main/examples/whisper
- **faster-whisper-server**: https://github.com/fedirz/faster-whisper-server
- **Triton PyTorch backend**: https://github.com/triton-inference-server/pytorch_backend
- **wyoming-faster-whisper**: https://github.com/rhasspy/wyoming-faster-whisper

## Recommended Path

### Phase 1: PyAnnote Embeddings via Triton (Highest ROI)
1. Export WeSpeaker embedding model to TorchScript/ONNX
2. Deploy as Triton model with dynamic batching enabled
3. Modify `diarizer.py` to send embedding requests to Triton instead of direct model calls
4. Keep Whisper on CTranslate2 (already fast)
5. Benchmark: compare concurrent=10 throughput before/after

### Phase 2: Evaluate Whisper Alternatives
1. Benchmark TensorRT-LLM Whisper vs CTranslate2 at batch=32
2. If TensorRT is faster, add as Triton model
3. If not, keep CTranslate2 with current thread model

### Phase 3: Full Triton Pipeline
1. All models served via Triton
2. Celery workers become thin clients that send requests and process responses
3. Triton handles all GPU scheduling, batching, and memory management

## Decision Criteria

Move to Triton when:
- Concurrent file processing regularly exceeds 8-10 files
- GPU SM utilization at high concurrency drops below 80%
- Per-file slowdown at high concurrency exceeds 5x single-file time
- Multi-GPU deployments need unified inference management

Stay with current thread model when:
- Typical concurrency is 1-6 files
- Single-GPU deployment
- Simplicity is prioritized over maximum throughput
