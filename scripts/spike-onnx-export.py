#!/usr/bin/env python3
"""Phase 6.2 spike — attempt ONNX export of pyannote segmentation + WeSpeaker embedding.

Goal: determine whether the models export cleanly before investing in wrapper
integration. Runs inside the backend image with `onnx` + `onnxruntime-gpu`
installed ad-hoc.

Outputs:
    /tmp/onnx_spike/segmentation.onnx
    /tmp/onnx_spike/embedding.onnx

Per-model report: export success/failure, rtol vs PyTorch eager, ORT session
load success, ORT inference success.
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np
import torch

OUT = Path("/tmp/onnx_spike")
OUT.mkdir(parents=True, exist_ok=True)


def report(name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}: {detail}")


def try_export_wespeaker() -> None:
    """Export WeSpeaker ResNet-based embedding model."""
    print("\n=== WeSpeaker embedding export ===")
    try:
        from pyannote.audio.models.embedding.wespeaker import WeSpeakerResNet34
        model = WeSpeakerResNet34().eval().cuda()
        report("wespeaker/load", True, type(model).__name__)
    except Exception as exc:
        report("wespeaker/load", False, str(exc))
        return

    # WeSpeaker consumes (batch, 1, n_samples) mono waveform @ 16 kHz. Forward
    # computes fbank internally via torch.vmap(self._fbank).
    dummy = torch.randn(2, 1, 16000, device="cuda")
    try:
        with torch.no_grad():
            y_eager = model(dummy)
        report("wespeaker/forward_eager", True, f"out_shape={tuple(y_eager.shape)}")
    except Exception as exc:
        report("wespeaker/forward_eager", False, str(exc))
        traceback.print_exc()
        return

    onnx_path = OUT / "embedding.onnx"
    # Try dynamo-based exporter first (handles vmap + modern ops)
    for mode in ("dynamo", "script"):
        try:
            if mode == "dynamo":
                torch.onnx.export(
                    model, (dummy,), str(onnx_path),
                    opset_version=18, dynamo=True,
                    input_names=["waveform"], output_names=["embedding"],
                )
            else:
                torch.onnx.export(
                    model, (dummy,), str(onnx_path),
                    opset_version=18,
                    input_names=["waveform"], output_names=["embedding"],
                )
            report(f"wespeaker/export[{mode}]", True,
                   f"{onnx_path} ({onnx_path.stat().st_size // 1024} KiB)")
            break
        except Exception as exc:
            report(f"wespeaker/export[{mode}]", False, f"{type(exc).__name__}: {str(exc)[:200]}")
    else:
        return

    try:
        import onnx
        m = onnx.load(str(onnx_path))
        onnx.checker.check_model(m)
        report("wespeaker/onnx_check", True, f"ir_version={m.ir_version}, opset={m.opset_import[0].version}")
    except Exception as exc:
        report("wespeaker/onnx_check", False, str(exc))
        return

    try:
        import onnxruntime as ort
        providers = [
            ("CUDAExecutionProvider", {"device_id": 0}),
            "CPUExecutionProvider",
        ]
        session = ort.InferenceSession(str(onnx_path), providers=providers)
        report("wespeaker/ort_session", True, f"providers={session.get_providers()}")
    except Exception as exc:
        report("wespeaker/ort_session", False, str(exc))
        return

    try:
        y_ort = session.run(None, {"waveform": dummy.cpu().numpy()})[0]
        y_ort_t = torch.from_numpy(y_ort).to(y_eager.device)
        diff = (y_eager - y_ort_t).abs().max().item()
        rtol_ok = diff < 1e-4
        report("wespeaker/parity", rtol_ok, f"max_abs_diff={diff:.3e}")
    except Exception as exc:
        report("wespeaker/parity", False, str(exc))


def try_export_segmentation() -> None:
    """Export pyannote speaker-segmentation-3.0 model."""
    print("\n=== Pyannote segmentation-3.0 export ===")
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    try:
        from pyannote.audio import Model
        model = Model.from_pretrained("pyannote/segmentation-3.0", token=token).eval().cuda()
        report("seg/load", True, type(model).__name__)
    except Exception as exc:
        report("seg/load", False, str(exc))
        traceback.print_exc()
        return

    # Pyannote seg consumes 10-second mono chunks at 16 kHz.
    dummy = torch.randn(2, 1, 160000, device="cuda")
    try:
        with torch.no_grad():
            y_eager = model(dummy)
        report("seg/forward_eager", True, f"out_shape={tuple(y_eager.shape)}")
    except Exception as exc:
        report("seg/forward_eager", False, str(exc))
        traceback.print_exc()
        return

    # Force all norm layers to eval mode (the export warning indicates some leak through)
    for mod in model.modules():
        if hasattr(mod, "training"):
            mod.training = False

    onnx_path = OUT / "segmentation.onnx"
    for mode in ("dynamo", "script"):
        try:
            if mode == "dynamo":
                torch.onnx.export(
                    model, (dummy,), str(onnx_path),
                    opset_version=18, dynamo=True,
                    input_names=["waveform"], output_names=["segmentation"],
                )
            else:
                torch.onnx.export(
                    model, (dummy,), str(onnx_path),
                    opset_version=18,
                    input_names=["waveform"], output_names=["segmentation"],
                )
            report(f"seg/export[{mode}]", True,
                   f"{onnx_path} ({onnx_path.stat().st_size // 1024} KiB)")
            break
        except Exception as exc:
            report(f"seg/export[{mode}]", False, f"{type(exc).__name__}: {str(exc)[:200]}")
    else:
        return

    try:
        import onnx
        m = onnx.load(str(onnx_path))
        onnx.checker.check_model(m)
        report("seg/onnx_check", True, f"ir_version={m.ir_version}, opset={m.opset_import[0].version}")
    except Exception as exc:
        report("seg/onnx_check", False, str(exc))

    try:
        import onnxruntime as ort
        providers = [
            ("CUDAExecutionProvider", {"device_id": 0}),
            "CPUExecutionProvider",
        ]
        session = ort.InferenceSession(str(onnx_path), providers=providers)
        report("seg/ort_session", True, f"providers={session.get_providers()}")
    except Exception as exc:
        report("seg/ort_session", False, str(exc))
        return

    try:
        y_ort = session.run(None, {"waveform": dummy.cpu().numpy()})[0]
        y_ort_t = torch.from_numpy(y_ort).to(y_eager.device)
        diff = (y_eager - y_ort_t).abs().max().item()
        rtol_ok = diff < 1e-4
        report("seg/parity", rtol_ok, f"max_abs_diff={diff:.3e}")
    except Exception as exc:
        report("seg/parity", False, str(exc))


if __name__ == "__main__":
    torch.manual_seed(0)
    try_export_wespeaker()
    try_export_segmentation()
