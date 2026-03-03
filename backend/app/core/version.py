"""Application version, read from the VERSION file at repo root."""

import os
from pathlib import Path


def _read_version() -> str:
    """Read app version from VERSION file.

    Searches several possible locations to handle both local dev
    and Docker container environments.
    """
    # Walk up from this file to find VERSION
    current = Path(__file__).resolve().parent
    for _ in range(6):
        candidate = current / "VERSION"
        if candidate.is_file():
            return candidate.read_text().strip()
        current = current.parent

    # Fallback: environment variable (set during Docker build)
    env_version = os.environ.get("APP_VERSION")
    if env_version:
        return env_version

    return "unknown"


APP_VERSION = _read_version()
