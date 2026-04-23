# Phase 6.2 — ONNX Export for Consumer Deployments (feasibility memo)

**Status**: Feasibility analysis. **Recommended** as a 2-3 day investigation + commit.
**Projected impact**: 10-20% on segmentation, 5-10% on embeddings, zero first-run delay.
**Tier**: Tier 2 — consumer default, portable across NVIDIA/Apple/CPU.

## Context

OpenTranscribe's default deployment target is **consumer hardware with non-technical users**: laptops with 3080 Ti / 4070 / M-series Macs, desktops with mid-range GPUs. Two constraints shape the deployment story:

1. **No per-hardware runtime compilation delay.** A 6-13 min first-run TensorRT build (Phase 6.3) is unacceptable when "it's frozen" is the first support ticket.
2. **Portability across accelerator vendors.** NVIDIA, Apple (MPS via CoreML EP), AMD (ROCm EP), and CPU-fallback all need to work from the same artifact.

ONNX + ONNX Runtime threads this needle: **models exported once at build time, run portably at load time with per-backend kernel selection**. No user-visible compile.

## Why ONNX fits

| Property | ONNX Runtime | torch.compile | TensorRT |
|---|---|---|---|
| First-run delay on user's GPU | **None** | 2-3 min | 6-13 min |
| Artifact baked into Docker image | **Yes** (~100-200 MB) | No | No |
| NVIDIA support | CUDA EP + TensorRT EP | Yes | Yes |
| Apple MPS support | CoreML EP | Partial | No |
| AMD support | ROCm EP | No | No |
| CPU fallback | Native | Eager | No |
| Quality risk | **None if fp32 export** | None | None if fp32 |

## Scope — what to export

Two model graphs are pure forward passes with fixed input shapes, making them clean ONNX candidates:

| Model | Source | Complexity | Expected speedup |
|---|---|---|---|
| **Segmentation** (SincNet+SCN+PyaNet+Powerset head) | `pyannote/audio/models/segmentation/...` | Medium. SincNet has custom parameterized sinc filters — needs `opset >= 18` or manual decomposition. | 10-20% (kernel fusion) |
| **Embedding** (WeSpeaker ResNet34) | `pyannote/audio/models/embedding/wespeaker/` | Low. Standard ResNet + stats pooling. Straightforward export. | 5-10% |

**Out of scope:**
- `Inference.aggregate`, `reconstruct`, VBx clustering — not models, they're Python pipeline glue. ONNX can't help.
- `compute_fbank` — mixes FFT + mel filter + log. Exportable but the Phase A MPS-native FFT fix already handles the biggest perf hit. Low ROI.

## Export pipeline

### Build-time step (runs during Docker image build)

```python
# backend/scripts/export_onnx_models.py (new)
import torch
from pyannote.audio import Model

seg_model = Model.from_pretrained("pyannote/segmentation-3.0").eval()
torch.onnx.export(
    seg_model,
    (torch.randn(1, 1, 160000),),  # fixed 10s chunk @ 16kHz
    "models/segmentation.onnx",
    opset_version=18,
    dynamic_axes={"input": {0: "batch"}},  # allow variable batch
    input_names=["waveform"],
    output_names=["segmentation"],
)

wespeaker = load_wespeaker_model().eval()
torch.onnx.export(
    wespeaker,
    (torch.randn(16, 80, 298),),  # fbank input shape
    "models/embedding.onnx",
    opset_version=18,
    dynamic_axes={"input": {0: "batch"}},
    input_names=["fbank"],
    output_names=["embedding"],
)
```

### Runtime integration

Pyannote's `Inference` class calls `model(waveform)` — we intercept at a wrapper:

```python
# fork: pyannote/audio/core/onnx_runtime.py (new)
import onnxruntime as ort

class ONNXModelWrapper(torch.nn.Module):
    def __init__(self, onnx_path: str, device: str):
        super().__init__()
        providers = self._select_providers(device)
        self.session = ort.InferenceSession(onnx_path, providers=providers)
        self.input_name = self.session.get_inputs()[0].name

    @staticmethod
    def _select_providers(device: str):
        if device.startswith("cuda"):
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        if device == "mps":
            return ["CoreMLExecutionProvider", "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.session.run(None, {self.input_name: x.cpu().numpy()})
        return torch.from_numpy(out[0]).to(x.device)
```

**Gate behind env var** (`PYANNOTE_USE_ONNX=1`) for rollout safety. Default off until measured.

### Cache & artifact strategy

- Export runs **once at image build time** (`backend/Dockerfile.blackwell`).
- Exported `.onnx` files baked into `${MODEL_CACHE_DIR}/onnx/` in the image.
- No user-visible delay. No per-hardware recompile.
- Image size growth: ~150-250 MB (segmentation ~30 MB, embedding ~100 MB, ONNX Runtime ~50 MB).

## Risks

### 1. SincNet export fragility

SincNet's parameterized sinc filters compute `torch.sin(...)/x` at export time. PyTorch's ONNX exporter sometimes fails on this pattern or produces a non-optimized subgraph. Mitigation: pre-compute filter weights at export, export as standard conv1d.

**Gate**: if export fails or output drifts >1e-4 rtol from PyTorch, fall back to Tier 1 (torch.compile) for segmentation.

### 2. CPU→GPU→CPU round-trip overhead

`ort.InferenceSession.run()` takes numpy input. Current ONNX Runtime requires a `.cpu().numpy()` for GPU input even with CUDA EP — it binds to host buffers. PyTorch 2.10 has an `io_binding` API that avoids this but adds code complexity.

**Measurement gate**: if CUDA EP ONNX is slower than eager PyTorch due to transfer overhead, use `io_binding`. If still slower, revert segmentation to torch and keep embedding on ONNX (smaller tensor, smaller transfer cost).

### 3. CoreML EP coverage on MPS

CoreML EP supports most but not all ONNX ops. Unsupported ops fall back to CPU — could regress MPS. Phase 1.5 already showed MPS is 1.79× slower than CUDA E2E; we don't want to make it worse.

**Gate**: MPS ONNX path must be ≥ eager MPS path. If not, keep MPS on eager + Phase A's MPS-native FFT.

### 4. opset version drift

ONNX Runtime 1.17+ supports opset 18-21. If PyAnnote pins to an old torch version we might have to export at opset 16 and lose some fused ops. Check fork's `torch` requirement pin.

### 5. Quality (DER) invariance

ONNX export is bit-exact for inference-only graphs **at fp32**. DER must be 0.00 delta. If any delta appears: export accidentally introduced fp16 somewhere, or an op has non-deterministic reduction order. Investigate before shipping.

## Measurement plan

1. Export both models. Verify fp32 byte-equality vs PyTorch on 100 random inputs (rtol=1e-5).
2. A/B benchmark: eager PyTorch vs ONNX Runtime on 2.2h + 4.7h A6000 + M2 Max.
3. Accept per-model if:
   - Stage ≥5% faster.
   - DER 0.00 delta.
   - Peak VRAM delta ≤ +50 MB.
   - cv < 10% over 3 runs.
4. If only one model wins, ship that one. Modular opt-in.

## Deployment positioning

**Ship ONNX as the consumer default** once Phase 6.2 passes its gate:

- Docker Hub image: `davidamacey/opentranscribe-backend:latest` includes ONNX models.
- `PYANNOTE_USE_ONNX=1` set by default in production compose overlay.
- Works on NVIDIA consumer GPUs (3080 Ti, 4070, etc.) and Apple MPS without first-run delay.

## Interaction with Phase 6.1 / 6.3

- Phase 6.1 (`torch.compile`) stays on as fallback — if ONNX export fails for a model, torch.compile still helps.
- Phase 6.3 (TensorRT) is additive — TensorRT Execution Provider can load the same `.onnx` artifact and build an optimized engine on startup. ONNX is the portable source-of-truth; TensorRT plans are a per-hardware derivative.

## Open questions for the investigation session

1. Does SincNet export cleanly at opset 18, or does it need manual decomposition?
2. Is ONNX Runtime's CUDA EP with `io_binding` faster than eager PyTorch at our tensor sizes?
3. Does CoreML EP cover all segmentation ops, or are there silent CPU fallbacks?
4. What's the size-on-disk breakdown — can we stay under 250 MB image growth?

## Recommendation

**Investigate + commit if gates pass.** 2-3 days: export scripts, wrapper class, benchmark on 3 hardware tiers (A6000 / 3080 Ti / M2 Max), DER verification, image rebuild.

If both models pass: default-on for consumer deployments. If only embedding passes: ship that, leave segmentation on Phase 6.1 `torch.compile`.
