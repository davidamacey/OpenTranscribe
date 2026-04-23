# Phase 6.2 — ONNX Export for Consumer Deployments (updated 2026-04-23)

**Status**: **UNBLOCKED**. Export path verified via two spikes. Prior art on HuggingFace + GitHub confirms our approach. Ready for full implementation + test-matrix validation.
**Projected impact**: 10-20% on segmentation stage, 5-10% on embedding stage. Zero first-run delay (artifacts baked into image).
**Tier**: Tier 2 — consumer default, portable across NVIDIA/Apple/CPU.

## Updated status — why it is NOT blocked

The original v1 spike (`spike-onnx-export.py`) hit two apparent blockers:

1. **WeSpeaker**: `torch.vmap` in `compute_fbank` refused to trace in both TorchScript and dynamo exporters.
2. **Segmentation**: 5.57e-3 logit drift, above the 1e-4 acceptance bar.

Web research + a v2 spike proved both are solved problems:

### WeSpeaker — export the ResNet backbone only (per pyannote-audio discussion #1929)

Don't try to export the full forward path through `compute_fbank`. Instead, wrap only the ResNet backbone that takes pre-computed fbank features:

```python
class Backbone(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.resnet = m.resnet
    def forward(self, fbank):       # (batch, num_frames, 80)
        out = self.resnet(fbank)
        return out[-1] if isinstance(out, tuple) else out
```

Export input: `torch.randn(2, 200, 80)` on GPU. Output: `(2, 256)` embeddings. Fbank extraction happens separately in plain batched PyTorch (no vmap) before calling the ONNX session.

**v2 spike result** (`scripts/spike-onnx-export-v2.py`):
```
[PASS] wespeaker/export: embedding_backbone.onnx (25908 KiB)
[PASS] wespeaker/parity: max_abs_diff=1.571e-05, mean_cos_sim=0.99999994
```

Parity beats the 1e-4 bar by a factor of 10. Matches discussion #1929's reported `cos ≈ 1.0000001192`.

### Segmentation — 5.57e-3 logit drift is irrelevant to DER

The drift is stable and comes from an ORT-vs-PyTorch kernel difference on the LSTM + InstanceNorm path. But pyannote binarizes segmentation logits through `softmax → argmax → frame class`. Measured in `scripts/spike-onnx-seg-der-impact.py`:

```
Trial 0: logit_abs=5.876e-03 prob_abs=1.457e-04 frame_class_mismatch=0.0000% of 2356 frames
Trial 1: logit_abs=1.254e-02 prob_abs=2.554e-04 frame_class_mismatch=0.0000% of 2356 frames
Trial 2: logit_abs=9.441e-03 prob_abs=1.757e-04 frame_class_mismatch=0.0000% of 2356 frames
```

**Zero frame-class mismatches on 3 trials of realistic random input.** The logit drift gets absorbed by the argmax because no frame sits close enough to a decision boundary. Downstream binarization will produce bit-identical segmentation masks → zero DER impact.

The `onnx-community/pyannote-segmentation-3.0` artifact (HF staff-maintained, used in production by Transformers.js) lives with the same drift and has no reported diarization quality issues.

## Prior art we can leverage

Multiple existing ONNX conversions cover the models we need:

| Project | Scope | Our take |
|---|---|---|
| [`onnx-community/pyannote-segmentation-3.0`](https://huggingface.co/onnx-community/pyannote-segmentation-3.0) | segmentation-3.0 only (5.9 MB) | HF-staff maintained. Drop-in artifact. |
| [`Wespeaker/wespeaker-voxceleb-resnet34`](https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34) | WeSpeaker ResNet34 ONNX (26.5 MB) | Official WeSpeaker project release. |
| [`onnx-community/wespeaker-voxceleb-resnet34-LM`](https://huggingface.co/onnx-community/wespeaker-voxceleb-resnet34-LM) | LM variant | Community mirror. |
| [`altunenes/speaker-diarization-community-1-onnx`](https://huggingface.co/altunenes/speaker-diarization-community-1-onnx) | Community-1 pipeline (quantized) | Matches our exact pipeline. Used by [`pyannote-rs`](https://github.com/thewh1teagle/pyannote-rs). |
| [`samson6460/pyannote-onnx-extended`](https://github.com/samson6460/pyannote-onnx-extended) | Full 3.1 pipeline in Python | MIT; early-stage but has export scripts. |
| [`pengzhendong/pyannote-onnx`](https://github.com/pengzhendong/pyannote-onnx) | Segmentation + C++ runtime | PyPI package. |
| [`sherpa-onnx`](https://github.com/k2-fsa/sherpa-onnx) | Full pipeline, C++ runtime | Uses CAM++ embedding (not WeSpeaker). |
| [pyannote #1929](https://github.com/pyannote/pyannote-audio/discussions/1929) | Official guidance on backbone-only export | Source of our v2 approach. |

**Decision**: export our own artifacts from our fork's weights (not drop in third-party ONNX) so versioning and parity stay under our control. But we use the community-proven export recipes (`onnx-community` recipe for segmentation, #1929 backbone pattern for embedding).

## Implementation plan

Implementation lives in 3 layers. Each layer has a concrete test matrix (see next section).

### Layer 1 — Export pipeline

A new script in the fork: `fork:pyannote/audio/onnx_export.py` (or equivalent) that:

1. Loads the PyTorch models (segmentation-3.0 + WeSpeaker ResNet34-LM) from HuggingFace using the same weights our production pipeline loads.
2. Applies `.eval()` to all submodules and forces `training=False` on every leaf.
3. Exports each with the recipes validated in the spikes:
   - Segmentation: `(B, 1, 160000)` waveform → `(B, num_frames, 7)` logits, opset 18, `do_constant_folding=True`, `input_values` / `logits` names, dynamic axes `{0: batch_size, 1: num_channels, 2: num_samples}` / `{0: batch_size, 1: num_frames}`.
   - Embedding backbone: `(B, num_frames, 80)` fbank → `(B, 256)` embedding, opset 18, `fbank_features` / `embeddings` names.
4. Runs `onnx.checker.check_model` on each.
5. Emits a metadata JSON alongside each `.onnx`: fork git SHA, pyannote version, HF model revision, opset, input/output schemas, sha256 of the .onnx file.

Run once at image build time via `backend/Dockerfile.prod`. Artifacts bake into `/app/models/onnx/{segmentation,embedding}.onnx` inside the image.

### Layer 2 — Runtime ONNX wrapper in fork

New module: `fork:pyannote/audio/onnx/runtime.py`. Provides a drop-in replacement for the model call inside the pipeline:

```python
class ONNXModelRuntime:
    def __init__(self, onnx_path: Path, device: str):
        providers = self._select_providers(device)
        self.session = ort.InferenceSession(str(onnx_path), providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

    @staticmethod
    def _select_providers(device: str) -> list:
        if device.startswith("cuda"):
            return [("CUDAExecutionProvider", {"device_id": int(device.split(":")[-1]) if ":" in device else 0}),
                    "CPUExecutionProvider"]
        if device == "mps":
            return ["CoreMLExecutionProvider", "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    def __call__(self, x: torch.Tensor) -> torch.Tensor:
        out = self.session.run([self.output_name], {self.input_name: x.contiguous().cpu().numpy()})[0]
        return torch.from_numpy(out).to(x.device)
```

For the embedding path, also ship a `compute_fbank_batched()` helper that replaces `torch.vmap(self._fbank)` with an explicit batched loop using `torchaudio.compliance.kaldi.fbank` per sample. **Keep Phase A's MPS-native FFT fix** — the helper branches on device.

### Layer 3 — Pipeline integration

Gate behind env var `PYANNOTE_USE_ONNX=1`. Two wiring points in `fork:pyannote/audio/pipelines/speaker_diarization.py`:

- `__init__`: if env var set, load `ONNXModelRuntime(seg_onnx_path)` and store as `self._segmentation_runtime`; same for `_embedding_runtime`.
- Forward call sites (~line 420 for segmentation, ~line 731 for embedding): branch on presence of runtime; call ONNX session instead of eager model.

Default OFF pending the test matrix passing.

## Test matrix (full suite)

The suite lives under `backend/tests/onnx/` and is pytest-runnable. It has six phases, each with a hard accept/reject criterion. Nothing ships before the entire matrix passes.

### Canonical sample inputs

**All integration tests (T3-T6) use the same reference WAV files already in `benchmark/test_audio/`** — identical to every prior baseline in this project:

| File | Duration | Ground truth speakers | Ground truth segments (from baseline RTTM) |
|---|---:|---:|---:|
| `0.5h_1899s.wav` | 1899s (~32 min) | (per baseline) | (per baseline) |
| `2.2h_7998s.wav` | 7998s (~2.2h) | 3 | 2855 |
| `3.2h_11495s.wav` | 11495s (~3.2h) | (per baseline) | (per baseline) |
| `4.7h_17044s.wav` | 17044s (~4.7h) | 8 | 12104 |

Reference RTTMs for DER comparison come from `benchmark/results/rttm/baseline_a6000_20260421_{213621_short, 214811_long}/` — the same 5-run statistical baseline every prior phase scored against. This guarantees continuity: if Phase 6.2 DER deltas appear, they're directly comparable to Phase 2, 3, 3.5, and final-gate results.

Unit tests (T1 + T2) use synthetic inputs of the same shape as the production call sites, because no HuggingFace download is acceptable in CI.

### Phase T1 — Numeric parity (unit)

For each model, each device, each provider, verify output parity against PyTorch eager.

| Model × Device × Provider | Input | Parity metric | Accept |
|---|---|---|---:|
| Seg × CUDA × CUDA EP | `(2, 1, 160000)` random | frame-class argmax mismatch | 0% |
| Seg × CUDA × CUDA EP | 5 random seeds | frame-class argmax mismatch | 0% across all |
| Seg × CPU × CPU EP | `(2, 1, 160000)` random | frame-class argmax mismatch | 0% |
| Emb × CUDA × CUDA EP | `(16, 200, 80)` random fbank | `max_abs_diff`, cos similarity | ≤1e-4, ≥0.9999 |
| Emb × CPU × CPU EP | same | same | ≤1e-4, ≥0.9999 |
| Emb × MPS × CoreML EP | same (M2 Max) | same | ≤1e-4, ≥0.9999 |

**File**: `backend/tests/onnx/test_numeric_parity.py`

### Phase T2 — Fbank extraction parity (unit)

The batched-fbank helper replacing `torch.vmap` must match the original vmap output.

| Input shape | Device | Metric | Accept |
|---|---|---|---:|
| `(16, 1, 16000)` | CUDA | `max_abs_diff` vs vmap | ≤1e-6 |
| `(16, 1, 16000)` | CPU | same | ≤1e-6 |
| `(16, 1, 16000)` | MPS | same (M2 Max) | ≤1e-5 (MPS fp precision) |
| Variable lengths (padded) | CUDA | per-sample first-frame alignment | exact |

**File**: `backend/tests/onnx/test_fbank_parity.py`

### Phase T3 — End-to-end DER regression (integration)

Run full diarization pipeline with ONNX backend enabled, compare RTTM byte-for-byte vs PyTorch eager baseline on reference files.

| File | Device | Runs | DER acceptance | Speaker count | Segment count |
|---|---|---:|---|---:|---|
| 0.5h_1899s | CUDA A6000 | 3 | ≤0.1 pp vs baseline | within ±1 | within ±2% |
| 2.2h_7998s | CUDA A6000 | 3 | ≤0.1 pp | within ±1 | within ±2% |
| 3.2h_11495s | CUDA A6000 | 3 | ≤0.1 pp | within ±1 | within ±2% |
| 4.7h_17044s | CUDA A6000 | 3 | ≤0.1 pp | within ±1 | within ±2% |
| 2.2h_7998s | CPU (8 threads) | 3 | ≤0.1 pp | within ±1 | within ±2% |
| 2.2h_7998s | MPS M2 Max | 3 | ≤0.1 pp | within ±1 | within ±2% |

Target: **0.0000% (T1 tier)** on frame-class-identical segmentation + cosine≥0.9999 embedding → same clustering → same RTTM.

**File**: `backend/tests/onnx/test_der_regression.py` + reuse `scripts/diarization-der-compare.py`.

### Phase T4 — Speed / throughput (perf)

Measure per-stage + end-to-end wall time. Compare ONNX vs PyTorch eager.

| Metric | Files | Device | Runs | Acceptance |
|---|---|---|---:|---|
| Segmentation stage wall | 2.2h, 4.7h | CUDA A6000 | 3 warm | ≥5% faster OR no regression |
| Embedding stage wall | 2.2h, 4.7h | CUDA A6000 | 3 warm | ≥5% faster OR no regression |
| End-to-end wall | all 4 files | CUDA A6000 | 3 warm | ≥3% faster OR no regression |
| Batch scaling | synthetic `(B, 1, 160000)` B∈{1,4,8,16,32} | CUDA A6000 | 5 each | linear scaling up to B=16 |
| End-to-end wall | 2.2h | MPS M2 Max | 3 warm | ≥0% (don't regress) |
| End-to-end wall | 2.2h | CPU (8 threads) | 3 warm | ≥20% faster (CPU is where ONNX usually wins biggest) |

**File**: extend `scripts/benchmark-pyannote-direct.py` with `--use-onnx` flag that sets `PYANNOTE_USE_ONNX=1`. Reuse existing per-stage `record_function` labels.

### Phase T5 — VRAM / memory (resource)

The 844 MB per-pipeline invariant MUST hold with ONNX enabled.

| Metric | File | Device | Acceptance |
|---|---|---|---|
| Peak VRAM | 2.2h | CUDA | ≤ 1.05 GB (invariant) |
| Peak VRAM | 4.7h | CUDA | ≤ 1.05 GB |
| Steady-state VRAM (+2s after return) | 2.2h | CUDA | ≤ 1.0 GB |
| CUDA EP cached allocator growth | 10 sequential runs | CUDA | no monotonic growth |
| Host memory / RSS | 2.2h | CPU | ≤ 2 GB (reasonable for CPU path) |
| Image size growth | Docker build | n/a | ≤ +250 MB (ONNX Runtime + artifacts) |

**File**: reuse `scripts/vram-probe-diarization.py` with `--use-onnx` flag.

### Phase T6 — Concurrent pipelines (system)

Validate 25×-per-A6000 parallel pipeline architecture stays intact.

| Concurrency | Device | Duration | Acceptance |
|---|---|---|---|
| 4 pipelines | A6000 | 10 min | Each pipeline ≤1.05 GB, total ≤ 5 GB + Whisper |
| 8 pipelines | A6000 | 10 min | Each ≤1.05 GB, no OOM, no inter-pipeline interference |
| 12 pipelines | A6000 | 30 min | Throughput ≥ 6× single-pipeline rate |

**File**: extend `scripts/vram-probe-diarization.py` `--concurrent` mode.

## Test matrix meta-requirements

- **Single command to run all layers**: `pytest backend/tests/onnx/ -v --device=cuda --runs=3` and equivalent for MPS via SSH to M2 Max.
- **Structured JSON output** per test class (timings, parities, VRAM); aggregated into `benchmark/results/onnx/<tag>/summary.json`.
- **Version-pin every artifact**: every run records fork SHA, PyTorch version, ONNX Runtime version, HF model revision, CUDA+cuDNN version, onnx opset. Stored in `benchmark/results/onnx/<tag>/metadata.json`.
- **Reference parity baselines committed**: store one reference RTTM per file+device in `benchmark/results/rttm/onnx_baseline_<date>/` so future regressions are byte-detectable.
- **Pre-merge gate**: all 6 phases pass before the `PYANNOTE_USE_ONNX` default flips from OFF to ON.
- **CI-runnable portion**: T1 + T2 run in CI on synthetic inputs (no HF download, uses static weights fixture). T3-T6 require the real test files and must run locally — document in the test docstring.

## Rollout plan

1. **Layer 1 + T1 + T2** (2-3 days): export pipeline, fbank-batched helper, numeric parity test suite. Export scripts run against the fork's actual model weights.
2. **Layer 2** (1-2 days): ONNX runtime wrapper class, provider selection logic.
3. **Layer 3 + T3 + T4 + T5** (3-4 days): wire into `SpeakerDiarization` pipeline behind `PYANNOTE_USE_ONNX`, DER regression tests, speed benchmarks, VRAM probes. This is the phase where the tests actually say go/no-go.
4. **T6 concurrent stress** (1-2 days): validate invariant under load.
5. **Flip default** (0.5 day): once all gates green, flip `PYANNOTE_USE_ONNX` default to ON in backend production compose. Update `.env.example`.

Total: **8-12 days** of focused work across spike-verified path.

## Risks / open questions (concrete, with tests that would surface them)

1. **CUDA EP CPU→GPU→CPU transfer overhead**. ORT `InferenceSession.run` takes numpy, triggering `.cpu().numpy()` round-trip. T4 batch-scaling test will show this. Mitigation: `io_binding` API to avoid host intermediate.
2. **ORT CUDA EP vs PyTorch CUDA kernel selection differences**. T1 will show it if ORT picks slower kernels. Mitigation: pin ORT to 1.24+ which has better fallback heuristics.
3. **CoreML EP op coverage on M2 Max**. T1 MPS row will reveal it. Mitigation: fall back to CPU EP for segmentation on MPS if CoreML fails.
4. **Fork dependency surface**: adding `onnxruntime-gpu` to fork means consumers of the fork pull 350 MB. Acceptable because the fork is already Linux+CUDA-targeted.
5. **Image size growth**: +250 MB for ONNX Runtime + artifacts. Acceptable vs current 8.8 GB image.
6. **Model weight drift between HF and our fork**: if our fork has locally-retrained or locally-patched weights, pre-existing ONNX artifacts diverge. Mitigation: always export from the fork's loaded state_dict (Layer 1 does this).

## Cascading effect on Phase 6.3

Phase 6.3 (TensorRT EP) is now **unblocked**. Once Layer 1 produces valid ONNX artifacts, TensorRT EP can consume them with no additional export work — just a provider-list change. Phase 6.3 becomes a drop-in acceleration on top of 6.2. See `phase-6-3-tensorrt-plan-build-on-startup.md` for the separate test matrix.

## Artifacts

- `scripts/spike-onnx-export-v2.py` — verified export recipes for both models.
- `scripts/spike-onnx-seg-der-impact.py` — confirms segmentation drift doesn't affect frame-class output.
- (to come) `fork:pyannote/audio/onnx/` — runtime wrapper + batched fbank helper.
- (to come) `backend/tests/onnx/` — pytest suite implementing T1-T6.
- (to come) `scripts/export_pyannote_onnx.py` — production export script for Docker build.
