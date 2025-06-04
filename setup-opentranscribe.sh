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
    
    # Detect OS
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        DETECTED_PLATFORM="linux"
        echo "✓ Detected: Linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        DETECTED_PLATFORM="macos"
        echo "✓ Detected: macOS"
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        DETECTED_PLATFORM="windows"
        echo "✓ Detected: Windows (WSL/Cygwin)"
    else
        DETECTED_PLATFORM="unknown"
        echo "⚠️  Unknown platform: $OSTYPE"
    fi
    
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

configure_docker_runtime() {
    echo -e "${BLUE}🐳 Configuring Docker runtime...${NC}"
    
    if [[ "$USE_GPU_RUNTIME" == "true" && "$DETECTED_DEVICE" == "cuda" ]]; then
        # Check for NVIDIA Container Toolkit
        if docker run --rm --gpus all nvidia/cuda:11.8-base-ubuntu22.04 nvidia-smi &> /dev/null; then
            echo "✓ NVIDIA Container Toolkit detected and working"
            DOCKER_RUNTIME="nvidia"
        else
            echo -e "${RED}❌ NVIDIA Container Toolkit not detected${NC}"
            echo "Install with: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
            echo "Falling back to CPU mode..."
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
# DEPENDENCY CHECKS
#######################

check_dependencies() {
    echo -e "${BLUE}📋 Checking dependencies...${NC}"
    
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

download_configuration_files() {
    echo -e "${BLUE}📥 Downloading configuration files...${NC}"
    
    # Base URL for raw files
    BASE_URL="https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master"
    
    # Download unified docker-compose configuration
    if curl -fsSL "$BASE_URL/docker-compose.unified.yml" -o docker-compose.yml; then
        echo "✓ Downloaded unified docker-compose.yml"
    else
        echo -e "${RED}❌ Failed to download docker-compose.yml${NC}"
        echo "Falling back to production compose file..."
        if curl -fsSL "$BASE_URL/docker-compose.prod.yml" -o docker-compose.yml; then
            echo "✓ Downloaded fallback docker-compose.yml"
        else
            echo -e "${RED}❌ Failed to download any docker-compose configuration${NC}"
            exit 1
        fi
    fi
    
    # Download .env.example
    if curl -fsSL "$BASE_URL/.env.example" -o .env.example; then
        echo "✓ Downloaded .env.example"
    else
        echo -e "${RED}❌ Failed to download .env.example${NC}"
        exit 1
    fi
    
    # Download override configuration for development
    if curl -fsSL "$BASE_URL/docker-compose.override.yml" -o docker-compose.override.yml; then
        echo "✓ Downloaded docker-compose.override.yml"
    else
        echo "⚠️  Could not download override file (optional)"
    fi
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
    
    # Get HuggingFace token
    echo -e "${YELLOW}🤗 HuggingFace Configuration${NC}"
    echo "A HuggingFace token is REQUIRED for speaker diarization."
    echo "Get your token at: https://huggingface.co/settings/tokens"
    read -p "Enter your HuggingFace token (press Enter to skip): " HUGGINGFACE_TOKEN
    
    # Model selection based on hardware
    select_whisper_model
    
    # Create .env file
    create_env_file
    
    # Configure Docker Compose for hardware
    configure_docker_compose
}

select_whisper_model() {
    echo -e "${YELLOW}🎤 Whisper Model Selection${NC}"
    echo "Recommended model based on your hardware ($DETECTED_DEVICE):"
    
    case "$DETECTED_DEVICE" in
        "cuda")
            echo "1) large-v2 - Best quality (recommended for CUDA, requires 10GB+ VRAM)"
            echo "2) medium   - Good quality (requires 5GB+ VRAM)"
            echo "3) small    - Decent quality (requires 2GB+ VRAM)"
            echo "4) base     - Basic quality"
            DEFAULT_MODEL="large-v2"
            ;;
        "mps")
            echo "1) medium   - Good quality (recommended for Apple Silicon)"
            echo "2) small    - Decent quality (faster)"
            echo "3) base     - Basic quality (fastest)"
            echo "4) large-v2 - Best quality (may be slow)"
            DEFAULT_MODEL="medium"
            ;;
        "cpu")
            echo "1) base     - Basic quality (recommended for CPU)"
            echo "2) small    - Decent quality (slower)"
            echo "3) medium   - Good quality (much slower)"
            echo "4) large-v2 - Best quality (very slow)"
            DEFAULT_MODEL="base"
            ;;
    esac
    
    read -p "Select model (1-4) [default: $DEFAULT_MODEL]: " MODEL_CHOICE
    
    case "$MODEL_CHOICE" in
        1)
            case "$DETECTED_DEVICE" in
                "cuda") WHISPER_MODEL="large-v2" ;;
                "mps") WHISPER_MODEL="medium" ;;
                "cpu") WHISPER_MODEL="base" ;;
            esac
            ;;
        2)
            case "$DETECTED_DEVICE" in
                "cuda") WHISPER_MODEL="medium" ;;
                "mps") WHISPER_MODEL="small" ;;
                "cpu") WHISPER_MODEL="small" ;;
            esac
            ;;
        3)
            case "$DETECTED_DEVICE" in
                "cuda") WHISPER_MODEL="small" ;;
                "mps") WHISPER_MODEL="base" ;;
                "cpu") WHISPER_MODEL="medium" ;;
            esac
            ;;
        4)
            case "$DETECTED_DEVICE" in
                "cuda") WHISPER_MODEL="base" ;;
                "mps") WHISPER_MODEL="large-v2" ;;
                "cpu") WHISPER_MODEL="large-v2" ;;
            esac
            ;;
        *)
            WHISPER_MODEL="$DEFAULT_MODEL"
            ;;
    esac
    
    echo "✓ Selected model: $WHISPER_MODEL"
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
    
    # Clean up backup file
    rm -f .env.bak
    
    echo "✓ Environment configured for $DETECTED_DEVICE with $COMPUTE_TYPE precision"
}

configure_docker_compose() {
    echo "✓ Configuring Docker Compose for $DETECTED_DEVICE..."
    
    # The unified docker-compose.yml already handles all platforms automatically
    # Just ensure environment variables are properly set for Docker Compose
    
    if [[ "$DETECTED_DEVICE" == "cuda" && "$USE_GPU_RUNTIME" == "true" ]]; then
        # Create additional environment variables for GPU configuration
        cat >> .env << EOF

# GPU Configuration (Auto-detected)
DOCKER_RUNTIME=nvidia
TARGETPLATFORM=linux/amd64
BACKEND_DOCKERFILE=Dockerfile.multiplatform
EOF
        echo "✓ Docker Compose configured for NVIDIA GPU runtime"
    elif [[ "$DETECTED_DEVICE" == "mps" ]]; then
        # Apple Silicon configuration
        cat >> .env << EOF

# Apple Silicon Configuration (Auto-detected)
DOCKER_RUNTIME=
TARGETPLATFORM=linux/arm64
BACKEND_DOCKERFILE=Dockerfile.multiplatform
EOF
        echo "✓ Docker Compose configured for Apple Silicon"
    else
        # CPU configuration
        cat >> .env << EOF

# CPU Configuration (Auto-detected)
DOCKER_RUNTIME=
TARGETPLATFORM=linux/amd64
BACKEND_DOCKERFILE=Dockerfile.multiplatform
EOF
        echo "✓ Docker Compose configured for CPU processing"
    fi
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

show_access_info() {
    echo -e "${GREEN}🌐 Access Information:${NC}"
    echo "  • Web Interface:     http://localhost:5173"
    echo "  • API Documentation: http://localhost:8080/docs"
    echo "  • API Endpoint:      http://localhost:8080/api"
    echo "  • Flower Dashboard:  http://localhost:5555/flower"
    echo "  • MinIO Console:     http://localhost:9091"
    echo ""
    echo -e "${YELLOW}⏳ Please wait a moment for all services to initialize...${NC}"
}

case "${1:-help}" in
    start)
        check_environment
        echo -e "${YELLOW}🚀 Starting OpenTranscribe...${NC}"
        # Use override file if it exists for development features
        if [ -f docker-compose.override.yml ]; then
            docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
        else
            docker compose up -d
        fi
        echo -e "${GREEN}✅ OpenTranscribe started!${NC}"
        show_access_info
        ;;
    stop)
        check_environment
        echo -e "${YELLOW}🛑 Stopping OpenTranscribe...${NC}"
        if [ -f docker-compose.override.yml ]; then
            docker compose -f docker-compose.yml -f docker-compose.override.yml down
        else
            docker compose down
        fi
        echo -e "${GREEN}✅ OpenTranscribe stopped${NC}"
        ;;
    restart)
        check_environment
        echo -e "${YELLOW}🔄 Restarting OpenTranscribe...${NC}"
        if [ -f docker-compose.override.yml ]; then
            docker compose -f docker-compose.yml -f docker-compose.override.yml down
            docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
        else
            docker compose down
            docker compose up -d
        fi
        echo -e "${GREEN}✅ OpenTranscribe restarted!${NC}"
        show_access_info
        ;;
    status)
        check_environment
        echo -e "${BLUE}📊 Container Status:${NC}"
        if [ -f docker-compose.override.yml ]; then
            docker compose -f docker-compose.yml -f docker-compose.override.yml ps
        else
            docker compose ps
        fi
        ;;
    logs)
        check_environment
        service=${2:-}
        COMPOSE_CMD="docker compose"
        if [ -f docker-compose.override.yml ]; then
            COMPOSE_CMD="docker compose -f docker-compose.yml -f docker-compose.override.yml"
        fi
        
        if [ -z "$service" ]; then
            echo -e "${BLUE}📋 Showing all logs (Ctrl+C to exit):${NC}"
            $COMPOSE_CMD logs -f
        else
            echo -e "${BLUE}📋 Showing logs for $service (Ctrl+C to exit):${NC}"
            $COMPOSE_CMD logs -f "$service"
        fi
        ;;
    update)
        check_environment
        echo -e "${YELLOW}📥 Updating to latest images...${NC}"
        if [ -f docker-compose.override.yml ]; then
            docker compose -f docker-compose.yml -f docker-compose.override.yml down
            docker compose -f docker-compose.yml -f docker-compose.override.yml pull
            docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
        else
            docker compose down
            docker compose pull
            docker compose up -d
        fi
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
            docker compose down -v
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
        docker compose exec "$service" /bin/bash || docker compose exec "$service" /bin/sh
        ;;
    config)
        check_environment
        echo -e "${BLUE}⚙️  Current Configuration:${NC}"
        echo "Environment file (.env):"
        grep -E "^[A-Z]" .env | head -20
        echo ""
        echo "Hardware Detection:"
        docker compose exec backend python -c "
from app.utils.hardware_detection import detect_hardware
config = detect_hardware()
for key, value in config.get_summary().items():
    print(f'  {key}: {value}')
" 2>/dev/null || echo "  Backend not running - start services first"
        ;;
    health)
        check_environment
        echo -e "${BLUE}🩺 Health Check:${NC}"
        
        # Check container status
        echo "Container Status:"
        docker compose ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"
        
        echo ""
        echo "Service Health:"
        
        # Backend health
        if curl -s http://localhost:8080/health > /dev/null 2>&1; then
            echo "  ✅ Backend: Healthy"
        else
            echo "  ❌ Backend: Unhealthy"
        fi
        
        # Frontend health  
        if curl -s http://localhost:5173 > /dev/null 2>&1; then
            echo "  ✅ Frontend: Healthy"
        else
            echo "  ❌ Frontend: Unhealthy"
        fi
        
        # Database health
        if docker compose exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
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
    echo -e "${BLUE}📋 Configuration Summary:${NC}"
    echo "  • Platform: $DETECTED_PLATFORM"
    echo "  • Device: $DETECTED_DEVICE"
    echo "  • Compute Type: $COMPUTE_TYPE"
    echo "  • Batch Size: $BATCH_SIZE"
    echo "  • Whisper Model: $WHISPER_MODEL"
    echo "  • Docker Runtime: $DOCKER_RUNTIME"
    echo ""
    echo -e "${YELLOW}🚀 To start OpenTranscribe:${NC}"
    echo "  cd $PROJECT_DIR"
    echo "  ./opentranscribe.sh start"
    echo ""
    
    if [[ -z "$HUGGINGFACE_TOKEN" ]]; then
        echo -e "${RED}⚠️  Warning: No HuggingFace token provided${NC}"
        echo "Speaker diarization will not work without a token."
        echo "Add your token to the .env file before starting."
        echo ""
    fi
    
    if [[ "$DETECTED_DEVICE" == "cuda" && "$USE_GPU_RUNTIME" == "false" ]]; then
        echo -e "${YELLOW}💡 Note: NVIDIA GPU detected but Container Toolkit not available${NC}"
        echo "Install NVIDIA Container Toolkit for GPU acceleration:"
        echo "https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
        echo ""
    fi
    
    echo -e "${GREEN}📚 For help: ./opentranscribe.sh help${NC}"
    echo -e "${GREEN}🔧 For debugging: ./opentranscribe.sh logs${NC}"
}

#######################
# MAIN EXECUTION
#######################

main() {
    # Run setup steps
    detect_platform
    check_dependencies
    configure_docker_runtime
    setup_project_directory
    download_configuration_files
    configure_environment
    create_management_script
    validate_setup
    display_summary
}

# Execute main function
main