---
sidebar_position: 2
---

# Multi-GPU Worker Scaling

For systems with multiple GPUs, OpenTranscribe supports parallel GPU workers to dramatically increase transcription throughput.

## Overview

**Standard Setup**: 1 GPU = 1 worker = 70x realtime (1-hour file in ~50 seconds)

**Scaled Setup**: 1 GPU = 4 workers = 280x realtime (4 files simultaneously)

## When to Use

Multi-GPU scaling is ideal for:
- Batch processing large numbers of files
- High-throughput production systems
- Systems with dedicated transcription GPU
- Workflows with concurrent uploads

## Hardware Example

```
GPU 0: NVIDIA RTX A6000 (49GB) - Local LLM (vLLM/Ollama)
GPU 1: RTX 3080 Ti (12GB) - Default worker (disabled when scaling)
GPU 2: NVIDIA RTX A6000 (49GB) - 4 parallel workers (scaled)
```

## Configuration

### Step 1: Configure Environment

Edit `.env`:

```bash
# Enable multi-GPU scaling
GPU_SCALE_ENABLED=true

# Which GPU to use for scaled workers
GPU_SCALE_DEVICE_ID=2

# Number of parallel workers
GPU_SCALE_WORKERS=4
```

### Step 2: Start with Scaling

```bash
# Development
./opentr.sh start dev --gpu-scale

# Production
./opentr.sh start prod --gpu-scale

# Reset with scaling
./opentr.sh reset dev --gpu-scale
```

## Performance

| Workers | Throughput | Example (4x 1-hour files) |
|---------|------------|---------------------------|
| 1 worker | 70x realtime | ~3 minutes (sequential) |
| 4 workers | 280x realtime | ~50 seconds (parallel) |

## VRAM Requirements

| Workers | Recommended VRAM | Supported Models |
|---------|------------------|------------------|
| 2 | 12GB+ | large-v2 |
| 4 | 24GB+ | large-v2 |
| 6 | 48GB+ | large-v2 |

## Monitoring

```bash
# Watch GPU usage
watch -n 1 nvidia-smi

# View scaled worker logs
docker compose logs -f celery-worker-gpu-scaled

# Monitor task queue
# Open: http://localhost:5175/flower
```

## Troubleshooting

### Out of Memory Errors

Reduce worker count:
```bash
GPU_SCALE_WORKERS=2  # instead of 4
```

### Poor GPU Utilization

Increase worker count (if VRAM available):
```bash
GPU_SCALE_WORKERS=6  # instead of 4
```

## Next Steps

- [GPU Setup](../installation/gpu-setup.md)
- [Hardware Requirements](../installation/hardware-requirements.md)
- [Environment Variables](./environment-variables.md)
