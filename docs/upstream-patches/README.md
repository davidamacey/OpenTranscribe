# PyAnnote v4 GPU Optimization Patches

These patches contain GPU and MPS optimization improvements for pyannote-audio v4, benchmarked on NVIDIA RTX A6000 (48GB) and Mac Studio M2 Max (32GB).

## Results

### CUDA (RTX A6000)
- **1.28x overall speedup** (718s -> 563s across 5 files, 0.5h-4.7h)
- **1.44x embedding stage speedup** (consistent across all file sizes)
- **66-68% VRAM reduction** (variable 7-17GB -> constant 5.6GB)
- **Zero accuracy degradation** (speaker counts +/-1, segments +/-1.8%)

### MPS (Mac Studio M2 Max)
- **1.17x overall speedup** (47.7s -> 40.8s, 5 runs, std 0.1s)
- **1.21x embedding stage speedup** (consistent for 3-5 speaker files)
- **MPS-native FFT**: 4.46x faster than stock CPU fallback (at batch=32)
- **Zero accuracy degradation** (speakers match, segments +/-0.5%)

### Memory Safety (All Devices)
- **115x CPU RAM reduction** for long files (58.8GB -> 39MB for 4.7h/21-speaker)
- Prevents OOM crashes on machines with 8-16GB RAM
- Constant memory usage regardless of file length or speaker count

## Architecture

All changes live in a single fork branch (`gpu-optimizations`) that can be pip-installed:

```bash
pip install git+https://github.com/davidamacey/pyannote-audio.git@gpu-optimizations
```

### Modified Files

| File | Changes | Devices |
|------|---------|---------|
| `pipelines/speaker_diarization.py` | Vectorized chunks, memory-safe batching, adaptive batch size, TF32, CUDA streams, direct model calls, empty_cache | CUDA + MPS + CPU |
| `pipelines/speaker_verification.py` | Pinned memory transfers, MPS device path | CUDA + MPS |
| `core/inference.py` | Pinned memory for segmentation | CUDA |
| `models/embedding/wespeaker/__init__.py` | MPS-native FFT with CPU fallback | MPS |

## Patches (Legacy — Use Fork Instead)

### 01: inference-pinned-memory.patch (16 lines)
Adds pinned memory + non-blocking transfers for segmentation model inference.
- File: `pyannote/audio/core/inference.py`
- Impact: ~5% speedup on H2D data transfer during segmentation
- Backward compatible: only activates on CUDA devices

### 02: speaker-diarization-gpu-optimization.patch (444 lines)
Main optimization patch for the speaker diarization pipeline.
- File: `pyannote/audio/pipelines/speaker_diarization.py`
- Changes:
  - **Vectorized chunk extraction**: `torch.unfold()` replaces individual `crop()` calls
  - **Memory-efficient batch indexing**: per-batch `_get_batch_waveforms()` replaces `repeat_interleave()`
  - **Vectorized mask selection**: numpy broadcasting replaces per-chunk loops
  - **TF32 re-enablement**: Re-enables TensorFloat-32 after segmentation for embedding inference
  - **Adaptive batch size**: Auto-selects 64-256 based on free GPU VRAM or MPS recommended_max_memory
  - **Double-buffered prefetch**: CUDA stream prefetch for embedding batches
  - **Direct model calls**: Bypasses PyAnnote wrapper overhead
  - **VRAM cleanup**: `empty_cache()` between pipeline stages

### 03: speaker-verification-pinned-memory.patch (50 lines)
Adds pinned memory + non-blocking transfers for embedding model forward pass.
- File: `pyannote/audio/pipelines/speaker_verification.py`
- Impact: ~5% speedup on H2D data transfer during embedding extraction
- Backward compatible: only activates on CUDA devices, MPS path skips pin_memory

## Applying Patches

```bash
cd /path/to/pyannote-audio

# Apply all patches
for patch in /path/to/upstream-patches/*.patch; do
    patch -p2 < "$patch"
done

# Or apply individually
patch -p2 < 01-inference-pinned-memory.patch
patch -p2 < 02-speaker-diarization-gpu-optimization.patch
patch -p2 < 03-speaker-verification-pinned-memory.patch
```

## Benchmark Evidence

Full results in `benchmark/results/`:
- `benchmark_stock_latest.json` -- stock PyAnnote v4 baseline
- `benchmark_optimized_latest.json` -- all patches applied

Run your own benchmark:
```bash
python scripts/benchmark-pyannote-direct.py --both --gpu-index 0
```

## Compatibility

- **PyAnnote v4**: Tested against commit `78c0d16a`
- **PyTorch 2.3+**: Required for MPS FFT (graceful fallback for older)
- **PyTorch 2.x**: Required for torch.compile and TF32 support
- **CUDA 12+**: Recommended for best performance
- **Ampere+ GPUs**: Required for TF32 benefit (pre-Ampere: safe, no benefit)
- **All GPUs**: Adaptive batch size works from 6GB to 256GB VRAM
- **Apple Silicon**: M1/M2/M3/M4, 8GB-192GB unified memory
- **Low-RAM machines**: Memory-safe indexing prevents OOM (constant 39MB per batch)
