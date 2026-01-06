"""
Hardware Detection and Configuration Module

This module provides automatic detection of available hardware acceleration
(CUDA, MPS, CPU) and configures optimal settings for each platform.

Supports:
- NVIDIA GPUs with CUDA (Linux/Windows)
- Apple Silicon with MPS (macOS)
- CPU fallback (all platforms)
"""

import logging
import os
import platform
from typing import Any
from typing import Optional

logger = logging.getLogger(__name__)


class HardwareConfig:
    """Hardware detection and configuration for cross-platform AI processing."""

    def __init__(
        self,
        force_device: Optional[str] = None,
        force_compute_type: Optional[str] = None,
    ):
        """
        Initialize hardware configuration.

        Args:
            force_device: Force specific device ('cuda', 'mps', 'cpu')
            force_compute_type: Force compute type ('float16', 'float32', 'int8')
        """
        self.system = platform.system().lower()
        self.machine = platform.machine().lower()
        self.python_version = platform.python_version()

        # Detect PyTorch availability
        try:
            import torch

            self.torch_available = True
            self.torch_version = torch.__version__
        except ImportError:
            self.torch_available = False
            self.torch_version = None

        # Device and compute type detection
        self.device = force_device or self._detect_optimal_device()
        self.compute_type = force_compute_type or self._detect_optimal_compute_type()
        self.batch_size = self._get_optimal_batch_size()

        # Log configuration
        logger.info(f"Hardware Config: {self.get_summary()}")

    def _detect_optimal_device(self) -> str:
        """Detect the best available device for AI processing."""
        if not self.torch_available:
            logger.warning("PyTorch not available, defaulting to CPU")
            return "cpu"

        import torch

        # Check for CUDA (NVIDIA GPU)
        if torch.cuda.is_available():
            cuda_device_count = torch.cuda.device_count()
            logger.info(f"CUDA available with {cuda_device_count} device(s)")

            # In production, Docker maps the requested GPU (via GPU_DEVICE_ID) to device 0
            # For simplicity, always use device 0 since celery-worker runs in Docker
            torch.cuda.set_device(0)
            device_name = torch.cuda.get_device_name(0)
            gpu_requested = os.getenv("GPU_DEVICE_ID", "0")
            logger.info(f"Using CUDA device 0 (GPU_DEVICE_ID={gpu_requested}): {device_name}")
            return "cuda"

        # Check for MPS (Apple Silicon)
        if (
            self.system == "darwin"
            and hasattr(torch.backends, "mps")
            and torch.backends.mps.is_available()
        ):
            logger.info("Apple MPS available")
            return "mps"

        # Fallback to CPU
        logger.info("Using CPU (no GPU acceleration available)")
        return "cpu"

    def _detect_optimal_compute_type(self) -> str:
        """Detect optimal compute precision based on device and capabilities."""
        if not self.torch_available:
            return "int8"  # Most compatible for CPU-only

        import torch

        if self.device == "cuda":
            # Check for bfloat16 support (newer GPUs)
            if torch.cuda.is_bf16_supported():
                return "float16"
            # Check CUDA capability for half precision
            capability = torch.cuda.get_device_capability()
            if capability[0] >= 7:  # Volta and newer
                return "float16"
            else:
                return "float32"

        elif self.device == "mps":
            # MPS works best with float32
            return "float32"

        else:  # CPU
            # CPU: int8 for better performance, float32 for compatibility
            return "int8"

    def _get_optimal_batch_size(self) -> int:
        """Get optimal batch size based on device and available memory."""
        if self.device == "cuda":
            try:
                import torch

                # Get GPU memory info
                total_memory = torch.cuda.get_device_properties(0).total_memory
                memory_gb = total_memory / (1024**3)

                if memory_gb >= 24:  # High-end GPU
                    return 16
                elif memory_gb >= 12:  # Mid-range GPU
                    return 8
                elif memory_gb >= 6:  # Entry-level GPU
                    return 4
                else:
                    return 2
            except Exception:
                return 8  # Safe default

        elif self.device == "mps":
            # Apple Silicon - conservative due to unified memory
            # Increase batch size since WhisperX will use CPU
            return 8

        else:  # CPU
            # CPU processing - very conservative
            return 1

    def get_torch_device(self):
        """Get PyTorch device object."""
        if not self.torch_available:
            raise RuntimeError("PyTorch not available")

        import torch

        if self.device == "cuda":
            # Always use device 0 (Docker maps selected GPU to index 0)
            return torch.device("cuda:0")
        else:
            return torch.device(self.device)

    def get_whisperx_config(self) -> dict[str, Any]:
        """Get configuration parameters for WhisperX."""
        # WhisperX doesn't support MPS natively, so we use CPU for Apple Silicon
        # but keep other optimizations
        whisperx_device = "cpu" if self.device == "mps" else self.device
        whisperx_compute_type = "int8" if self.device == "mps" else self.compute_type

        config = {
            "device": whisperx_device,
            "compute_type": whisperx_compute_type,
            "batch_size": self.batch_size,
        }

        # Add device-specific configurations
        if self.device == "cuda":
            # Always use device 0 (Docker maps selected GPU to index 0)
            config["device_index"] = 0

        return config

    def get_pyannote_config(self) -> dict[str, Any]:
        """Get configuration parameters for PyAnnote (speaker diarization)."""
        config = {"device": self.get_torch_device() if self.torch_available else "cpu"}

        return config

    def get_vram_usage(self) -> dict[str, Any]:
        """
        Get current VRAM usage statistics.

        Returns:
            Dictionary with VRAM usage info (allocated, reserved, free, total in MB)
        """
        if not self.torch_available:
            return {"error": "PyTorch not available"}

        import torch

        if self.device == "cuda" and torch.cuda.is_available():
            try:
                # Get memory stats from PyTorch
                allocated = torch.cuda.memory_allocated(0) / (1024**2)  # Convert to MB
                reserved = torch.cuda.memory_reserved(0) / (1024**2)
                total = torch.cuda.get_device_properties(0).total_memory / (1024**2)
                free = total - allocated

                return {
                    "allocated_mb": round(allocated, 2),
                    "reserved_mb": round(reserved, 2),
                    "free_mb": round(free, 2),
                    "total_mb": round(total, 2),
                    "usage_percent": round((allocated / total) * 100, 2),
                }
            except Exception as e:
                logger.error(f"Error getting VRAM usage: {e}")
                return {"error": str(e)}
        else:
            return {"device": self.device, "message": "Not using CUDA"}

    def log_vram_usage(self, context: str = ""):
        """
        Log current VRAM usage with context.

        Args:
            context: Description of current operation for logging
        """
        vram = self.get_vram_usage()
        if "error" in vram:
            logger.debug(f"VRAM monitoring unavailable: {vram.get('error', 'unknown')}")
            return

        # Non cuda devices don't have the keys we need
        required_keys = {"allocated_mb", "reserved_mb", "total_mb", "usage_percent"}
        if not required_keys.issubset(vram.keys()):
            logger.debug(
                "VRAM monitoring skipped: stats unavailable "
                f"(device={vram.get('device', 'unknown')}, message={vram.get('message', 'n/a')})"
            )
            return

        logger.info(
            f"VRAM Usage [{context}]: "
            f"{vram['allocated_mb']:.0f}MB allocated, "
            f"{vram['reserved_mb']:.0f}MB reserved / "
            f"{vram['total_mb']:.0f}MB total "
            f"({vram['usage_percent']:.1f}% allocated, "
            f"{vram['reserved_mb'] / vram['total_mb'] * 100:.1f}% reserved)"
        )

    def optimize_memory_usage(self, aggressive: bool = True):
        """
        Optimize memory usage based on device.

        Args:
            aggressive: If True, perform multiple rounds of cleanup to maximize memory release
        """
        if not self.torch_available:
            return

        import gc

        import torch

        # Log VRAM before cleanup
        self.log_vram_usage("before cleanup")

        # Perform aggressive garbage collection FIRST
        # This ensures Python objects are freed before GPU cleanup
        for _ in range(3 if aggressive else 1):
            gc.collect()

        # Check what devices actually have allocated memory
        try:
            if self.device == "cuda" and torch.cuda.is_available():
                # Aggressive CUDA memory cleanup
                # Multiple calls to empty_cache() can help release stubborn cached memory
                for _ in range(3 if aggressive else 1):
                    torch.cuda.empty_cache()

                # Synchronize to ensure all GPU operations complete
                torch.cuda.synchronize()

                if aggressive:
                    # Force PyTorch to release unused cached memory back to CUDA
                    # This is more aggressive than empty_cache() alone
                    torch.cuda.reset_peak_memory_stats()
                    torch.cuda.empty_cache()

        except Exception as e:
            logger.debug(f"CUDA memory cleanup skipped: {e}")

        try:
            if (
                self.device == "mps"
                and hasattr(torch.backends, "mps")
                and torch.backends.mps.is_available()
                and hasattr(torch.mps, "empty_cache")
            ):
                # Clear MPS cache only if MPS is actually being used
                torch.mps.empty_cache()
        except Exception as e:
            logger.debug(f"MPS memory cleanup skipped: {e}")

        # Final garbage collection pass
        gc.collect()

        # Log VRAM after cleanup
        self.log_vram_usage("after cleanup")

    def get_environment_variables(self) -> dict[str, str]:
        """Get environment variables to optimize performance."""
        env_vars = {}

        if self.device == "cpu":
            # CPU optimizations
            import multiprocessing

            cpu_count = multiprocessing.cpu_count()

            env_vars.update(
                {
                    "OMP_NUM_THREADS": str(cpu_count),
                    "MKL_NUM_THREADS": str(cpu_count),
                    "NUMEXPR_NUM_THREADS": str(cpu_count),
                    "TORCH_CPP_LOG_LEVEL": "WARNING",
                }
            )

        elif self.device == "mps":
            # MPS optimizations
            env_vars.update(
                {
                    "PYTORCH_ENABLE_MPS_FALLBACK": "1",
                    "PYTORCH_MPS_HIGH_WATERMARK_RATIO": "0.0",
                }
            )

        elif self.device == "cuda":
            # CUDA optimizations
            env_vars.update({"TORCH_CUDA_ARCH_LIST": "6.0 6.1 7.0 7.5 8.0 8.6+PTX"})
            # Docker maps GPU_DEVICE_ID to container device 0

        return env_vars

    def get_summary(self) -> dict[str, Any]:
        """Get summary of hardware configuration."""
        return {
            "system": self.system,
            "machine": self.machine,
            "device": self.device,
            "compute_type": self.compute_type,
            "batch_size": self.batch_size,
            "torch_available": self.torch_available,
            "torch_version": self.torch_version,
        }

    def validate_configuration(self) -> tuple[bool, str]:
        """Validate the current configuration."""
        if not self.torch_available:
            return False, "PyTorch not available"

        import torch

        try:
            device = self.get_torch_device()
            # Test tensor creation
            test_tensor = torch.ones(1, device=device)

            if self.device == "cuda":
                # Test CUDA functionality
                test_tensor = test_tensor.cuda()
                torch.cuda.synchronize()

            elif self.device == "mps":
                # Test MPS functionality
                test_tensor = test_tensor.to("mps")

            return True, "Configuration valid"

        except Exception as e:
            return False, f"Configuration validation failed: {str(e)}"


def detect_hardware() -> HardwareConfig:
    """
    Convenience function to detect hardware configuration.

    Returns:
        HardwareConfig instance with detected settings
    """
    # Check for environment variable overrides
    force_device = os.getenv("TORCH_DEVICE")
    force_compute_type = os.getenv("COMPUTE_TYPE")

    # Allow 'auto' to mean None (auto-detection)
    if force_device == "auto":
        force_device = None
    if force_compute_type == "auto":
        force_compute_type = None

    return HardwareConfig(force_device, force_compute_type)


def get_docker_runtime_config() -> dict[str, Any]:
    """
    Get Docker runtime configuration based on detected hardware.

    Returns:
        Dictionary with Docker runtime settings
    """
    config = detect_hardware()

    docker_config = {"environment": config.get_environment_variables(), "deploy": {}}

    if config.device == "cuda":
        # NVIDIA GPU runtime
        docker_config["deploy"]["resources"] = {
            "reservations": {
                "devices": [
                    {
                        "driver": "nvidia",
                        "device_ids": [os.getenv("GPU_DEVICE_ID", "0")],
                        "capabilities": ["gpu"],
                    }
                ]
            }
        }

    return docker_config


if __name__ == "__main__":
    # Test hardware detection
    config = detect_hardware()
    print("Hardware Configuration:")
    for key, value in config.get_summary().items():
        print(f"  {key}: {value}")

    # Validate configuration
    is_valid, message = config.validate_configuration()
    print(f"\nValidation: {message}")

    # Show optimizations
    env_vars = config.get_environment_variables()
    if env_vars:
        print("\nRecommended environment variables:")
        for key, value in env_vars.items():
            print(f"  {key}={value}")
