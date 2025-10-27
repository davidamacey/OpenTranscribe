#!/bin/bash
set -e

# OpenTranscribe Offline Installation Script
# Installs OpenTranscribe on air-gapped systems
# Usage: sudo ./install.sh

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/opentranscribe"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

# Check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

#######################
# SYSTEM VALIDATION
#######################

validate_system() {
    print_header "System Validation"

    # Check OS
    if [ -f /etc/os-release ]; then
        # shellcheck source=/dev/null  # Runtime file, not available during static analysis
        . /etc/os-release
        # shellcheck disable=SC2153  # NAME and VERSION are set by /etc/os-release
        print_info "Operating System: $NAME $VERSION"

        if [[ ! "$ID" =~ ^(ubuntu|debian)$ ]]; then
            print_warning "This script is designed for Ubuntu/Debian"
            print_warning "You are running: $NAME"
            read -p "Continue anyway? (y/N) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
        fi
    else
        print_warning "Cannot detect OS version"
    fi

    # Check Docker
    if ! command_exists docker; then
        print_error "Docker is not installed"
        print_info "Please install Docker before running this installer"
        print_info "Visit: https://docs.docker.com/engine/install/"
        exit 1
    fi

    local docker_version
    docker_version=$(docker --version | cut -d' ' -f3 | cut -d',' -f1)
    print_success "Docker installed: $docker_version"

    # Check if Docker is running
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker daemon is not running"
        print_info "Start Docker with: sudo systemctl start docker"
        exit 1
    fi

    print_success "Docker daemon is running"

    # Check for NVIDIA GPU
    if command_exists nvidia-smi; then
        print_info "Checking NVIDIA GPU..."
        if nvidia-smi > /dev/null 2>&1; then
            local gpu_info
            gpu_info=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
            print_success "GPU detected: $gpu_info"

            # Check NVIDIA Container Toolkit (check for package, not by running container)
            if dpkg -l | grep -q nvidia-container-toolkit; then
                local toolkit_version
                toolkit_version=$(dpkg -l | grep nvidia-container-toolkit | awk '{print $3}')
                print_success "NVIDIA Container Toolkit installed: $toolkit_version"
            elif rpm -qa | grep -q nvidia-container-toolkit; then
                local toolkit_version
                toolkit_version=$(rpm -qa | grep nvidia-container-toolkit | head -1)
                print_success "NVIDIA Container Toolkit installed: $toolkit_version"
            else
                print_warning "NVIDIA GPU detected but Container Toolkit not installed"
                print_warning "Install it from: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
                print_warning "OpenTranscribe will fall back to CPU mode"
            fi
        else
            print_warning "nvidia-smi command failed"
        fi
    else
        print_info "No NVIDIA GPU detected - will use CPU mode"
    fi

    # Check disk space (need at least 80GB)
    local available_space
    available_space=$(df -BG /opt 2>/dev/null | tail -1 | awk '{print $4}' | sed 's/G//')
    if [ -z "$available_space" ]; then
        available_space=$(df -BG / 2>/dev/null | tail -1 | awk '{print $4}' | sed 's/G//')
    fi

    if [ -n "$available_space" ] && [ "$available_space" -lt 80 ]; then
        print_error "Insufficient disk space"
        print_error "Required: 80GB, Available: ${available_space}GB"
        exit 1
    fi

    print_success "Sufficient disk space available: ${available_space}GB"

    # Check Docker Compose
    if docker compose version > /dev/null 2>&1; then
        local compose_version
        compose_version=$(docker compose version --short)
        print_success "Docker Compose installed: $compose_version"
    else
        print_error "Docker Compose not available"
        print_info "Please install Docker Compose v2"
        exit 1
    fi

    print_success "System validation passed"
}

#######################
# PACKAGE VERIFICATION
#######################

verify_package() {
    print_header "Verifying Package Integrity"

    # Check for checksums file
    if [ ! -f "$SCRIPT_DIR/checksums.sha256" ]; then
        print_warning "Checksum file not found - skipping verification"
        return
    fi

    print_info "Verifying package checksums..."

    cd "$SCRIPT_DIR"

    # Run checksum verification with detailed output
    local checksum_output
    checksum_output=$(sha256sum -c checksums.sha256 2>&1)
    local checksum_result=$?

    if [ $checksum_result -eq 0 ]; then
        print_success "Package integrity verified"
    else
        print_error "Package integrity check failed"
        print_error "Details:"
        echo "$checksum_output" | while read -r line; do
            if [[ "$line" =~ FAILED ]]; then
                print_error "  $line"
            fi
        done
        print_error "Package may be corrupted or tampered with"

        # Show which files failed
        echo
        print_info "Failed checksums:"
        echo "$checksum_output" | grep FAILED

        exit 1
    fi
    cd - > /dev/null
}

#######################
# DOCKER IMAGES
#######################

load_docker_images() {
    print_header "Loading Docker Images"

    local image_dir="$SCRIPT_DIR/docker-images"

    if [ ! -d "$image_dir" ]; then
        print_error "Docker images directory not found: $image_dir"
        exit 1
    fi

    local images=("$image_dir"/*.tar)
    local total=${#images[@]}
    local current=0

    print_info "Found $total Docker images to load"
    print_warning "This may take 15-30 minutes..."
    echo

    for image_file in "${images[@]}"; do
        current=$((current + 1))
        local image_name
        image_name=$(basename "$image_file" .tar | tr '__' ':')

        echo -ne "${BLUE}[INFO]${NC} [$current/$total] Loading: $image_name"

        if docker load -i "$image_file" > /dev/null 2>&1; then
            echo -e "\r${GREEN}[SUCCESS]${NC} [$current/$total] Loaded: $image_name        "
        else
            echo -e "\r${RED}[ERROR]${NC} [$current/$total] Failed: $image_name        "
            print_error "Failed to load $image_file"
            exit 1
        fi
    done

    echo
    print_success "All Docker images loaded successfully"

    # Show loaded images
    print_info "Loaded images:"
    docker images --format "  {{.Repository}}:{{.Tag}}" | grep -E "(opentranscribe|postgres|redis|minio|opensearch)" || true
}

#######################
# INSTALLATION
#######################

install_files() {
    print_header "Installing OpenTranscribe"

    # Create installation directory
    print_info "Creating installation directory: $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR/models"
    mkdir -p "$INSTALL_DIR/config"
    mkdir -p "$INSTALL_DIR/database"
    mkdir -p "$INSTALL_DIR/scripts"
    mkdir -p "$INSTALL_DIR/temp"

    # Copy Docker Compose configuration (base + offline override pattern)
    print_info "Copying configuration files..."
    cp "$SCRIPT_DIR/config/docker-compose.yml" "$INSTALL_DIR/docker-compose.yml"
    cp "$SCRIPT_DIR/config/docker-compose.offline.yml" "$INSTALL_DIR/docker-compose.offline.yml"
    cp "$SCRIPT_DIR/database/init_db.sql" "$INSTALL_DIR/database/"
    cp "$SCRIPT_DIR/config/nginx.conf" "$INSTALL_DIR/config/"

    # Copy scripts
    if [ -d "$SCRIPT_DIR/scripts" ]; then
        cp -r "$SCRIPT_DIR/scripts"/* "$INSTALL_DIR/scripts/" || true
    fi

    # Copy management wrapper
    cp "$SCRIPT_DIR/opentr-offline.sh" "$INSTALL_DIR/opentr.sh"
    chmod +x "$INSTALL_DIR/opentr.sh"

    # Copy uninstall script
    cp "$SCRIPT_DIR/uninstall.sh" "$INSTALL_DIR/uninstall.sh"
    chmod +x "$INSTALL_DIR/uninstall.sh"

    print_success "Files installed"
}

install_models() {
    print_header "Installing AI Models"

    local model_dir="$SCRIPT_DIR/models"

    if [ ! -d "$model_dir" ]; then
        print_warning "Models directory not found - skipping"
        print_info "You will need to download models on first use"
        return
    fi

    print_info "Copying AI models to $INSTALL_DIR/models"
    print_warning "This may take 10-20 minutes (copying ~38GB)..."

    # Create model cache directories with proper structure
    mkdir -p "$INSTALL_DIR/models/huggingface"
    mkdir -p "$INSTALL_DIR/models/torch"
    mkdir -p "$INSTALL_DIR/models/nltk_data"
    mkdir -p "$INSTALL_DIR/models/sentence-transformers"

    # Copy models
    if [ -d "$model_dir/huggingface" ]; then
        print_info "Copying HuggingFace models..."
        cp -r "$model_dir/huggingface" "$INSTALL_DIR/models/"
    fi

    if [ -d "$model_dir/torch" ]; then
        print_info "Copying PyTorch models..."
        cp -r "$model_dir/torch" "$INSTALL_DIR/models/"
    fi

    if [ -d "$model_dir/nltk_data" ]; then
        print_info "Copying NLTK data..."
        cp -r "$model_dir/nltk_data" "$INSTALL_DIR/models/"
    fi

    if [ -d "$model_dir/sentence-transformers" ]; then
        print_info "Copying sentence-transformers models..."
        cp -r "$model_dir/sentence-transformers" "$INSTALL_DIR/models/"
    fi

    # Copy model manifest if exists
    if [ -f "$model_dir/model_manifest.json" ]; then
        cp "$model_dir/model_manifest.json" "$INSTALL_DIR/models/"
    fi

    # Set proper permissions for non-root container user (UID 1000)
    print_info "Setting model cache permissions for container compatibility..."
    chown -R 1000:1000 "$INSTALL_DIR/models" 2>/dev/null || {
        print_warning "Could not set ownership to UID 1000 - you may need to run:"
        echo "  sudo chown -R 1000:1000 $INSTALL_DIR/models"
        echo "  Or use: $INSTALL_DIR/scripts/fix-model-permissions.sh"
    }
    chmod -R 755 "$INSTALL_DIR/models"

    print_success "AI models installed"
}

select_gpu_device() {
    # Only prompt if GPU is available and multiple GPUs detected
    local gpu_count
    gpu_count=$(nvidia-smi --query-gpu=index --format=csv,noheader,nounits 2>/dev/null | wc -l)

    if [ "$gpu_count" -le 1 ]; then
        return 0
    fi

    echo
    print_info "Multiple GPUs Detected: $gpu_count GPUs available"
    echo
    print_info "Available GPUs:"
    nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader | while IFS=, read -r idx name mem_total mem_free; do
        echo "  [${idx}] ${name} (${mem_total} total, ${mem_free} free)"
    done

    echo
    print_info "Select which GPU to use for transcription processing"
    echo

    # Prompt user for GPU selection
    while true; do
        read -r -p "Enter GPU index to use [0-$((gpu_count-1))] (default: ${gpu_device_id}): " selected_gpu

        # Use default if empty
        if [ -z "$selected_gpu" ]; then
            selected_gpu=$gpu_device_id
            break
        fi

        # Validate input is a number
        if ! [[ "$selected_gpu" =~ ^[0-9]+$ ]]; then
            print_error "Invalid input. Please enter a number."
            continue
        fi

        # Validate GPU index is within range
        if [ "$selected_gpu" -ge 0 ] && [ "$selected_gpu" -lt "$gpu_count" ]; then
            break
        else
            print_error "Invalid GPU index. Please enter a number between 0 and $((gpu_count-1))."
        fi
    done

    # Update gpu_device_id with user selection
    gpu_device_id=$selected_gpu

    # Get selected GPU details
    local gpu_name
    local gpu_memory
    gpu_name=$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits -i "$gpu_device_id")
    gpu_memory=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits -i "$gpu_device_id")

    echo
    print_success "Selected GPU ${gpu_device_id}: ${gpu_name} (${gpu_memory}MB)"
    echo
}

create_env_file() {
    print_header "Creating Environment Configuration"

    # Auto-detect GPU
    local use_gpu="false"
    local torch_device="cpu"
    local compute_type="int8"
    local gpu_device_id="0"

    if command_exists nvidia-smi && nvidia-smi > /dev/null 2>&1; then
        # Check if NVIDIA Container Toolkit is installed (package check, not container run)
        if dpkg -l 2>/dev/null | grep -q nvidia-container-toolkit || rpm -qa 2>/dev/null | grep -q nvidia-container-toolkit; then
            use_gpu="true"
            torch_device="cuda"
            compute_type="float16"
            print_success "GPU support enabled"

            # Allow user to select GPU if multiple available
            select_gpu_device
        else
            print_warning "NVIDIA GPU detected but Container Toolkit not installed - using CPU mode"
        fi
    fi

    if [ "$use_gpu" = "false" ]; then
        print_info "GPU support disabled (CPU mode)"
    fi

    # Read WHISPER_MODEL from package manifest if available
    local whisper_model="large-v2"
    if [ -f "$SCRIPT_DIR/models/model_manifest.json" ]; then
        # Extract whisper_model from JSON using grep and sed
        local manifest_model
        manifest_model=$(grep -o '"whisper_model"[[:space:]]*:[[:space:]]*"[^"]*"' "$SCRIPT_DIR/models/model_manifest.json" | sed 's/.*"whisper_model"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
        if [ -n "$manifest_model" ]; then
            whisper_model="$manifest_model"
            print_info "Using Whisper model from package: $whisper_model"
        fi
    fi

    # Create .env file from template (robust to future .env.example changes)
    print_info "Creating .env configuration from .env.example template..."

    # Check if .env.example exists in package
    if [ ! -f ".env.example" ]; then
        print_error ".env.example not found in package!"
        print_error "Package may be corrupted. Please re-download."
        exit 1
    fi

    # Copy .env.example as base
    cp .env.example "$INSTALL_DIR/.env"

    # Generate all secure credentials using openssl
    print_info "Generating secure credentials..."
    local POSTGRES_PASSWORD=$(openssl rand -hex 32)
    local MINIO_ROOT_PASSWORD=$(openssl rand -hex 32)
    local JWT_SECRET_KEY=$(openssl rand -hex 64)
    local ENCRYPTION_KEY=$(openssl rand -hex 64)
    local REDIS_PASSWORD=$(openssl rand -hex 32)
    local OPENSEARCH_PASSWORD=$(openssl rand -hex 32)

    # Replace placeholders with generated passwords
    sed -i "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${POSTGRES_PASSWORD}|g" "$INSTALL_DIR/.env"
    sed -i "s|MINIO_ROOT_PASSWORD=.*|MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}|g" "$INSTALL_DIR/.env"
    sed -i "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=${JWT_SECRET_KEY}|g" "$INSTALL_DIR/.env"
    sed -i "s|ENCRYPTION_KEY=.*|ENCRYPTION_KEY=${ENCRYPTION_KEY}|g" "$INSTALL_DIR/.env"
    sed -i "s|REDIS_PASSWORD=.*|REDIS_PASSWORD=${REDIS_PASSWORD}|g" "$INSTALL_DIR/.env"
    sed -i "s|OPENSEARCH_PASSWORD=.*|OPENSEARCH_PASSWORD=${OPENSEARCH_PASSWORD}|g" "$INSTALL_DIR/.env"

    # Update hardware-specific settings (auto-detected)
    sed -i "s|USE_GPU=.*|USE_GPU=${use_gpu}|g" "$INSTALL_DIR/.env"
    sed -i "s|TORCH_DEVICE=.*|TORCH_DEVICE=${torch_device}|g" "$INSTALL_DIR/.env"
    sed -i "s|COMPUTE_TYPE=.*|COMPUTE_TYPE=${compute_type}|g" "$INSTALL_DIR/.env"
    sed -i "s|GPU_DEVICE_ID=.*|GPU_DEVICE_ID=${gpu_device_id}|g" "$INSTALL_DIR/.env"
    sed -i "s|WHISPER_MODEL=.*|WHISPER_MODEL=${whisper_model}|g" "$INSTALL_DIR/.env"

    # Update installation-specific paths
    sed -i "s|MODEL_CACHE_DIR=.*|MODEL_CACHE_DIR=${INSTALL_DIR}/models|g" "$INSTALL_DIR/.env"
    # Note: TEMP_DIR override for offline install locations
    sed -i "s|^#.*TEMP_DIR=.*|TEMP_DIR=${INSTALL_DIR}/temp|g" "$INSTALL_DIR/.env"

    # Set offline mode for HuggingFace (append if not already present)
    if ! grep -q "HF_HUB_OFFLINE" "$INSTALL_DIR/.env"; then
        echo "" >> "$INSTALL_DIR/.env"
        echo "# Offline Mode (set by installer)" >> "$INSTALL_DIR/.env"
        echo "HF_HUB_OFFLINE=1" >> "$INSTALL_DIR/.env"
    fi

    # Note: INIT_DB_PATH uses default ./database/init_db.sql from .env.example
    # No need to override - all deployment methods use the same path

    print_success "Environment configuration created (using .env.example template)"
    print_info "✓ Secure credentials auto-generated (64-char JWT/encryption, 32-char passwords)"
    print_warning "IMPORTANT: Edit $INSTALL_DIR/.env to set your HUGGINGFACE_TOKEN"
}

set_permissions() {
    print_header "Setting Permissions"

    print_info "Setting directory permissions..."

    chown -R root:root "$INSTALL_DIR"
    chmod -R 755 "$INSTALL_DIR"
    chmod 644 "$INSTALL_DIR/.env"

    print_success "Permissions set"
}

#######################
# POST-INSTALL
#######################

post_install_info() {
    print_header "Installation Complete!"

    echo -e "${GREEN}✅ OpenTranscribe has been installed successfully!${NC}\n"

    echo -e "${CYAN}Installation Location:${NC}"
    echo -e "  $INSTALL_DIR\n"

    echo -e "${CYAN}Next Steps:${NC}"
    echo -e "  1. ${YELLOW}Edit configuration:${NC}"
    echo -e "     sudo nano $INSTALL_DIR/.env"
    echo -e "     ${RED}REQUIRED: Set your HUGGINGFACE_TOKEN${NC}\n"

    echo -e "  2. ${YELLOW}Start OpenTranscribe:${NC}"
    echo -e "     cd $INSTALL_DIR"
    echo -e "     sudo ./opentr.sh start\n"

    echo -e "  3. ${YELLOW}Access the application:${NC}"
    echo -e "     http://localhost:5173\n"

    echo -e "${CYAN}Management Commands:${NC}"
    echo -e "  cd $INSTALL_DIR"
    echo -e "  sudo ./opentr.sh start     ${BLUE}# Start all services${NC}"
    echo -e "  sudo ./opentr.sh stop      ${BLUE}# Stop all services${NC}"
    echo -e "  sudo ./opentr.sh status    ${BLUE}# Check service status${NC}"
    echo -e "  sudo ./opentr.sh logs      ${BLUE}# View logs${NC}"
    echo -e "  sudo ./opentr.sh restart   ${BLUE}# Restart services${NC}\n"

    echo -e "${CYAN}Documentation:${NC}"
    echo -e "  $SCRIPT_DIR/README-OFFLINE.md\n"

    if [ "$use_gpu" = "false" ]; then
        echo -e "${YELLOW}⚠️  WARNING: Running in CPU mode${NC}"
        echo -e "   Transcription will be significantly slower without GPU\n"
    fi

    print_success "Installation complete! 🎉"
}

#######################
# CLEANUP
#######################

cleanup() {
    if [ $? -ne 0 ]; then
        print_error "Installation failed"
        print_info "Check the error messages above"
        exit 1
    fi
}

trap cleanup EXIT

#######################
# MAIN
#######################

main() {
    print_header "OpenTranscribe Offline Installer"

    print_info "This will install OpenTranscribe to: $INSTALL_DIR"
    print_warning "This process will take 30-60 minutes"
    echo

    read -p "Continue with installation? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Installation cancelled"
        exit 0
    fi

    # Check root
    check_root

    # Run installation steps
    validate_system
    verify_package
    load_docker_images
    install_files
    install_models
    create_env_file
    set_permissions
    post_install_info
}

# Run main function
main
