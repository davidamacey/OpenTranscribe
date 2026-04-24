"""Phase 6.2 ONNX runtime test suite.

Layers T1-T6 per ``docs/upstream-patches/phase-6-2-onnx-export-feasibility.md``.

Runs in two environments:

- Unit tests (``test_numeric_parity.py``, ``test_fbank_parity.py``) are
  CI-runnable on synthetic inputs with a CPU-only ONNX Runtime.
- Integration tests (``test_der_regression.py`` + benchmark scripts) require
  a real GPU and the canonical sample WAVs in ``benchmark/test_audio/``.
"""
