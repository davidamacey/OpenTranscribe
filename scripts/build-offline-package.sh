#!/bin/bash
set -e

# OpenTranscribe Offline Package Builder
# Creates a complete offline installation package for air-gapped deployments
# Usage: ./scripts/build-offline-package.sh [version]

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Load .env file if it exists and HUGGINGFACE_TOKEN is not already set
if [ -z "$HUGGINGFACE_TOKEN" ] && [ -f .env ]; then
    export HUGGINGFACE_TOKEN=$(grep "^HUGGINGFACE_TOKEN=" .env | cut -d'=' -f2)
fi

# Configuration
VERSION="${1:-$(git rev-parse --short HEAD)}"
PACKAGE_NAME="opentranscribe-offline-v${VERSION}"
BUILD_DIR="./offline-package-build"
PACKAGE_DIR="${BUILD_DIR}/${PACKAGE_NAME}"

# Required files and directories
CONFIG_FILES=(
    "docker-compose.offline.yml"
    ".env"
    "database/init_db.sql"
    "frontend/nginx.conf"
)

SCRIPT_FILES=(
    "scripts/common.sh"
    "scripts/download-models.py"
)

#######################
# HELPER FUNCTIONS
#######################

print_header() {
    echo -e "\n${CYAN}================================================================${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}================================================================${NC}\n"
}

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

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Calculate directory size
get_dir_size() {
    du -sh "$1" 2>/dev/null | cut -f1 || echo "0"
}

# Create checksums
create_checksums() {
    local dir=$1
    print_info "Creating checksums for verification..."

    cd "$dir"
    find . -type f ! -name "checksums.sha256" -exec sha256sum {} \; > checksums.sha256
    cd - > /dev/null

    print_success "Checksums created"
}

#######################
# PRE-FLIGHT CHECKS
#######################

preflight_checks() {
    print_header "Pre-flight Checks"

    # Check for required commands
    local missing_commands=()

    for cmd in docker git tar xz; do
        if ! command_exists "$cmd"; then
            missing_commands+=("$cmd")
        fi
    done

    if [ ${#missing_commands[@]} -ne 0 ]; then
        print_error "Missing required commands: ${missing_commands[*]}"
        exit 1
    fi

    print_success "All required commands available"

    # Check Docker is running
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker is not running"
        exit 1
    fi

    print_success "Docker is running"

    # Check disk space (need at least 80GB free)
    local available_space=$(df -BG . | tail -1 | awk '{print $4}' | sed 's/G//')
    if [ "$available_space" -lt 80 ]; then
        print_warning "Less than 80GB free space available (${available_space}GB)"
        print_warning "Package building may fail if you run out of space"
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        print_success "Sufficient disk space available (${available_space}GB)"
    fi

    print_success "Pre-flight checks passed"
}

#######################
# IMAGE EXTRACTION
#######################

extract_infrastructure_images() {
    local compose_file="docker-compose.yml"

    if [ ! -f "$compose_file" ]; then
        print_error "docker-compose.yml not found!"
        exit 1
    fi

    # Extract infrastructure service images (postgres, redis, minio, opensearch)
    # These are the same in both dev and production
    grep -E "^\s*image:\s*" "$compose_file" | \
        sed -E 's/^\s*image:\s*//; s/\s*$//' | \
        grep -v "^#" | \
        sort -u
}

extract_docker_images() {
    print_header "Extracting Docker Images from Configuration"

    print_info "Source: docker-compose.yml (single source of truth)"

    # Get infrastructure images from main docker-compose.yml
    INFRASTRUCTURE_IMAGES=($(extract_infrastructure_images))

    # Add production application images (these use 'build:' in dev, pre-built images in prod)
    APPLICATION_IMAGES=(
        "davidamacey/opentranscribe-backend:latest"
        "davidamacey/opentranscribe-frontend:latest"
    )

    # Combine all images
    IMAGES=("${APPLICATION_IMAGES[@]}" "${INFRASTRUCTURE_IMAGES[@]}")

    if [ ${#IMAGES[@]} -eq 0 ]; then
        print_error "No images found!"
        exit 1
    fi

    print_success "Found ${#IMAGES[@]} images to package:"
    print_info "Application images (pre-built for production):"
    for img in "${APPLICATION_IMAGES[@]}"; do
        print_info "  - $img"
    done
    print_info "Infrastructure images (from docker-compose.yml):"
    for img in "${INFRASTRUCTURE_IMAGES[@]}"; do
        print_info "  - $img"
    done
    echo
}

#######################
# SETUP
#######################

setup_directories() {
    print_header "Setting Up Build Environment"

    # Clean old build if exists
    if [ -d "$BUILD_DIR" ]; then
        print_warning "Removing existing build directory..."
        rm -rf "$BUILD_DIR"
    fi

    # Create directory structure
    print_info "Creating directory structure..."
    mkdir -p "${PACKAGE_DIR}/docker-images"
    mkdir -p "${PACKAGE_DIR}/models/huggingface"
    mkdir -p "${PACKAGE_DIR}/models/torch"
    mkdir -p "${PACKAGE_DIR}/config"
    mkdir -p "${PACKAGE_DIR}/database"
    mkdir -p "${PACKAGE_DIR}/scripts"

    print_success "Directory structure created"
}

#######################
# DOCKER IMAGES
#######################

pull_and_save_images() {
    print_header "Pulling and Saving Docker Images"

    local total_images=${#IMAGES[@]}
    local current=0

    for image in "${IMAGES[@]}"; do
        current=$((current + 1))
        local image_file=$(echo "$image" | tr '/:' '__')
        local output_path="${PACKAGE_DIR}/docker-images/${image_file}.tar"

        print_info "[$current/$total_images] Processing: $image"

        # Pull image
        print_info "  Pulling image..."
        if ! docker pull "$image"; then
            print_error "  Failed to pull $image"
            exit 1
        fi

        # Save image
        print_info "  Saving image to tar..."
        if ! docker save "$image" -o "$output_path"; then
            print_error "  Failed to save $image"
            exit 1
        fi

        local size=$(get_dir_size "$output_path")
        print_success "  Saved ($size)"
    done

    # Create image metadata
    print_info "Creating image metadata..."
    cat > "${PACKAGE_DIR}/docker-images/metadata.json" <<EOF
{
  "created_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "version": "${VERSION}",
  "images": [
$(for img in "${IMAGES[@]}"; do
    echo "    \"$img\","
done | sed '$ s/,$//')
  ]
}
EOF

    print_success "All Docker images saved"
}

#######################
# AI MODELS
#######################

download_models() {
    print_header "Downloading AI Models"

    # Check for HuggingFace token
    if [ -z "$HUGGINGFACE_TOKEN" ]; then
        print_error "HUGGINGFACE_TOKEN environment variable not set"
        print_info "Get your token at: https://huggingface.co/settings/tokens"
        print_info "Export it: export HUGGINGFACE_TOKEN=your_token_here"
        exit 1
    fi

    print_info "Starting model download container..."
    print_info "This will download approximately 38GB of AI models"
    print_warning "This may take 30-60 minutes depending on your internet speed..."

    # Create temporary model cache directory
    local temp_model_cache="${BUILD_DIR}/temp_models"
    mkdir -p "${temp_model_cache}/huggingface"
    mkdir -p "${temp_model_cache}/torch"

    # Run backend container with model download script
    print_info "Running model download in Docker container..."

    # Run as appuser (non-root) matching container security configuration
    docker run --rm \
        --gpus all \
        -e HUGGINGFACE_TOKEN="${HUGGINGFACE_TOKEN}" \
        -e WHISPER_MODEL="${WHISPER_MODEL:-large-v2}" \
        -e DIARIZATION_MODEL="${DIARIZATION_MODEL:-pyannote/speaker-diarization-3.1}" \
        -e USE_GPU="${USE_GPU:-true}" \
        -e COMPUTE_TYPE="${COMPUTE_TYPE:-float16}" \
        -v "${temp_model_cache}/huggingface:/home/appuser/.cache/huggingface" \
        -v "${temp_model_cache}/torch:/home/appuser/.cache/torch" \
        -v "$(pwd)/scripts/download-models.py:/app/download-models.py" \
        -v "$(pwd)/test_videos:/app/test_videos:ro" \
        davidamacey/opentranscribe-backend:latest \
        python /app/download-models.py

    # Copy models to package (files created as appuser UID 1000)
    print_info "Copying models to package..."
    if [ -d "${temp_model_cache}/huggingface" ] && [ "$(ls -A ${temp_model_cache}/huggingface 2>/dev/null)" ]; then
        cp -r "${temp_model_cache}/huggingface"/* "${PACKAGE_DIR}/models/huggingface/"
        print_info "  Copied HuggingFace models"
    else
        print_warning "No HuggingFace models found to copy"
    fi

    if [ -d "${temp_model_cache}/torch" ] && [ "$(ls -A ${temp_model_cache}/torch 2>/dev/null)" ]; then
        cp -r "${temp_model_cache}/torch"/* "${PACKAGE_DIR}/models/torch/"
        print_info "  Copied PyTorch/PyAnnote models"
    else
        print_warning "No PyTorch models found to copy"
    fi

    # Check if model manifest was created (it's inside the huggingface cache dir)
    if [ -f "${temp_model_cache}/huggingface/model_manifest.json" ]; then
        cp "${temp_model_cache}/huggingface/model_manifest.json" "${PACKAGE_DIR}/models/"
    else
        print_warning "Model manifest not found"
    fi

    # Clean up temp directory
    print_info "Cleaning up temporary files..."
    rm -rf "${temp_model_cache}"

    local model_size=$(get_dir_size "${PACKAGE_DIR}/models")
    print_success "Models downloaded and packaged ($model_size)"
}

#######################
# CONFIGURATION FILES
#######################

copy_configuration() {
    print_header "Copying Configuration Files"

    # Sync infrastructure image versions from docker-compose.yml to docker-compose.offline.yml
    print_info "Syncing infrastructure image versions to docker-compose.offline.yml..."

    # Create temporary copy of offline compose
    local temp_compose="${PACKAGE_DIR}/config/docker-compose.offline.yml"
    cp docker-compose.offline.yml "$temp_compose"

    # Extract and sync each infrastructure image version
    for img in "${INFRASTRUCTURE_IMAGES[@]}"; do
        # Get service name and image (e.g., postgres:17.5-alpine -> postgres and full image)
        local service_name=$(echo "$img" | cut -d: -f1 | cut -d/ -f1)

        # Update the image line in offline compose file for this service
        # Find the service block and update its image line
        sed -i "s|image: ${service_name}[:/][^ ]*|image: ${img}|g" "$temp_compose"
    done

    print_success "Infrastructure images synced from docker-compose.yml"

    # Copy and template .env file
    print_info "Creating .env template..."
    cat .env | sed 's/=.*/=/' > "${PACKAGE_DIR}/config/.env.template"

    # Copy database init
    print_info "Copying database initialization..."
    cp database/init_db.sql "${PACKAGE_DIR}/database/"

    # Copy nginx config
    print_info "Copying nginx configuration..."
    cp frontend/nginx.conf "${PACKAGE_DIR}/config/"

    # Copy common scripts
    print_info "Copying utility scripts..."
    cp scripts/common.sh "${PACKAGE_DIR}/scripts/"

    print_success "Configuration files copied"
}

#######################
# INSTALLATION SCRIPTS
#######################

copy_installation_scripts() {
    print_header "Copying Installation Scripts"

    # Copy installation script
    print_info "Copying install.sh..."
    cp scripts/install-offline-package.sh "${PACKAGE_DIR}/install.sh"
    chmod +x "${PACKAGE_DIR}/install.sh"

    # Copy management wrapper
    print_info "Copying opentr-offline.sh..."
    cp scripts/opentr-offline.sh "${PACKAGE_DIR}/opentr-offline.sh"
    chmod +x "${PACKAGE_DIR}/opentr-offline.sh"

    print_success "Installation scripts copied"
}

#######################
# DOCUMENTATION
#######################

copy_documentation() {
    print_header "Copying Documentation"

    print_info "Copying README-OFFLINE.md..."
    cp README-OFFLINE.md "${PACKAGE_DIR}/"

    print_success "Documentation copied"
}

#######################
# PACKAGE FINALIZATION
#######################

finalize_package() {
    print_header "Finalizing Package"

    # Create checksums
    create_checksums "$PACKAGE_DIR"

    # Create package info
    print_info "Creating package metadata..."
    cat > "${PACKAGE_DIR}/package-info.json" <<EOF
{
  "name": "OpenTranscribe Offline Package",
  "version": "${VERSION}",
  "created_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "created_by": "$(whoami)@$(hostname)",
  "git_commit": "$(git rev-parse HEAD)",
  "git_branch": "$(git rev-parse --abbrev-ref HEAD)",
  "docker_images": ${#IMAGES[@]},
  "package_size_uncompressed": "$(get_dir_size "$PACKAGE_DIR")"
}
EOF

    print_success "Package finalized"
}

#######################
# COMPRESSION
#######################

compress_package() {
    print_header "Compressing Package"

    local output_file="${BUILD_DIR}/${PACKAGE_NAME}.tar.xz"

    print_info "Compressing with multi-threaded xz..."
    print_info "This may take 30-60 minutes..."
    print_warning "Using all available CPU threads for maximum speed"

    cd "$BUILD_DIR"

    # Use xz with all threads (-T0) for maximum speed
    # -9 for maximum compression
    # -v for verbose output
    # --keep to keep the source directory
    tar -cf - "$PACKAGE_NAME" | xz -9 -T0 -v -c > "${PACKAGE_NAME}.tar.xz"

    cd - > /dev/null

    local compressed_size=$(get_dir_size "$output_file")
    local uncompressed_size=$(get_dir_size "$PACKAGE_DIR")

    print_success "Package compressed"
    print_info "Uncompressed size: $uncompressed_size"
    print_info "Compressed size: $compressed_size"
    print_info "Location: $output_file"

    # Create checksum for the compressed package
    print_info "Creating package checksum..."
    cd "$BUILD_DIR"
    sha256sum "${PACKAGE_NAME}.tar.xz" > "${PACKAGE_NAME}.tar.xz.sha256"
    cd - > /dev/null

    print_success "Package checksum created"
}

#######################
# MAIN
#######################

main() {
    print_header "OpenTranscribe Offline Package Builder v${VERSION}"

    print_info "This script will create a complete offline installation package"
    print_info "Package name: ${PACKAGE_NAME}"
    print_info "Estimated size: 15-20GB compressed, ~60GB uncompressed"
    print_warning "This process will take 1-2 hours and requires internet access"
    echo

    # Execute build steps
    preflight_checks
    extract_docker_images
    setup_directories
    pull_and_save_images
    download_models
    copy_configuration
    copy_installation_scripts
    copy_documentation
    finalize_package
    compress_package

    # Final summary
    print_header "Build Complete!"

    echo -e "${GREEN}✅ Offline package created successfully!${NC}\n"
    echo -e "Package location:"
    echo -e "  ${CYAN}${BUILD_DIR}/${PACKAGE_NAME}.tar.xz${NC}\n"
    echo -e "Package checksum:"
    echo -e "  ${CYAN}${BUILD_DIR}/${PACKAGE_NAME}.tar.xz.sha256${NC}\n"
    echo -e "Next steps:"
    echo -e "  1. Verify checksum: ${YELLOW}sha256sum -c ${PACKAGE_NAME}.tar.xz.sha256${NC}"
    echo -e "  2. Transfer package to target system"
    echo -e "  3. Extract: ${YELLOW}tar -xf ${PACKAGE_NAME}.tar.xz${NC}"
    echo -e "  4. Install: ${YELLOW}cd ${PACKAGE_NAME} && sudo ./install.sh${NC}\n"

    print_success "🎉 Build process complete!"
}

# Run main function
main
