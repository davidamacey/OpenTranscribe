"""
VRAM Profiling Utility

Context-manager-based profiler that captures per-step VRAM snapshots during
the transcription pipeline. Produces structured JSON reports for optimization.

Enable with ENABLE_VRAM_PROFILING=true environment variable.
"""

import json
import logging
import os
import time
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)


def is_profiling_enabled() -> bool:
    """Check if VRAM profiling is enabled via environment variable."""
    return os.getenv("ENABLE_VRAM_PROFILING", "false").lower() == "true"


class VRAMProfiler:
    """Collects per-step VRAM usage and timing data during pipeline execution."""

    def __init__(self, enabled: bool | None = None):
        """Initialize profiler.

        Args:
            enabled: Override enable state. If None, reads ENABLE_VRAM_PROFILING env var.
        """
        self.enabled = enabled if enabled is not None else is_profiling_enabled()
        self.steps: list[dict[str, Any]] = []
        self._cuda_available = False

        if self.enabled:
            try:
                import torch

                self._cuda_available = torch.cuda.is_available()
                if not self._cuda_available:
                    logger.info("VRAM profiling enabled but CUDA not available, timing-only mode")
            except ImportError:
                logger.warning("VRAM profiling enabled but PyTorch not installed")

    def _get_vram_mb(self) -> dict[str, float]:
        """Get current VRAM stats in MB."""
        if not self._cuda_available:
            return {}
        import torch

        return {
            "allocated_mb": torch.cuda.memory_allocated(0) / (1024**2),
            "reserved_mb": torch.cuda.memory_reserved(0) / (1024**2),
            "peak_mb": torch.cuda.max_memory_allocated(0) / (1024**2),
            "free_mb": (
                torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated(0)
            )
            / (1024**2),
        }

    def _reset_peak(self) -> None:
        """Reset peak memory stats for next measurement."""
        if self._cuda_available:
            import torch

            torch.cuda.reset_peak_memory_stats(0)

    @contextmanager
    def step(self, name: str):
        """Profile a pipeline step.

        Args:
            name: Human-readable step name (e.g., "transcription", "diarization")

        Yields:
            None - use as context manager around the step code
        """
        if not self.enabled:
            yield
            return

        self._reset_peak()
        vram_before = self._get_vram_mb()
        start_time = time.perf_counter()

        yield

        elapsed = time.perf_counter() - start_time
        vram_after = self._get_vram_mb()

        step_data = {
            "name": name,
            "duration_s": round(elapsed, 3),
            "vram_before_mb": round(vram_before.get("allocated_mb", 0), 1),
            "vram_peak_mb": round(vram_after.get("peak_mb", 0), 1),
            "vram_after_mb": round(vram_after.get("allocated_mb", 0), 1),
            "vram_reserved_mb": round(vram_after.get("reserved_mb", 0), 1),
        }
        self.steps.append(step_data)

        logger.info(
            f"VRAM_PROFILE [{name}]: {step_data['duration_s']}s, "
            f"before={step_data['vram_before_mb']}MB, "
            f"peak={step_data['vram_peak_mb']}MB, "
            f"after={step_data['vram_after_mb']}MB"
        )

    def get_report(self) -> dict[str, Any]:
        """Get full profiling report."""
        total_duration = sum(s["duration_s"] for s in self.steps)
        peak_vram = max((s["vram_peak_mb"] for s in self.steps), default=0)

        return {
            "profiling_enabled": self.enabled,
            "cuda_available": self._cuda_available,
            "total_duration_s": round(total_duration, 3),
            "peak_vram_mb": round(peak_vram, 1),
            "steps": self.steps,
        }

    def save_report(self, output_path: str) -> None:
        """Save profiling report to JSON file."""
        report = self.get_report()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        logger.info(f"VRAM profile saved to {output_path}")

    def log_report(self) -> None:
        """Log the full profiling report at INFO level."""
        if not self.enabled or not self.steps:
            return
        report = self.get_report()
        logger.info(f"VRAM PROFILE REPORT: {json.dumps(report, indent=2)}")
