#!/usr/bin/env python3
"""Apply Blackwell SM_121 compatibility patches at Docker build time.

NVIDIA Blackwell GPUs (GB10, DGX Spark) report compute capability 12.1
(SM_121), which is not recognized by NVRTC, CTranslate2, or other JIT
compilers bundled with current PyTorch releases.

This script applies three patches:

1. Monkey-patch torch.cuda.get_device_capability() to return (9, 0) for
   SM_12x GPUs, so JIT compilers target Hopper (SM_90) instead.

2. Fix torchaudio's fbank implementation to avoid jiterator .abs() which
   crashes on Blackwell.  Replaces with torch.abs().

3. Disable pyannote.audio's version check, which fails against NVIDIA's
   dev-version torch strings (e.g., 2.6.0a0+abc123).

All patches are idempotent — safe to run multiple times.
"""

from __future__ import annotations

import os
import sys

PATCH_MARKER = "# --- Blackwell SM_121 compatibility patch ---"

TORCH_INIT_PATCH = """
# --- Blackwell SM_121 compatibility patch ---
# Spoof compute capability to SM_90 (Hopper) so that NVRTC-based JIT
# compilers (CTranslate2, triton, etc.) don't crash on unknown SM_121.
_original_get_device_capability = torch.cuda.get_device_capability


def _patched_get_device_capability(device=None):
    cap = _original_get_device_capability(device)
    if cap[0] >= 12:
        return (9, 0)
    return cap


torch.cuda.get_device_capability = _patched_get_device_capability
# --- End Blackwell patch ---
"""

PYANNOTE_VERSION_STUB = """\
# Blackwell patch: skip version check for NVIDIA dev torch builds.
# The NVIDIA container bundles torch with a dev version string
# (e.g., 2.6.0a0+abc123) that fails pyannote's version comparison.


def check():
    pass
"""


def patch_torch_init() -> None:
    """Append SM_121 -> SM_90 monkey-patch to torch/__init__.py."""
    import torch

    init_path = os.path.join(os.path.dirname(torch.__file__), "__init__.py")
    with open(init_path) as f:
        content = f.read()

    if PATCH_MARKER in content:
        print(f"  [skip] {init_path} already patched")
        return

    with open(init_path, "a") as f:
        f.write(TORCH_INIT_PATCH)
    print(f"  [ok]   Patched {init_path}")


def patch_torchaudio_fbank() -> None:
    """Replace .abs() with torch.abs() in torchaudio's kaldi compliance."""
    try:
        import torchaudio
    except ImportError:
        print("  [skip] torchaudio not installed")
        return

    kaldi_path = os.path.join(os.path.dirname(torchaudio.__file__), "compliance", "kaldi.py")
    if not os.path.exists(kaldi_path):
        print(f"  [skip] {kaldi_path} not found")
        return

    with open(kaldi_path) as f:
        content = f.read()

    if "torch.abs(dct_filters)" in content:
        print(f"  [skip] {kaldi_path} already patched")
        return

    # Replace jiterator .abs() call with explicit torch.abs()
    new_content = content.replace(
        ".abs()",
        "# .abs() replaced for Blackwell compatibility\n"
        "    dct_filters = torch.abs(dct_filters)  # noqa: F841",
    )

    if new_content == content:
        print(f"  [skip] {kaldi_path} — pattern not found (may be a newer version)")
        return

    with open(kaldi_path, "w") as f:
        f.write(new_content)
    print(f"  [ok]   Patched {kaldi_path}")


def patch_pyannote_version() -> None:
    """Replace pyannote's version check with a no-op stub."""
    try:
        import pyannote.audio
    except ImportError:
        print("  [skip] pyannote.audio not installed")
        return

    version_path = os.path.join(os.path.dirname(pyannote.audio.__file__), "utils", "version.py")
    if not os.path.exists(version_path):
        print(f"  [skip] {version_path} not found (fork may not need this)")
        return

    with open(version_path) as f:
        content = f.read()

    if "Blackwell patch" in content:
        print(f"  [skip] {version_path} already patched")
        return

    with open(version_path, "w") as f:
        f.write(PYANNOTE_VERSION_STUB)
    print(f"  [ok]   Patched {version_path}")


def main() -> int:
    """Apply all Blackwell compatibility patches."""
    print("Applying Blackwell SM_121 compatibility patches...")

    patch_torch_init()
    patch_torchaudio_fbank()
    patch_pyannote_version()

    print("Blackwell patches complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
