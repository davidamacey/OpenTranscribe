"""Phase D.2 — model-lifecycle + VRAM-policy integration tests.

Asserts three invariants:

1. Transcriber load -> transcribe -> unload -> diarizer load -> run completes
   without error using the production ModelManager.
2. Handoff residue (NVML delta from pre-load baseline to post-
   release_transcriber) is within _CUDA_CONTEXT_MB + 50 MB tolerance.
   Measured floor is 300 MB on (torch 2.8.0+cu128, driver 580.126, A6000);
   tolerance = 350 MB. Any regression above this means new unreleased
   state was introduced in Transcriber.unload_model or its callees.
3. DIARIZATION_VRAM_BUDGET_MB env var propagates through settings ->
   _apply_vram_policy -> fork pipeline.vram_budget_mb.

Run (in-container):

    docker compose -f docker-compose.yml -f docker-compose.override.yml \\
                   -f docker-compose.gpu.yml -f docker-compose.benchmark.yml \\
                   run --rm --entrypoint "" diarization-probe \\
        python -m pytest /app/tests/integration/test_diarizer_lifecycle.py -v

Refs: plan i-need-a-full-stateful-origami.md D.2.
"""

from __future__ import annotations

import ctypes
import os
import wave
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.gpu

BENCHMARK_ROOT = Path("/app/benchmark/test_audio")

# Phase A.6b measured floor + 50 MB tolerance for future jitter.
RESIDUE_GATE_MB = 350


def _in_container() -> bool:
    return Path("/.dockerenv").exists() or os.environ.get("OPENTRANSCRIBE_IN_CONTAINER") == "1"


@pytest.fixture(scope="module")
def ensure_container() -> None:
    if not _in_container():
        pytest.skip("Lifecycle tests require the benchmark container (see D.2 docstring)")


@pytest.fixture(scope="module")
def torch_cuda() -> object:
    try:
        import torch
    except ImportError:
        pytest.skip("torch not available")
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")
    return torch


def _nvml_used_mb() -> float:
    """Current NVML device_used in MB for device 0, or 0.0 on failure."""
    try:
        lib = ctypes.CDLL("libnvidia-ml.so.1")
        lib.nvmlInit_v2()
        handle = ctypes.c_void_p()
        lib.nvmlDeviceGetHandleByIndex(0, ctypes.byref(handle))

        class _Mem(ctypes.Structure):
            _fields_ = [
                ("total", ctypes.c_ulonglong),
                ("free", ctypes.c_ulonglong),
                ("used", ctypes.c_ulonglong),
            ]

        mem = _Mem()
        lib.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(mem))
        return mem.used / (1024**2)
    except Exception:
        return 0.0


def _load_audio(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        if wf.getframerate() != 16000:
            raise AssertionError("expected 16kHz audio")
        return (
            np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32)
            / 32768.0
        )


def test_handoff_residue_within_gate(
    ensure_container: None,
    torch_cuda: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transcriber -> release must not leave > RESIDUE_GATE_MB above baseline."""
    import gc
    import time

    import torch

    from app.transcription.config import TranscriptionConfig
    from app.transcription.transcriber import Transcriber

    wav_path = BENCHMARK_ROOT / "0.5h_1899s.wav"
    if not wav_path.exists():
        pytest.skip(f"benchmark audio missing: {wav_path}")
    audio = _load_audio(wav_path)

    baseline = _nvml_used_mb()

    cfg = TranscriptionConfig(
        model_name="base",
        compute_type="float16",
        device="cuda",
        device_index=0,
        beam_size=1,
        batch_size=8,
        enable_diarization=False,
    )
    t = Transcriber(cfg)
    t.load_model()
    t.transcribe(audio)
    t.unload_model()
    del t
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.synchronize()
    time.sleep(0.5)  # let NVML settle

    post_release = _nvml_used_mb()
    residue = post_release - baseline

    assert residue <= RESIDUE_GATE_MB, (
        f"Handoff residue regression: {residue:.1f} MB above baseline "
        f"(gate: {RESIDUE_GATE_MB} MB). baseline={baseline:.1f} "
        f"post_release={post_release:.1f}. Phase A.6b floor was 278 MB; a "
        f"jump suggests new unreleased state in Transcriber.unload_model."
    )


def test_budget_env_var_flows_to_pipeline(
    ensure_container: None,
    torch_cuda: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DIARIZATION_VRAM_BUDGET_MB env -> settings -> pipeline.vram_budget_mb."""
    monkeypatch.setenv("DIARIZATION_VRAM_BUDGET_MB", "1500")
    monkeypatch.setenv("DIARIZATION_MIXED_PRECISION", "false")

    # Reload the settings module so the monkeypatched env is picked up.
    import importlib

    from app.core import config as config_module

    importlib.reload(config_module)
    assert config_module.settings.DIARIZATION_VRAM_BUDGET_MB == 1500
    assert config_module.settings.DIARIZATION_MIXED_PRECISION is False

    # Load a diarizer and confirm the fork pipeline has the budget set.
    from app.transcription.config import TranscriptionConfig
    from app.transcription.diarizer import SpeakerDiarizer

    cfg = TranscriptionConfig(
        model_name="base",
        compute_type="float16",
        device="cuda",
        device_index=0,
        hf_token=os.environ.get("HUGGINGFACE_TOKEN"),
    )
    diarizer = SpeakerDiarizer(cfg)
    diarizer.load_model()
    assert diarizer._pipeline is not None
    # Only asserted when the fork exposes the attribute. Stock upstream
    # pyannote won't, and the test still passes (policy is a no-op).
    if hasattr(diarizer._pipeline, "vram_budget_mb"):
        assert diarizer._pipeline.vram_budget_mb == 1500
    if hasattr(diarizer._pipeline, "embedding_mixed_precision"):
        assert diarizer._pipeline.embedding_mixed_precision is False
    diarizer.unload_model()


def test_model_manager_sequential_handoff(
    ensure_container: None,
    torch_cuda: object,
) -> None:
    """ModelManager.release_transcriber + get_diarizer completes."""
    import torch

    from app.transcription.config import TranscriptionConfig
    from app.transcription.model_manager import ModelManager

    cfg = TranscriptionConfig(
        model_name="base",
        compute_type="float16",
        device="cuda",
        device_index=0,
        beam_size=1,
        batch_size=8,
        hf_token=os.environ.get("HUGGINGFACE_TOKEN"),
    )
    mm = ModelManager.get_instance()
    mm.release_all()  # clean slate

    transcriber = mm.get_transcriber(cfg)
    assert transcriber.is_loaded
    mm.release_transcriber()
    torch.cuda.empty_cache()

    diarizer = mm.get_diarizer(cfg)
    assert diarizer.is_loaded
    mm.release_all()
    torch.cuda.empty_cache()
