"""Local Whisper model discovery — scans the HuggingFace cache for downloaded models.

This module provides ``discover_local_models()`` which returns a list of locally
available faster-whisper model short names (e.g. ``"large-v3-turbo"``).  It works
by scanning the HuggingFace hub cache directory for directories matching the
``models--{org}--faster-whisper-*`` naming convention and mapping them back to the
canonical short names used by faster-whisper / CTranslate2.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Mapping from faster-whisper short name → HuggingFace repo id.
# Mirrors faster_whisper.utils._MODELS but kept here to avoid importing
# the full faster_whisper package in non-GPU contexts (e.g. API server).
_SHORT_NAME_TO_REPO: dict[str, str] = {
    "tiny.en": "Systran/faster-whisper-tiny.en",
    "tiny": "Systran/faster-whisper-tiny",
    "base.en": "Systran/faster-whisper-base.en",
    "base": "Systran/faster-whisper-base",
    "small.en": "Systran/faster-whisper-small.en",
    "small": "Systran/faster-whisper-small",
    "medium.en": "Systran/faster-whisper-medium.en",
    "medium": "Systran/faster-whisper-medium",
    "large-v1": "Systran/faster-whisper-large-v1",
    "large-v2": "Systran/faster-whisper-large-v2",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large": "Systran/faster-whisper-large-v3",
    "distil-large-v2": "Systran/faster-distil-whisper-large-v2",
    "distil-medium.en": "Systran/faster-distil-whisper-medium.en",
    "distil-small.en": "Systran/faster-distil-whisper-small.en",
    "distil-large-v3": "Systran/faster-distil-whisper-large-v3",
    "distil-large-v3.5": "distil-whisper/distil-large-v3.5-ct2",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    "turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}

# Reverse mapping: HuggingFace cache dir name → preferred short name.
# The cache dir format is "models--{org}--{repo}" with "/" replaced by "--".
# When multiple short names map to the same repo (e.g. "large" and "large-v3"),
# we prefer the more specific name.
_REPO_DIR_TO_SHORT: dict[str, str] = {}
for _name, _repo in sorted(_SHORT_NAME_TO_REPO.items(), key=lambda x: len(x[0]), reverse=True):
    _dir_name = f"models--{_repo.replace('/', '--')}"
    if _dir_name not in _REPO_DIR_TO_SHORT:
        _REPO_DIR_TO_SHORT[_dir_name] = _name


def _get_hf_cache_dir() -> Path:
    """Return the HuggingFace hub cache directory path."""
    # In Docker: volume-mounted to /home/appuser/.cache/huggingface
    # Locally: ~/.cache/huggingface  or HF_HOME / HUGGINGFACE_HUB_CACHE env vars
    cache = os.getenv("HUGGINGFACE_HUB_CACHE") or os.getenv("HF_HOME")
    if cache:
        return Path(cache) / "hub" if "hub" not in cache else Path(cache)

    # MODEL_CACHE_DIR is the project-level setting from .env
    model_cache = os.getenv("MODEL_CACHE_DIR")
    if model_cache:
        return Path(model_cache) / "huggingface" / "hub"

    return Path.home() / ".cache" / "huggingface" / "hub"


def discover_local_models() -> list[dict]:
    """Scan the HuggingFace cache for downloaded faster-whisper models.

    Returns a list of dicts, each with:
        - ``short_name``: the canonical faster-whisper short name (e.g. "large-v3-turbo")
        - ``repo_id``: the HuggingFace repo identifier
        - ``downloaded``: always True (only downloaded models are returned)
    """
    cache_dir = _get_hf_cache_dir()
    if not cache_dir.is_dir():
        logger.debug("HuggingFace cache dir not found: %s", cache_dir)
        return []

    found: list[dict] = []
    seen_names: set[str] = set()

    try:
        for entry in cache_dir.iterdir():
            if not entry.is_dir():
                continue
            short_name = _REPO_DIR_TO_SHORT.get(entry.name)
            if short_name and short_name not in seen_names:
                # Verify the model has actual blobs (not just an empty placeholder)
                blobs_dir = entry / "blobs"
                if blobs_dir.is_dir() and any(blobs_dir.iterdir()):
                    repo_id = _SHORT_NAME_TO_REPO.get(short_name, "")
                    found.append(
                        {
                            "short_name": short_name,
                            "repo_id": repo_id,
                            "downloaded": True,
                        }
                    )
                    seen_names.add(short_name)
    except OSError as exc:
        logger.warning("Error scanning model cache %s: %s", cache_dir, exc)

    # Sort by short name for stable ordering
    found.sort(key=lambda m: m["short_name"])
    return found


def get_downloaded_model_names() -> set[str]:
    """Return a set of short names of locally downloaded Whisper models."""
    return {m["short_name"] for m in discover_local_models()}
