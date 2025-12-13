#!/bin/bash
set -e

# Docker Build and Push Script for OpenTranscribe
# Quick fix for pushing Docker images to Docker Hub locally

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DOCKERHUB_USERNAME="${DOCKERHUB_USERNAME:-davidamacey}"
REPO_BACKEND="${DOCKERHUB_USERNAME}/opentranscribe-backend"
REPO_FRONTEND="${DOCKERHUB_USERNAME}/opentranscribe-frontend"

# Get commit SHA for tagging
COMMIT_SHA=$(git rev-parse --short HEAD)
BRANCH=$(git rev-parse --abbrev-ref HEAD)

# Default to building both platforms
PLATFORMS="linux/amd64,linux/arm64"
BUILD_TARGET="${1:-all}"

# Remote builder configuration
# Set USE_REMOTE_BUILDER=true to use remote ARM64 builder (much faster!)
# Set REMOTE_BUILDER_NAME to override the builder name
USE_REMOTE_BUILDER="${USE_REMOTE_BUILDER:-false}"
REMOTE_BUILDER_NAME="${REMOTE_BUILDER_NAME:-opentranscribe-multiarch}"
DEFAULT_BUILDER_NAME="opentranscribe-builder"

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Function to check if Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker is not running. Please start Docker and try again."
        exit 1
    fi
}

# Function to check if logged into Docker Hub
check_docker_login() {
    if ! docker info | grep -q "Username"; then
        print_warning "Not logged into Docker Hub. Attempting login..."
        docker login
    else
        print_success "Already logged into Docker Hub"
    fi
}

# Function to detect changes since last commit
detect_changes() {
    local component=$1

    if [ -z "$(git status --porcelain "${component}/")" ]; then
        print_info "No uncommitted changes in ${component}"
        # Check last commit
        if git diff --name-only HEAD~1 HEAD | grep -q "^${component}/"; then
            print_info "Changes detected in last commit for ${component}"
            return 0
        else
            print_warning "No recent changes in ${component}"
            return 1
        fi
    else
        print_info "Uncommitted changes detected in ${component}"
        return 0
    fi
}

# Function to run security scan if enabled
run_security_scan() {
    local component=$1

    if [ "${SKIP_SECURITY_SCAN}" = "true" ]; then
        print_warning "Security scanning skipped (SKIP_SECURITY_SCAN=true)"
        return 0
    fi

    if [ ! -f "./scripts/security-scan.sh" ]; then
        print_warning "Security scan script not found, skipping..."
        return 0
    fi

    print_info "Running security scan for ${component}..."
    if OUTPUT_DIR="./security-reports" FAIL_ON_CRITICAL="${FAIL_ON_CRITICAL:-false}" ./scripts/security-scan.sh "${component}"; then
        print_success "Security scan passed for ${component}"
        return 0
    else
        print_warning "Security scan found issues for ${component}"
        if [ "${FAIL_ON_SECURITY_ISSUES}" = "true" ]; then
            print_error "Failing build due to security issues (FAIL_ON_SECURITY_ISSUES=true)"
            return 1
        else
            print_warning "Continuing despite security issues (set FAIL_ON_SECURITY_ISSUES=true to fail)"
            return 0
        fi
    fi
}

# Function to build and push backend
build_backend() {
    print_info "Building backend image..."
    print_info "Platforms: ${PLATFORMS}"
    print_info "Version: ${VERSION_FULL}"
    print_info "Tags: latest, ${VERSION_FULL}, ${VERSION_MAJOR_MINOR}, ${VERSION_MAJOR}, ${COMMIT_SHA}"

    cd backend

    # Build and push multi-arch image with all version tags
    docker buildx build \
        --platform "${PLATFORMS}" \
        --file Dockerfile.prod \
        --tag "${REPO_BACKEND}:latest" \
        --tag "${REPO_BACKEND}:${VERSION_FULL}" \
        --tag "${REPO_BACKEND}:${VERSION_MAJOR_MINOR}" \
        --tag "${REPO_BACKEND}:${VERSION_MAJOR}" \
        --tag "${REPO_BACKEND}:${COMMIT_SHA}" \
        ${CACHE_FLAG} \
        --push \
        .

    cd ..

    print_success "Backend image built and pushed successfully"
    print_info "Tags pushed:"
    print_info "  - ${REPO_BACKEND}:latest"
    print_info "  - ${REPO_BACKEND}:${VERSION_FULL}"
    print_info "  - ${REPO_BACKEND}:${VERSION_MAJOR_MINOR}"
    print_info "  - ${REPO_BACKEND}:${VERSION_MAJOR}"
    print_info "  - ${REPO_BACKEND}:${COMMIT_SHA}"

    # Remove old local image and pull fresh amd64 image for scanning
    print_info "Pulling fresh amd64 image from registry for security scan..."
    docker rmi "${REPO_BACKEND}:latest" 2>/dev/null || true
    docker pull --platform linux/amd64 "${REPO_BACKEND}:latest"

    # Run security scan on freshly pulled image
    run_security_scan "backend"
}

# Function to build and push frontend
build_frontend() {
    print_info "Building frontend image..."
    print_info "Platforms: ${PLATFORMS}"
    print_info "Version: ${VERSION_FULL}"
    print_info "Tags: latest, ${VERSION_FULL}, ${VERSION_MAJOR_MINOR}, ${VERSION_MAJOR}, ${COMMIT_SHA}"

    cd frontend

    # Build and push multi-arch image with all version tags
    docker buildx build \
        --platform "${PLATFORMS}" \
        --file Dockerfile.prod \
        --tag "${REPO_FRONTEND}:latest" \
        --tag "${REPO_FRONTEND}:${VERSION_FULL}" \
        --tag "${REPO_FRONTEND}:${VERSION_MAJOR_MINOR}" \
        --tag "${REPO_FRONTEND}:${VERSION_MAJOR}" \
        --tag "${REPO_FRONTEND}:${COMMIT_SHA}" \
        ${CACHE_FLAG} \
        --push \
        .

    cd ..

    print_success "Frontend image built and pushed successfully"
    print_info "Tags pushed:"
    print_info "  - ${REPO_FRONTEND}:latest"
    print_info "  - ${REPO_FRONTEND}:${VERSION_FULL}"
    print_info "  - ${REPO_FRONTEND}:${VERSION_MAJOR_MINOR}"
    print_info "  - ${REPO_FRONTEND}:${VERSION_MAJOR}"
    print_info "  - ${REPO_FRONTEND}:${COMMIT_SHA}"

    # Remove old local image and pull fresh amd64 image for scanning
    print_info "Pulling fresh amd64 image from registry for security scan..."
    docker rmi "${REPO_FRONTEND}:latest" 2>/dev/null || true
    docker pull --platform linux/amd64 "${REPO_FRONTEND}:latest"

    # Run security scan on freshly pulled image
    run_security_scan "frontend"
}

# Function to show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTION]

Build and push Docker images to Docker Hub

Options:
    backend     Build and push only backend image
    frontend    Build and push only frontend image
    all         Build and push both images (default)
    auto        Auto-detect changes and build only changed components
    help        Show this help message

Environment Variables:
    VERSION                   Semantic version (e.g., v1.2.3) - overrides VERSION file
    DOCKERHUB_USERNAME        Docker Hub username (default: davidamacey)
    PLATFORMS                 Target platforms (default: linux/amd64,linux/arm64)
    USE_REMOTE_BUILDER        Use remote ARM64 builder for faster builds (default: false)
    REMOTE_BUILDER_NAME       Remote builder name (default: opentranscribe-multiarch)
    NO_CACHE                  Build without cache (default: false)
    SKIP_SECURITY_SCAN        Skip security scanning (default: false)
    FAIL_ON_SECURITY_ISSUES   Fail build if security issues found (default: false)
    FAIL_ON_CRITICAL          Fail scan if CRITICAL vulnerabilities found (default: false)

Examples:
    $0              # Build and push both images with security scanning
    $0 backend      # Build and push only backend
    $0 auto         # Auto-detect and build changed components

    # Specify version (creates tags: v1.2.3, v1.2, v1, latest)
    VERSION=v1.2.3 $0 all

    # Version from VERSION file (recommended for releases)
    echo "v1.2.3" > VERSION
    $0 all

    # Use remote ARM64 builder for 10-20x faster builds
    USE_REMOTE_BUILDER=true $0 all

    # Build without cache (fresh build)
    NO_CACHE=true $0 frontend

    # Build only for current platform (faster)
    PLATFORMS=linux/amd64 $0 backend

    # Skip security scanning for faster builds
    SKIP_SECURITY_SCAN=true $0 all

    # Fail build if security issues found (recommended for CI)
    FAIL_ON_SECURITY_ISSUES=true FAIL_ON_CRITICAL=true $0 all

Versioning:
    The script supports semantic versioning via VERSION file or environment variable:
    - Creates tags: vX.Y.Z (full), vX.Y (minor), vX (major), latest, commit-sha
    - Version can be specified as v1.2.3 or 1.2.3 (v prefix added automatically)
    - Environment variable VERSION overrides VERSION file
    - If neither exists, defaults to v0.0.0 with a warning

Remote Builder Setup:
    For dramatically faster ARM64 builds, set up a remote builder:
    1. Run: ./scripts/setup-remote-builder.sh setup
    2. Follow the interactive prompts to configure your Mac Studio
    3. Use: USE_REMOTE_BUILDER=true $0

    This uses native ARM64 compilation instead of QEMU emulation (10-20x faster!)

Security Scanning:
    After building, images are automatically scanned with:
    - Hadolint: Dockerfile linting
    - Dockle: CIS best practices
    - Trivy: Vulnerability scanning
    - Grype: Additional vulnerability scanning
    - Syft: SBOM generation

    Reports are saved to ./security-reports/

EOF
}

# Main script
main() {
    # Version management - read from VERSION file or environment variable
    if [ -n "${VERSION}" ]; then
        # Use VERSION from environment variable
        SEMVER="${VERSION}"
    elif [ -f "VERSION" ]; then
        # Read VERSION from file
        SEMVER=$(cat VERSION | tr -d '[:space:]')
    else
        # Default version if neither exists
        SEMVER="v0.0.0"
    fi

    # Validate semantic version format (vX.Y.Z or X.Y.Z)
    if [[ ! "${SEMVER}" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        print_error "Invalid semantic version format: ${SEMVER}"
        print_error "Expected format: v1.2.3 or 1.2.3"
        exit 1
    fi

    # Ensure version starts with 'v'
    if [[ ! "${SEMVER}" =~ ^v ]]; then
        SEMVER="v${SEMVER}"
    fi

    # Parse version components for additional tags
    VERSION_FULL="${SEMVER}"  # e.g., v1.2.3
    VERSION_MAJOR_MINOR=$(echo "${SEMVER}" | cut -d. -f1-2)  # e.g., v1.2
    VERSION_MAJOR=$(echo "${SEMVER}" | cut -d. -f1)  # e.g., v1

    print_info "OpenTranscribe Docker Build & Push Script"
    print_info "=========================================="
    print_info "Version: ${VERSION_FULL}"
    print_info "Commit:  ${COMMIT_SHA}"
    print_info "Branch:  ${BRANCH}"
    print_info ""

    # Warn if using default version
    if [ "${SEMVER}" = "v0.0.0" ]; then
        print_warning "No VERSION file or VERSION env var found, using default: ${SEMVER}"
        print_warning "Create a VERSION file or set VERSION environment variable for production builds"
        print_info ""
    fi

    # Cache control - set NO_CACHE=true to force rebuild without cache
    CACHE_FLAG=""
    if [ "${NO_CACHE}" = "true" ]; then
        CACHE_FLAG="--no-cache"
        print_info "Building without cache (NO_CACHE=true)"
    fi

    # Check prerequisites
    check_docker
    check_docker_login

    # Select and configure builder based on USE_REMOTE_BUILDER setting
    if [ "${USE_REMOTE_BUILDER}" = "true" ]; then
        # Use remote multi-arch builder
        if ! docker buildx inspect "${REMOTE_BUILDER_NAME}" > /dev/null 2>&1; then
            print_error "Remote builder '${REMOTE_BUILDER_NAME}' not found!"
            print_info "Please run: ./scripts/setup-remote-builder.sh setup"
            print_info "Or set USE_REMOTE_BUILDER=false to use QEMU emulation"
            exit 1
        fi
        print_success "Using remote multi-arch builder: ${REMOTE_BUILDER_NAME}"
        print_info "This will use native ARM64 builds on your remote machine (much faster!)"
        docker buildx use "${REMOTE_BUILDER_NAME}"
        docker buildx inspect --bootstrap
    else
        # Use local builder with QEMU emulation (slower but works without setup)
        if ! docker buildx inspect "${DEFAULT_BUILDER_NAME}" > /dev/null 2>&1; then
            print_info "Creating local buildx builder (with QEMU emulation)..."
            docker buildx create --name "${DEFAULT_BUILDER_NAME}" --use
            docker buildx inspect --bootstrap
        else
            print_info "Using existing local buildx builder (with QEMU emulation)"
            docker buildx use "${DEFAULT_BUILDER_NAME}"
        fi
        if [[ "${PLATFORMS}" == *"arm64"* ]]; then
            print_warning "Building ARM64 with QEMU emulation (slow)"
            print_info "For faster builds, set up remote builder: ./scripts/setup-remote-builder.sh"
            print_info "Then use: USE_REMOTE_BUILDER=true $0"
        fi
    fi

    case "${BUILD_TARGET}" in
        backend)
            print_info "Building backend only..."
            build_backend
            ;;
        frontend)
            print_info "Building frontend only..."
            build_frontend
            ;;
        all)
            print_info "Building both backend and frontend..."
            build_backend
            build_frontend
            ;;
        auto)
            print_info "Auto-detecting changes..."
            BUILT_SOMETHING=false

            if detect_changes "backend"; then
                build_backend
                BUILT_SOMETHING=true
            fi

            if detect_changes "frontend"; then
                build_frontend
                BUILT_SOMETHING=true
            fi

            if [ "$BUILT_SOMETHING" = false ]; then
                print_warning "No changes detected in backend or frontend"
                print_info "Use '$0 all' to force build both images"
                exit 0
            fi
            ;;
        help|--help|-h)
            show_usage
            exit 0
            ;;
        *)
            print_error "Invalid option: ${BUILD_TARGET}"
            show_usage
            exit 1
            ;;
    esac

    print_success "All builds completed successfully!"
    print_info ""
    print_info "Images pushed to Docker Hub with version ${VERSION_FULL}:"
    if [ "${BUILD_TARGET}" = "backend" ] || [ "${BUILD_TARGET}" = "all" ]; then
        print_info "Backend:"
        print_info "  - ${REPO_BACKEND}:latest"
        print_info "  - ${REPO_BACKEND}:${VERSION_FULL}"
        print_info "  - ${REPO_BACKEND}:${VERSION_MAJOR_MINOR}"
        print_info "  - ${REPO_BACKEND}:${VERSION_MAJOR}"
        print_info "  - ${REPO_BACKEND}:${COMMIT_SHA}"
    fi
    if [ "${BUILD_TARGET}" = "frontend" ] || [ "${BUILD_TARGET}" = "all" ]; then
        print_info "Frontend:"
        print_info "  - ${REPO_FRONTEND}:latest"
        print_info "  - ${REPO_FRONTEND}:${VERSION_FULL}"
        print_info "  - ${REPO_FRONTEND}:${VERSION_MAJOR_MINOR}"
        print_info "  - ${REPO_FRONTEND}:${VERSION_MAJOR}"
        print_info "  - ${REPO_FRONTEND}:${COMMIT_SHA}"
    fi
    print_info ""
    print_info "To pull specific versions:"
    if [ "${BUILD_TARGET}" = "backend" ] || [ "${BUILD_TARGET}" = "all" ]; then
        print_info "  docker pull ${REPO_BACKEND}:latest           # Always latest"
        print_info "  docker pull ${REPO_BACKEND}:${VERSION_FULL}  # Specific version"
        print_info "  docker pull ${REPO_BACKEND}:${VERSION_MAJOR}            # Major version"
    fi
    if [ "${BUILD_TARGET}" = "frontend" ] || [ "${BUILD_TARGET}" = "all" ]; then
        print_info "  docker pull ${REPO_FRONTEND}:latest           # Always latest"
        print_info "  docker pull ${REPO_FRONTEND}:${VERSION_FULL}  # Specific version"
        print_info "  docker pull ${REPO_FRONTEND}:${VERSION_MAJOR}            # Major version"
    fi

    # CRITICAL: Switch back to default builder to prevent interference with local dev builds
    print_info ""
    print_info "🔧 Switching back to default Docker builder..."
    docker buildx use default
    print_success "✅ Default builder restored. Local development builds will work normally."

    # Show build performance info if using emulation
    if [ "${USE_REMOTE_BUILDER}" = "false" ] && [[ "${PLATFORMS}" == *"arm64"* ]]; then
        print_info ""
        print_info "⚡ Performance Tip:"
        print_info "You used QEMU emulation for ARM64 builds (10-20x slower than native)"
        print_info "To speed up future builds, set up a remote ARM64 builder:"
        print_info "  1. Run: ./scripts/setup-remote-builder.sh setup"
        print_info "  2. Then: USE_REMOTE_BUILDER=true $0"
    fi

    # Auto-commit and push security reports if they exist
    if [ -d "./security-reports" ] && [ "$(ls -A ./security-reports 2>/dev/null)" ]; then
        print_info ""
        print_info "📋 Committing security reports..."

        # Check if there are changes to commit
        if git status --porcelain ./security-reports | grep -q .; then
            git add ./security-reports/
            git commit -m "chore: Update security reports for ${VERSION_FULL}

Security scan results from Docker build process.
Reports include: Hadolint, Dockle, Trivy, Grype, and Syft SBOM.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

            # Push to current branch
            CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
            if git push origin "${CURRENT_BRANCH}"; then
                print_success "✅ Security reports committed and pushed to ${CURRENT_BRANCH}"
            else
                print_warning "⚠️  Failed to push security reports (you may need to push manually)"
            fi
        else
            print_info "No changes to security reports"
        fi
    else
        print_info "No security reports directory found (security scanning may be disabled)"
    fi
}

# Run main function
main
