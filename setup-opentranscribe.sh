#!/bin/bash
set -e

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}OpenTranscribe Setup Script${NC}"
echo "This script will set up OpenTranscribe using Docker Hub images"
echo ""

# Check for Docker and Docker Compose
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker is not installed. Please install Docker first.${NC}"
    echo "Visit https://docs.docker.com/get-docker/ for installation instructions."
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo -e "${RED}Docker Compose is not installed or not in your PATH.${NC}"
    echo "Visit https://docs.docker.com/compose/install/ for installation instructions."
    exit 1
fi

# Create project directory
echo -e "${YELLOW}Creating project directory...${NC}"
mkdir -p opentranscribe
cd opentranscribe

# Download docker-compose.yml
echo -e "${YELLOW}Downloading docker-compose.yml...${NC}"
curl -sLO https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/docker-compose.prod.yml

# Download .env.example from the repository
echo -e "${YELLOW}Downloading .env.example...${NC}"
curl -s https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/.env.example -o .env.example

# Interactive configuration for .env file
if [ ! -f .env ]; then
    echo -e "${YELLOW}Setting up environment configuration...${NC}"
    
    # Generate a random JWT secret
    JWT_SECRET=$(openssl rand -hex 32 2>/dev/null || echo "change_this_in_production")
    
    # GPU configuration
    echo -e "${YELLOW}GPU Configuration${NC}"
    read -p "Do you have an NVIDIA GPU for transcription? (y/N): " -n 1 -r USE_GPU_INPUT
    echo ""
    if [[ $USE_GPU_INPUT =~ ^[Yy]$ ]]; then
        USE_GPU="true"
        
        # Check if nvidia-smi is available
        if command -v nvidia-smi &> /dev/null; then
            echo "Available GPUs:"
            nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader
            read -p "Enter the GPU device ID to use (recommended: 2): " GPU_DEVICE_ID
            GPU_DEVICE_ID=${GPU_DEVICE_ID:-2}
        else
            echo -e "${RED}Warning: nvidia-smi not found, but GPU support was requested.${NC}"
            echo "Make sure you have NVIDIA drivers and the NVIDIA Container Toolkit installed."
            GPU_DEVICE_ID=2
        fi
    else
        USE_GPU="false"
        GPU_DEVICE_ID=0
    fi
    
    # Hugging Face token (required for speaker diarization)
    echo -e "\n${YELLOW}AI Model Configuration${NC}"
    echo "A Hugging Face token is REQUIRED for speaker diarization."
    echo "Get your token at: https://huggingface.co/settings/tokens"
    read -p "Enter your Hugging Face token (required for full functionality): " HUGGINGFACE_TOKEN
    
    # Model configuration
    echo -e "\n${YELLOW}Transcription Model Configuration${NC}"
    echo "1) large-v2 - Best quality, requires 10GB+ VRAM (default)"
    echo "2) medium   - Good quality, requires 5GB+ VRAM"
    echo "3) small    - Decent quality, requires 2GB+ VRAM"
    echo "4) base     - Basic quality, works on CPU"
    read -p "Select Whisper model (1-4): " MODEL_CHOICE
    
    case "$MODEL_CHOICE" in
        2) WHISPER_MODEL="medium" ;;
        3) WHISPER_MODEL="small" ;;
        4) WHISPER_MODEL="base" ;;
        *) WHISPER_MODEL="large-v2" ;;
    esac
    
    # Compute type based on GPU/CPU choice
    if [[ "$USE_GPU" == "true" ]]; then
        COMPUTE_TYPE="float16"
        BATCH_SIZE="16"
    else
        COMPUTE_TYPE="int8"
        BATCH_SIZE="1"
    fi
    
    # Create the .env file by modifying the example
    cp .env.example .env
    
    # Update key parameters in the .env file
    sed -i "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$JWT_SECRET|g" .env
    sed -i "s|USE_GPU=.*|USE_GPU=$USE_GPU|g" .env
    sed -i "s|GPU_DEVICE_ID=.*|GPU_DEVICE_ID=$GPU_DEVICE_ID|g" .env
    sed -i "s|device_ids: \['.*'\]|device_ids: ['$GPU_DEVICE_ID']|g" docker-compose.prod.yml
    sed -i "s|HUGGINGFACE_TOKEN=.*|HUGGINGFACE_TOKEN=$HUGGINGFACE_TOKEN|g" .env
    sed -i "s|WHISPER_MODEL=.*|WHISPER_MODEL=$WHISPER_MODEL|g" .env
    sed -i "s|BATCH_SIZE=.*|BATCH_SIZE=$BATCH_SIZE|g" .env
    sed -i "s|COMPUTE_TYPE=.*|COMPUTE_TYPE=$COMPUTE_TYPE|g" .env
    
    echo -e "${GREEN}Created .env file with your configuration based on the template.${NC}"
    
    if [[ -z "$HUGGINGFACE_TOKEN" ]]; then
        echo -e "${RED}Warning: No Hugging Face token provided.${NC}"
        echo "Speaker diarization (identifying different speakers) WILL NOT WORK."
        echo "You must add your token by editing the .env file before using speaker diarization."
    fi
    
else
    echo -e "${YELLOW}Using existing .env file.${NC}"
fi

# Create startup script
cat > opentranscribe.sh << 'EOF'
#!/bin/bash
set -e

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

function show_help {
    echo "OpenTranscribe Management Script"
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
    echo "  help        Show this help message"
    echo ""
}

case "$1" in
    start)
        echo -e "${YELLOW}Starting OpenTranscribe...${NC}"
        docker compose -f docker-compose.prod.yml up -d
        echo -e "${GREEN}OpenTranscribe started!${NC}"
        echo "The application is now running. Please wait a moment for all services to initialize."
        echo "- API: http://localhost:8080"
        echo "- Web interface: http://localhost:5173"
        echo "- Flower dashboard: http://localhost:5555/flower"
        echo "- MinIO console: http://localhost:9091"
        ;;
    stop)
        echo -e "${YELLOW}Stopping OpenTranscribe...${NC}"
        docker compose -f docker-compose.prod.yml down
        echo -e "${GREEN}OpenTranscribe stopped.${NC}"
        ;;
    restart)
        echo -e "${YELLOW}Restarting OpenTranscribe...${NC}"
        docker compose -f docker-compose.prod.yml down
        docker compose -f docker-compose.prod.yml up -d
        echo -e "${GREEN}OpenTranscribe restarted!${NC}"
        ;;
    status)
        echo -e "${YELLOW}Container status:${NC}"
        docker compose -f docker-compose.prod.yml ps
        ;;
    logs)
        if [ -z "$2" ]; then
            echo -e "${YELLOW}Showing all logs:${NC}"
            docker compose -f docker-compose.prod.yml logs
        else
            echo -e "${YELLOW}Showing logs for $2:${NC}"
            docker compose -f docker-compose.prod.yml logs "$2" "${@:3}"
        fi
        ;;
    update)
        echo -e "${YELLOW}Updating to latest Docker images...${NC}"
        docker compose -f docker-compose.prod.yml down
        docker compose -f docker-compose.prod.yml pull
        docker compose -f docker-compose.prod.yml up -d
        echo -e "${GREEN}OpenTranscribe updated to latest version!${NC}"
        ;;
    clean)
        echo -e "${RED}⚠️  WARNING: This will remove all data including transcriptions, user accounts, and settings!${NC}"
        read -p "Are you sure you want to continue? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}Removing all containers and volumes...${NC}"
            docker compose -f docker-compose.prod.yml down -v
            echo -e "${GREEN}All data has been removed.${NC}"
        else
            echo -e "${GREEN}Operation cancelled.${NC}"
        fi
        ;;
    help|*)
        show_help
        ;;
esac
EOF

chmod +x opentranscribe.sh

echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "To start OpenTranscribe, run:"
echo "  cd opentranscribe"
echo "  ./opentranscribe.sh start"
echo ""
echo "NOTE: For GPU support, make sure to:"
echo "1. Edit the .env file to set USE_GPU=true and the correct GPU_DEVICE_ID"
echo "2. Install the NVIDIA Container Toolkit if you haven't already"
echo "3. For speaker diarization, add your HUGGINGFACE_TOKEN to the .env file"
echo ""
echo "Enjoy using OpenTranscribe!"
