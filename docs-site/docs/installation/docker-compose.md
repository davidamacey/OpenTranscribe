---
sidebar_position: 1
title: Docker Compose Installation
---

# Docker Compose Installation

This guide covers installing OpenTranscribe using Docker Compose - the recommended method for all deployment scenarios.

## Quick Installation

The fastest way to install OpenTranscribe is using our one-line installer:

```bash
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash
```

Skip to [Manual Installation](#manual-installation) if you prefer more control.

## Prerequisites

### Required Software

**Docker Engine** (v20.10+)
```bash
# Check Docker version
docker --version

# Expected output
Docker version 20.10.x or higher
```

**Docker Compose** (v2.0+)
```bash
# Check Docker Compose version
docker compose version

# Expected output
Docker Compose version v2.x.x or higher
```

:::warning Important
Use `docker compose` (with space), not `docker-compose` (with hyphen). OpenTranscribe requires Docker Compose V2.
:::

**Installing Docker:**
- **Linux**: [docs.docker.com/engine/install](https://docs.docker.com/engine/install/)
- **macOS**: [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)
- **Windows**: [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/) with WSL2

### System Requirements

See [Hardware Requirements](./hardware-requirements.md) for detailed specs.

**Minimum:**
- 8GB RAM
- 4 CPU cores
- 50GB disk space
- Internet connection (for initial setup)

**Recommended:**
- 16GB+ RAM
- 8+ CPU cores
- 100GB+ SSD storage
- NVIDIA GPU with 8GB+ VRAM

### Optional: NVIDIA GPU

For GPU acceleration (recommended):

1. **NVIDIA GPU** with CUDA support (GTX 1060 or better)
2. **NVIDIA Driver** (version 470.x or higher)
3. **NVIDIA Container Toolkit** installed

See [GPU Setup Guide](./gpu-setup.md) for installation instructions.

## Manual Installation

If you prefer manual installation or need more control:

### Step 1: Clone Repository (Development)

For **development from source**:

```bash
# Clone the repository
git clone https://github.com/davidamacey/OpenTranscribe.git
cd OpenTranscribe

# Make utility script executable
chmod +x opentr.sh
```

### Step 2: Download Production Files (Deployment)

For **production deployment with Docker Hub images**:

```bash
# Create directory
mkdir opentranscribe && cd opentranscribe

# Download production docker-compose file
curl -O https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/docker-compose.prod.yml

# Rename for convenience
mv docker-compose.prod.yml docker-compose.yml

# Download management script
curl -O https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/opentranscribe.sh
chmod +x opentranscribe.sh

# Download environment template
curl -O https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/.env.example
```

### Step 3: Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit configuration
nano .env  # or use your preferred editor
```

**Key variables to configure:**

```bash
# Security (REQUIRED - generate strong secrets)
SECRET_KEY=your-super-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key

# Generate secrets with
openssl rand -hex 32

# HuggingFace Token (REQUIRED for speaker diarization)
HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Database (use strong passwords in production)
POSTGRES_PASSWORD=strong-password-here

# Storage
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=strong-minio-password

# GPU Settings (auto-detected by installer)
USE_GPU=true                  # false for CPU-only
CUDA_VISIBLE_DEVICES=0        # GPU device ID
WHISPER_MODEL=large-v2        # large-v2, medium, base
COMPUTE_TYPE=float16          # float16 for GPU, int8 for CPU
BATCH_SIZE=16                 # 16 for GPU, 1-4 for CPU

# Model Cache (where AI models are stored)
MODEL_CACHE_DIR=./models
```

See [Environment Variables](../configuration/environment-variables.md) for all options.

### Step 4: Set Up HuggingFace

**This step is CRITICAL for speaker diarization**

1. **Get a token** at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
2. **Accept model agreements** for:
   - [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
   - [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
3. **Add to .env**: `HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxx`

See [HuggingFace Setup](./huggingface-setup.md) for detailed instructions.

### Step 5: Download AI Models (Optional but Recommended)

Pre-download models to avoid first-use delays:

```bash
# Using Docker to download models
docker run --rm \
  -v ./models:/models \
  -e HUGGINGFACE_TOKEN=your_token_here \
  davidamacey/opentranscribe-backend:latest \
  python -c "from app.tasks.transcription import download_models; download_models()"
```

This downloads ~2.5GB of AI models.

### Step 6: Start OpenTranscribe

**For Development (source code):**
```bash
./opentr.sh start dev
```

**For Production (Docker Hub images):**
```bash
./opentranscribe.sh start
# or
docker compose up -d
```

### Step 7: Verify Installation

Check that all services are running:

```bash
# Check service status
docker compose ps

# Expected output - all services should show "Up"
NAME                    STATUS
opentranscribe-backend  Up (healthy)
opentranscribe-celery   Up (healthy)
opentranscribe-frontend Up
opentranscribe-postgres Up (healthy)
opentranscribe-redis    Up (healthy)
opentranscribe-minio    Up (healthy)
opentranscribe-opensearch Up (healthy)
opentranscribe-flower   Up
```

Check logs for any errors:

```bash
# View all logs
docker compose logs

# View specific service logs
docker compose logs backend
docker compose logs celery-worker
```

### Step 8: Access the Application

Open your browser and navigate to:

- **Web Interface**: http://localhost:5173
- **API Documentation**: http://localhost:8080/docs
- **Task Monitor** (Flower): http://localhost:5555/flower
- **MinIO Console**: http://localhost:9091
- **OpenSearch**: http://localhost:9200

## Docker Compose Structure

OpenTranscribe uses a base + override pattern:

### File Structure

```
docker-compose.yml          # Base configuration (all environments)
docker-compose.override.yml # Development overrides (auto-loaded)
docker-compose.prod.yml     # Production overrides
docker-compose.offline.yml  # Offline/airgapped overrides
docker-compose.gpu-scale.yml # Multi-GPU scaling overrides
```

### Usage

**Development** (with hot reload):
```bash
# Automatically loads docker-compose.yml + docker-compose.override.yml
docker compose up
```

**Production** (with Docker Hub images):
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

**Offline** (airgapped environment):
```bash
docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d
```

**Multi-GPU** (parallel processing):
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu-scale.yml up -d
```

## Service Architecture

OpenTranscribe consists of 8 Docker services:

### Core Services

**backend** (FastAPI)
- REST API server
- WebSocket support
- User authentication
- File management
- Port: 8080

**frontend** (Svelte + Vite)
- React-based UI
- Progressive Web App
- Port: 5173

**postgres** (PostgreSQL 15)
- Main database
- User data, transcriptions, speakers
- Port: 5432

**redis** (Redis 7)
- Celery message broker
- Task queue coordination
- Port: 6379

### Storage Services

**minio** (MinIO)
- S3-compatible object storage
- Media files, audio, waveforms
- Port: 9000 (API), 9091 (Console)

**opensearch** (OpenSearch 3.3.1)
- Full-text search
- Vector search for semantic search
- Port: 9200

### Worker Services

**celery-worker** (Celery)
- Background AI processing
- Transcription, diarization, summarization
- Multi-queue architecture (GPU, CPU, NLP, Download)

**flower** (Celery monitoring)
- Task monitoring dashboard
- Worker status
- Port: 5555

## Management Commands

### Starting and Stopping

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# Stop and remove volumes (deletes data!)
docker compose down -v

# Restart specific service
docker compose restart backend
```

### Viewing Logs

```bash
# View all logs
docker compose logs

# Follow logs in real-time
docker compose logs -f

# View specific service logs
docker compose logs backend
docker compose logs celery-worker

# View last 100 lines
docker compose logs --tail=100
```

### Accessing Containers

```bash
# Execute command in container
docker compose exec backend bash

# Access database
docker compose exec postgres psql -U postgres -d opentranscribe

# Check worker status
docker compose exec celery-worker celery -A app.tasks.celery_app inspect active
```

### Updating

```bash
# Pull latest images (for production deployment)
docker compose pull

# Rebuild images (for development)
docker compose build

# Restart with new images
docker compose up -d
```

## Advanced Configuration

### Custom Ports

Edit `docker-compose.yml` or use environment variables:

```yaml
services:
  frontend:
    ports:
      - "${FRONTEND_PORT:-5173}:5173"
  backend:
    ports:
      - "${BACKEND_PORT:-8080}:8080"
```

### Resource Limits

```yaml
services:
  celery-worker:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 16G
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

### Persistent Data

Data is persisted in Docker volumes:

```bash
# List volumes
docker volume ls | grep opentranscribe

# Backup volume
docker run --rm -v opentranscribe_postgres-data:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/postgres-backup.tar.gz /data

# Restore volume
docker run --rm -v opentranscribe_postgres-data:/data -v $(pwd):/backup \
  ubuntu tar xzf /backup/postgres-backup.tar.gz -C /
```

## Troubleshooting

### Services Won't Start

```bash
# Check Docker is running
systemctl status docker

# Check Docker Compose version
docker compose version

# Check for port conflicts
netstat -tulpn | grep -E '5173|8080|5432|6379|9000|9200'

# Check logs
docker compose logs
```

### Out of Memory

```bash
# Check Docker resources
docker stats

# Reduce model size in .env
WHISPER_MODEL=medium  # or base
BATCH_SIZE=8          # or lower

# Increase Docker memory limit (Docker Desktop)
# Docker Desktop → Settings → Resources → Memory
```

### GPU Not Working

```bash
# Check NVIDIA driver
nvidia-smi

# Check NVIDIA Container Toolkit
docker run --rm --gpus all nvidia/cuda:11.8-base-ubuntu22.04 nvidia-smi

# Check GPU is visible to container
docker compose exec celery-worker nvidia-smi
```

### Permission Errors

```bash
# Fix model cache permissions
./scripts/fix-model-permissions.sh

# Or manually
sudo chown -R 1000:1000 ./models
```

## Next Steps

- **[Hardware Requirements](./hardware-requirements.md)** - Optimize for your hardware
- **[GPU Setup](./gpu-setup.md)** - Enable GPU acceleration
- **[Configuration](../configuration/environment-variables.md)** - Customize settings
- **[Troubleshooting](./troubleshooting.md)** - Resolve common issues
- **[Production Deployment](../deployment/production.md)** - Deploy to production

## Getting Help

- **[FAQ](../faq.md)** - Common questions
- **[GitHub Issues](https://github.com/davidamacey/OpenTranscribe/issues)** - Report bugs
- **[GitHub Discussions](https://github.com/davidamacey/OpenTranscribe/discussions)** - Ask questions
