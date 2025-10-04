# OpenTranscribe Build Scripts

## Docker Build & Push Script

Quick solution for building and pushing Docker images to Docker Hub locally while GitHub Actions handles automated deployments.

### Prerequisites

1. **Docker with buildx support** (Docker Desktop or Docker Engine 19.03+)
2. **Docker Hub account** logged in:
   ```bash
   docker login
   ```

### Usage

#### Basic Usage

```bash
# Build and push both backend and frontend
./scripts/docker-build-push.sh

# Build and push only backend
./scripts/docker-build-push.sh backend

# Build and push only frontend
./scripts/docker-build-push.sh frontend

# Auto-detect changes and build only what changed
./scripts/docker-build-push.sh auto
```

#### Environment Variables

```bash
# Use different Docker Hub username
DOCKERHUB_USERNAME=myusername ./scripts/docker-build-push.sh

# Build for specific platform only (faster for testing)
PLATFORMS=linux/amd64 ./scripts/docker-build-push.sh backend

# Build for multiple platforms (default)
PLATFORMS=linux/amd64,linux/arm64 ./scripts/docker-build-push.sh
```

### Image Tagging Strategy

Each build creates two tags:
- `latest` - Always points to the most recent build
- `<commit-sha>` - Specific commit for version tracking

**Examples:**
- `davidamacey/opentranscribe-backend:latest`
- `davidamacey/opentranscribe-backend:a1b2c3d`
- `davidamacey/opentranscribe-frontend:latest`
- `davidamacey/opentranscribe-frontend:a1b2c3d`

### Features

✅ **Multi-architecture builds** - Supports both AMD64 and ARM64
✅ **Smart change detection** - Auto mode only builds changed components
✅ **Colored output** - Easy to read build progress
✅ **Automatic Docker Hub login check** - Prompts if not logged in
✅ **Git-based versioning** - Tags images with commit SHA
✅ **Buildx builder management** - Creates and reuses builder instance

### Build Times

**Frontend (~2 minutes):**
- AMD64: ~1 min
- ARM64: ~1 min
- Image size: ~51 MB

**Backend (~15-30 minutes):**
- AMD64: ~8-15 min
- ARM64: ~8-15 min
- Image size: ~13.8 GB

### Tips for Faster Builds

1. **Build single platform for testing:**
   ```bash
   PLATFORMS=linux/amd64 ./scripts/docker-build-push.sh backend
   ```

2. **Use auto mode during development:**
   ```bash
   ./scripts/docker-build-push.sh auto
   ```

3. **Build only what you need:**
   ```bash
   # Just changed frontend code
   ./scripts/docker-build-push.sh frontend
   ```

### Workflow Integration

This script complements the GitHub Actions workflow:

- **GitHub Actions**: Automated builds on push to main
- **Local Script**: Quick manual builds and testing
- **Use Cases**:
  - Testing production builds locally
  - Pushing urgent fixes manually
  - Building when GitHub runners have issues
  - Pre-release testing

### Troubleshooting

**Error: "Cannot connect to Docker daemon"**
```bash
# Start Docker
sudo systemctl start docker  # Linux
# or open Docker Desktop on Mac/Windows
```

**Error: "no builder instance found"**
```bash
# The script will auto-create, but you can manually create:
docker buildx create --name opentranscribe-builder --use
docker buildx inspect --bootstrap
```

**Error: "denied: requested access to resource is denied"**
```bash
# Login to Docker Hub
docker login
```

**Build is very slow**
```bash
# Build for single platform
PLATFORMS=linux/amd64 ./scripts/docker-build-push.sh backend

# Check Docker resources
docker info | grep -i cpu
docker info | grep -i memory
```

### Pulling Images

Users can pull the images using:

```bash
# Latest version
docker pull davidamacey/opentranscribe-backend:latest
docker pull davidamacey/opentranscribe-frontend:latest

# Specific version
docker pull davidamacey/opentranscribe-backend:a1b2c3d
```

### Next Steps

See Issue #81 for the full roadmap including:
- [ ] Self-hosted GitHub Actions runner setup
- [ ] Automated change detection in CI/CD
- [ ] Image size optimization
- [ ] Build cache improvements

### Related Files

- [docker-build-push.sh](./docker-build-push.sh) - Main build script
- [../backend/Dockerfile.prod](../backend/Dockerfile.prod) - Backend production Dockerfile
- [../frontend/Dockerfile.prod](../frontend/Dockerfile.prod) - Frontend production Dockerfile
- [../.github/workflows/docker-publish.yml](../.github/workflows/docker-publish.yml) - GitHub Actions workflow
