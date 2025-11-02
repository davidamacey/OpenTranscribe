#!/bin/bash
set -e

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions for colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_header() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════${NC}"
    echo ""
}

echo -e "${YELLOW}OpenTranscribe Cross-Platform Setup Script${NC}"
echo "Automatic hardware detection and configuration for CUDA, MPS, and CPU"
echo ""

# Global variables
PROJECT_DIR="opentranscribe"
DETECTED_PLATFORM=""
DETECTED_DEVICE=""
COMPUTE_TYPE=""
BATCH_SIZE=""
DOCKER_RUNTIME=""
USE_GPU_RUNTIME="false"

#######################
# HARDWARE DETECTION
#######################

detect_platform() {
    echo -e "${BLUE}🔍 Detecting platform and hardware...${NC}"

    # Detect OS and Architecture
    DETECTED_PLATFORM=$(uname -s | tr '[:upper:]' '[:lower:]')
    ARCH=$(uname -m)

    case "$DETECTED_PLATFORM" in
        "linux")
            echo "✓ Detected: Linux ($ARCH)"
            ;;
        "darwin")
            DETECTED_PLATFORM="macos"
            echo "✓ Detected: macOS ($ARCH)"
            ;;
        "mingw"*|"msys"*|"cygwin"*)
            DETECTED_PLATFORM="windows"
            echo "✓ Detected: Windows ($ARCH)"
            ;;
        *)
            echo "⚠️  Unknown platform: $DETECTED_PLATFORM ($ARCH)"
            ;;
    esac

    # Detect hardware acceleration
    detect_hardware_acceleration
}

detect_hardware_acceleration() {
    DETECTED_DEVICE="cpu"  # Default fallback

    # Check for NVIDIA GPU (CUDA)
    if command -v nvidia-smi &> /dev/null; then
        if nvidia-smi &> /dev/null; then
            echo "✓ NVIDIA GPU detected"
            nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader
            DETECTED_DEVICE="cuda"
            COMPUTE_TYPE="float16"
            BATCH_SIZE="16"
            USE_GPU_RUNTIME="true"

            # Get count of available GPUs
            GPU_COUNT=$(nvidia-smi --query-gpu=index --format=csv,noheader,nounits | wc -l)

            # Get default GPU (first available)
            DEFAULT_GPU=$(nvidia-smi --query-gpu=index --format=csv,noheader,nounits | head -n1)
            GPU_DEVICE_ID=${DEFAULT_GPU:-0}

            return
        fi
    fi

    # Check for Apple Silicon (MPS)
    if [[ "$DETECTED_PLATFORM" == "macos" ]]; then
        # Check for Apple Silicon
        if [[ $(uname -m) == "arm64" ]]; then
            echo "✓ Apple Silicon detected (M1/M2)"
            DETECTED_DEVICE="mps"
            COMPUTE_TYPE="float32"
            BATCH_SIZE="8"

            # Check macOS version for MPS support (requires macOS 12.3+)
            macos_version=$(sw_vers -productVersion)
            if [[ $(echo "$macos_version" | cut -d. -f1) -ge 12 ]] && [[ $(echo "$macos_version" | cut -d. -f2) -ge 3 ]]; then
                echo "✓ macOS $macos_version supports MPS acceleration"
            else
                echo "⚠️  macOS $macos_version detected, MPS requires 12.3+, falling back to CPU"
                DETECTED_DEVICE="cpu"
            fi

            return
        else
            echo "✓ Intel Mac detected"
        fi
    fi

    # CPU fallback
    echo "ℹ️  Using CPU processing (no GPU acceleration detected)"
    DETECTED_DEVICE="cpu"
    COMPUTE_TYPE="int8"
    BATCH_SIZE="4"

    # Detect CPU cores for optimization
    if command -v nproc &> /dev/null; then
        CPU_CORES=$(nproc)
    elif command -v sysctl &> /dev/null; then
        CPU_CORES=$(sysctl -n hw.ncpu)
    else
        CPU_CORES=4
    fi
    echo "✓ Detected $CPU_CORES CPU cores"
}

#######################
# DOCKER CONFIGURATION
#######################

check_gpu_support() {
    # Check for NVIDIA GPUs
    if command -v nvidia-smi &> /dev/null; then
        echo "✅ NVIDIA GPU detected:"
        nvidia-smi --query-gpu=name --format=csv,noheader
    else
        echo "❌ No NVIDIA GPU detected or nvidia-smi not found"
        return 1
    fi

    # Check for NVIDIA container runtime
    if docker info 2>/dev/null | grep -q "nvidia"; then
        echo "✅ NVIDIA Container Runtime is properly configured"
        return 0
    else
        echo "❌ NVIDIA Container Runtime is not properly configured"
        return 1
    fi
}

configure_docker_runtime() {
    echo -e "${BLUE}🐳 Configuring Docker runtime...${NC}"

    if [[ "$USE_GPU_RUNTIME" == "true" && "$DETECTED_DEVICE" == "cuda" ]]; then
        echo "🧪 Testing NVIDIA Container Toolkit..."

        if check_gpu_support; then
            echo -e "${GREEN}✅ NVIDIA Container Toolkit fully functional${NC}"
            DOCKER_RUNTIME="nvidia"
        else
            echo -e "${RED}❌ NVIDIA Container Toolkit tests failed${NC}"
            echo ""
            echo "Possible solutions:"
            echo "1. Install NVIDIA Container Toolkit:"
            echo "   https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
            echo "2. Restart Docker daemon after installation"
            echo "3. Check NVIDIA driver installation with: nvidia-smi"
            echo ""
            echo -e "${YELLOW}⚠️  Automatically falling back to CPU mode...${NC}"
            fallback_to_cpu
        fi
    else
        DOCKER_RUNTIME="default"
        echo "✓ Using default Docker runtime"
    fi
}

fallback_to_cpu() {
    DETECTED_DEVICE="cpu"
    COMPUTE_TYPE="int8"
    BATCH_SIZE="4"
    USE_GPU_RUNTIME="false"
    DOCKER_RUNTIME="default"
}

#######################
# NETWORK AND DEPENDENCY CHECKS
#######################

check_network_connectivity() {
    echo -e "${BLUE}🌐 Checking network connectivity...${NC}"

    # Test GitHub connectivity
    if ! curl -s --connect-timeout 5 --max-time 10 https://raw.githubusercontent.com > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  GitHub may not be accessible for downloading files${NC}"
        echo "This could affect the setup process. Please check your internet connection."
        echo ""
        read -p "Do you want to continue anyway? (y/N) " -n 1 -r </dev/tty
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Setup cancelled by user."
            exit 1
        fi
    else
        echo "✓ Network connectivity verified"
    fi
}

validate_downloaded_files() {
    echo -e "${BLUE}🔍 Validating downloaded files...${NC}"

    # Validate init_db.sql (in database/ subdirectory)
    if [ ! -f "database/init_db.sql" ]; then
        echo -e "${RED}❌ database/init_db.sql file not found${NC}"
        return 1
    fi

    # Check file size (should be substantial)
    local db_size
    db_size=$(wc -c < database/init_db.sql)
    if [ "$db_size" -lt 10000 ]; then
        echo -e "${RED}❌ database/init_db.sql file too small ($db_size bytes)${NC}"
        return 1
    fi

    # Check for essential database content including admin user
    if ! grep -q "CREATE TABLE.*user" database/init_db.sql || ! grep -q "CREATE TABLE.*media_file" database/init_db.sql || ! grep -q "admin@example.com" database/init_db.sql; then
        echo -e "${RED}❌ database/init_db.sql missing essential database tables or admin user${NC}"
        return 1
    fi

    echo "✓ database/init_db.sql validated ($db_size bytes)"

    # Validate docker-compose files exist
    if [ ! -f "docker-compose.yml" ]; then
        echo -e "${RED}❌ docker-compose.yml file not found${NC}"
        return 1
    fi

    if [ ! -f "docker-compose.prod.yml" ]; then
        echo -e "${RED}❌ docker-compose.prod.yml file not found${NC}"
        return 1
    fi

    # Check for essential services in base file
    if ! grep -q "services:" docker-compose.yml; then
        echo -e "${RED}❌ docker-compose.yml appears invalid (no 'services:' section)${NC}"
        return 1
    fi

    if ! grep -q "backend:" docker-compose.yml || ! grep -q "frontend:" docker-compose.yml; then
        echo -e "${RED}❌ docker-compose.yml missing essential services${NC}"
        return 1
    fi

    echo "✓ docker-compose.yml and docker-compose.prod.yml validated"
    echo "  (Full configuration validation will occur after .env file creation)"
    echo "✓ All downloaded files validated successfully"
    return 0
}

check_dependencies() {
    echo -e "${BLUE}📋 Checking dependencies...${NC}"

    # Check for curl
    if ! command -v curl &> /dev/null; then
        echo -e "${RED}❌ curl is not installed${NC}"
        echo "curl is required to download configuration files."
        echo "Please install curl and try again."
        exit 1
    else
        echo "✓ curl detected"
    fi

    # Check for Docker
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker is not installed${NC}"
        echo "Visit https://docs.docker.com/get-docker/ for installation instructions."
        exit 1
    else
        docker_version=$(docker --version | cut -d' ' -f3 | cut -d',' -f1)
        echo "✓ Docker $docker_version detected"
    fi

    # Check for Docker Compose
    if ! docker compose version &> /dev/null; then
        echo -e "${RED}❌ Docker Compose is not installed or not in PATH${NC}"
        echo "Visit https://docs.docker.com/compose/install/ for installation instructions."
        exit 1
    else
        compose_version=$(docker compose version --short)
        echo "✓ Docker Compose $compose_version detected"
    fi

    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        echo -e "${RED}❌ Docker daemon is not running${NC}"
        echo "Please start Docker and try again."
        exit 1
    else
        echo "✓ Docker daemon is running"
    fi

    # Check network connectivity
    check_network_connectivity
}

#######################
# CONFIGURATION SETUP
#######################

setup_project_directory() {
    echo -e "${BLUE}📁 Setting up project directory...${NC}"

    # Create and enter project directory
    mkdir -p "$PROJECT_DIR"
    cd "$PROJECT_DIR"
    echo "✓ Created project directory: $PROJECT_DIR"
}

create_database_files() {
    echo "✓ Downloading database initialization files..."

    # Create database directory
    mkdir -p database

    # Download the official init_db.sql from the repository
    local max_retries=3
    local retry_count=0
    local branch="${OPENTRANSCRIBE_BRANCH:-master}"
    # URL-encode the branch name (replace / with %2F)
    local encoded_branch
    encoded_branch=$(echo "$branch" | sed 's|/|%2F|g')
    local download_url="https://raw.githubusercontent.com/davidamacey/OpenTranscribe/${encoded_branch}/database/init_db.sql"

    while [ $retry_count -lt $max_retries ]; do
        if curl -fsSL --connect-timeout 10 --max-time 30 "$download_url" -o database/init_db.sql; then
            # Validate downloaded file
            if [ -s database/init_db.sql ] && grep -q "CREATE TABLE" database/init_db.sql && grep -q "admin@example.com" database/init_db.sql; then
                echo "✓ Downloaded and validated database/init_db.sql"
                return 0
            else
                echo "⚠️  Downloaded file appears invalid, retrying..."
                rm -f database/init_db.sql
            fi
        else
            echo "⚠️  Download attempt $((retry_count + 1)) failed"
        fi

        retry_count=$((retry_count + 1))
        if [ $retry_count -lt $max_retries ]; then
            echo "⏳ Retrying in 2 seconds..."
            sleep 2
        fi
    done

    echo -e "${RED}❌ Failed to download database initialization file after $max_retries attempts${NC}"
    echo "Please check your internet connection and try again."
    echo "Alternative: You can manually download from:"
    echo "$download_url"
    exit 1
}

create_configuration_files() {
    echo -e "${BLUE}📄 Creating configuration files...${NC}"

    # Create database initialization files
    create_database_files

    # Create comprehensive docker-compose.yml directly
    create_production_compose

    # Validate all downloaded files
    if ! validate_downloaded_files; then
        echo -e "${RED}❌ File validation failed${NC}"
        exit 1
    fi

    # Download opentranscribe.sh management script
    download_management_script

    # Download model downloader scripts
    download_model_downloader_scripts

    # Create .env.example
    create_production_env_example
}

create_production_compose() {
    echo "✓ Downloading production docker-compose configuration..."

    local max_retries=3
    local branch="${OPENTRANSCRIBE_BRANCH:-master}"
    # URL-encode the branch name (replace / with %2F)
    local encoded_branch
    encoded_branch=$(echo "$branch" | sed 's|/|%2F|g')

    # Download base docker-compose.yml
    echo "  Downloading base docker-compose.yml..."
    local retry_count=0
    local base_url="https://raw.githubusercontent.com/davidamacey/OpenTranscribe/${encoded_branch}/docker-compose.yml"

    while [ $retry_count -lt $max_retries ]; do
        if curl -fsSL --connect-timeout 10 --max-time 30 "$base_url" -o docker-compose.yml; then
            if [ -s docker-compose.yml ] && grep -q "services:" docker-compose.yml; then
                echo "  ✓ Downloaded base docker-compose.yml"
                break
            else
                echo "  ⚠️  Downloaded base file appears invalid, retrying..."
                rm -f docker-compose.yml
            fi
        else
            echo "  ⚠️  Download attempt $((retry_count + 1)) failed"
        fi

        retry_count=$((retry_count + 1))
        if [ $retry_count -lt $max_retries ]; then
            sleep 2
        fi
    done

    if [ $retry_count -ge $max_retries ]; then
        echo -e "${RED}❌ Failed to download base docker-compose.yml${NC}"
        echo "Please check your internet connection and try again."
        echo "Alternative: You can manually download from: $base_url"
        exit 1
    fi

    # Download production overrides docker-compose.prod.yml
    echo "  Downloading production overrides docker-compose.prod.yml..."
    retry_count=0
    local prod_url="https://raw.githubusercontent.com/davidamacey/OpenTranscribe/${encoded_branch}/docker-compose.prod.yml"

    while [ $retry_count -lt $max_retries ]; do
        if curl -fsSL --connect-timeout 10 --max-time 30 "$prod_url" -o docker-compose.prod.yml; then
            if [ -s docker-compose.prod.yml ] && grep -q "services:" docker-compose.prod.yml; then
                echo "  ✓ Downloaded production docker-compose.prod.yml"

                # Download optional gpu-scale overlay (non-fatal)
                download_gpu_scale_overlay

                echo "✓ Production docker-compose configuration complete"
                return 0
            else
                echo "  ⚠️  Downloaded prod file appears invalid, retrying..."
                rm -f docker-compose.prod.yml
            fi
        else
            echo "  ⚠️  Download attempt $((retry_count + 1)) failed"
        fi

        retry_count=$((retry_count + 1))
        if [ $retry_count -lt $max_retries ]; then
            sleep 2
        fi
    done

    echo -e "${RED}❌ Failed to download docker-compose.prod.yml${NC}"
    echo "Please check your internet connection and try again."
    echo "Alternative: You can manually download from: $prod_url"
    exit 1
}

download_gpu_scale_overlay() {
    # Optional: Download docker-compose.gpu-scale.yml for multi-GPU support
    # This is non-fatal - users can skip if they don't have multi-GPU setups
    echo "  Downloading optional docker-compose.gpu-scale.yml (multi-GPU support)..."

    local branch="${OPENTRANSCRIBE_BRANCH:-master}"
    local encoded_branch
    encoded_branch=$(echo "$branch" | sed 's|/|%2F|g')
    local gpu_scale_url="https://raw.githubusercontent.com/davidamacey/OpenTranscribe/${encoded_branch}/docker-compose.gpu-scale.yml"

    if curl -fsSL --connect-timeout 10 --max-time 30 "$gpu_scale_url" -o docker-compose.gpu-scale.yml 2>/dev/null; then
        if [ -s docker-compose.gpu-scale.yml ] && grep -q "celery-worker-gpu-scaled:" docker-compose.gpu-scale.yml; then
            echo "  ✓ Downloaded docker-compose.gpu-scale.yml (optional multi-GPU scaling)"
        else
            echo "  ⚠️  Downloaded gpu-scale file appears invalid, removing..."
            rm -f docker-compose.gpu-scale.yml
        fi
    else
        echo "  ℹ️  docker-compose.gpu-scale.yml not available (optional feature)"
    fi
}

download_management_script() {
    echo "✓ Downloading OpenTranscribe management script..."

    # Download the opentranscribe.sh script from the repository
    local max_retries=3
    local retry_count=0
    local branch="${OPENTRANSCRIBE_BRANCH:-master}"
    # URL-encode the branch name (replace / with %2F)
    local encoded_branch
    encoded_branch=$(echo "$branch" | sed 's|/|%2F|g')
    local download_url="https://raw.githubusercontent.com/davidamacey/OpenTranscribe/${encoded_branch}/opentranscribe.sh"

    while [ $retry_count -lt $max_retries ]; do
        if curl -fsSL --connect-timeout 10 --max-time 30 "$download_url" -o opentranscribe.sh; then
            # Validate downloaded file
            if [ -s opentranscribe.sh ] && grep -q "OpenTranscribe Management Script" opentranscribe.sh; then
                chmod +x opentranscribe.sh
                echo "✓ Downloaded and validated opentranscribe.sh"
                return 0
            else
                echo "⚠️  Downloaded opentranscribe.sh appears invalid, retrying..."
                rm -f opentranscribe.sh
            fi
        else
            echo "⚠️  Download attempt $((retry_count + 1)) failed"
        fi

        retry_count=$((retry_count + 1))
        if [ $retry_count -lt $max_retries ]; then
            echo "⏳ Retrying in 2 seconds..."
            sleep 2
        fi
    done

    echo -e "${YELLOW}⚠️  Failed to download opentranscribe.sh after $max_retries attempts${NC}"
    echo "You can manually download from: $download_url"
}

download_model_downloader_scripts() {
    echo "✓ Downloading model downloader scripts..."

    # Create scripts directory
    mkdir -p scripts

    # Download download-models.sh
    local max_retries=3
    local retry_count=0
    local branch="${OPENTRANSCRIBE_BRANCH:-master}"
    local encoded_branch
    encoded_branch=$(echo "$branch" | sed 's|/|%2F|g')
    local download_url="https://raw.githubusercontent.com/davidamacey/OpenTranscribe/${encoded_branch}/scripts/download-models.sh"

    while [ $retry_count -lt $max_retries ]; do
        if curl -fsSL --connect-timeout 10 --max-time 30 "$download_url" -o scripts/download-models.sh; then
            if [ -s scripts/download-models.sh ] && grep -q "OpenTranscribe Model Downloader" scripts/download-models.sh; then
                chmod +x scripts/download-models.sh
                echo "✓ Downloaded and validated download-models.sh"
                break
            else
                echo "⚠️  Downloaded download-models.sh appears invalid, retrying..."
                rm -f scripts/download-models.sh
            fi
        else
            echo "⚠️  Download attempt $((retry_count + 1)) failed"
        fi

        retry_count=$((retry_count + 1))
        if [ $retry_count -lt $max_retries ]; then
            echo "⏳ Retrying in 2 seconds..."
            sleep 2
        fi
    done

    # Download download-models.py
    retry_count=0
    download_url="https://raw.githubusercontent.com/davidamacey/OpenTranscribe/${encoded_branch}/scripts/download-models.py"

    while [ $retry_count -lt $max_retries ]; do
        if curl -fsSL --connect-timeout 10 --max-time 30 "$download_url" -o scripts/download-models.py; then
            if [ -s scripts/download-models.py ] && grep -q "Download all required AI models" scripts/download-models.py; then
                echo "✓ Downloaded and validated download-models.py"
                return 0
            else
                echo "⚠️  Downloaded download-models.py appears invalid, retrying..."
                rm -f scripts/download-models.py
            fi
        else
            echo "⚠️  Download attempt $((retry_count + 1)) failed"
        fi

        retry_count=$((retry_count + 1))
        if [ $retry_count -lt $max_retries ]; then
            echo "⏳ Retrying in 2 seconds..."
            sleep 2
        fi
    done

    echo -e "${YELLOW}⚠️  Failed to download model downloader scripts${NC}"
    echo "Models will be downloaded on first application run instead."
}

create_production_env_example() {
    echo "✓ Downloading environment configuration template..."

    # Download the official .env.example from the repository
    local max_retries=3
    local retry_count=0
    local branch="${OPENTRANSCRIBE_BRANCH:-master}"
    # URL-encode the branch name (replace / with %2F)
    local encoded_branch
    encoded_branch=$(echo "$branch" | sed 's|/|%2F|g')
    local download_url="https://raw.githubusercontent.com/davidamacey/OpenTranscribe/${encoded_branch}/.env.example"

    while [ $retry_count -lt $max_retries ]; do
        if curl -fsSL --connect-timeout 10 --max-time 30 "$download_url" -o .env.example; then
            # Validate downloaded file
            if [ -s .env.example ] && grep -q "POSTGRES_HOST" .env.example && grep -q "HUGGINGFACE_TOKEN" .env.example; then
                echo "✓ Downloaded and validated .env.example"
                return 0
            else
                echo "⚠️  Downloaded env file appears invalid, retrying..."
                rm -f .env.example
            fi
        else
            echo "⚠️  Download attempt $((retry_count + 1)) failed"
        fi

        retry_count=$((retry_count + 1))
        if [ $retry_count -lt $max_retries ]; then
            echo "⏳ Retrying in 2 seconds..."
            sleep 2
        fi
    done

    echo -e "${RED}❌ Failed to download .env.example file after $max_retries attempts${NC}"
    echo "Please check your internet connection and try again."
    echo "Alternative: You can manually download from:"
    echo "$download_url"
    exit 1
}

prompt_huggingface_token() {
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}🤗 HuggingFace Token Configuration${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${RED}⚠️  IMPORTANT: Token + Model Agreements REQUIRED!${NC}"
    echo ""
    echo "Without this token:"
    echo "  • Transcription will work normally"
    echo "  • Speaker diarization (who said what) will NOT work"
    echo "  • Models cannot be pre-downloaded (will download on first use)"
    echo ""
    echo -e "${CYAN}Step 1: Get your FREE HuggingFace token${NC}"
    echo "  1. Visit: https://huggingface.co/settings/tokens"
    echo "  2. Click 'New token'"
    echo "  3. Give it a name (e.g., 'OpenTranscribe')"
    echo "  4. Select 'Read' permissions"
    echo "  5. Copy the token"
    echo ""
    echo -e "${CYAN}Step 2: Accept BOTH gated model agreements (CRITICAL!)${NC}"
    echo -e "  ${RED}You MUST accept BOTH models or downloads will fail!${NC}"
    echo ""
    echo "  1. Segmentation Model:"
    echo "     https://huggingface.co/pyannote/segmentation-3.0"
    echo -e "     ${GREEN}→ Click 'Agree and access repository'${NC}"
    echo ""
    echo "  2. Speaker Diarization Model:"
    echo "     https://huggingface.co/pyannote/speaker-diarization-3.1"
    echo -e "     ${GREEN}→ Click 'Agree and access repository'${NC}"
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    # Ask if they want to enter token now
    read -p "Do you have a HuggingFace token to enter now? (Y/n) " -n 1 -r </dev/tty
    echo
    echo

    if [[ $REPLY =~ ^[Nn]$ ]]; then
        print_warning "Skipping HuggingFace token - you can add it later"
        echo "To add later:"
        echo "  1. Edit: $PROJECT_DIR/.env"
        echo "  2. Set: HUGGINGFACE_TOKEN=your_token_here"
        echo "  3. Restart: cd $PROJECT_DIR && ./opentranscribe.sh restart"
        echo ""
        HUGGINGFACE_TOKEN=""
        return 0
    fi

    # Prompt for token
    echo "Please enter your HuggingFace token:"
    echo "(Token will be hidden for security)"
    read -s HUGGINGFACE_TOKEN </dev/tty
    echo

    # Strip any 'HUGGINGFACE_TOKEN=' prefix if user pasted it
    HUGGINGFACE_TOKEN="${HUGGINGFACE_TOKEN#HUGGINGFACE_TOKEN=}"

    # Validate token format (basic check - should start with hf_)
    if [[ -z "$HUGGINGFACE_TOKEN" ]]; then
        print_warning "No token entered - you can add it later in .env file"
        HUGGINGFACE_TOKEN=""
    elif [[ ! "$HUGGINGFACE_TOKEN" =~ ^hf_ ]]; then
        print_warning "Token doesn't start with 'hf_' - this may not be valid"
        echo "Using it anyway, but verify it's correct."
        echo ""
    else
        print_success "HuggingFace token configured!"
        echo ""
    fi
}

configure_environment() {
    echo -e "${BLUE}⚙️  Configuring environment...${NC}"

    if [ -f .env ]; then
        echo "ℹ️  Using existing .env file"
        return
    fi

    # Generate all secure secrets using openssl or python3 fallback
    echo "🔒 Generating secure credentials..."

    if command -v openssl &> /dev/null; then
        # Use openssl for cryptographically secure random generation
        POSTGRES_PASSWORD=$(openssl rand -hex 32)
        MINIO_ROOT_PASSWORD=$(openssl rand -hex 32)
        JWT_SECRET=$(openssl rand -hex 64)
        # ENCRYPTION_KEY: Add prefix to make it invalid base64, forcing backend exception handler path
        # This ensures backend uses the working derive-from-string logic
        ENCRYPTION_KEY="opentranscribe_$(openssl rand -base64 48)"
        REDIS_PASSWORD=$(openssl rand -hex 32)
        OPENSEARCH_PASSWORD=$(openssl rand -hex 32)
    elif command -v python3 &> /dev/null; then
        # Fallback to Python's secrets module
        POSTGRES_PASSWORD=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        MINIO_ROOT_PASSWORD=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(64))")
        # ENCRYPTION_KEY: Add prefix to force backend exception handler path
        ENCRYPTION_KEY=$(python3 -c "import secrets, base64; print('opentranscribe_' + base64.b64encode(secrets.token_bytes(48)).decode())")
        REDIS_PASSWORD=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        OPENSEARCH_PASSWORD=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    else
        # Basic fallback (not recommended for production)
        POSTGRES_PASSWORD="postgres_$(date +%s)_$(shuf -i 10000-99999 -n 1 2>/dev/null || echo $RANDOM)"
        MINIO_ROOT_PASSWORD="minio_$(date +%s)_$(shuf -i 10000-99999 -n 1 2>/dev/null || echo $RANDOM)"
        JWT_SECRET="jwt_secret_$(date +%s)_$(shuf -i 10000-99999 -n 1 2>/dev/null || echo $RANDOM)"
        ENCRYPTION_KEY="encryption_key_$(date +%s)_$(shuf -i 10000-99999 -n 1 2>/dev/null || echo $RANDOM)"
        REDIS_PASSWORD="redis_$(date +%s)_$(shuf -i 10000-99999 -n 1 2>/dev/null || echo $RANDOM)"
        OPENSEARCH_PASSWORD="opensearch_$(date +%s)_$(shuf -i 10000-99999 -n 1 2>/dev/null || echo $RANDOM)"
        echo "⚠️  Using basic secrets - install openssl or python3 for cryptographically secure generation"
    fi

    print_success "Secure credentials generated (64-char JWT/encryption, 32-char passwords)"

    # Prompt for HuggingFace token
    prompt_huggingface_token

    # Model selection based on hardware
    select_whisper_model

    # GPU selection for multi-GPU systems
    select_gpu_device

    # LLM configuration for AI features
    configure_llm_settings

    # Create .env file
    create_env_file
}

select_whisper_model() {
    echo -e "${YELLOW}🎤 Selecting Whisper Model based on hardware...${NC}"
    echo ""

    # Auto-select optimal model based on hardware with GPU memory detection
    local RECOMMENDED_MODEL=""
    local RECOMMENDATION_REASON=""

    case "$DETECTED_DEVICE" in
        "cuda")
            # Try to detect GPU memory for better model selection
            if command -v nvidia-smi &> /dev/null; then
                GPU_MEMORY=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits -i "${GPU_DEVICE_ID:-0}")
                if [[ $GPU_MEMORY -gt 16000 ]]; then
                    RECOMMENDED_MODEL="large-v2"
                    RECOMMENDATION_REASON="High-end GPU detected (${GPU_MEMORY}MB VRAM)"
                elif [[ $GPU_MEMORY -gt 8000 ]]; then
                    RECOMMENDED_MODEL="large-v2"
                    RECOMMENDATION_REASON="Mid-range GPU detected (${GPU_MEMORY}MB VRAM)"
                elif [[ $GPU_MEMORY -gt 4000 ]]; then
                    RECOMMENDED_MODEL="medium"
                    RECOMMENDATION_REASON="Entry-level GPU detected (${GPU_MEMORY}MB VRAM)"
                else
                    RECOMMENDED_MODEL="small"
                    RECOMMENDATION_REASON="Low-memory GPU detected (${GPU_MEMORY}MB VRAM)"
                fi
            else
                # Fallback if nvidia-smi fails
                RECOMMENDED_MODEL="medium"
                RECOMMENDATION_REASON="CUDA detected - safe default"
            fi
            ;;
        "mps")
            RECOMMENDED_MODEL="small"
            RECOMMENDATION_REASON="Apple Silicon detected - optimized for CPU/MPS processing"
            ;;
        "cpu")
            RECOMMENDED_MODEL="base"
            RECOMMENDATION_REASON="CPU processing - fastest option"
            ;;
    esac

    # Display recommendation
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
    echo "Note: Larger models provide better accuracy but require more memory"
    echo "      and processing time. You can change this later in the .env file."
    echo ""

    # Prompt user for model selection
    while true; do
        read -p "Select model (tiny/base/small/medium/large-v2) [${RECOMMENDED_MODEL}]: " user_model </dev/tty

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
                echo -e "${RED}Invalid model. Please choose: tiny, base, small, medium, or large-v2${NC}"
                ;;
        esac
    done

    echo ""
    echo -e "${GREEN}✓ Selected model: ${WHISPER_MODEL}${NC}"
    if [ "$WHISPER_MODEL" != "$RECOMMENDED_MODEL" ]; then
        echo -e "${YELLOW}  Note: You selected a different model than recommended${NC}"
    fi
    echo ""
}

select_gpu_device() {
    # Only prompt if CUDA is detected and multiple GPUs are available
    if [[ "$DETECTED_DEVICE" != "cuda" ]] || [[ ${GPU_COUNT:-0} -le 1 ]]; then
        return 0
    fi

    echo ""
    echo -e "${YELLOW}🎮 Multiple GPUs Detected${NC}"
    echo "================================================="
    echo "Your system has ${GPU_COUNT} NVIDIA GPUs available."
    echo ""
    echo "Available GPUs:"
    echo ""

    # Display GPU list with detailed information
    nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader | while IFS=, read -r idx name mem_total mem_free; do
        echo "  [${idx}] ${name} (${mem_total} total, ${mem_free} free)"
    done

    echo ""
    echo "Select which GPU to use for AI model downloads and transcription processing."
    echo "Consider GPU availability, memory, and existing workloads when choosing."
    echo ""

    # Prompt user for GPU selection
    while true; do
        read -p "Enter GPU index to use [0-$((GPU_COUNT-1))] (default: ${GPU_DEVICE_ID}): " selected_gpu </dev/tty

        # Use default if empty
        if [[ -z "$selected_gpu" ]]; then
            selected_gpu=$GPU_DEVICE_ID
            break
        fi

        # Validate input is a number
        if ! [[ "$selected_gpu" =~ ^[0-9]+$ ]]; then
            echo -e "${RED}❌ Invalid input. Please enter a number.${NC}"
            continue
        fi

        # Validate GPU index is within range
        if [[ $selected_gpu -ge 0 && $selected_gpu -lt $GPU_COUNT ]]; then
            break
        else
            echo -e "${RED}❌ Invalid GPU index. Please enter a number between 0 and $((GPU_COUNT-1)).${NC}"
        fi
    done

    # Update GPU_DEVICE_ID with user selection
    GPU_DEVICE_ID=$selected_gpu

    # Get selected GPU details
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits -i "$GPU_DEVICE_ID")
    GPU_MEMORY=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits -i "$GPU_DEVICE_ID")

    echo ""
    echo -e "${GREEN}✓ Selected GPU ${GPU_DEVICE_ID}: ${GPU_NAME} (${GPU_MEMORY}MB)${NC}"
    echo ""
}

configure_llm_settings() {
    echo ""
    echo -e "${YELLOW}🤖 LLM Configuration for AI Features${NC}"
    echo "=================================================="
    echo "OpenTranscribe includes AI features that require an LLM (Large Language Model):"
    echo "  • AI-powered transcript summarization with BLUF format"
    echo "  • Speaker identification suggestions"
    echo ""
    echo -e "${BLUE}Supported LLM Providers:${NC}"
    echo "1. vLLM (Default) - Local server with OpenAI-compatible API"
    echo "2. OpenAI - Official OpenAI API (requires API key)"
    echo "3. Ollama - Local Ollama server"
    echo "4. Anthropic Claude - Claude API (requires API key)"
    echo "5. OpenRouter - Multi-provider API service"
    echo ""
    echo -e "${YELLOW}💡 Configuration Options:${NC}"
    echo "• Configure now (recommended for vLLM users)"
    echo "• Skip configuration (you can set up later in .env file)"
    echo ""

    read -p "Do you want to configure LLM settings now? (y/N) " -n 1 -r </dev/tty
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        echo "Select your LLM provider:"
        echo "1) vLLM (Local server - recommended)"
        echo "2) OpenAI"
        echo "3) Ollama"
        echo "4) Anthropic Claude"
        echo "5) OpenRouter"
        echo "6) Skip (configure manually later)"

        read -p "Enter your choice (1-6): " -n 1 -r llm_choice </dev/tty
        echo
        echo

        case $llm_choice in
            1)
                echo "✓ Configuring vLLM (Local server)"
                LLM_PROVIDER="vllm"
                read -p "Enter your vLLM server URL [http://localhost:8000/v1]: " vllm_url </dev/tty
                VLLM_BASE_URL=${vllm_url:-"http://localhost:8000/v1"}
                read -p "Enter your vLLM API key (optional): " vllm_key </dev/tty
                VLLM_API_KEY=${vllm_key:-""}
                read -p "Enter your model name [gpt-oss]: " vllm_model </dev/tty
                VLLM_MODEL_NAME=${vllm_model:-"gpt-oss"}
                echo "✓ vLLM configured: $VLLM_BASE_URL with model $VLLM_MODEL_NAME"
                ;;
            2)
                echo "✓ Configuring OpenAI"
                LLM_PROVIDER="openai"
                read -p "Enter your OpenAI API key: " openai_key </dev/tty
                OPENAI_API_KEY=$openai_key
                read -p "Enter OpenAI model [gpt-4o-mini]: " openai_model </dev/tty
                OPENAI_MODEL_NAME=${openai_model:-"gpt-4o-mini"}
                echo "✓ OpenAI configured with model $OPENAI_MODEL_NAME"
                ;;
            3)
                echo "✓ Configuring Ollama"
                LLM_PROVIDER="ollama"
                read -p "Enter your Ollama server URL [http://localhost:11434]: " ollama_url </dev/tty
                OLLAMA_BASE_URL=${ollama_url:-"http://localhost:11434"}
                read -p "Enter Ollama model [llama2:7b-chat]: " ollama_model </dev/tty
                OLLAMA_MODEL_NAME=${ollama_model:-"llama2:7b-chat"}
                echo "✓ Ollama configured: $OLLAMA_BASE_URL with model $OLLAMA_MODEL_NAME"
                ;;
            4)
                echo "✓ Configuring Anthropic Claude"
                LLM_PROVIDER="anthropic"
                read -p "Enter your Anthropic API key: " anthropic_key </dev/tty
                ANTHROPIC_API_KEY=$anthropic_key
                read -p "Enter Claude model [claude-3-haiku-20240307]: " anthropic_model </dev/tty
                ANTHROPIC_MODEL_NAME=${anthropic_model:-"claude-3-haiku-20240307"}
                echo "✓ Anthropic Claude configured with model $ANTHROPIC_MODEL_NAME"
                ;;
            5)
                echo "✓ Configuring OpenRouter"
                LLM_PROVIDER="openrouter"
                read -p "Enter your OpenRouter API key: " openrouter_key </dev/tty
                OPENROUTER_API_KEY=$openrouter_key
                read -p "Enter OpenRouter model [anthropic/claude-3-haiku]: " openrouter_model </dev/tty
                OPENROUTER_MODEL_NAME=${openrouter_model:-"anthropic/claude-3-haiku"}
                echo "✓ OpenRouter configured with model $OPENROUTER_MODEL_NAME"
                ;;
            6|*)
                echo "⏭️  Skipping LLM configuration - you can configure manually in .env file"
                LLM_PROVIDER="vllm"  # Default
                ;;
        esac
    else
        echo "⏭️  Skipping LLM configuration - you can configure manually in .env file"
        echo "💡 Edit the LLM_* variables in .env file to enable AI features"
        LLM_PROVIDER="vllm"  # Default
    fi

    echo ""
    echo -e "${YELLOW}💡 LLM Configuration Notes:${NC}"
    echo "• AI features require a working LLM endpoint"
    echo "• You can change providers anytime by editing .env file"
    echo "• See .env.example for all available configuration options"
}

create_env_file() {
    echo "✓ Creating .env file with optimized settings..."

    # Copy example and update values
    cp .env.example .env

    # Update security credentials (auto-generated)
    sed -i.bak "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$POSTGRES_PASSWORD|g" .env
    sed -i.bak "s|MINIO_ROOT_PASSWORD=.*|MINIO_ROOT_PASSWORD=$MINIO_ROOT_PASSWORD|g" .env
    sed -i.bak "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$JWT_SECRET|g" .env
    sed -i.bak "s|ENCRYPTION_KEY=.*|ENCRYPTION_KEY=$ENCRYPTION_KEY|g" .env
    sed -i.bak "s|REDIS_PASSWORD=.*|REDIS_PASSWORD=$REDIS_PASSWORD|g" .env
    sed -i.bak "s|OPENSEARCH_PASSWORD=.*|OPENSEARCH_PASSWORD=$OPENSEARCH_PASSWORD|g" .env

    # Update AI model configuration
    sed -i.bak "s|HUGGINGFACE_TOKEN=.*|HUGGINGFACE_TOKEN=$HUGGINGFACE_TOKEN|g" .env
    sed -i.bak "s|WHISPER_MODEL=.*|WHISPER_MODEL=$WHISPER_MODEL|g" .env
    sed -i.bak "s|BATCH_SIZE=.*|BATCH_SIZE=$BATCH_SIZE|g" .env
    sed -i.bak "s|COMPUTE_TYPE=.*|COMPUTE_TYPE=$COMPUTE_TYPE|g" .env

    # Update LLM configuration
    if [[ -n "$LLM_PROVIDER" ]]; then
        sed -i.bak "s|LLM_PROVIDER=.*|LLM_PROVIDER=$LLM_PROVIDER|g" .env
    fi

    # Provider-specific configurations
    if [[ "$LLM_PROVIDER" == "vllm" && -n "$VLLM_BASE_URL" ]]; then
        sed -i.bak "s|VLLM_BASE_URL=.*|VLLM_BASE_URL=$VLLM_BASE_URL|g" .env
        if [[ -n "$VLLM_API_KEY" ]]; then
            sed -i.bak "s|VLLM_API_KEY=.*|VLLM_API_KEY=$VLLM_API_KEY|g" .env
        fi
        if [[ -n "$VLLM_MODEL_NAME" ]]; then
            sed -i.bak "s|VLLM_MODEL_NAME=.*|VLLM_MODEL_NAME=$VLLM_MODEL_NAME|g" .env
        fi
    elif [[ "$LLM_PROVIDER" == "openai" && -n "$OPENAI_API_KEY" ]]; then
        sed -i.bak "s|# OPENAI_API_KEY=.*|OPENAI_API_KEY=$OPENAI_API_KEY|g" .env
        if [[ -n "$OPENAI_MODEL_NAME" ]]; then
            sed -i.bak "s|# OPENAI_MODEL_NAME=.*|OPENAI_MODEL_NAME=$OPENAI_MODEL_NAME|g" .env
        fi
    elif [[ "$LLM_PROVIDER" == "ollama" && -n "$OLLAMA_BASE_URL" ]]; then
        sed -i.bak "s|# OLLAMA_BASE_URL=.*|OLLAMA_BASE_URL=$OLLAMA_BASE_URL|g" .env
        if [[ -n "$OLLAMA_MODEL_NAME" ]]; then
            sed -i.bak "s|# OLLAMA_MODEL_NAME=.*|OLLAMA_MODEL_NAME=$OLLAMA_MODEL_NAME|g" .env
        fi
    elif [[ "$LLM_PROVIDER" == "anthropic" && -n "$ANTHROPIC_API_KEY" ]]; then
        sed -i.bak "s|# ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY|g" .env
        if [[ -n "$ANTHROPIC_MODEL_NAME" ]]; then
            sed -i.bak "s|# ANTHROPIC_MODEL_NAME=.*|ANTHROPIC_MODEL_NAME=$ANTHROPIC_MODEL_NAME|g" .env
        fi
    elif [[ "$LLM_PROVIDER" == "openrouter" && -n "$OPENROUTER_API_KEY" ]]; then
        sed -i.bak "s|# OPENROUTER_API_KEY=.*|OPENROUTER_API_KEY=$OPENROUTER_API_KEY|g" .env
        if [[ -n "$OPENROUTER_MODEL_NAME" ]]; then
            sed -i.bak "s|# OPENROUTER_MODEL_NAME=.*|OPENROUTER_MODEL_NAME=$OPENROUTER_MODEL_NAME|g" .env
        fi
    fi

    # Hardware-specific configurations
    case "$DETECTED_DEVICE" in
        "cuda")
            sed -i.bak "s|USE_GPU=.*|USE_GPU=true|g" .env
            sed -i.bak "s|GPU_DEVICE_ID=.*|GPU_DEVICE_ID=${GPU_DEVICE_ID:-0}|g" .env
            sed -i.bak "s|TORCH_DEVICE=.*|TORCH_DEVICE=cuda|g" .env
            ;;
        "mps")
            sed -i.bak "s|USE_GPU=.*|USE_GPU=false|g" .env
            sed -i.bak "s|TORCH_DEVICE=.*|TORCH_DEVICE=mps|g" .env
            ;;
        "cpu")
            sed -i.bak "s|USE_GPU=.*|USE_GPU=false|g" .env
            sed -i.bak "s|TORCH_DEVICE=.*|TORCH_DEVICE=cpu|g" .env
            ;;
    esac

    # Set model cache directory
    MODEL_CACHE_DIR="${MODEL_CACHE_DIR:-./models}"
    sed -i.bak "s|MODEL_CACHE_DIR=.*|MODEL_CACHE_DIR=$MODEL_CACHE_DIR|g" .env

    # Add Docker runtime configuration
    echo "" >> .env
    echo "# Hardware Configuration (Auto-detected)" >> .env
    echo "DETECTED_DEVICE=${DETECTED_DEVICE}" >> .env
    echo "USE_NVIDIA_RUNTIME=${USE_GPU_RUNTIME}" >> .env

    # Note: INIT_DB_PATH uses default ./database/init_db.sql from .env.example
    # All deployment methods now use the same standardized path

    # Clean up backup file
    rm -f .env.bak

    echo "✓ Environment configured for $DETECTED_DEVICE with $COMPUTE_TYPE precision"
}

#######################
# MODEL DOWNLOADING
#######################

download_ai_models() {
    print_header "AI Model Pre-Download"

    echo "OpenTranscribe requires AI models (~2.5GB) for transcription and speaker diarization."
    echo ""
    echo "Configuration summary:"
    echo "  • Hardware: $DETECTED_DEVICE ($COMPUTE_TYPE precision)"
    echo "  • Whisper Model: $WHISPER_MODEL"
    echo "  • HuggingFace Token: $([[ -n "$HUGGINGFACE_TOKEN" ]] && echo "✓ Configured" || echo "✗ Not configured")"
    echo ""

    # If HuggingFace token not set, offer one more chance to enter it
    if [ -z "$HUGGINGFACE_TOKEN" ]; then
        print_warning "HuggingFace token not configured"
        echo ""
        echo "Without a token, speaker diarization will not work and models cannot be pre-downloaded."
        echo ""
        echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${RED}REMINDER: You need BOTH steps completed:${NC}"
        echo "  1. HuggingFace token (Read permissions)"
        echo "  2. Accept BOTH gated model agreements:"
        echo "     • https://huggingface.co/pyannote/segmentation-3.0"
        echo "     • https://huggingface.co/pyannote/speaker-diarization-3.1"
        echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
        read -p "Would you like to enter your HuggingFace token now? (y/N) " -n 1 -r </dev/tty
        echo
        echo

        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Please enter your HuggingFace token:"
            echo "(Token will be hidden for security)"
            read -s HUGGINGFACE_TOKEN </dev/tty
            echo

            # Strip any 'HUGGINGFACE_TOKEN=' prefix if user pasted it
            HUGGINGFACE_TOKEN="${HUGGINGFACE_TOKEN#HUGGINGFACE_TOKEN=}"

            # Validate and update .env file
            if [[ -n "$HUGGINGFACE_TOKEN" ]]; then
                # Update the token in .env file
                sed -i.bak "s|HUGGINGFACE_TOKEN=.*|HUGGINGFACE_TOKEN=$HUGGINGFACE_TOKEN|g" .env
                rm -f .env.bak

                if [[ "$HUGGINGFACE_TOKEN" =~ ^hf_ ]]; then
                    print_success "HuggingFace token configured and saved to .env!"
                    echo ""
                    echo -e "${YELLOW}⚠️  FINAL REMINDER:${NC} Ensure you accepted BOTH model agreements:"
                    echo "   • pyannote/segmentation-3.0"
                    echo "   • pyannote/speaker-diarization-3.1"
                    echo ""
                else
                    print_warning "Token doesn't start with 'hf_' - this may not be valid"
                    echo "Continuing anyway..."
                    echo ""
                fi
            else
                print_warning "No token entered - skipping model pre-download"
                echo ""
                HUGGINGFACE_TOKEN=""
            fi
        fi
    fi

    # If still no token, skip download
    if [ -z "$HUGGINGFACE_TOKEN" ]; then
        print_info "Skipping model pre-download"
        echo ""
        echo "Models will be downloaded automatically when you first run the application."
        echo "This will cause a 10-30 minute delay on first use."
        echo ""
        echo "To pre-download models later:"
        echo "  1. Add your HuggingFace token to .env file"
        echo "  2. Run: cd $PROJECT_DIR && bash scripts/download-models.sh"
        echo ""
        read -p "Press Enter to continue setup..." -r </dev/tty
        echo
        return 0
    fi

    # Token is configured - proceed with download
    echo -e "${YELLOW}Ready to download AI models (~2.5GB)${NC}"
    echo "This will take 10-30 minutes depending on your internet speed."
    echo ""
    read -p "Start model download now? (Y/n) " -n 1 -r </dev/tty
    echo
    echo

    if [[ $REPLY =~ ^[Nn]$ ]]; then
        print_info "Skipping model pre-download"
        echo "Models will be downloaded automatically when you first run the application."
        echo ""
        echo "To download models later, run:"
        echo "  cd $PROJECT_DIR && bash scripts/download-models.sh"
        echo ""
        return 0
    fi

    # Check if scripts exist
    if [ ! -f "scripts/download-models.sh" ]; then
        print_warning "Model download script not found - skipping pre-download"
        echo "Models will be downloaded automatically when you first run the application."
        echo ""
        return 0
    fi

    print_info "Starting model download..."
    echo ""

    # Export necessary environment variables
    export HUGGINGFACE_TOKEN
    export WHISPER_MODEL
    export COMPUTE_TYPE
    export DETECTED_DEVICE
    export GPU_DEVICE_ID

    # Create models directory structure with proper permissions
    print_info "Creating model cache directories with proper permissions..."

    # Create main directory and subdirectories
    mkdir -p models/huggingface models/torch models/nltk_data models/sentence-transformers

    # Set ownership to prevent permission issues in non-root containers
    # Container runs as UID 1000, so we need to ensure host directories are accessible
    if [ "$(id -u)" -eq 0 ]; then
        # Running as root - explicitly set ownership to UID 1000 for container compatibility
        echo "  Detected root user - setting ownership to UID 1000 for container compatibility"
        chown -R 1000:1000 models
    else
        # Running as regular user - ensure current user owns the directories
        current_uid=$(id -u)
        current_gid=$(id -g)
        echo "  Setting ownership to current user (UID:GID $current_uid:$current_gid)"
        chown -R "$current_uid:$current_gid" models 2>/dev/null || true
    fi

    # Set proper permissions (755 for directories)
    chmod -R 755 models

    # Verify directories are writable
    if [ -w models/huggingface ] && [ -w models/torch ] && [ -w models/nltk_data ] && [ -w models/sentence-transformers ]; then
        echo "✓ Model cache directories created with proper permissions"
    else
        print_warning "Model directories exist but may not be writable"
        echo "  If you encounter permission errors, run: ./scripts/fix-model-permissions.sh"
    fi

    # Run the download script and capture exit status
    # Important: Use || true to prevent script exit on download failure
    set +e  # Temporarily disable exit on error
    bash scripts/download-models.sh models
    local download_exit_code=$?
    set -e  # Re-enable exit on error

    echo ""

    # Check download result and provide clear feedback
    if [ $download_exit_code -eq 0 ]; then
        print_success "✨ Models downloaded and cached successfully!"
        print_info "Docker containers will start with models ready to use"
        echo ""
        return 0
    else
        print_error "⚠️  ⚠️  CRITICAL: Model download failed"
        echo ""
        echo -e "${RED}╔══════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║  WITHOUT PYANNOTE MODELS, TRANSCRIPTION WILL NOT WORK!           ║${NC}"
        echo -e "${RED}╚══════════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${YELLOW}What this means:${NC}"
        echo -e "  ${RED}• The transcription pipeline REQUIRES speaker diarization models${NC}"
        echo -e "  ${RED}• Without PyAnnote models, ALL transcriptions will FAIL${NC}"
        echo "  • Models will auto-download on first use (10-30 minute delay)"
        echo "  • First transcription attempt may fail if models can't download"
        echo ""
        echo -e "${YELLOW}Most common cause: Missing gated model access${NC}"
        echo "  You likely have NOT accepted BOTH PyAnnote model agreements"
        echo ""
        echo -e "${CYAN}To fix before starting:${NC}"
        echo "  1. Accept both model agreements (URLs shown above)"
        echo "  2. Wait 1-2 minutes for permissions to propagate"
        echo "  3. Run: cd $PROJECT_DIR && bash scripts/download-models.sh models"
        echo ""
        echo -e "${YELLOW}Or continue and fix later:${NC}"
        echo "  • Models will download when you first transcribe a file"
        echo "  • Ensure you've accepted model agreements before first use"
        echo ""

        # Ask if user wants to continue or abort with default to NO
        read -p "Continue setup WITHOUT models? (y/N): " continue_choice </dev/tty
        if [[ ! $continue_choice =~ ^[Yy]$ ]]; then
            print_error "Setup aborted - please fix model access and run setup again"
            echo ""
            echo "Quick fix steps:"
            echo "  1. Accept: https://huggingface.co/pyannote/segmentation-3.0"
            echo "  2. Accept: https://huggingface.co/pyannote/speaker-diarization-3.1"
            echo "  3. Wait 1-2 minutes"
            echo "  4. Run setup again"
            exit 1
        fi

        print_warning "⚠️  Continuing WITHOUT models - transcription will not work until models download"
        echo ""
        return 0  # Return success to allow setup to continue
    fi
}



#######################
# FINAL VALIDATION
#######################

validate_setup() {
    echo -e "${BLUE}✅ Validating setup...${NC}"

    # Check required files
    local required_files=(".env" "docker-compose.yml" "docker-compose.prod.yml" "opentranscribe.sh" "database/init_db.sql")
    for file in "${required_files[@]}"; do
        if [ -f "$file" ]; then
            echo "✓ $file exists"
        else
            echo -e "${RED}❌ $file missing${NC}"
            echo "Required file not found: $file"
            exit 1
        fi
    done

    # Validate Docker Compose (use production overlay) - now that .env exists
    echo "Validating Docker Compose configuration with .env file..."

    # For one-line installation, build contexts (./backend, ./frontend) don't exist
    # since we're using pre-built images from Docker Hub. We'll check if the
    # configuration can be parsed and validated for image-only deployment.
    local compose_error
    compose_error=$(docker compose -f docker-compose.yml -f docker-compose.prod.yml config 2>&1)
    local exit_code=$?

    # Check for specific errors vs warnings
    if [ $exit_code -eq 0 ]; then
        echo "✓ Docker Compose configuration valid (with .env file)"
    elif echo "$compose_error" | grep -q "build context.*does not exist"; then
        # Build contexts don't exist - this is expected for one-line installation
        echo "✓ Docker Compose configuration valid (using pre-built images)"
        echo "  Note: Build contexts not present (expected for Docker Hub deployment)"
    else
        # Real configuration error
        echo -e "${RED}❌ Docker Compose configuration validation failed${NC}"
        echo -e "${YELLOW}Error details:${NC}"
        echo "$compose_error" | head -15
        echo ""
        echo "This usually means:"
        echo "  1. Missing or invalid environment variables in .env"
        echo "  2. Syntax errors in docker-compose files"
        echo "  3. Missing required files referenced in docker-compose"
        echo "  4. Missing database/init_db.sql file"
        echo ""
        read -p "Continue setup anyway? (y/N) " -n 1 -r </dev/tty
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
        echo "⚠️  Continuing with potentially invalid configuration..."
    fi

    echo "✓ Setup validation complete"
}

pull_docker_images() {
    print_header "Pulling Latest Docker Images"

    print_info "Pulling latest OpenTranscribe container images..."
    print_info "This ensures you have the newest features and fixes"
    echo ""

    # Pull images explicitly to ensure latest versions (use production overlay)
    if docker compose -f docker-compose.yml -f docker-compose.prod.yml pull; then
        print_success "Docker images pulled successfully"
        return 0
    else
        print_warning "Failed to pull some images - will use cached versions"
        print_info "You can manually pull images later with: docker compose -f docker-compose.yml -f docker-compose.prod.yml pull"
        return 1
    fi
}

display_summary() {
    echo ""
    echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}🎉  OpenTranscribe Setup Complete!${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
    echo ""

    # Configuration Summary (show first, above the fold)
    echo -e "${BLUE}📋 Configuration Summary${NC}"
    echo "┌─ Hardware:"
    echo "│  • Platform: $DETECTED_PLATFORM ($ARCH)"
    echo "│  • Device: $DETECTED_DEVICE ($COMPUTE_TYPE precision)"
    if [[ "$DETECTED_DEVICE" == "cuda" ]]; then
        if command -v nvidia-smi &> /dev/null; then
            GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits -i "${GPU_DEVICE_ID:-0}" 2>/dev/null || echo "Unknown")
            GPU_MEMORY=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits -i "${GPU_DEVICE_ID:-0}" 2>/dev/null || echo "Unknown")
            echo "│  • GPU: $GPU_NAME (${GPU_MEMORY}MB) [Device ID: ${GPU_DEVICE_ID:-0}]"
        fi
    fi
    echo "│"
    echo "└─ Application:"
    echo "   • Whisper Model: $WHISPER_MODEL"
    echo "   • Speaker Diarization: $([[ -n "$HUGGINGFACE_TOKEN" ]] && echo "✅ Enabled" || echo "⚠️  Not configured")"
    echo "   • LLM Provider: ${LLM_PROVIDER:-vllm}"
    echo "   • Project Location: $PROJECT_DIR"
    echo ""

    # QUICK START section (show last so users see it without scrolling)
    echo ""
    echo -e "${YELLOW}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║  🚀  QUICK START - Get Up and Running Now!      ║${NC}"
    echo -e "${YELLOW}╚══════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${GREEN}1. Navigate to the project directory:${NC}"
    echo -e "   ${BLUE}cd $PROJECT_DIR${NC}"
    echo ""
    echo -e "${GREEN}2. Start OpenTranscribe:${NC}"
    echo -e "   ${BLUE}./opentranscribe.sh start${NC}"
    echo ""
    echo -e "${GREEN}3. Wait 30-60 seconds for services to initialize${NC}"
    echo ""
    echo -e "${GREEN}4. Open your browser and visit:${NC}"
    echo -e "   ${BLUE}http://localhost:${FRONTEND_PORT:-5173}${NC}"
    echo ""
    echo -e "${GREEN}5. Login with default credentials:${NC}"
    echo -e "   Email:    ${BLUE}admin@example.com${NC}"
    echo -e "   Password: ${BLUE}password${NC}"
    echo -e "   ${RED}⚠️  Change password after first login!${NC}"
    echo ""
    echo -e "${YELLOW}════════════════════════════════════════════════════${NC}"
    echo ""

    # Access URLs
    echo -e "${BLUE}🌐 Service URLs (after starting)${NC}"
    echo "  • Web Interface:     http://localhost:${FRONTEND_PORT:-5173}"
    echo "  • API Documentation: http://localhost:${BACKEND_PORT:-5174}/docs"
    echo "  • Task Monitor:      http://localhost:${FLOWER_PORT:-5175}/flower"
    echo "  • MinIO Console:     http://localhost:${MINIO_CONSOLE_PORT:-5179}"
    echo ""

    # Management commands
    echo -e "${BLUE}📚 Useful Management Commands${NC}"
    echo -e "  ${BLUE}./opentranscribe.sh status${NC}  - Check service status"
    echo -e "  ${BLUE}./opentranscribe.sh logs${NC}    - View logs (Ctrl+C to exit)"
    echo -e "  ${BLUE}./opentranscribe.sh restart${NC} - Restart all services"
    echo -e "  ${BLUE}./opentranscribe.sh stop${NC}    - Stop all services"
    echo -e "  ${BLUE}./opentranscribe.sh help${NC}    - Show all commands"
    echo ""

    # Optional setup notices (collapsed, less prominent)
    if [[ -z "$HUGGINGFACE_TOKEN" ]]; then
        echo -e "${YELLOW}💡 Optional: Enable Speaker Diarization${NC}"
        echo "   To identify who said what in transcripts:"
        echo "   1. Get free token: https://huggingface.co/settings/tokens"
        echo "   2. Edit .env file: HUGGINGFACE_TOKEN=your_token_here"
        echo "   3. Run: ./opentranscribe.sh restart"
        echo ""
    fi

    if [[ -z "$VLLM_BASE_URL" && "$LLM_PROVIDER" == "vllm" ]]; then
        echo -e "${YELLOW}💡 Optional: Enable AI Summarization${NC}"
        echo "   To get AI-powered transcript summaries:"
        echo "   1. Set up LLM server (vLLM, Ollama, OpenAI, etc.)"
        echo "   2. Edit .env file and configure LLM_* variables"
        echo "   3. Run: ./opentranscribe.sh restart"
        echo ""
    fi

    if [[ "$DETECTED_DEVICE" == "cuda" && "$DOCKER_RUNTIME" != "nvidia" ]]; then
        echo -e "${YELLOW}⚠️  Note: NVIDIA GPU detected but runtime not fully configured${NC}"
        echo "   If you experience GPU issues:"
        echo "   https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
        echo ""
    fi
}

#######################
# MAIN EXECUTION
#######################

main() {
    # Run setup steps
    detect_platform
    check_dependencies
    check_network_connectivity
    configure_docker_runtime
    setup_project_directory
    create_configuration_files
    configure_environment
    download_ai_models
    validate_setup
    pull_docker_images
    display_summary
}

# Execute main function
main
