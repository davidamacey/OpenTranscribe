#!/bin/bash
set -e

# OpenTranscribe Offline Package Builder
# Creates a complete offline installation package for air-gapped deployments
# Usage: ./scripts/build-offline-package.sh [version] [--local]
#
# Options:
#   version    Package version (default: git short hash)
#   --local    Use locally built Docker images instead of pulling from Docker Hub

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Load .env file if it exists and HUGGINGFACE_TOKEN is not already set
if [ -z "$HUGGINGFACE_TOKEN" ] && [ -f .env ]; then
    HUGGINGFACE_TOKEN=$(grep "^HUGGINGFACE_TOKEN=" .env | cut -d'=' -f2)
    export HUGGINGFACE_TOKEN
fi

# Parse command line arguments
USE_LOCAL_IMAGES=false
VERSION=""

for arg in "$@"; do
    case $arg in
        --local)
            USE_LOCAL_IMAGES=true
            shift
            ;;
        *)
            # Assume it's the version if not a flag
            if [ -z "$VERSION" ]; then
                VERSION="$arg"
            fi
            ;;
    esac
done

# Configuration
VERSION="${VERSION:-$(git rev-parse --short HEAD)}"
PACKAGE_NAME="opentranscribe-offline-v${VERSION}"
BUILD_DIR="./offline-package-build"
PACKAGE_DIR="${BUILD_DIR}/${PACKAGE_NAME}"

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
    local available_space
    available_space=$(df -BG . | tail -1 | awk '{print $4}' | sed 's/G//')
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
    mapfile -t INFRASTRUCTURE_IMAGES < <(extract_infrastructure_images)

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
    mkdir -p "${PACKAGE_DIR}/models/nltk_data"
    mkdir -p "${PACKAGE_DIR}/models/sentence-transformers"
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
        local image_file
        image_file=$(echo "$image" | tr '/:' '__')
        local output_path="${PACKAGE_DIR}/docker-images/${image_file}.tar"

        print_info "[$current/$total_images] Processing: $image"

        # Pull image from Docker Hub (unless --local flag is set)
        if [ "$USE_LOCAL_IMAGES" = true ]; then
            print_info "  Using local image (skipping pull)..."
            # Check if image exists locally
            if ! docker image inspect "$image" &>/dev/null; then
                print_error "  Local image not found: $image"
                print_info "  Please build the image first with: docker compose build"
                exit 1
            fi
        else
            print_info "  Pulling image from Docker Hub..."
            if ! docker pull "$image"; then
                print_error "  Failed to pull $image"
                exit 1
            fi
        fi

        # Save image
        print_info "  Saving image to tar..."
        if ! docker save "$image" -o "$output_path"; then
            print_error "  Failed to save $image"
            exit 1
        fi

        local size
        size=$(get_dir_size "$output_path")
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

select_whisper_model_for_offline() {
    print_header "Whisper Model Selection"

    # Detect GPU if available for recommendation
    local RECOMMENDED_MODEL="large-v2"
    local RECOMMENDATION_REASON="Best accuracy - recommended for offline deployments"
    local GPU_MEMORY=""

    if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
        GPU_MEMORY=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits -i "${GPU_DEVICE_ID:-0}" 2>/dev/null)
        if [ -n "$GPU_MEMORY" ]; then
            if [[ $GPU_MEMORY -gt 16000 ]]; then
                RECOMMENDED_MODEL="large-v2"
                RECOMMENDATION_REASON="High-end GPU detected (${GPU_MEMORY}MB VRAM) - best accuracy"
            elif [[ $GPU_MEMORY -gt 8000 ]]; then
                RECOMMENDED_MODEL="large-v2"
                RECOMMENDATION_REASON="Mid-range GPU detected (${GPU_MEMORY}MB VRAM) - best accuracy"
            elif [[ $GPU_MEMORY -gt 4000 ]]; then
                RECOMMENDED_MODEL="medium"
                RECOMMENDATION_REASON="Entry-level GPU detected (${GPU_MEMORY}MB VRAM)"
            else
                RECOMMENDED_MODEL="small"
                RECOMMENDATION_REASON="Low-memory GPU detected (${GPU_MEMORY}MB VRAM)"
            fi
        fi
    fi

    echo -e "${BLUE}Available Whisper Models:${NC}"
    echo ""
    echo "  Model       Size    Memory   Speed       Accuracy    Download"
    echo "  ────────────────────────────────────────────────────────────────"
    echo "  tiny        39MB    ~1GB     Fastest     Lowest      ~39MB"
    echo "  base        74MB    ~1GB     Very Fast   Low         ~74MB"
    echo "  small       244MB   ~2GB     Fast        Good        ~244MB"
    echo "  medium      769MB   ~5GB     Moderate    Better      ~769MB"
    echo "  large-v2    1.5GB   ~10GB    Slow        Best        ~1.5GB"
    echo ""
    echo -e "${GREEN}Recommendation: ${RECOMMENDED_MODEL}${NC}"
    echo "  Reason: ${RECOMMENDATION_REASON}"
    echo ""
    echo -e "${YELLOW}IMPORTANT for Offline Deployments:${NC}"
    echo "  • Choose based on the GPU that will be used on the target system"
    echo "  • The selected model will be included in the offline package"
    echo "  • You cannot download a different model after deployment without internet"
    echo "  • Consider the target system's GPU memory, not your current build system"
    echo ""

    # Check if WHISPER_MODEL is already set in environment
    if [ -n "$WHISPER_MODEL" ]; then
        print_info "WHISPER_MODEL already set to: $WHISPER_MODEL"
        read -p "Use this model or select a different one? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_success "Using model: $WHISPER_MODEL"
            return 0
        fi
    fi

    # Prompt user for model selection
    while true; do
        read -r -p "Select model for offline package (tiny/base/small/medium/large-v2) [${RECOMMENDED_MODEL}]: " user_model

        # Use recommended if user just presses Enter
        if [ -z "$user_model" ]; then
            WHISPER_MODEL="$RECOMMENDED_MODEL"
            break
        fi

        # Validate input
        case "$user_model" in
            tiny|base|small|medium|large-v2|large-v1)
                WHISPER_MODEL="$user_model"
                break
                ;;
            *)
                print_error "Invalid model. Please choose: tiny, base, small, medium, or large-v2"
                ;;
        esac
    done

    echo ""
    print_success "Selected model for offline package: ${WHISPER_MODEL}"
    if [ "$WHISPER_MODEL" != "$RECOMMENDED_MODEL" ]; then
        print_warning "Note: You selected a different model than recommended"
    fi

    # Export for use in download_models
    export WHISPER_MODEL
    echo ""
}

select_gpu_device_for_build() {
    print_header "GPU Selection for Model Downloads"

    # Check if nvidia-smi is available
    if ! command_exists nvidia-smi; then
        print_warning "nvidia-smi not found - GPU not available"
        print_info "Model downloads will use CPU mode (slower)"
        export GPU_DEVICE_ID=""
        return 0
    fi

    # Check if any GPUs are detected
    local gpu_count
    gpu_count=$(nvidia-smi --query-gpu=index --format=csv,noheader,nounits 2>/dev/null | wc -l)

    if [ "$gpu_count" -eq 0 ]; then
        print_warning "No NVIDIA GPUs detected"
        print_info "Model downloads will use CPU mode (slower)"
        export GPU_DEVICE_ID=""
        return 0
    fi

    # Single GPU - use it automatically
    if [ "$gpu_count" -eq 1 ]; then
        export GPU_DEVICE_ID="0"
        local gpu_name
        local gpu_memory
        gpu_name=$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits -i 0 2>/dev/null)
        gpu_memory=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits -i 0 2>/dev/null)
        print_success "Using GPU 0: ${gpu_name} (${gpu_memory}MB)"
        return 0
    fi

    # Multiple GPUs - prompt user to select
    echo
    print_info "Multiple GPUs Detected: $gpu_count GPUs available"
    echo
    print_info "Available GPUs:"
    nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader | while IFS=, read -r idx name mem_total mem_free; do
        echo "  [${idx}] ${name} (${mem_total} total, ${mem_free} free)"
    done

    echo
    print_info "Select which GPU to use for model downloads"
    print_warning "Choose a GPU that is not heavily used by other tasks"
    echo

    local selected_gpu="0"

    # Prompt user for GPU selection
    while true; do
        read -r -p "Enter GPU index to use [0-$((gpu_count-1))] (default: 0): " user_input

        # Use default if empty
        if [ -z "$user_input" ]; then
            selected_gpu="0"
            break
        fi

        # Validate input is a number
        if ! [[ "$user_input" =~ ^[0-9]+$ ]]; then
            print_error "Invalid input. Please enter a number."
            continue
        fi

        # Validate GPU index is within range
        if [ "$user_input" -ge 0 ] && [ "$user_input" -lt "$gpu_count" ]; then
            selected_gpu="$user_input"
            break
        else
            print_error "Invalid GPU index. Please enter a number between 0 and $((gpu_count-1))."
        fi
    done

    # Export GPU_DEVICE_ID for use in download_models
    export GPU_DEVICE_ID="$selected_gpu"

    # Get selected GPU details
    local gpu_name
    local gpu_memory
    gpu_name=$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits -i "$GPU_DEVICE_ID" 2>/dev/null)
    gpu_memory=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits -i "$GPU_DEVICE_ID" 2>/dev/null)

    echo
    print_success "Selected GPU ${GPU_DEVICE_ID}: ${gpu_name} (${gpu_memory}MB)"
    echo
}

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
    print_info "Downloading Whisper model: ${WHISPER_MODEL}"
    print_info "This will download approximately 5-40GB depending on model size"
    print_warning "This may take 10-60 minutes depending on your internet speed..."

    # Create temporary model cache directory
    local temp_model_cache="${BUILD_DIR}/temp_models"
    mkdir -p "${temp_model_cache}/huggingface"
    mkdir -p "${temp_model_cache}/torch"
    mkdir -p "${temp_model_cache}/nltk_data"
    mkdir -p "${temp_model_cache}/sentence-transformers"

    # Run backend container with model download script
    print_info "Running model download in Docker container..."

    # Determine GPU arguments
    local gpu_args="--gpus all"
    if [ -n "$GPU_DEVICE_ID" ]; then
        gpu_args="--gpus device=${GPU_DEVICE_ID}"
        print_info "Using GPU ${GPU_DEVICE_ID} for model downloads"
    fi

    # Run as appuser (non-root) matching container security configuration
    # Note: --gpus device=X remaps that GPU to index 0 inside container
    # shellcheck disable=SC2086
    docker run --rm \
        $gpu_args \
        -e CUDA_VISIBLE_DEVICES=0 \
        -e HUGGINGFACE_TOKEN="${HUGGINGFACE_TOKEN}" \
        -e WHISPER_MODEL="${WHISPER_MODEL:-large-v2}" \
        -e DIARIZATION_MODEL="${DIARIZATION_MODEL:-pyannote/speaker-diarization-3.1}" \
        -e USE_GPU="${USE_GPU:-true}" \
        -e COMPUTE_TYPE="${COMPUTE_TYPE:-float16}" \
        -v "${temp_model_cache}/huggingface:/home/appuser/.cache/huggingface" \
        -v "${temp_model_cache}/torch:/home/appuser/.cache/torch" \
        -v "${temp_model_cache}/nltk_data:/home/appuser/.cache/nltk_data" \
        -v "${temp_model_cache}/sentence-transformers:/home/appuser/.cache/sentence-transformers" \
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

    if [ -d "${temp_model_cache}/nltk_data" ] && [ "$(ls -A ${temp_model_cache}/nltk_data 2>/dev/null)" ]; then
        cp -r "${temp_model_cache}/nltk_data"/* "${PACKAGE_DIR}/models/nltk_data/"
        print_info "  Copied NLTK data files"
    else
        print_warning "No NLTK data found to copy"
    fi

    if [ -d "${temp_model_cache}/sentence-transformers" ] && [ "$(ls -A ${temp_model_cache}/sentence-transformers 2>/dev/null)" ]; then
        cp -r "${temp_model_cache}/sentence-transformers"/* "${PACKAGE_DIR}/models/sentence-transformers/"
        print_info "  Copied sentence-transformers models"
    else
        print_warning "No sentence-transformers models found to copy"
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

    local model_size
    model_size=$(get_dir_size "${PACKAGE_DIR}/models")
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
        local service_name
        service_name=$(echo "$img" | cut -d: -f1 | cut -d/ -f1)

        # Update the image line in offline compose file for this service
        # Find the service block and update its image line
        sed -i "s|image: ${service_name}[:/][^ ]*|image: ${img}|g" "$temp_compose"
    done

    print_success "Infrastructure images synced from docker-compose.yml"

    # Copy and template .env file
    print_info "Creating .env template..."
    sed 's/=.*/=/' .env > "${PACKAGE_DIR}/config/.env.template"

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

    # Copy uninstall script
    print_info "Copying uninstall.sh..."
    cp scripts/uninstall-offline-package.sh "${PACKAGE_DIR}/uninstall.sh"
    chmod +x "${PACKAGE_DIR}/uninstall.sh"

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

prompt_compression() {
    print_header "Package Compression"

    local package_size
    package_size=$(get_dir_size "$PACKAGE_DIR")

    print_info "Package is ready to compress"
    print_info "Uncompressed package size: $package_size"
    print_info "Estimated compressed size: 15-20GB"
    echo
    print_warning "Compression will take 30-60 minutes using all CPU threads"
    print_info "You can skip compression if:"
    print_info "  - Testing the package locally"
    print_info "  - Using fast local network transfer"
    print_info "  - Planning to compress manually later"
    echo

    # Prompt user for compression
    while true; do
        read -p "Do you want to compress the package now? (y/n): " -r response
        case $response in
            [Yy]* )
                return 0  # Compress
                ;;
            [Nn]* )
                return 1  # Skip compression
                ;;
            * )
                echo "Please answer y (yes) or n (no)."
                ;;
        esac
    done
}

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

    local compressed_size
    local uncompressed_size
    compressed_size=$(get_dir_size "$output_file")
    uncompressed_size=$(get_dir_size "$PACKAGE_DIR")

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

create_uncompressed_checksum() {
    print_header "Creating Package Checksum"

    print_info "Creating checksum for uncompressed package..."
    cd "$BUILD_DIR"

    # Create a checksum file listing all files in the package
    find "$PACKAGE_NAME" -type f -exec sha256sum {} \; > "${PACKAGE_NAME}.sha256"

    cd - > /dev/null

    print_success "Checksum file created: ${BUILD_DIR}/${PACKAGE_NAME}.sha256"
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
    select_whisper_model_for_offline
    select_gpu_device_for_build
    pull_and_save_images
    download_models
    copy_configuration
    copy_installation_scripts
    copy_documentation
    finalize_package

    # Prompt for compression
    if prompt_compression; then
        # User chose to compress
        compress_package
        PACKAGE_COMPRESSED=true
    else
        # User chose to skip compression
        print_info "Skipping compression..."
        create_uncompressed_checksum
        PACKAGE_COMPRESSED=false
    fi

    # Final summary
    print_header "Build Complete!"

    echo -e "${GREEN}✅ Offline package created successfully!${NC}\n"

    if [ "$PACKAGE_COMPRESSED" = true ]; then
        # Compressed package summary
        echo -e "Package location:"
        echo -e "  ${CYAN}${BUILD_DIR}/${PACKAGE_NAME}.tar.xz${NC}\n"
        echo -e "Package checksum:"
        echo -e "  ${CYAN}${BUILD_DIR}/${PACKAGE_NAME}.tar.xz.sha256${NC}\n"
        echo -e "Next steps:"
        echo -e "  1. Verify checksum: ${YELLOW}sha256sum -c ${PACKAGE_NAME}.tar.xz.sha256${NC}"
        echo -e "  2. Transfer package to target system"
        echo -e "  3. Extract: ${YELLOW}tar -xf ${PACKAGE_NAME}.tar.xz${NC}"
        echo -e "  4. Install: ${YELLOW}cd ${PACKAGE_NAME} && sudo ./install.sh${NC}\n"
    else
        # Uncompressed package summary
        echo -e "Package location (uncompressed):"
        echo -e "  ${CYAN}${BUILD_DIR}/${PACKAGE_NAME}/${NC}\n"
        echo -e "Package checksum:"
        echo -e "  ${CYAN}${BUILD_DIR}/${PACKAGE_NAME}.sha256${NC}\n"
        echo -e "Next steps:"
        echo -e "  ${YELLOW}Option 1: Transfer uncompressed${NC}"
        echo -e "    1. Copy entire directory to target system"
        echo -e "    2. Install: ${YELLOW}cd ${PACKAGE_NAME} && sudo ./install.sh${NC}\n"
        echo -e "  ${YELLOW}Option 2: Compress manually later${NC}"
        echo -e "    1. Compress: ${YELLOW}tar -cf - ${PACKAGE_NAME} | xz -9 -T0 > ${PACKAGE_NAME}.tar.xz${NC}"
        echo -e "    2. Create checksum: ${YELLOW}sha256sum ${PACKAGE_NAME}.tar.xz > ${PACKAGE_NAME}.tar.xz.sha256${NC}"
        echo -e "    3. Transfer and extract as usual\n"
    fi

    print_success "🎉 Build process complete!"
}

# Run main function
main
