# PyAnnote ONNX Pre-Conversion Guide

## Overview

PyAnnote models are converted to ONNX format **once and cached** for production use. There is **zero runtime conversion overhead** — models are loaded directly from disk.

## Why Pre-Convert?

❌ **Don't do this** (runtime conversion):
```python
# Slow: converts on every pipeline initialization
pipeline = Pipeline.from_pretrained("...")  # ~10-20s conversion
pipeline._setup_onnx_cpu(quantize=True)     # Exports + quantizes
```

✅ **Do this** (pre-cached):
```python
# Fast: uses cached models
python scripts/preconvert-onnx-models.py  # Run ONCE (~30s)
# ... then always uses cached models (~100ms load)
```

## Installation & Pre-Conversion

### 1. Install Dependencies
```bash
pip install onnx onnxruntime
```

### 2. Run Pre-Conversion (One-Time)
```bash
# Convert and cache models in default location (./models)
python scripts/preconvert-onnx-models.py

# Or specify custom cache directory
python scripts/preconvert-onnx-models.py --cache-dir /path/to/models

# Skip INT8 quantization (if disk space is critical)
python scripts/preconvert-onnx-models.py --no-quantize
```

**Output**:
```
======================================================================
PyAnnote → ONNX Conversion
======================================================================

[1/4] Loading PyAnnote pipeline...
[2/4] Exporting to ONNX FP32: ./models/onnx/pyannote_segmentation_fp32.onnx
   ✓ Saved 5.7 MB

[3/4] Quantizing to INT8: ./models/onnx/pyannote_segmentation_int8.onnx
   ✓ Saved 1.5 MB

[4/4] Verifying ONNX models...
   ✓ FP32 model verified (output shape: (1, 21, 1501))
   ✓ INT8 model verified (output shape: (1, 21, 1501))

======================================================================
✓ ONNX Models Ready!
======================================================================
  FP32 (5.7MB): ./models/onnx/pyannote_segmentation_fp32.onnx
  INT8 (1.5MB): ./models/onnx/pyannote_segmentation_int8.onnx

  Location: ./models/onnx
  Cache Dir: ./models

These models are now cached and will be reused on all subsequent runs.
No runtime conversion overhead!
```

### 3. Verify Cached Models
```bash
ls -lh models/onnx/
# pyannote_segmentation_fp32.onnx  5.7M
# pyannote_segmentation_int8.onnx  1.5M
```

## Usage in Code

### Automatic Loading (CPU ONNX Path)

```python
from pyannote.audio import Pipeline

# Load pipeline
pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")

# Enable CPU ONNX mode (loads cached models, no conversion)
pipeline._setup_onnx_cpu(quantize=True)  # Loads INT8 from cache

# Use normally
diarization = pipeline({"waveform": waveform, "sample_rate": 16000})
```

**What happens**:
1. ✅ Checks for cached `models/onnx/pyannote_segmentation_int8.onnx`
2. ✅ Loads it with ONNX Runtime (~100ms)
3. ✅ Patches segmentation.infer() to use ONNX
4. ✅ Embeddings still use PyTorch (on CPU or GPU, your choice)

### Benchmark Script

The benchmark script automatically detects cached models:

```bash
# Uses cached ONNX models (fast)
python scripts/benchmark-pyannote-direct.py --variant optimized_cpu

# Error if models not pre-converted:
# FileNotFoundError: ONNX models not found in ./models/onnx.
# Please pre-convert models once using:
#   python scripts/preconvert-onnx-models.py --cache-dir ./models
```

## Deployment

### Local Development

```bash
# Run once after cloning repo
python scripts/preconvert-onnx-models.py

# Verify
ls -lh models/onnx/

# Then use normally (no conversion overhead)
```

### Docker / CI/CD

Add to your Dockerfile or setup script:

```dockerfile
# Install dependencies
RUN pip install onnx onnxruntime

# Pre-convert models (one-time, baked into image)
RUN python scripts/preconvert-onnx-models.py

# Models are now cached in the image
```

Or in GitHub Actions:

```yaml
- name: Pre-convert ONNX models
  run: python scripts/preconvert-onnx-models.py
```

### Hosting Pre-Built Models

For air-gapped deployments or to reduce setup time, host models on Hugging Face:

```bash
# 1. Create a HF repo
huggingface-cli repo create opentranscribe-pyannote-onnx --type model

# 2. Upload cached models
huggingface-cli upload davidamacey/opentranscribe-pyannote-onnx \
  models/onnx/pyannote_segmentation_int8.onnx \
  pyannote_segmentation_int8.onnx

# 3. Users can download with one line
from huggingface_hub import hf_hub_download
model_path = hf_hub_download("davidamacey/opentranscribe-pyannote-onnx",
                              "pyannote_segmentation_int8.onnx")
```

## Configuration

### Model Cache Location

Set via environment variable:

```bash
# Default
export MODEL_CACHE_DIR=./models

# Custom location
export MODEL_CACHE_DIR=/var/cache/opentranscribe/models
python scripts/preconvert-onnx-models.py --cache-dir $MODEL_CACHE_DIR
```

### Quantization Options

```bash
# Enable INT8 quantization (recommended, 73% smaller)
python scripts/preconvert-onnx-models.py --quantize

# Disable quantization (if disk space unlimited)
python scripts/preconvert-onnx-models.py --no-quantize
```

## Performance

### Pre-Conversion (One-Time)
```
[2/4] Exporting to ONNX FP32: 5-10s
[3/4] Quantizing to INT8:     10-20s
[4/4] Verifying models:       5s
Total:                        ~20-35s (one-time)
```

### Production (Every Run)
```
Loading ONNX model from cache: 100-200ms (disk I/O)
No conversion overhead! ✓
```

### Model Sizes
- **FP32**: 5.7 MB (full precision)
- **INT8**: 1.5 MB (quantized, 73% smaller)

## Troubleshooting

### "ONNX models not found"
```
FileNotFoundError: ONNX models not found in ./models/onnx.
```

**Solution**: Run pre-conversion once:
```bash
python scripts/preconvert-onnx-models.py
```

### "onnxruntime not installed"
```
WARNING: onnxruntime not installed, ONNX CPU mode disabled
```

**Solution**: Install onnxruntime:
```bash
pip install onnxruntime
```

### Model output shapes don't match
```
AssertionError: Expected shape (1, 21, 1501), got (1, 21, 1500)
```

**Possible causes**:
- Different audio duration (use 10s dummy input)
- ONNX opset version mismatch (use opset 17+)

**Solution**: Re-run pre-conversion:
```bash
python scripts/preconvert-onnx-models.py
```

## Architecture Decision

### Why Pre-Convert Instead of Runtime Conversion?

| Approach | Pros | Cons |
|----------|------|------|
| **Pre-Convert (current)** | ✓ Zero runtime overhead ✓ Reproducible ✓ Cacheable | One-time setup |
| Runtime Convert | No setup | ✓ 10-20s delay per pipeline init ✓ Non-deterministic |

Pre-conversion is **production-ready**: models are deterministic, cached, and zero-overhead.

## Related Files

- `scripts/preconvert-onnx-models.py` — Pre-conversion script
- `reference_repos/pyannote-audio-optimized/src/pyannote/audio/pipelines/speaker_diarization.py` — Updated `_setup_onnx_cpu()` (loads cached only)
- `scripts/benchmark-pyannote-direct.py` — Benchmark script (uses cached models)
- `docs/GPU_OPTIMIZATION_RESULTS.md` — Full optimization results

## Next Steps

1. **Run pre-conversion** (one-time):
   ```bash
   python scripts/preconvert-onnx-models.py
   ```

2. **Verify cached models**:
   ```bash
   ls -lh models/onnx/
   ```

3. **Use in your code**:
   ```python
   pipeline._setup_onnx_cpu(quantize=True)
   ```

4. **Optional: Host on HF** for distribution

Done! Models are now cached and ready for production.
