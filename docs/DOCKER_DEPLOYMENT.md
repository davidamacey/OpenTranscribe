# Docker Image Deployment Guide

This guide explains how Docker images are built and published for OpenTranscribe.

## Current Setup (Hybrid Approach)

### Automated (GitHub Actions)
**Triggers:** Push to `master` branch
**File:** `.github/workflows/docker-publish.yml`

**What it builds:**
- ✅ Frontend: AMD64 + ARM64
- ✅ Backend: AMD64 only (ARM64 disabled due to size)

**When to use:**
- Automatic on every push to master
- Can manually trigger via GitHub Actions UI

**Limitations:**
- Backend ARM64 builds disabled (13.8GB image causes runner failures)
- May still fail if backend AMD64 build hits disk limits

### Manual (Local Script)
**Location:** `./scripts/docker-build-push.sh`
**Documentation:** [scripts/README.md](scripts/README.md)

**What it builds:**
- ✅ Frontend: AMD64 + ARM64
- ✅ Backend: AMD64 + ARM64 (full multi-arch support)

**When to use:**
- When GitHub Actions fails
- When you need ARM64 backend images
- For testing before pushing to main
- Quick iterations during development

## Recommended Workflow

### For Regular Development

1. **Make changes and commit:**
   ```bash
   git add .
   git commit -m "Your changes"
   git push origin master
   ```

2. **GitHub Actions automatically builds:**
   - Frontend: AMD64 + ARM64 ✅
   - Backend: AMD64 only ✅
   - Check progress: https://github.com/davidamacey/OpenTranscribe/actions

3. **If GitHub Actions fails or you need ARM64 backend:**
   ```bash
   ./scripts/docker-build-push.sh
   ```

### For Quick Iterations

```bash
# Only build what changed
./scripts/docker-build-push.sh auto

# Or build specific component
./scripts/docker-build-push.sh backend
./scripts/docker-build-push.sh frontend
```

### For Testing Before Production

```bash
# Fast single-platform build
PLATFORMS=linux/amd64 ./scripts/docker-build-push.sh backend

# Test the image locally
docker run -p 8080:8080 davidamacey/opentranscribe-backend:latest
```

## Image Tags

All builds create two tags:

- `latest` - Always the most recent build
- `<commit-sha>` - Specific version (e.g., `a1b2c3d`)

**Examples:**
```bash
# Pull latest
docker pull davidamacey/opentranscribe-backend:latest
docker pull davidamacey/opentranscribe-frontend:latest

# Pull specific version
docker pull davidamacey/opentranscribe-backend:1e013ea
```

## Architecture Support

| Component | AMD64 | ARM64 | Notes |
|-----------|-------|-------|-------|
| Frontend  | ✅ Auto | ✅ Auto | GitHub Actions builds both |
| Backend   | ✅ Auto | ⚠️ Manual | ARM64 needs local build (13.8GB) |

## Troubleshooting

### GitHub Actions Failing

**Symptom:** Build cancelled or runs out of disk space
**Solution:** Use manual script
```bash
./scripts/docker-build-push.sh
```

### Need ARM64 Backend

**Symptom:** Docker pull fails on ARM64 systems (Apple Silicon, etc.)
**Solution:** Build locally with full multi-arch support
```bash
./scripts/docker-build-push.sh backend
```

### Slow Builds

**Solution:** Build single platform or use auto-detection
```bash
# Single platform (much faster)
PLATFORMS=linux/amd64 ./scripts/docker-build-push.sh

# Only build what changed
./scripts/docker-build-push.sh auto
```

### Not Logged Into Docker Hub

**Symptom:** "denied: requested access to resource"
**Solution:**
```bash
docker login
# Enter your Docker Hub credentials
```

## Future Improvements

See [Issue #81](https://github.com/davidamacey/OpenTranscribe/issues/81) for planned enhancements:

- [ ] Self-hosted GitHub Actions runner (solves disk space issue)
- [ ] Backend image size optimization (13.8GB → <10GB)
- [ ] Smart change detection in GitHub Actions
- [ ] Automated ARM64 backend builds

## Build Times Reference

**Frontend** (~2 minutes total):
- AMD64: ~1 min
- ARM64: ~1 min
- Size: ~51 MB

**Backend** (~15-30 minutes total):
- AMD64: ~8-15 min
- ARM64: ~8-15 min
- Size: ~13.8 GB

## Related Files

- [scripts/docker-build-push.sh](scripts/docker-build-push.sh) - Local build script
- [scripts/README.md](scripts/README.md) - Detailed script documentation
- [.github/workflows/docker-publish.yml](.github/workflows/docker-publish.yml) - GitHub Actions workflow
- [backend/Dockerfile.prod](backend/Dockerfile.prod) - Backend production Dockerfile
- [frontend/Dockerfile.prod](frontend/Dockerfile.prod) - Frontend production Dockerfile
