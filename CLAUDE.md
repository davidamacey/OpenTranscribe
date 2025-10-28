# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Architecture

OpenTranscribe is a containerized AI-powered transcription application with these core services:
- **Frontend**: Svelte/TypeScript SPA with Progressive Web App capabilities
- **Backend**: FastAPI with async support and OpenAPI documentation
- **Database**: PostgreSQL with SQLAlchemy ORM (no migrations during development)
- **Storage**: MinIO S3-compatible object storage
- **Search**: OpenSearch for full-text and vector search
- **Queue**: Celery with Redis for background AI processing
- **Monitoring**: Flower for task monitoring

### Key Technologies
- **AI Models**: WhisperX for transcription, PyAnnote for speaker diarization
- **Frontend**: Svelte, TypeScript, Vite, Plyr for media playback
- **Backend**: FastAPI, SQLAlchemy 2.0, Alembic, Celery
- **Infrastructure**: Docker Compose, NGINX for production

## Development Commands

### Primary Development Script
Use `./opentr.sh` for all development operations:

```bash
# Start development environment
./opentr.sh start dev

# Stop all services
./opentr.sh stop

# View logs (all or specific service)
./opentr.sh logs [backend|frontend|postgres|celery-worker]

# Reset environment (WARNING: deletes all data)
./opentr.sh reset dev

# Check service status
./opentr.sh status

# Access container shell
./opentr.sh shell [backend|frontend|postgres]

# Database backup/restore
./opentr.sh backup
./opentr.sh restore backups/backup_file.sql

# Multi-GPU scaling (optional - for high-throughput systems)
./opentr.sh start dev --gpu-scale
./opentr.sh reset dev --gpu-scale
```

### Multi-GPU Worker Scaling (Optional)

For systems with multiple GPUs, you can enable parallel GPU workers to significantly increase transcription throughput.

**Use Case**: You have multiple GPUs and want to maximize processing speed by running multiple transcription workers in parallel.

**Example Hardware Setup**:
- GPU 0: NVIDIA RTX A6000 (49GB) - Running LLM model
- GPU 1: RTX 3080 Ti (12GB) - Default single worker (disabled when scaling)
- GPU 2: NVIDIA RTX A6000 (49GB) - Scaled workers (4 parallel)

**Configuration** (in `.env`):
```bash
GPU_SCALE_ENABLED=true      # Enable multi-GPU scaling
GPU_SCALE_DEVICE_ID=2       # Which GPU to use (default: 2)
GPU_SCALE_WORKERS=4         # Number of parallel workers (default: 4)
```

**Usage**:
```bash
# Start with GPU scaling enabled
./opentr.sh start dev --gpu-scale

# Reset with GPU scaling enabled
./opentr.sh reset dev --gpu-scale

# View scaled worker logs
docker compose logs -f celery-worker-gpu-scaled
```

**How It Works**:
- When `--gpu-scale` flag is used, the system loads `docker-compose.gpu-scale.yml` overlay
- Default single GPU worker is disabled (`scale: 0`)
- A new single container is created with `concurrency=4` (configurable via `GPU_SCALE_WORKERS`)
- The container runs 4 parallel Celery workers within a single process
- All workers target the specified GPU device and process from the `gpu` queue
- Celery automatically distributes tasks across the worker pool

**Performance**: With 4 parallel workers on a high-end GPU like the A6000, you can process 4 videos simultaneously, significantly reducing total processing time for batches of media files.

**Scaling**: Simply change `GPU_SCALE_WORKERS` in your `.env` file to adjust the number of concurrent workers (e.g., 2, 4, 6, 8) based on your GPU's memory and processing capacity.

### Docker Build & Push (Production Images)

Build and push production Docker images to Docker Hub:

```bash
# Build and push both services
./scripts/docker-build-push.sh

# Build specific service only
./scripts/docker-build-push.sh backend
./scripts/docker-build-push.sh frontend

# Auto-detect changes and build only what changed
./scripts/docker-build-push.sh auto

# Build for single platform (faster testing)
PLATFORMS=linux/amd64 ./scripts/docker-build-push.sh backend
```

See [scripts/README.md](scripts/README.md) for detailed documentation.

### Frontend Development
```bash
# From frontend/ directory
npm run dev          # Start dev server
npm run build        # Production build
npm run check        # Type checking
```

### Backend Development
```bash
# From backend/ directory (or via container)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
pytest tests/        # Run tests
alembic upgrade head # Apply migrations (production only)
```

## Database Management

**IMPORTANT**: During development, do NOT create Alembic migrations. Instead:
1. Update `database/init_db.sql` directly
2. Update SQLAlchemy models in `backend/app/models/`
3. Update Pydantic schemas in `backend/app/schemas/`
4. Reset the development database: `./opentr.sh reset dev`

For production deployments, migrations will be handled differently.

## Code Organization Patterns

### Backend Structure
- `app/api/endpoints/` - REST API routes organized by resource
- `app/models/` - SQLAlchemy ORM models
- `app/schemas/` - Pydantic validation schemas
- `app/services/` - Business logic and external integrations
- `app/tasks/` - Celery background tasks
- `app/core/` - Configuration and security

### Frontend Structure
- `src/components/` - Reusable Svelte components
- `src/routes/` - Page components
- `src/stores/` - Svelte stores for state management
- `src/lib/` - Utilities and services

### Key Patterns
- **Authentication**: JWT-based with role-based access control
- **File Processing**: Upload to MinIO → Celery task → AI processing → Database storage
- **Real-time Updates**: WebSockets for task progress notifications
- **Error Handling**: Structured error responses with proper HTTP status codes

## Development Guidelines

### Code Quality
- Keep files under 200-300 lines
- Use Google-style docstrings for Python code
- Follow existing patterns before creating new ones
- Always check for TypeScript errors
- Ensure light/dark mode compliance for frontend changes

### Docker and Services
- Use `docker compose` (not `docker-compose`)
- **Docker Compose Structure** (base + override pattern):
  - `docker-compose.yml` - Base configuration (all environments)
  - `docker-compose.override.yml` - Development overrides (auto-loaded)
  - `docker-compose.prod.yml` - Production overrides
  - `docker-compose.offline.yml` - Offline/airgapped overrides
- **Development**: Just run `docker compose up` (auto-loads override)
- **Production**: Use `-f docker-compose.yml -f docker-compose.prod.yml`
- **Offline**: Use `-f docker-compose.yml -f docker-compose.offline.yml`
- Always check container logs after starting services
- Kill existing servers before testing changes
- Layer Docker files for optimal caching

### Testing and Deployment
- Write thorough tests for major functionality
- No mocking data for dev/prod (tests only)
- Always restart/reset services after making changes
- Use appropriate opentr.sh commands for testing changes

## Service Endpoints

### Development URLs
- Frontend: http://localhost:5173
- Backend API: http://localhost:5174/api
- API Docs: http://localhost:5174/docs
- MinIO Console: http://localhost:5179
- Flower Dashboard: http://localhost:5175/flower
- OpenSearch: http://localhost:5180

### Important File Locations
- Environment config: `.env` (never overwrite without confirmation)
- Environment template: `.env.example` (template for all installations)
- Database init: `database/init_db.sql`
- Docker base config: `docker-compose.yml` (common to all environments)
- Docker dev config: `docker-compose.override.yml` (auto-loaded in dev)
- Docker prod config: `docker-compose.prod.yml` (production overrides)
- Docker offline config: `docker-compose.offline.yml` (airgapped overrides)
- Frontend build: `frontend/vite.config.ts`

## AI Processing Workflow

1. File upload to MinIO storage
2. Metadata extraction and database record creation
3. Celery task dispatch to worker with GPU support
4. WhisperX transcription with word-level alignment
5. PyAnnote speaker diarization and voice fingerprinting
6. **LLM speaker identification suggestions** (optional - manual verification required)
7. **LLM-powered summarization** with BLUF format (optional - user-triggered)
   - Automatic context-aware processing (single or multi-section based on transcript length)
   - Intelligent chunking at speaker/topic boundaries for long content
   - Section-by-section analysis with final summary stitching
8. Database storage and OpenSearch indexing
9. WebSocket notification to frontend

### LLM Features (New in v2.0)

The application now includes optional AI-powered features using Large Language Models:

**AI Summarization:**
- BLUF (Bottom Line Up Front) format summaries
- Speaker analysis with talk time and key contributions
- Action items extraction with priorities and assignments
- Key decisions and follow-up items identification
- Support for multiple LLM providers (vLLM, OpenAI, Ollama, Claude)
- Intelligent section-by-section processing for transcripts of any length
- Automatic context-aware chunking and summary stitching

**Speaker Identification:**
- LLM-powered speaker name suggestions based on conversation context
- Confidence scoring for identification accuracy
- Manual verification workflow (suggestions are not auto-applied)
- Cross-video speaker matching with embedding analysis

**Configuration:**
- Set `LLM_PROVIDER` in .env file (vllm, openai, ollama, anthropic, openrouter)
- Configure provider-specific settings (API keys, endpoints, models)
- Features work independently - transcription works without LLM configuration

**Deployment Options:**
- **Cloud Providers**: Use `.env` configuration with external providers (OpenAI, Claude, OpenRouter, etc.)
- **Self-Hosted LLM**: Configure vLLM or Ollama endpoints in `.env` (deployed separately)
- **No LLM**: Leave LLM_PROVIDER empty for transcription-only mode

## Model Caching System

OpenTranscribe uses a simple volume-based model caching system that automatically persists AI models between container restarts.

### Configuration
- Set `MODEL_CACHE_DIR` in `.env` to specify cache location (default: `./models`)
- Models are automatically downloaded on first use
- All models persist across container restarts and rebuilds

### Directory Structure
```
${MODEL_CACHE_DIR}/
├── huggingface/          # HuggingFace models cache
│   ├── hub/             # WhisperX models (~1.5GB)
│   └── transformers/    # PyAnnote transformer cache
├── torch/               # PyTorch models cache
│   ├── hub/checkpoints/ # Wav2Vec2 alignment model (~360MB)
│   └── pyannote/        # PyAnnote speaker models (~500MB)
├── nltk_data/           # NLTK data files
│   ├── tokenizers/      # punkt_tab tokenizer (~13MB)
│   └── taggers/         # POS taggers
└── sentence-transformers/ # Sentence transformers models
    └── sentence-transformers_all-MiniLM-L6-v2/ # Semantic search model (~80MB)
```

### Speaker Diarization Configuration

**MIN_SPEAKERS / MAX_SPEAKERS Parameters:**

PyAnnote's speaker diarization uses sklearn's `AgglomerativeClustering`, which has **NO hard maximum limit** on the number of speakers:
- Default: `MIN_SPEAKERS=1`, `MAX_SPEAKERS=20`
- Can be increased to 50+ for large conferences/events with many speakers
- No hard upper limit - only constrained by the number of audio samples
- Performance threshold at `max(100, 0.02 * n_samples)` where algorithm behavior changes for efficiency

**Use Cases:**
- Small meetings: 2-5 speakers (default works fine)
- Medium meetings: 5-15 speakers (default works fine)
- Large conferences: 15-50 speakers (increase MAX_SPEAKERS to 30-50)
- Very large events: 50+ speakers (increase MAX_SPEAKERS accordingly)

**Note**: Higher values may impact processing time but will not cause errors.

### Docker Volume Mappings
The system uses simple volume mappings to cache models to their natural locations:
```yaml
volumes:
  - ${MODEL_CACHE_DIR}/huggingface:/home/appuser/.cache/huggingface
  - ${MODEL_CACHE_DIR}/torch:/home/appuser/.cache/torch
  - ${MODEL_CACHE_DIR}/nltk_data:/home/appuser/.cache/nltk_data
  - ${MODEL_CACHE_DIR}/sentence-transformers:/home/appuser/.cache/sentence-transformers
```

### Key Benefits
- **No code complexity**: Models use their natural cache locations
- **Persistent storage**: Models saved between container restarts
- **User configurable**: Simple `.env` variable controls cache location
- **No re-downloads**: Models cached after first download (~2.6GB total)

## Security Features

### Non-Root Container User

OpenTranscribe backend containers run as a non-root user (`appuser`, UID 1000) following Docker security best practices.

**Benefits:**
- Follows principle of least privilege
- Reduces security risk from container escape vulnerabilities
- Compliant with security scanning tools (Trivy, Snyk, etc.)
- Prevents host root compromise in case of container breach

**Automatic Permission Management:**

The startup scripts (`./opentr.sh` and `./opentranscribe.sh`) automatically check and fix model cache permissions before starting containers. This ensures the non-root container user (UID 1000) can access the model cache without permission errors.

If you encounter permission issues, you can manually fix them:

```bash
# Fix permissions on existing model cache
./scripts/fix-model-permissions.sh
```

This script will change ownership of your model cache to UID:GID 1000:1000, making it accessible to the non-root container user.

**Technical Details:**
- Container user: `appuser` (UID 1000, GID 1000)
- User groups: `appuser`, `video` (for GPU access)
- Cache directories: `/home/appuser/.cache/huggingface`, `/home/appuser/.cache/torch`
- Multi-stage build for minimal attack surface
- Health checks for container orchestration

## Common Tasks

### Adding New API Endpoints
1. Create endpoint in `backend/app/api/endpoints/`
2. Add to router in `backend/app/api/router.py`
3. Create/update schemas in `backend/app/schemas/`
4. Update database models if needed
5. Test with `./opentr.sh restart-backend`

### Frontend Component Development
1. Create component in `src/components/`
2. Ensure light/dark mode support
3. Test responsive design
4. Update relevant routes/stores if needed
5. Test with `./opentr.sh restart-frontend`

### Database Changes
1. Modify `database/init_db.sql`
2. Update SQLAlchemy models
3. Update Pydantic schemas
4. Reset dev environment: `./opentr.sh reset dev`
