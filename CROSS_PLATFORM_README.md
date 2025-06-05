# OpenTranscribe Cross-Platform Compatibility

## Overview

OpenTranscribe now supports **complete cross-platform compatibility** with automatic hardware detection and optimization for:

- **NVIDIA GPUs** with CUDA (Linux/Windows WSL)
- **Apple Silicon** with MPS acceleration (macOS M1/M2)
- **CPU-only processing** (all platforms)

The system automatically detects available hardware and optimizes configuration for maximum performance.

## Quick Start

### 1. Download and Run Setup Script

```bash
# Get the setup script
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/feat/cross-platform-compatibility/setup-opentranscribe.sh -o setup-opentranscribe.sh

# Make it executable and run
chmod +x setup-opentranscribe.sh
./setup-opentranscribe.sh
```

The setup script will:
- Detect your hardware (CUDA/MPS/CPU)
- Test NVIDIA Container Toolkit (if GPU detected)
- Configure optimal precision and batch sizes
- Create production docker-compose.yml
- Generate secure .env configuration
- Create management scripts

### 2. Start OpenTranscribe (Manual)

```bash
cd opentranscribe
./opentranscribe.sh start
```

This approach gives you control over when Docker images are downloaded and containers are started.

## Hardware Support

### NVIDIA GPU (CUDA)

**Requirements:**
- NVIDIA GPU with CUDA Compute Capability 6.0+
- NVIDIA Driver 470+
- NVIDIA Container Toolkit

**Automatic Configuration:**
- Device: `cuda`
- Precision: `float16` (if supported) or `float32`
- Batch Size: `16` (high-end) to `4` (entry-level)
- Model: `large-v2` (recommended)

**Performance:** ~0.1x real-time (10x faster than real-time)

### Apple Silicon (MPS)

**Requirements:**
- macOS 12.3+ with Apple Silicon (M1/M2)
- At least 8GB unified memory

**Automatic Configuration:**
- Device: `mps`
- Precision: `float32`
- Batch Size: `8` (M1 Max/Ultra) to `4` (M1)
- Model: `medium` (recommended)

**Performance:** ~0.3x real-time (3x faster than real-time)

### CPU Processing

**Requirements:**
- Multi-core CPU (4+ cores recommended)
- 8GB+ RAM

**Automatic Configuration:**
- Device: `cpu`
- Precision: `int8` (optimized for CPU)
- Batch Size: `1-4` (based on CPU cores)
- Model: `base` (recommended for speed)

**Performance:** ~1.5x real-time (slower than real-time)

## Key Features

### ✅ Automatic Hardware Detection

The system automatically detects and configures:
- Available GPUs (NVIDIA CUDA, Apple MPS)
- Optimal precision (float16/float32/int8)
- Memory-appropriate batch sizes
- Docker runtime configuration

### ✅ Production Docker Images

- Pre-built images from Docker Hub
- Single backend image supports all platforms
- Single frontend image for all deployments
- Automatic hardware detection at runtime

### ✅ Smart Configuration

- Environment variables auto-detected
- Override capability for advanced users
- Performance optimization per platform
- Memory management and cleanup

### ✅ Comprehensive Scripts

- `setup-opentranscribe.sh` - Complete installation
- `opentranscribe.sh` - Daily management
- Hardware validation and health checks
- Cross-platform compatibility

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    OpenTranscribe                          │
├─────────────────────────────────────────────────────────────┤
│  Frontend (Svelte) - Universal for all platforms           │
├─────────────────────────────────────────────────────────────┤
│  Backend (FastAPI) - Unified cross-platform container      │
│  ├─ Hardware Detection Layer                               │
│  ├─ WhisperX Service (CUDA/MPS/CPU)                       │
│  ├─ PyAnnote Diarization (Multi-platform)                 │
│  └─ Celery Workers (Hardware-optimized)                   │
├─────────────────────────────────────────────────────────────┤
│  Infrastructure Services                                   │
│  ├─ PostgreSQL (Database)                                 │
│  ├─ Redis (Task Queue)                                    │
│  ├─ MinIO (Object Storage)                                │
│  └─ OpenSearch (Full-text Search)                         │
└─────────────────────────────────────────────────────────────┘
```

## Configuration Options

### Environment Variables

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `TORCH_DEVICE` | `auto`, `cuda`, `mps`, `cpu` | `auto` | Force specific device |
| `COMPUTE_TYPE` | `auto`, `float16`, `float32`, `int8` | `auto` | Force precision |
| `BATCH_SIZE` | `auto`, `1-32` | `auto` | Processing batch size |
| `WHISPER_MODEL` | `tiny`, `base`, `small`, `medium`, `large-v2` | Platform-optimized | AI model size |
| `GPU_DEVICE_ID` | `0`, `1`, `2`, etc. | `0` | GPU selection |

### Docker Compose Usage

```bash
# Production deployment (recommended)
./opentranscribe.sh start

# Direct Docker Compose usage
docker compose up -d

# Check configuration
docker compose config
```

## Management Commands

### OpenTranscribe Script (`./opentranscribe.sh`)

```bash
# Start with hardware detection
./opentranscribe.sh start

# View real-time logs
./opentranscribe.sh logs

# Check system health
./opentranscribe.sh health

# Show hardware configuration
./opentranscribe.sh config

# Access container shell
./opentranscribe.sh shell backend

# Full system restart
./opentranscribe.sh restart

# Clean installation (⚠️ removes all data)
./opentranscribe.sh clean
```

### Development Script (`./opentr.sh`)

```bash
# Start development environment
./opentr.sh start dev

# Reset development database
./opentr.sh reset dev

# Rebuild specific services
./opentr.sh rebuild-backend
./opentr.sh rebuild-frontend

# Monitor logs
./opentr.sh logs backend
```

## Performance Comparison

| Platform | Model | Batch | Memory | Speed (RTF) | Quality |
|----------|-------|-------|--------|-------------|---------|
| RTX 4090 | large-v2 | 16 | 16GB | 0.05 | Excellent |
| RTX 3080 | large-v2 | 8 | 10GB | 0.1 | Excellent |
| M2 Max | medium | 8 | 8GB | 0.3 | Very Good |
| M1 | small | 4 | 4GB | 0.5 | Good |
| CPU 16c | base | 4 | 16GB | 1.5 | Basic |

*RTF = Real-Time Factor (lower is faster)*

## Troubleshooting

### NVIDIA GPU Not Detected

```bash
# Check GPU availability
nvidia-smi

# Check Docker GPU support
docker run --rm --gpus all nvidia/cuda:11.8-base-ubuntu22.04 nvidia-smi

# Install NVIDIA Container Toolkit
# Follow: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
```

### Apple Silicon Issues

```bash
# Check macOS version (requires 12.3+)
sw_vers -productVersion

# Check Docker platform
docker --version

# Verify MPS availability
python3 -c "import torch; print(torch.backends.mps.is_available())"
```

### Memory Issues

```bash
# Reduce batch size
export BATCH_SIZE=4

# Use smaller model
export WHISPER_MODEL=small

# Check available memory
docker stats
```

### Performance Optimization

```bash
# Force specific device
export TORCH_DEVICE=cuda

# Optimize for memory
export COMPUTE_TYPE=int8

# Increase batch size (if memory allows)
export BATCH_SIZE=32
```

## Development

### Hardware Detection Module

Located at `backend/app/utils/hardware_detection.py`:

```python
from app.utils.hardware_detection import detect_hardware

# Get hardware configuration
config = detect_hardware()
print(config.get_summary())

# Get optimized settings
whisperx_config = config.get_whisperx_config()
docker_config = config.get_docker_runtime_config()
```

### Adding New Platforms

1. Update `detect_hardware_acceleration()` in `hardware_detection.py`
2. Add platform-specific configuration in `setup-opentranscribe.sh`
3. Update docker-compose template in setup script
4. Test with the validation workflow

### Testing

```bash
# Test hardware detection
python3 -c "from backend.app.utils.hardware_detection import detect_hardware; print(detect_hardware().get_summary())"

# Validate Docker configuration
docker compose config

# End-to-end test
./opentranscribe.sh health
```

## Contributing

When contributing to cross-platform support:

1. Test on multiple platforms (Linux, macOS, Windows WSL)
2. Verify both GPU and CPU modes work
3. Check memory usage and performance
4. Update documentation for new features
5. Ensure backward compatibility

## License

Same as OpenTranscribe main project.

## Support

- **Issues:** GitHub Issues
- **Discussions:** GitHub Discussions
- **Documentation:** This README and inline code docs

---

**Ready to transcribe on any platform! 🚀**