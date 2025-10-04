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

    if [ -z "$(git status --porcelain ${component}/)" ]; then
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

# Function to build and push backend
build_backend() {
    print_info "Building backend image..."
    print_info "Platforms: ${PLATFORMS}"
    print_info "Tags: latest, ${COMMIT_SHA}"

    cd backend

    # Build and push multi-arch image
    docker buildx build \
        --platform "${PLATFORMS}" \
        --file Dockerfile.prod \
        --tag "${REPO_BACKEND}:latest" \
        --tag "${REPO_BACKEND}:${COMMIT_SHA}" \
        --push \
        .

    cd ..

    print_success "Backend image built and pushed successfully"
    print_info "Tags: ${REPO_BACKEND}:latest, ${REPO_BACKEND}:${COMMIT_SHA}"
}

# Function to build and push frontend
build_frontend() {
    print_info "Building frontend image..."
    print_info "Platforms: ${PLATFORMS}"
    print_info "Tags: latest, ${COMMIT_SHA}"

    cd frontend

    # Build and push multi-arch image
    docker buildx build \
        --platform "${PLATFORMS}" \
        --file Dockerfile.prod \
        --tag "${REPO_FRONTEND}:latest" \
        --tag "${REPO_FRONTEND}:${COMMIT_SHA}" \
        --push \
        .

    cd ..

    print_success "Frontend image built and pushed successfully"
    print_info "Tags: ${REPO_FRONTEND}:latest, ${REPO_FRONTEND}:${COMMIT_SHA}"
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
    DOCKERHUB_USERNAME    Docker Hub username (default: davidamacey)
    PLATFORMS             Target platforms (default: linux/amd64,linux/arm64)

Examples:
    $0              # Build and push both images
    $0 backend      # Build and push only backend
    $0 auto         # Auto-detect and build changed components

    # Build only for current platform (faster)
    PLATFORMS=linux/amd64 $0 backend

EOF
}

# Main script
main() {
    print_info "OpenTranscribe Docker Build & Push Script"
    print_info "=========================================="
    print_info "Commit: ${COMMIT_SHA}"
    print_info "Branch: ${BRANCH}"
    print_info ""

    # Check prerequisites
    check_docker
    check_docker_login

    # Create buildx builder if it doesn't exist
    if ! docker buildx inspect opentranscribe-builder > /dev/null 2>&1; then
        print_info "Creating buildx builder..."
        docker buildx create --name opentranscribe-builder --use
        docker buildx inspect --bootstrap
    else
        print_info "Using existing buildx builder"
        docker buildx use opentranscribe-builder
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
    print_info "Images pushed to Docker Hub:"
    if [ "${BUILD_TARGET}" = "backend" ] || [ "${BUILD_TARGET}" = "all" ]; then
        print_info "  - ${REPO_BACKEND}:latest"
        print_info "  - ${REPO_BACKEND}:${COMMIT_SHA}"
    fi
    if [ "${BUILD_TARGET}" = "frontend" ] || [ "${BUILD_TARGET}" = "all" ]; then
        print_info "  - ${REPO_FRONTEND}:latest"
        print_info "  - ${REPO_FRONTEND}:${COMMIT_SHA}"
    fi
    print_info ""
    print_info "To pull these images:"
    if [ "${BUILD_TARGET}" = "backend" ] || [ "${BUILD_TARGET}" = "all" ]; then
        print_info "  docker pull ${REPO_BACKEND}:latest"
    fi
    if [ "${BUILD_TARGET}" = "frontend" ] || [ "${BUILD_TARGET}" = "all" ]; then
        print_info "  docker pull ${REPO_FRONTEND}:latest"
    fi

    # CRITICAL: Switch back to default builder to prevent interference with local dev builds
    print_info ""
    print_info "🔧 Switching back to default Docker builder..."
    docker buildx use default
    print_success "✅ Default builder restored. Local development builds will work normally."
}

# Run main function
main
