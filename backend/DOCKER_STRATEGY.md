# Docker Build Strategy - OpenTranscribe Backend

## Overview

The OpenTranscribe backend uses two Docker build strategies optimized for different use cases:

1. **Dockerfile.prod** - Standard production build (currently in use)
2. **Dockerfile.prod.optimized** - Multi-stage build for enhanced security (future use)

## Current Configuration

### Active Dockerfile: `Dockerfile.prod`

**Base Image:** `python:3.12-slim-bookworm` (Debian 12)

**Key Features:**
- ✅ Single-stage build for faster iteration
- ✅ CUDA 12.8 & cuDNN 9 compatibility
- ✅ Security updates (CVE-2025-32434 fixed)
- ✅ Root user (required for GPU access in development)

**Used By:**
- `backend` service (docker-compose.yml:80)
- `celery-worker` service (docker-compose.yml:152)
- `flower` service (docker-compose.yml:254)

### ML/AI Stack (All cuDNN 9 Compatible)

| Package | Version | Notes |
|---------|---------|-------|
| PyTorch | 2.8.0+cu128 | CVE-2025-32434 fixed, CUDA 12.8 |
| CTranslate2 | ≥4.6.0 | cuDNN 9 support |
| WhisperX | 3.7.0 | Latest with ctranslate2 4.5+ support |
| PyAnnote Audio | ≥3.3.2 | PyTorch 2.6+ compatible |
| NumPy | ≥1.25.2 | 2.x compatible, no CVEs |

### Critical Configuration

**LD_LIBRARY_PATH** (Line 28):
```dockerfile
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib:/usr/local/lib/python3.12/site-packages/nvidia/cuda_runtime/lib
```

**Why This Matters:**
- PyAnnote diarization requires cuDNN 9 libraries
- Libraries are in Python package directory, not system path
- Without this, you get: `Unable to load libcudnn_cnn.so.9` → SIGABRT crash
- Must be set at Dockerfile level (persistent, can't be overridden)

## Future Strategy: Optimized Build

### Dockerfile.prod.optimized (Not Yet Active)

**When to Use:**
- Production deployments requiring maximum security
- Environments that support non-root containers
- CI/CD pipelines with security scanning

**Key Improvements:**

1. **Multi-Stage Build**
   - Stage 1 (builder): Compiles dependencies with build tools
   - Stage 2 (runtime): Minimal image, only runtime dependencies
   - Result: ~40% smaller image size

2. **Non-Root User**
   - Runs as `appuser` (UID 1000)
   - Follows principle of least privilege
   - Better for production security posture

3. **Security Enhancements**
   - No build tools in final image
   - No curl/git (attack surface reduction)
   - OCI-compliant labels for tracking
   - Built-in health checks

4. **Library Paths** (Adjusted for non-root)
   ```dockerfile
   ENV LD_LIBRARY_PATH=/home/appuser/.local/lib/python3.12/site-packages/nvidia/cudnn/lib:/home/appuser/.local/lib/python3.12/site-packages/nvidia/cuda_runtime/lib
   ```

### Migration Path

**Phase 1: Current** ✅
- Using `Dockerfile.prod` (root user)
- Verified working with GPU/CUDA
- All services stable

**Phase 2: Testing** (Next Step)
1. Test `Dockerfile.prod.optimized` with same workload
2. Verify GPU access works with non-root user
3. Confirm cuDNN libraries load correctly
4. Run full transcription pipeline test

**Phase 3: Migration**
1. Update docker-compose.yml to use `Dockerfile.prod.optimized`
2. Update GPU device permissions if needed
3. Deploy to staging environment
4. Monitor for 48 hours
5. Production rollout

## Troubleshooting

### Common Issues

**Problem:** `Unable to load libcudnn_cnn.so.9`
- **Cause:** LD_LIBRARY_PATH not set
- **Fix:** Ensure LD_LIBRARY_PATH in Dockerfile (not docker-compose)

**Problem:** `Worker exited with SIGABRT`
- **Cause:** cuDNN library version mismatch
- **Fix:** Verify PyTorch 2.8.0+cu128 → cuDNN 9.10.2

**Problem:** GPU not accessible in optimized build
- **Cause:** Non-root user lacks GPU permissions
- **Fix:** Add user to `video` group or use `--privileged`

## Development Workflow

### Local Development (with venv)
```bash
cd backend/
source venv/bin/activate
pip install -r requirements-dev.txt  # Includes testing tools
```

### Container Testing
```bash
# Current production build
./opentr.sh start prod

# Test optimized build (after migration)
docker compose -f docker-compose.yml -f docker-compose.optimized.yml up
```

### Building Images
```bash
# Standard build
docker compose build backend celery-worker flower

# Optimized build (future)
docker compose build -f Dockerfile.prod.optimized backend
```

## Security Considerations

### Current (Dockerfile.prod)
- ✅ Updated base image (Debian 12 Bookworm)
- ✅ CVE-2025-32434 fixed (PyTorch 2.8.0)
- ✅ Minimal package installation
- ⚠️ Runs as root (required for current GPU setup)

### Future (Dockerfile.prod.optimized)
- ✅ All above, plus:
- ✅ Non-root user execution
- ✅ Multi-stage build (no build tools in runtime)
- ✅ Explicit OCI labels for compliance
- ✅ Health check integration

## File Structure

```
backend/
├── Dockerfile.prod              # Current production (in use)
├── Dockerfile.prod.optimized    # Future optimized build
├── requirements.txt             # Production dependencies
├── requirements-dev.txt         # Development tools
├── DOCKER_STRATEGY.md          # This file
└── .dockerignore               # Excludes venv, etc.
```

## Key Takeaways

1. **Always use Dockerfile.prod for now** - verified working
2. **LD_LIBRARY_PATH is critical** - must be in Dockerfile
3. **cuDNN 9 compatibility** - all packages updated
4. **Optimized build is ready** - awaiting GPU permission testing
5. **No downgrade needed** - NumPy 2.x works perfectly

## Change History

- **2025-10-11**: Initial strategy with cuDNN 9 migration
  - Updated PyTorch 2.2.2 → 2.8.0+cu128
  - Updated CTranslate2 4.4.0 → 4.6.0
  - Updated WhisperX 3.4.3 → 3.7.0
  - Fixed LD_LIBRARY_PATH for cuDNN libraries
  - Removed obsolete Dockerfile.dev variants
  - Created Dockerfile.prod.optimized for future use
