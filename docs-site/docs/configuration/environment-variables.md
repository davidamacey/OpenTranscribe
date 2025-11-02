---
sidebar_position: 1
---

# Environment Variables

Comprehensive reference for all OpenTranscribe environment variables.

## Quick Reference

Edit `.env` file in installation directory. See `.env.example` for full template.

## Database

```bash
POSTGRES_HOST=postgres
POSTGRES_PORT=5176
POSTGRES_USER=postgres
POSTGRES_PASSWORD=auto_generated_on_install
POSTGRES_DB=opentranscribe
```

## GPU Configuration

```bash
TORCH_DEVICE=auto  # or: cuda, mps, cpu
USE_GPU=auto  # or: true, false
GPU_DEVICE_ID=0  # Which GPU (0, 1, 2, etc.)
COMPUTE_TYPE=auto  # or: float16, float32, int8
BATCH_SIZE=auto  # or: 8, 16, 32
```

## AI Models

```bash
WHISPER_MODEL=large-v2  # or: tiny, base, small, medium, large-v3
MIN_SPEAKERS=1
MAX_SPEAKERS=20
HUGGINGFACE_TOKEN=hf_your_token_here
MODEL_CACHE_DIR=./models
```

## LLM Integration

```bash
LLM_PROVIDER=  # vllm, openai, anthropic, ollama, openrouter
VLLM_API_URL=http://localhost:8000/v1
OPENAI_API_KEY=sk-xxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxx
```

## Multi-GPU Scaling

```bash
GPU_SCALE_ENABLED=false
GPU_SCALE_DEVICE_ID=2
GPU_SCALE_WORKERS=4
```

## Ports

```bash
FRONTEND_PORT=5173
BACKEND_PORT=5174
FLOWER_PORT=5175
POSTGRES_PORT=5176
REDIS_PORT=5177
MINIO_PORT=5178
MINIO_CONSOLE_PORT=5179
OPENSEARCH_PORT=5180
```

## Next Steps

- [GPU Setup](../installation/gpu-setup.md)
- [Multi-GPU Scaling](./multi-gpu-scaling.md)
- [LLM Integration](../features/llm-integration.md)
