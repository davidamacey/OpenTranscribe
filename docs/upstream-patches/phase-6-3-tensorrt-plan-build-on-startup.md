# Phase 6.3 — TensorRT Engine Plans for Server Deployments (feasibility memo)

**Status**: Feasibility analysis. **Recommended** as a 1-week investigation + commit.
**Projected impact**: 20-40% on segmentation, 15-25% on embeddings (fp32 only — fp16 is out of scope per quality invariant).
**Tier**: Tier 3 — AWS / dedicated-GPU-server deployments, opt-in, not for consumer images.

## Context

AWS + Attevon deployments use dedicated GPU instances (`g5`, `g6`, or on-prem A6000 clusters). These deployments:

1. **Have one GPU family per instance type** — `g5.xlarge` is always A10G. A plan built at container startup is reusable forever.
2. **Tolerate a one-time startup delay** — operators deploy once, run for weeks. 8-13 min to build plans is fine.
3. **Benefit from every percent of throughput** — batch-style workloads at high concurrency × hours/day mean plan-level optimization pays back quickly.
4. **Are operated by technical staff** — "optimizing models for your GPU, 8 min remaining" is a normal deployment log line, not a support ticket.

Consumer deployments (Phase 6.2 / ONNX) get the portable-no-compile story; server deployments (Phase 6.3 / TensorRT) get the max-speed story.

## Why TensorRT is a server-tier tool, not a consumer tool

| Dimension | Consumer (Phase 6.2 ONNX) | Server (Phase 6.3 TensorRT) |
|---|---|---|
| First-run delay | 0 | 6-13 min per model |
| Hardware portability | NVIDIA + Apple + CPU | NVIDIA only, per-arch plans |
| Artifact in image | Yes (~150-250 MB) | No — built on target GPU |
| Cache invalidation | Never | TRT version + driver + SM arch change |
| Target audience | End users | Ops / SRE |

The constraint that **engine plans can't be baked into images** is the core reason this is a separate memo. A plan built on A6000 (`sm_86`) doesn't run on A10G (`sm_86` but different SKU behavior) or H100 (`sm_90`). Build-on-first-startup is the only sane pattern.

## Architecture

### Build phase (first container startup on each unique GPU)

```python
# backend/app/transcription/tensorrt_builder.py (new)
import tensorrt as trt
from pathlib import Path

def build_engine(onnx_path: Path, plan_path: Path, max_batch: int):
    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(network, logger)

    with open(onnx_path, "rb") as f:
        if not parser.parse(f.read()):
            for error in range(parser.num_errors):
                log.error(parser.get_error(error))
            raise RuntimeError(f"TRT parse failed for {onnx_path}")

    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 2 << 30)  # 2 GB
    # fp32 only — fp16 excluded per quality invariant
    # config.set_flag(trt.BuilderFlag.FP16)  # DO NOT ENABLE

    profile = builder.create_optimization_profile()
    profile.set_shape("waveform", (1, 1, 160000), (16, 1, 160000), (32, 1, 160000))
    config.add_optimization_profile(profile)

    plan = builder.build_serialized_network(network, config)
    plan_path.write_bytes(plan)
```

### Cache layout

```
${MODEL_CACHE_DIR}/tensorrt/
├── sm_86_cuda-13.0_trt-10.3/      # A6000, A10G, A5000
│   ├── segmentation.plan
│   └── embedding.plan
├── sm_89_cuda-13.0_trt-10.3/      # RTX 40-series
│   └── ...
├── sm_90_cuda-13.0_trt-10.3/      # H100, H200
│   └── ...
└── build_metadata.json            # version fingerprints
```

Cache key: `f"sm_{compute_capability}_cuda-{cuda_version}_trt-{trt_version}"`. If the directory exists and contains both plans, skip build. If fingerprints don't match (driver upgrade, TRT upgrade), rebuild.

### Startup hook

```python
# backend/app/transcription/diarizer.py
def _ensure_tensorrt_plans(self) -> Path | None:
    if not os.environ.get("ENABLE_TENSORRT"):
        return None  # opt-in only

    cache_dir = _tensorrt_cache_dir()
    if _plans_fresh(cache_dir):
        return cache_dir

    logger.info("Building TensorRT engine plans (first-time, ~8-13 min)...")
    _emit_websocket("tensorrt_build_started", {"eta_seconds": 600})
    build_engine(ONNX_SEG, cache_dir / "segmentation.plan", max_batch=32)
    _emit_websocket("tensorrt_build_progress", {"step": "segmentation_done"})
    build_engine(ONNX_EMB, cache_dir / "embedding.plan", max_batch=32)
    _emit_websocket("tensorrt_build_complete", {})
    logger.info(f"TensorRT plans cached to {cache_dir}")
    return cache_dir
```

Blocks Celery task dispatch until plans are ready — `worker_ready` signal handler. Phase 6.3 adds TRT build to the existing model-preload pipeline.

### Runtime integration

TensorRT EP in ONNX Runtime **reuses the Phase 6.2 ONNX artifact** and loads the precompiled plan:

```python
providers = [
    ("TensorrtExecutionProvider", {
        "trt_engine_cache_enable": True,
        "trt_engine_cache_path": str(cache_dir),
        "trt_fp16_enable": False,  # fp32 only
    }),
    "CUDAExecutionProvider",
    "CPUExecutionProvider",
]
```

No separate inference code path — the wrapper from Phase 6.2 stays the same. TensorRT EP is a drop-in.

## AWS deployment specifics

### Instance-type plan pre-building

For Attevon's AWS pipeline, we can **pre-build plans in CI** for each known target instance type and ship them in a separate OCI artifact:

- `davidamacey/opentranscribe-tensorrt-plans:sm86-v1.0` — A10G, A6000
- `davidamacey/opentranscribe-tensorrt-plans:sm89-v1.0` — RTX 40-series
- `davidamacey/opentranscribe-tensorrt-plans:sm90-v1.0` — H100

Deployment pulls the right plan artifact based on detected GPU arch. Skips the first-run build entirely.

**Build matrix in CI**: a GitHub Actions job with `runs-on: self-hosted` on a node with each GPU arch, building plans nightly against the latest image.

### Cost-benefit for AWS

A g5.xlarge at $1.006/hr. 30% speedup on segmentation + embeddings:
- Per-file savings: ~30s on a 2.2h file (segmentation 5.5s → 3.9s, embedding 75s → 52s).
- 500 files/day workload: ~4 hours of GPU time saved = **$4/day × 365 = ~$1500/yr per instance**.

Payback on the 1-week implementation: break-even at 4-5 g5 instance-months of production use.

## Risks

### 1. Engine plan size + cache bloat

Plans are ~80-300 MB each. With 3 arch targets × 2 models × version history = ~2-4 GB of cached plans over a year. Mitigation: TTL-based cleanup in `tensorrt_builder.py`, keep latest 2 versions per arch.

### 2. Build failures on unusual SKUs

TRT 10.x dropped support for pre-Turing GPUs. Any GPU older than `sm_75` (RTX 20-series) will fail. Mitigation: detect `sm_<75` at startup and skip TRT build, fall back to ONNX EP (Phase 6.2).

### 3. Workspace memory during build

TRT builder allocates up to 2 GB of workspace during plan generation. On GPUs with <8 GB VRAM, this can OOM if other processes are resident. Mitigation: build plans **before** model warmup (so Whisper + PyAnnote aren't loaded yet). Or bound workspace to 1 GB on small-VRAM targets.

### 4. Non-determinism across TRT versions

Plans built on TRT 10.3 don't load on TRT 10.4. Mitigation: cache key includes TRT version; image upgrades invalidate plans automatically.

### 5. Streaming / dynamic-shape costs

TRT optimization profiles quantize over `(min, opt, max)` shape ranges. Picking `opt=16` for embedding batch means shapes other than 16 run slower. Phase A pinned batch=16 — this aligns perfectly. For segmentation, the variable-length chunk problem is trickier; may need multiple profiles.

### 6. fp32 constraint leaves performance on the table

TensorRT's biggest wins come from fp16/int8. We've committed to fp32 per DER invariance. Phase 6.3 gets graph-fusion wins only — that's 20-40% stage speedup, not the 2-3× you'd see with fp16. This is by design and non-negotiable.

## Measurement plan

1. Build plans on A6000 in dev environment. Confirm cache directory populates.
2. Confirm inference output byte-equals Phase 6.2 ONNX output (rtol=1e-5).
3. A/B benchmark: ONNX (CUDA EP) vs ONNX (TensorRT EP) on 2.2h + 4.7h × 3 runs.
4. Accept per-model if:
   - Stage ≥15% faster over ONNX CUDA EP.
   - DER 0.00 delta.
   - Peak VRAM delta ≤ +200 MB (TRT workspace).
   - First-run build completes in <15 min on A6000.
5. Document cold-start delay in deployment docs + ops runbook.

## Deployment positioning

- **Default off** in consumer Docker images (consumers get ONNX from Phase 6.2).
- **Opt-in via `ENABLE_TENSORRT=true`** in AWS / on-prem production env files.
- **Pre-built plan images** for known-good AWS instance types (`g5`, `g6`) via CI.

## Interaction with Phase 6.1 / 6.2

TRT EP consumes the Phase 6.2 ONNX artifact. **Phase 6.2 is a hard prerequisite for Phase 6.3.** You can't ship 6.3 without 6.2.

Phase 6.1 (torch.compile) stays default-on everywhere. Layered fallback:
1. `ENABLE_TENSORRT=true` → TRT plan loads from cache → serves inference.
2. TRT plan build fails → fall back to ONNX CUDA EP.
3. ONNX fails to load → fall back to `torch.compile` eager.
4. All else fails → pure PyTorch eager. Pipeline still works.

## Open questions for the investigation session

1. Does TRT 10.x cleanly consume the Phase 6.2 SincNet-containing ONNX, or does it need op-level intervention?
2. What's the real cold-build time on A6000 vs A10G vs H100?
3. Is the CI-prebuilt-plan artifact pattern feasible with Attevon's existing deploy pipeline?
4. Does the workspace memory peak during build interfere with multi-tenant GPU sharing?

## Recommendation

**Commit after Phase 6.2 ships.** 1 week: TRT builder, cache manager, EP integration, CI matrix for pre-built plans, AWS deployment docs. Opt-in gate ensures consumer deployments don't accidentally hit the 10-min wall.

Order of operations:
1. Phase 6.1 (gcc in image) — ships first, 1 day.
2. Phase 6.2 (ONNX export) — ships second, 2-3 days, default for consumer.
3. Phase 6.3 (TensorRT plans) — ships third, 1 week, opt-in for server deployments.

Cumulative projected win stacking ONNX + TRT on server tier: **30-50% on segmentation + embedding stages**, translating to **~15-25% E2E on 2.2h batch workloads**. Combined with the Phase 5.4 concurrent-request raise (2-4× throughput), server tier could see **3-5× batch throughput** vs today.
