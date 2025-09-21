#!/bin/bash
set -e

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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
        read -p "Do you want to continue anyway? (y/N) " -n 1 -r
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
    
    # Validate init_db_complete.sql
    if [ ! -f "init_db_complete.sql" ]; then
        echo -e "${RED}❌ init_db_complete.sql file not found${NC}"
        return 1
    fi
    
    # Check file size (should be substantial)
    local db_size=$(wc -c < init_db_complete.sql)
    if [ "$db_size" -lt 10000 ]; then
        echo -e "${RED}❌ init_db_complete.sql file too small ($db_size bytes)${NC}"
        return 1
    fi
    
    # Check for essential database content including admin user
    if ! grep -q "CREATE TABLE.*user" init_db_complete.sql || ! grep -q "CREATE TABLE.*media_file" init_db_complete.sql || ! grep -q "admin@example.com" init_db_complete.sql; then
        echo -e "${RED}❌ init_db_complete.sql missing essential database tables or admin user${NC}"
        return 1
    fi
    
    echo "✓ init_db_complete.sql validated ($db_size bytes)"
    
    # Validate docker-compose.yml
    if [ ! -f "docker-compose.yml" ]; then
        echo -e "${RED}❌ docker-compose.yml file not found${NC}"
        return 1
    fi
    
    # Check docker-compose syntax
    if ! docker compose -f docker-compose.yml config > /dev/null 2>&1; then
        echo -e "${RED}❌ docker-compose.yml syntax validation failed${NC}"
        return 1
    fi
    
    # Check for essential services
    if ! grep -q "backend:" docker-compose.yml || ! grep -q "frontend:" docker-compose.yml; then
        echo -e "${RED}❌ docker-compose.yml missing essential services${NC}"
        return 1
    fi
    
    echo "✓ docker-compose.yml validated"
    echo "✓ All downloaded files validated successfully"
    return 0
}

check_network_connectivity() {
    echo "🌐 Checking network connectivity..."
    
    # Test connectivity to GitHub
    if ! curl -fsSL --connect-timeout 5 --max-time 10 "https://api.github.com" > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Warning: Unable to connect to GitHub${NC}"
        echo "Please check your internet connection before proceeding."
        echo "The setup script requires internet access to download configuration files."
        echo ""
        read -p "Do you want to continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Setup cancelled. Please check your network connection and try again."
            exit 1
        fi
    else
        echo "✓ Network connectivity verified"
    fi
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
    
    # Download the official init_db.sql from the repository
    local max_retries=3
    local retry_count=0
    local branch="${OPENTRANSCRIBE_BRANCH:-master}"
    # URL-encode the branch name (replace / with %2F)
    local encoded_branch=$(echo "$branch" | sed 's|/|%2F|g')
    local download_url="https://raw.githubusercontent.com/davidamacey/OpenTranscribe/${encoded_branch}/database/init_db_complete.sql"
    
    while [ $retry_count -lt $max_retries ]; do
        if curl -fsSL --connect-timeout 10 --max-time 30 "$download_url" -o init_db_complete.sql; then
            # Validate downloaded file
            if [ -s init_db_complete.sql ] && grep -q "CREATE TABLE" init_db_complete.sql && grep -q "admin@example.com" init_db_complete.sql; then
                echo "✓ Downloaded and validated init_db_complete.sql"
                return 0
            else
                echo "⚠️  Downloaded file appears invalid, retrying..."
                rm -f init_db_complete.sql
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
    
    # Download NVIDIA override file if GPU detected
    if [[ "$USE_GPU_RUNTIME" == "true" && "$DETECTED_DEVICE" == "cuda" ]]; then
        download_nvidia_override
    fi
    
    # Create .env.example
    create_production_env_example
}

create_production_compose() {
    echo "✓ Downloading production docker-compose configuration..."
    
    # Download the official production compose file from the repository
    local max_retries=3
    local retry_count=0
    local branch="${OPENTRANSCRIBE_BRANCH:-master}"
    # URL-encode the branch name (replace / with %2F)  
    local encoded_branch=$(echo "$branch" | sed 's|/|%2F|g')
    local download_url="https://raw.githubusercontent.com/davidamacey/OpenTranscribe/${encoded_branch}/docker-compose.prod.yml"
    
    while [ $retry_count -lt $max_retries ]; do
        if curl -fsSL --connect-timeout 10 --max-time 30 "$download_url" -o docker-compose.yml; then
            # Validate downloaded file
            if [ -s docker-compose.yml ] && grep -q "version:" docker-compose.yml && grep -q "services:" docker-compose.yml; then
                echo "✓ Downloaded and validated production docker-compose.yml"
                return 0
            else
                echo "⚠️  Downloaded compose file appears invalid, retrying..."
                rm -f docker-compose.yml
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
    
    echo -e "${RED}❌ Failed to download docker-compose configuration after $max_retries attempts${NC}"
    echo "Please check your internet connection and try again."
    echo "Alternative: You can manually download from:"
    echo "$download_url"
    exit 1
}

download_nvidia_override() {
    echo "✓ Downloading NVIDIA GPU override configuration..."
    
    # Download the NVIDIA override file from the repository
    local max_retries=3
    local retry_count=0
    local branch="${OPENTRANSCRIBE_BRANCH:-master}"
    # URL-encode the branch name (replace / with %2F)
    local encoded_branch=$(echo "$branch" | sed 's|/|%2F|g')
    local download_url="https://raw.githubusercontent.com/davidamacey/OpenTranscribe/${encoded_branch}/docker-compose.nvidia.yml"
    
    while [ $retry_count -lt $max_retries ]; do
        if curl -fsSL --connect-timeout 10 --max-time 30 "$download_url" -o docker-compose.nvidia.yml; then
            # Validate downloaded file
            if [ -s docker-compose.nvidia.yml ] && grep -q "runtime: nvidia" docker-compose.nvidia.yml; then
                echo "✓ Downloaded and validated docker-compose.nvidia.yml"
                return 0
            else
                echo "⚠️  Downloaded NVIDIA override file appears invalid, retrying..."
                rm -f docker-compose.nvidia.yml
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
    
    echo -e "${YELLOW}⚠️  Failed to download NVIDIA override file after $max_retries attempts${NC}"
    echo "GPU acceleration may not work optimally, but CPU processing will still function."
    echo "You can manually download from: $download_url"
}

create_production_env_example() {
    echo "✓ Downloading environment configuration template..."
    
    # Download the official .env.example from the repository
    local max_retries=3
    local retry_count=0
    local branch="${OPENTRANSCRIBE_BRANCH:-master}"
    # URL-encode the branch name (replace / with %2F)
    local encoded_branch=$(echo "$branch" | sed 's|/|%2F|g')
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

configure_environment() {
    echo -e "${BLUE}⚙️  Configuring environment...${NC}"
    
    if [ -f .env ]; then
        echo "ℹ️  Using existing .env file"
        return
    fi
    
    # Generate secure JWT secret
    if command -v openssl &> /dev/null; then
        JWT_SECRET=$(openssl rand -hex 32)
    elif command -v python3 &> /dev/null; then
        JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    else
        JWT_SECRET="change_this_in_production_$(date +%s)"
        echo "⚠️  Using basic JWT secret - consider generating a secure one"
    fi
    
    # Display HuggingFace token instructions
    echo ""
    echo -e "${YELLOW}🤗 HuggingFace Token Configuration${NC}"
    echo "================================================="
    echo -e "${RED}⚠️  IMPORTANT: A HuggingFace token is REQUIRED for speaker diarization!${NC}"
    echo ""
    echo "Without this token, the application will only do transcription (no speaker identification)."
    echo ""
    echo "To get your FREE token:"
    echo "1. Go to: https://huggingface.co/settings/tokens"
    echo "2. Click 'New token'"
    echo "3. Give it a name (e.g., 'OpenTranscribe')"
    echo "4. Select 'Read' permissions"
    echo "5. Copy the token"
    echo "6. Edit the .env file after setup and add: HUGGINGFACE_TOKEN=your_token_here"
    echo ""
    echo -e "${YELLOW}💡 You can add your token later by editing the .env file${NC}"
    echo ""
    
    # Set empty token for now - user will add it manually
    HUGGINGFACE_TOKEN=""
    
    # Model selection based on hardware
    select_whisper_model
    
    # LLM configuration for AI features
    configure_llm_settings
    
    # Create .env file
    create_env_file
}

select_whisper_model() {
    echo -e "${YELLOW}🎤 Auto-selecting Whisper Model based on hardware...${NC}"
    
    # Auto-select optimal model based on hardware with GPU memory detection
    case "$DETECTED_DEVICE" in
        "cuda")
            # Try to detect GPU memory for better model selection
            if command -v nvidia-smi &> /dev/null; then
                GPU_MEMORY=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
                if [[ $GPU_MEMORY -gt 16000 ]]; then
                    WHISPER_MODEL="large-v2"
                    echo "✓ High-end GPU detected (${GPU_MEMORY}MB) - selecting large-v2 model"
                elif [[ $GPU_MEMORY -gt 8000 ]]; then
                    WHISPER_MODEL="large-v2"
                    echo "✓ Mid-range GPU detected (${GPU_MEMORY}MB) - selecting large-v2 model"
                elif [[ $GPU_MEMORY -gt 4000 ]]; then
                    WHISPER_MODEL="medium"
                    echo "✓ Entry-level GPU detected (${GPU_MEMORY}MB) - selecting medium model"
                else
                    WHISPER_MODEL="small"
                    echo "✓ Low-memory GPU detected (${GPU_MEMORY}MB) - selecting small model"
                fi
            else
                # Fallback if nvidia-smi fails
                WHISPER_MODEL="medium"
                echo "✓ CUDA detected - selecting medium model (safe default)"
            fi
            ;;
        "mps")
            WHISPER_MODEL="small"
            echo "✓ Apple Silicon detected - selecting small model for faster CPU processing"
            echo "  Note: WhisperX will use CPU for compatibility, PyAnnote will use MPS acceleration"
            echo "  Tip: Edit WHISPER_MODEL in .env to 'tiny' for even faster processing"
            ;;
        "cpu")
            WHISPER_MODEL="base"
            echo "✓ CPU processing - selecting base model (fastest for CPU)"
            ;;
    esac
    
    echo "✓ Selected model: $WHISPER_MODEL"
    echo "💡 You can change this later by editing WHISPER_MODEL in the .env file"
    echo "   Available options: tiny, base, small, medium, large-v2"
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
    
    read -p "Do you want to configure LLM settings now? (y/N) " -n 1 -r
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
        
        read -p "Enter your choice (1-6): " -n 1 -r llm_choice
        echo
        echo
        
        case $llm_choice in
            1)
                echo "✓ Configuring vLLM (Local server)"
                LLM_PROVIDER="vllm"
                read -p "Enter your vLLM server URL [http://localhost:8000/v1]: " vllm_url
                VLLM_BASE_URL=${vllm_url:-"http://localhost:8000/v1"}
                read -p "Enter your vLLM API key (optional): " vllm_key
                VLLM_API_KEY=${vllm_key:-""}
                read -p "Enter your model name [gpt-oss]: " vllm_model
                VLLM_MODEL_NAME=${vllm_model:-"gpt-oss"}
                echo "✓ vLLM configured: $VLLM_BASE_URL with model $VLLM_MODEL_NAME"
                ;;
            2)
                echo "✓ Configuring OpenAI"
                LLM_PROVIDER="openai"
                read -p "Enter your OpenAI API key: " openai_key
                OPENAI_API_KEY=$openai_key
                read -p "Enter OpenAI model [gpt-4o-mini]: " openai_model
                OPENAI_MODEL_NAME=${openai_model:-"gpt-4o-mini"}
                echo "✓ OpenAI configured with model $OPENAI_MODEL_NAME"
                ;;
            3)
                echo "✓ Configuring Ollama"
                LLM_PROVIDER="ollama"
                read -p "Enter your Ollama server URL [http://localhost:11434]: " ollama_url
                OLLAMA_BASE_URL=${ollama_url:-"http://localhost:11434"}
                read -p "Enter Ollama model [llama2:7b-chat]: " ollama_model
                OLLAMA_MODEL_NAME=${ollama_model:-"llama2:7b-chat"}
                echo "✓ Ollama configured: $OLLAMA_BASE_URL with model $OLLAMA_MODEL_NAME"
                ;;
            4)
                echo "✓ Configuring Anthropic Claude"
                LLM_PROVIDER="anthropic"
                read -p "Enter your Anthropic API key: " anthropic_key
                ANTHROPIC_API_KEY=$anthropic_key
                read -p "Enter Claude model [claude-3-haiku-20240307]: " anthropic_model
                ANTHROPIC_MODEL_NAME=${anthropic_model:-"claude-3-haiku-20240307"}
                echo "✓ Anthropic Claude configured with model $ANTHROPIC_MODEL_NAME"
                ;;
            5)
                echo "✓ Configuring OpenRouter"
                LLM_PROVIDER="openrouter"
                read -p "Enter your OpenRouter API key: " openrouter_key
                OPENROUTER_API_KEY=$openrouter_key
                read -p "Enter OpenRouter model [anthropic/claude-3-haiku]: " openrouter_model
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
    
    # Update configuration values
    sed -i.bak "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$JWT_SECRET|g" .env
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
    
    # Add Docker runtime configuration
    echo "" >> .env
    echo "# Hardware Configuration (Auto-detected)" >> .env
    echo "DETECTED_DEVICE=${DETECTED_DEVICE}" >> .env
    echo "USE_NVIDIA_RUNTIME=${USE_GPU_RUNTIME}" >> .env
    
    # Clean up backup file
    rm -f .env.bak
    
    echo "✓ Environment configured for $DETECTED_DEVICE with $COMPUTE_TYPE precision"
}


#######################
# STARTUP SCRIPT CREATION
#######################

create_management_script() {
    echo -e "${BLUE}📝 Creating management script...${NC}"
    
    cat > opentranscribe.sh << 'EOF'
#!/bin/bash
set -e

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

function show_help {
    echo -e "${BLUE}OpenTranscribe Management Script${NC}"
    echo ""
    echo "Usage: ./opentranscribe.sh [command]"
    echo ""
    echo "Commands:"
    echo "  start       Start all services"
    echo "  stop        Stop all services"
    echo "  restart     Restart all services"
    echo "  status      Show container status"
    echo "  logs [svc]  View logs (all or specific service)"
    echo "  update      Pull latest Docker images"
    echo "  clean       Remove all volumes and data (⚠️ CAUTION)"
    echo "  shell [svc] Open shell in container (default: backend)"
    echo "  config      Show current configuration"
    echo "  health      Check service health"
    echo "  help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./opentranscribe.sh start"
    echo "  ./opentranscribe.sh logs backend"
    echo "  ./opentranscribe.sh shell backend"
    echo ""
}

check_environment() {
    if [ ! -f .env ]; then
        echo -e "${RED}❌ .env file not found${NC}"
        echo "Please run the setup script first."
        exit 1
    fi
    
    if [ ! -f docker-compose.yml ]; then
        echo -e "${RED}❌ docker-compose.yml not found${NC}"
        echo "Please run the setup script first."
        exit 1
    fi
}

get_compose_files() {
    local compose_files="-f docker-compose.yml"
    
    # Add NVIDIA override if it exists and GPU is detected
    if [ -f docker-compose.nvidia.yml ] && [ -f .env ]; then
        source .env 2>/dev/null || true
        if [[ "${USE_NVIDIA_RUNTIME:-false}" == "true" ]]; then
            compose_files="$compose_files -f docker-compose.nvidia.yml"
        fi
    fi
    
    # Add development override if it exists
    if [ -f docker-compose.override.yml ]; then
        compose_files="$compose_files -f docker-compose.override.yml"
    fi
    
    echo "$compose_files"
}

show_access_info() {
    # Source .env to get port values
    source .env 2>/dev/null || true
    
    echo -e "${GREEN}🌐 Access Information:${NC}"
    echo "  • Web Interface:     http://localhost:${FRONTEND_PORT:-5173}"
    echo "  • API Documentation: http://localhost:${BACKEND_PORT:-5174}/docs"
    echo "  • API Endpoint:      http://localhost:${BACKEND_PORT:-5174}/api"
    echo "  • Flower Dashboard:  http://localhost:${FLOWER_PORT:-5175}/flower"
    echo "  • MinIO Console:     http://localhost:${MINIO_CONSOLE_PORT:-5179}"
    echo ""
    echo -e "${YELLOW}⏳ Please wait a moment for all services to initialize...${NC}"
}

case "${1:-help}" in
    start)
        check_environment
        echo -e "${YELLOW}🚀 Starting OpenTranscribe...${NC}"
        compose_files=$(get_compose_files)
        docker compose $compose_files up -d
        echo -e "${GREEN}✅ OpenTranscribe started!${NC}"
        show_access_info
        ;;
    stop)
        check_environment
        echo -e "${YELLOW}🛑 Stopping OpenTranscribe...${NC}"
        compose_files=$(get_compose_files)
        docker compose $compose_files down
        echo -e "${GREEN}✅ OpenTranscribe stopped${NC}"
        ;;
    restart)
        check_environment
        echo -e "${YELLOW}🔄 Restarting OpenTranscribe...${NC}"
        compose_files=$(get_compose_files)
        docker compose $compose_files down
        docker compose $compose_files up -d
        echo -e "${GREEN}✅ OpenTranscribe restarted!${NC}"
        show_access_info
        ;;
    status)
        check_environment
        echo -e "${BLUE}📊 Container Status:${NC}"
        compose_files=$(get_compose_files)
        docker compose $compose_files ps
        ;;
    logs)
        check_environment
        service=${2:-}
        compose_files=$(get_compose_files)
        
        if [ -z "$service" ]; then
            echo -e "${BLUE}📋 Showing all logs (Ctrl+C to exit):${NC}"
            docker compose $compose_files logs -f
        else
            echo -e "${BLUE}📋 Showing logs for $service (Ctrl+C to exit):${NC}"
            docker compose $compose_files logs -f "$service"
        fi
        ;;
    update)
        check_environment
        echo -e "${YELLOW}📥 Updating to latest images...${NC}"
        compose_files=$(get_compose_files)
        docker compose $compose_files down
        docker compose $compose_files pull
        docker compose $compose_files up -d
        echo -e "${GREEN}✅ OpenTranscribe updated!${NC}"
        show_access_info
        ;;
    clean)
        check_environment
        echo -e "${RED}⚠️  WARNING: This will remove ALL data including transcriptions!${NC}"
        read -p "Are you sure you want to continue? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}🗑️  Removing all data...${NC}"
            compose_files=$(get_compose_files)
            docker compose $compose_files down -v
            docker system prune -f
            echo -e "${GREEN}✅ All data removed${NC}"
        else
            echo -e "${GREEN}✅ Operation cancelled${NC}"
        fi
        ;;
    shell)
        check_environment
        service=${2:-backend}
        echo -e "${BLUE}🔧 Opening shell in $service container...${NC}"
        compose_files=$(get_compose_files)
        docker compose $compose_files exec "$service" /bin/bash || docker compose $compose_files exec "$service" /bin/sh
        ;;
    config)
        check_environment
        echo -e "${BLUE}⚙️  Current Configuration:${NC}"
        echo "Environment file (.env):"
        grep -E "^[A-Z]" .env | head -20
        echo ""
        echo "Docker Compose configuration:"
        if docker compose config > /dev/null 2>&1; then
            echo "  ✅ Valid"
        else
            echo "  ❌ Invalid"
        fi
        ;;
    health)
        check_environment
        echo -e "${BLUE}🩺 Health Check:${NC}"
        
        # Check container status
        echo "Container Status:"
        compose_files=$(get_compose_files)
        docker compose $compose_files ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"
        
        echo ""
        echo "Service Health:"
        
        # Source .env to get port values
        source .env 2>/dev/null || true
        
        # Backend health
        if curl -s http://localhost:${BACKEND_PORT:-5174}/health > /dev/null 2>&1; then
            echo "  ✅ Backend: Healthy"
        else
            echo "  ❌ Backend: Unhealthy"
        fi
        
        # Frontend health  
        if curl -s http://localhost:${FRONTEND_PORT:-5173} > /dev/null 2>&1; then
            echo "  ✅ Frontend: Healthy"
        else
            echo "  ❌ Frontend: Unhealthy"
        fi
        
        # Database health
        if docker compose $compose_files exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
            echo "  ✅ Database: Healthy"
        else
            echo "  ❌ Database: Unhealthy"
        fi
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}❌ Unknown command: $1${NC}"
        show_help
        exit 1
        ;;
esac
EOF

    chmod +x opentranscribe.sh
    echo "✓ Created management script: opentranscribe.sh"
}

#######################
# FINAL VALIDATION
#######################

validate_setup() {
    echo -e "${BLUE}✅ Validating setup...${NC}"
    
    # Check required files
    local required_files=(".env" "docker-compose.yml" "opentranscribe.sh")
    for file in "${required_files[@]}"; do
        if [ -f "$file" ]; then
            echo "✓ $file exists"
        else
            echo -e "${RED}❌ $file missing${NC}"
            exit 1
        fi
    done
    
    # Validate Docker Compose
    if docker compose config &> /dev/null; then
        echo "✓ Docker Compose configuration valid"
    else
        echo -e "${RED}❌ Docker Compose configuration invalid${NC}"
        exit 1
    fi
    
    echo "✓ Setup validation complete"
}

display_summary() {
    echo ""
    echo -e "${GREEN}🎉 OpenTranscribe Setup Complete!${NC}"
    echo ""
    echo -e "${BLUE}📋 Hardware Configuration Summary:${NC}"
    echo "  • Platform: $DETECTED_PLATFORM ($ARCH)"
    echo "  • Device: $DETECTED_DEVICE"
    echo "  • Compute Type: $COMPUTE_TYPE"
    echo "  • Batch Size: $BATCH_SIZE"
    echo "  • Docker Runtime: ${DOCKER_RUNTIME:-default}"
    
    if [[ "$DETECTED_DEVICE" == "cuda" ]]; then
        echo "  • GPU Device ID: ${GPU_DEVICE_ID:-0}"
        if command -v nvidia-smi &> /dev/null; then
            GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits | head -1)
            echo "  • GPU: $GPU_NAME"
        fi
    fi
    
    echo ""
    echo -e "${BLUE}📋 Application Configuration:${NC}"
    echo "  • Whisper Model: $WHISPER_MODEL"
    echo "  • Speaker Diarization: $([[ -n "$HUGGINGFACE_TOKEN" ]] && echo "Enabled" || echo "Disabled")"
    echo "  • LLM Provider: ${LLM_PROVIDER:-vllm} (for AI summarization)"
    echo "  • Project Directory: $PROJECT_DIR"
    echo ""
    
    echo -e "${YELLOW}🚀 To start OpenTranscribe:${NC}"
    echo "  cd $PROJECT_DIR"
    echo "  ./opentranscribe.sh start"
    echo ""
    
    echo -e "${RED}⚠️  Speaker Diarization Setup Required${NC}"
    echo "To enable speaker identification:"
    echo "1. Get a free token at: https://huggingface.co/settings/tokens"
    echo "2. Edit the .env file and add: HUGGINGFACE_TOKEN=your_token_here"
    echo "3. Restart the application: ./opentranscribe.sh restart"
    echo ""
    
    if [[ -z "$VLLM_BASE_URL" && "$LLM_PROVIDER" == "vllm" ]]; then
        echo -e "${YELLOW}🤖 LLM Setup for AI Features${NC}"
        echo "To enable AI summarization and speaker identification:"
        echo "1. Set up your LLM server (vLLM, Ollama, etc.)"
        echo "2. Edit the .env file and configure LLM_* variables"
        echo "3. Restart the application: ./opentranscribe.sh restart"
        echo ""
    fi
    
    if [[ "$DETECTED_DEVICE" == "cuda" && "$DOCKER_RUNTIME" != "nvidia" ]]; then
        echo -e "${YELLOW}💡 Note: NVIDIA GPU detected but runtime not configured${NC}"
        echo "If you experience GPU issues, check NVIDIA Container Toolkit installation:"
        echo "https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
        echo ""
    fi
    
    echo -e "${GREEN}🌐 Access URLs (after starting):${NC}"
    echo "  • Web Interface: http://localhost:${FRONTEND_PORT:-5173}"
    echo "  • API Documentation: http://localhost:${BACKEND_PORT:-5174}/docs"
    echo "  • Task Monitor: http://localhost:${FLOWER_PORT:-5175}/flower"
    echo "  • MinIO Console: http://localhost:${MINIO_CONSOLE_PORT:-5179}"
    echo ""
    echo -e "${GREEN}🔐 Default Admin Login:${NC}"
    echo "  • Email: admin@example.com"
    echo "  • Password: password"
    echo "  • Change password after first login!"
    echo ""
    echo -e "${GREEN}📚 Management Commands:${NC}"
    echo "  • ./opentranscribe.sh help    # Show all commands"
    echo "  • ./opentranscribe.sh status  # Check service status"
    echo "  • ./opentranscribe.sh logs    # View logs"
    echo "  • ./opentranscribe.sh health  # Check service health"
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
    create_management_script
    validate_setup
    display_summary
}

# Execute main function
main