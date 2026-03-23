# vLLM Optimization for OpenTranscribe LLM Processing

## v0.4.0 LLM Feature Notes

### Organization Context

Admins can set an **organization context** (e.g., department name, project description, participant roster) that is automatically prepended to all LLM prompts. This improves speaker identification and summary quality without user intervention. Configure via **Admin → Settings → LLM → Organization Context**.

### Per-Collection Default Prompt

Each collection can have its own default AI prompt. When a file in that collection is summarized, the collection's prompt is used as the base instead of the global default. This allows different workflows (e.g., "meeting summary" vs "interview analysis") without changing global settings.

---

## Current Configuration (A6000 49GB, gpt-oss-20b)

File: `/mnt/nvm/repos/run_openwebui/docker-compose.yaml`

```yaml
# Current settings
image: vllm/vllm-openai:gptoss
command: >
  --model openai/gpt-oss-20b
  --served-model-name gpt-oss-20b
  --max-model-len 131000
  --gpu-memory-utilization 0.95
  --async-scheduling
  --swap-space 32
  --max-num-seqs 2          # <-- BOTTLENECK: only 2 concurrent requests
```

## Problem

`--max-num-seqs 2` limits the server to 2 concurrent requests. After the
OpenTranscribe parallel summary optimization, the system can send up to
4 parallel summary chunks + topics extraction + speaker ID = 6 concurrent requests.
With only 2 slots, 4 requests queue and wait, creating a 3x slowdown.

## Recommended Changes

### Step 1: Increase max-num-seqs (Start Conservative)

```yaml
command: >
  --model openai/gpt-oss-20b
  --served-model-name gpt-oss-20b
  --max-model-len 131000
  --gpu-memory-utilization 0.95
  --async-scheduling
  --swap-space 32
  --max-num-seqs 6              # Changed: 2 → 6
  --enable-chunked-prefill      # Added: better memory management for batched requests
```

**Why 6 (not 8):** The 20B model uses ~40GB at FP16, leaving ~6.5GB for KV cache.
vLLM's PagedAttention allocates KV cache dynamically per-token (not per max-model-len),
so 6 requests with short prompts (5-30K tokens each) should fit. Start at 6, then tune.

### Step 2: Restart and Monitor

```bash
cd /mnt/nvm/repos/run_openwebui
docker compose down vllm-gptoss-20b
docker compose up -d vllm-gptoss-20b

# Watch for OOM errors and request processing
docker logs -f vllm-gptoss-20b

# Monitor GPU memory in real-time
watch -n 1 nvidia-smi
```

**Expected behavior:**
- Idle: ~40GB (model weights)
- 2 concurrent requests: ~42-44GB
- 6 concurrent requests: ~44-47GB (depends on prompt lengths)
- If OOM errors appear: reduce `--max-num-seqs` to 4

### Step 3: Tune Based on Results

| Observation | Action |
|---|---|
| Memory stays < 45GB with 6 seqs | Try `--max-num-seqs 8` |
| OOM errors with 6 seqs | Reduce to `--max-num-seqs 4` |
| Slow first-token latency | Add `--enable-prefix-caching` |
| Requests time out | Increase `--swap-space` to 48 or 64 |

## Expected Performance Impact

| Metric | Before (max-num-seqs=2) | After (max-num-seqs=6) |
|---|---|---|
| Concurrent requests | 2 | 6 |
| Summary (4 chunks) time | ~40s sequential | ~10s parallel |
| Total LLM time per file | ~60s | ~15-20s |
| Throughput | ~1 file/min | ~3-4 files/min |

## Verification Checklist

- [ ] `--max-num-seqs` increased to 6
- [ ] `--enable-chunked-prefill` added
- [ ] Container restarted successfully (no OOM on startup)
- [ ] GPU memory < 47GB during multi-file processing
- [ ] No OOM errors in logs during burst processing
- [ ] Multiple LLM tasks process concurrently (check Celery/Flower)
- [ ] Overall per-file processing time reduced

## Troubleshooting

| Issue | Fix |
|---|---|
| OOM on startup | Reduce `--max-num-seqs` to 4, or lower `--gpu-memory-utilization` to 0.90 |
| OOM during processing | Reduce `--max-num-seqs`; large prompts (>80K tokens) consume more KV cache |
| Slow processing still | Check `docker logs` for request queuing; increase `--max-num-seqs` |
| vLLM won't start | Verify model path and `--max-model-len` matches model capability |

## Advanced: SGLang Alternative (Optional)

If vLLM still bottlenecks under load, SGLang offers superior continuous batching
and KV cache management. Drop-in replacement with the same OpenAI-compatible API:

```yaml
image: lmsysorg/sglang:latest
command:
  - python -m sglang.launch_server
  - --model-path openai/gpt-oss-20b
  - --host 0.0.0.0
  - --port 8000
  - --mem-fraction-static 0.90
  - --max-running-requests 8
```
