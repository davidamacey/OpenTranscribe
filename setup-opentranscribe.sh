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
DOCKER_COMPOSE_CMD="docker compose"

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
            DOCKER_COMPOSE_CMD="docker compose"
            ;;
        "darwin")
            DETECTED_PLATFORM="macos"
            echo "✓ Detected: macOS ($ARCH)"
            # macOS typically uses docker-compose (hyphenated) command
            DOCKER_COMPOSE_CMD="docker-compose"
            ;;
        "mingw"*|"msys"*|"cygwin"*)
            DETECTED_PLATFORM="windows"
            echo "✓ Detected: Windows ($ARCH)"
            DOCKER_COMPOSE_CMD="docker-compose"
            ;;
        *)
            echo "⚠️  Unknown platform: $DETECTED_PLATFORM ($ARCH)"
            # Default to docker compose with space
            DOCKER_COMPOSE_CMD="docker compose"
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
# DEPENDENCY CHECKS
#######################

check_dependencies() {
    echo -e "${BLUE}📋 Checking dependencies...${NC}"
    
    # Check for Docker
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker is not installed${NC}"
        case "$DETECTED_PLATFORM" in
            "macos")
                echo "For macOS, install Docker Desktop from https://docs.docker.com/desktop/install/mac/"
                echo "Or install via Homebrew: brew install --cask docker"
                ;;
            "windows")
                echo "For Windows, install Docker Desktop from https://docs.docker.com/desktop/install/windows/"
                ;;
            *)
                echo "Visit https://docs.docker.com/get-docker/ for installation instructions."
                ;;
        esac
        exit 1
    else
        docker_version=$(docker --version | cut -d' ' -f3 | cut -d',' -f1)
        echo "✓ Docker $docker_version detected"
    fi
    
    # Check for Docker Compose - try both 'docker compose' and 'docker-compose' formats
    if docker compose version &> /dev/null; then
        compose_version=$(docker compose version --short 2>/dev/null || docker compose version 2>/dev/null)
        echo "✓ Docker Compose $compose_version detected (docker compose format)"
        DOCKER_COMPOSE_CMD="docker compose"
    elif command -v docker-compose &> /dev/null; then
        compose_version=$(docker-compose version --short 2>/dev/null || docker-compose --version 2>/dev/null)
        echo "✓ Docker Compose detected (docker-compose format)"
        DOCKER_COMPOSE_CMD="docker-compose"
    else
        echo -e "${RED}❌ Docker Compose is not installed or not in PATH${NC}"
        
        case "$DETECTED_PLATFORM" in
            "macos")
                echo "For macOS, Docker Compose is included in Docker Desktop."
                echo "Or install via Homebrew: brew install docker-compose"
                ;;
            "windows")
                echo "For Windows, Docker Compose is included in Docker Desktop."
                ;;
            *)
                echo "Visit https://docs.docker.com/compose/install/ for installation instructions."
                ;;
        esac
        exit 1
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

create_database_files() {
    echo "✓ Creating database initialization files..."
    
    # Create init_db.sql file
    cat > init_db.sql << 'EOF'
-- Initialize database tables for OpenTranscribe

-- Users table
CREATE TABLE IF NOT EXISTS "user" (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    role VARCHAR(50) DEFAULT 'user',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Media files table
CREATE TABLE IF NOT EXISTS media_file (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    storage_path VARCHAR(500) NOT NULL,
    file_size BIGINT NOT NULL,
    duration FLOAT,
    upload_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE NULL,
    content_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    is_public BOOLEAN DEFAULT FALSE,
    language VARCHAR(10) NULL,
    summary TEXT NULL,
    translated_text TEXT NULL,
    file_hash VARCHAR(255) NULL,
    thumbnail_path VARCHAR(500) NULL,
    -- Detailed metadata fields
    metadata_raw JSONB NULL,
    metadata_important JSONB NULL,
    -- Media technical specs
    media_format VARCHAR(50) NULL,
    codec VARCHAR(50) NULL,
    frame_rate FLOAT NULL,
    frame_count INTEGER NULL,
    resolution_width INTEGER NULL,
    resolution_height INTEGER NULL,
    aspect_ratio VARCHAR(20) NULL,
    -- Audio specs
    audio_channels INTEGER NULL,
    audio_sample_rate INTEGER NULL,
    audio_bit_depth INTEGER NULL,
    -- Creation information
    creation_date TIMESTAMP WITH TIME ZONE NULL,
    last_modified_date TIMESTAMP WITH TIME ZONE NULL,
    -- Device information
    device_make VARCHAR(100) NULL,
    device_model VARCHAR(100) NULL,
    -- Content information
    title VARCHAR(255) NULL,
    author VARCHAR(255) NULL,
    description TEXT NULL,
    user_id INTEGER NOT NULL REFERENCES "user" (id)
);

-- Create the Tag table
CREATE TABLE IF NOT EXISTS tag (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create the FileTag join table
CREATE TABLE IF NOT EXISTS file_tag (
    id SERIAL PRIMARY KEY,
    media_file_id INTEGER NOT NULL REFERENCES media_file (id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tag (id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (media_file_id, tag_id)
);

-- Speakers table
CREATE TABLE IF NOT EXISTS speaker (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    media_file_id INTEGER NOT NULL REFERENCES media_file(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    display_name VARCHAR(255) NULL,
    uuid VARCHAR(255) NOT NULL,
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    embedding_vector JSONB NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, media_file_id, name)
);

-- Transcript segments table
CREATE TABLE IF NOT EXISTS transcript_segment (
    id SERIAL PRIMARY KEY,
    media_file_id INTEGER NOT NULL REFERENCES media_file(id),
    speaker_id INTEGER NULL REFERENCES speaker(id),
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    text TEXT NOT NULL
);

-- Comments table
CREATE TABLE IF NOT EXISTS comment (
    id SERIAL PRIMARY KEY,
    media_file_id INTEGER NOT NULL REFERENCES media_file(id),
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    text TEXT NOT NULL,
    timestamp FLOAT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tasks table
CREATE TABLE IF NOT EXISTS task (
    id VARCHAR(255) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    media_file_id INTEGER NULL REFERENCES media_file(id),
    task_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    progress FLOAT DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE NULL,
    error_message TEXT NULL
);

-- Analytics table
CREATE TABLE IF NOT EXISTS analytics (
    id SERIAL PRIMARY KEY,
    media_file_id INTEGER UNIQUE REFERENCES media_file(id),
    speaker_stats JSONB NULL,
    sentiment JSONB NULL,
    keywords JSONB NULL
);

-- Collections table
CREATE TABLE IF NOT EXISTS collection (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name)
);

-- Collection members join table
CREATE TABLE IF NOT EXISTS collection_member (
    id SERIAL PRIMARY KEY,
    collection_id INTEGER NOT NULL REFERENCES collection(id) ON DELETE CASCADE,
    media_file_id INTEGER NOT NULL REFERENCES media_file(id) ON DELETE CASCADE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(collection_id, media_file_id)
);

-- Insert admin user
INSERT INTO "user" (email, full_name, hashed_password, is_active, is_superuser, role) 
VALUES ('admin@example.com', 'Admin User', '$2b$12$VVtvMYmKcDrOkUEBeGm9luACJNDxPw.eAcTShleJS1gmh5ARHBFpm', true, true, 'admin') 
ON CONFLICT (email) DO NOTHING;
EOF

    echo "✓ Created init_db.sql"
}

create_configuration_files() {
    echo -e "${BLUE}📄 Creating configuration files...${NC}"
    
    # Create database initialization files
    create_database_files
    
    # Create comprehensive docker-compose.yml directly
    create_production_compose
    
    # Create .env.example
    create_production_env_example
}

create_production_compose() {
    echo "✓ Creating production docker-compose.yml with hardware-specific configuration..."
    
    # Create base compose file
    cat > docker-compose.yml << 'EOF'
version: '3.8'

# OpenTranscribe Production Configuration
# Cross-platform compatible with automatic GPU detection

services:
  postgres:
    image: postgres:14-alpine
    restart: always
    volumes:
      - postgres_data:/var/lib/postgresql/data/
    environment:
      - POSTGRES_USER=${POSTGRES_USER:-postgres}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-postgres}
      - POSTGRES_DB=${POSTGRES_DB:-opentranscribe}
    ports:
      - "${POSTGRES_PORT:-5176}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres}"]
      interval: 5s
      timeout: 5s
      retries: 5

  minio:
    image: minio/minio
    restart: always
    volumes:
      - minio_data:/data
    environment:
      - MINIO_ROOT_USER=${MINIO_ROOT_USER:-minioadmin}
      - MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:-minioadmin}
    ports:
      - "${MINIO_PORT:-5178}:9000"
      - "${MINIO_CONSOLE_PORT:-5179}:9001"
    command: server /data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 5s
      timeout: 10s
      retries: 5

  redis:
    image: redis:7-alpine
    restart: always
    ports:
      - "${REDIS_PORT:-5177}:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 30s
      retries: 50

  opensearch:
    image: opensearchproject/opensearch:2.5.0
    restart: always
    environment:
      - discovery.type=single-node
      - bootstrap.memory_lock=true
      - "OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m"
      - DISABLE_SECURITY_PLUGIN=true
    ulimits:
      memlock:
        soft: -1
        hard: -1
    volumes:
      - opensearch_data:/usr/share/opensearch/data
    ports:
      - "${OPENSEARCH_PORT:-5180}:9200"
      - "${OPENSEARCH_ADMIN_PORT:-5181}:9600"
    healthcheck:
      test: ["CMD-SHELL", "curl -sS http://localhost:9200 || exit 1"]
      interval: 5s
      timeout: 10s
      retries: 20

  db-init:
    image: postgres:14-alpine
    restart: "no"
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./init_db.sql:/init_db.sql:ro
    environment:
      - PGPASSWORD=${POSTGRES_PASSWORD:-postgres}
    command: >
      sh -c "
        echo '🗄️  Initializing database schema...' &&
        psql -h postgres -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-opentranscribe} -f /init_db.sql &&
        echo '✅ Database schema initialized!'
      "

  backend:
    image: davidamacey/opentranscribe-backend:latest
    restart: always
    volumes:
      - backend_models:/app/models
      - backend_temp:/app/temp
    ports:
      - "${BACKEND_PORT:-5174}:8080"
    environment:
      # Database
      - POSTGRES_HOST=${POSTGRES_HOST:-postgres}
      - POSTGRES_PORT=5432
      - POSTGRES_USER=${POSTGRES_USER:-postgres}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-postgres}
      - POSTGRES_DB=${POSTGRES_DB:-opentranscribe}
      # Storage
      - MINIO_HOST=${MINIO_HOST:-minio}
      - MINIO_PORT=9000
      - MINIO_ROOT_USER=${MINIO_ROOT_USER:-minioadmin}
      - MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:-minioadmin}
      - MEDIA_BUCKET_NAME=${MEDIA_BUCKET_NAME:-opentranscribe}
      # Cache
      - REDIS_HOST=${REDIS_HOST:-redis}
      - REDIS_PORT=6379
      # Search
      - OPENSEARCH_HOST=${OPENSEARCH_HOST:-opensearch}
      - OPENSEARCH_PORT=9200
      # Security
      - JWT_SECRET_KEY=${JWT_SECRET_KEY:-change_this_in_production}
      - JWT_ALGORITHM=${JWT_ALGORITHM:-HS256}
      - JWT_ACCESS_TOKEN_EXPIRE_MINUTES=${JWT_ACCESS_TOKEN_EXPIRE_MINUTES:-60}
      # Models
      - MODEL_BASE_DIR=${MODEL_BASE_DIR:-/app/models}
      - TEMP_DIR=${TEMP_DIR:-/app/temp}
      # Hardware (auto-detected)
      - TORCH_DEVICE=${TORCH_DEVICE:-auto}
      - COMPUTE_TYPE=${COMPUTE_TYPE:-auto}
      - USE_GPU=${USE_GPU:-auto}
      - GPU_DEVICE_ID=${GPU_DEVICE_ID:-0}
      # AI Models
      - HUGGINGFACE_TOKEN=${HUGGINGFACE_TOKEN:-}
      - WHISPER_MODEL=${WHISPER_MODEL:-large-v2}
      - BATCH_SIZE=${BATCH_SIZE:-auto}
      - DIARIZATION_MODEL=${DIARIZATION_MODEL:-pyannote/speaker-diarization-3.1}
      - MIN_SPEAKERS=${MIN_SPEAKERS:-1}
      - MAX_SPEAKERS=${MAX_SPEAKERS:-10}
    depends_on:
      db-init:
        condition: service_completed_successfully
      redis:
        condition: service_healthy
      minio:
        condition: service_healthy
      opensearch:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  celery-worker:
    image: davidamacey/opentranscribe-backend:latest
    restart: always
    command: celery -A app.core.celery worker --loglevel=info --concurrency=1
    volumes:
      - backend_models:/app/models
      - backend_temp:/app/temp
    environment:
      # Same environment as backend
      - POSTGRES_HOST=${POSTGRES_HOST:-postgres}
      - POSTGRES_PORT=5432
      - POSTGRES_USER=${POSTGRES_USER:-postgres}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-postgres}
      - POSTGRES_DB=${POSTGRES_DB:-opentranscribe}
      - MINIO_HOST=${MINIO_HOST:-minio}
      - MINIO_PORT=9000
      - MINIO_ROOT_USER=${MINIO_ROOT_USER:-minioadmin}
      - MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:-minioadmin}
      - REDIS_HOST=${REDIS_HOST:-redis}
      - REDIS_PORT=6379
      - OPENSEARCH_HOST=${OPENSEARCH_HOST:-opensearch}
      - OPENSEARCH_PORT=9200
      - MODEL_BASE_DIR=${MODEL_BASE_DIR:-/app/models}
      - TEMP_DIR=${TEMP_DIR:-/app/temp}
      - TORCH_DEVICE=${TORCH_DEVICE:-auto}
      - COMPUTE_TYPE=${COMPUTE_TYPE:-auto}
      - USE_GPU=${USE_GPU:-auto}
      - GPU_DEVICE_ID=${GPU_DEVICE_ID:-0}
      - HUGGINGFACE_TOKEN=${HUGGINGFACE_TOKEN:-}
      - WHISPER_MODEL=${WHISPER_MODEL:-large-v2}
      - BATCH_SIZE=${BATCH_SIZE:-auto}
      - DIARIZATION_MODEL=${DIARIZATION_MODEL:-pyannote/speaker-diarization-3.1}
      - MIN_SPEAKERS=${MIN_SPEAKERS:-1}
      - MAX_SPEAKERS=${MAX_SPEAKERS:-10}
    depends_on:
      - postgres
      - redis
      - minio
      - opensearch

  frontend:
    image: davidamacey/opentranscribe-frontend:latest
    restart: always
    ports:
      - "${FRONTEND_PORT:-5173}:80"
    environment:
      - NODE_ENV=production
      - VITE_API_BASE_URL=/api
      - VITE_WS_BASE_URL=auto
      - VITE_FLOWER_PORT=${FLOWER_PORT:-5175}
      - VITE_FLOWER_URL_PREFIX=${VITE_FLOWER_URL_PREFIX:-flower}
    depends_on:
      backend:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:80"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  flower:
    image: davidamacey/opentranscribe-backend:latest
    restart: always
    command: >
      python -m celery -A app.core.celery flower
      --port=5555
      --url_prefix=${VITE_FLOWER_URL_PREFIX:-flower}
      --persistent=True
      --db=/app/flower.db
      --broker=redis://${REDIS_HOST:-redis}:6379/0
    ports:
      - "${FLOWER_PORT:-5175}:5555"
    depends_on:
      - redis
      - celery-worker
    environment:
      - CELERY_BROKER_URL=redis://${REDIS_HOST:-redis}:6379/0
      - HUGGINGFACE_TOKEN=${HUGGINGFACE_TOKEN:-}
    volumes:
      - flower_data:/app

volumes:
  postgres_data:
  minio_data:
  redis_data:
  opensearch_data:
  backend_models:
  backend_temp:
  flower_data:

networks:
  default:
    driver: bridge
EOF

    # Add GPU configuration if CUDA is detected
    if [[ "$DETECTED_DEVICE" == "cuda" && "$USE_GPU_RUNTIME" == "true" ]]; then
        echo "✓ Adding NVIDIA GPU runtime configuration..."
        
        # Add GPU override file for CUDA systems
        cat > docker-compose.gpu.yml << 'EOF'
version: '3.8'

services:
  backend:
    runtime: nvidia
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['${GPU_DEVICE_ID:-0}']
              capabilities: [gpu]

  celery-worker:
    runtime: nvidia
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['${GPU_DEVICE_ID:-0}']
              capabilities: [gpu]
EOF
        echo "✓ Created GPU override configuration (docker-compose.gpu.yml)"
    fi
    
    echo "✓ Created production docker-compose.yml"
}

create_production_env_example() {
    cat > .env.example << 'EOF'
# OpenTranscribe Production Configuration
# This file is automatically configured by the setup script

# Database Configuration
POSTGRES_HOST=postgres
POSTGRES_PORT=5176
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=opentranscribe

# MinIO Object Storage Configuration
MINIO_HOST=minio
MINIO_PORT=5178
MINIO_CONSOLE_PORT=5179
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MEDIA_BUCKET_NAME=opentranscribe

# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=5177

# OpenSearch Configuration
OPENSEARCH_HOST=opensearch
OPENSEARCH_PORT=5180
OPENSEARCH_ADMIN_PORT=5181

# JWT Authentication
JWT_SECRET_KEY=change_this_in_production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Model Storage
MODEL_BASE_DIR=/app/models
TEMP_DIR=/app/temp

# Hardware Detection (auto-detected by setup script)
TORCH_DEVICE=auto
COMPUTE_TYPE=auto
USE_GPU=auto
GPU_DEVICE_ID=0

# AI Models Configuration
WHISPER_MODEL=large-v2
BATCH_SIZE=auto
DIARIZATION_MODEL=pyannote/speaker-diarization-3.1
MIN_SPEAKERS=1
MAX_SPEAKERS=10

# HuggingFace Token (REQUIRED for speaker diarization)
# Get your token at: https://huggingface.co/settings/tokens
HUGGINGFACE_TOKEN=your_huggingface_token_here

# External Port Configuration (sequential ports to avoid conflicts)
FRONTEND_PORT=5173
BACKEND_PORT=5174
FLOWER_PORT=5175
POSTGRES_PORT=5176
REDIS_PORT=5177
MINIO_PORT=5178
MINIO_CONSOLE_PORT=5179
OPENSEARCH_PORT=5180
OPENSEARCH_ADMIN_PORT=5181

# Frontend Configuration
NODE_ENV=production
VITE_FLOWER_URL_PREFIX=flower
EOF
    echo "✓ Created production .env.example"
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
            WHISPER_MODEL="medium"
            echo "✓ Apple Silicon detected - selecting medium model (optimized for MPS)"
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
    
    # Add Docker runtime configuration
    echo "" >> .env
    echo "# Hardware Configuration (Auto-detected)" >> .env
    echo "DOCKER_RUNTIME=${DOCKER_RUNTIME:-}" >> .env
    
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

get_compose_command() {
    # Build compose command with all available override files
    COMPOSE_FILES="-f docker-compose.yml"
    if [ -f docker-compose.gpu.yml ]; then
        COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu.yml"
    fi
    if [ -f docker-compose.override.yml ]; then
        COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.override.yml"
    fi
    # Use the platform-specific docker compose command
    local platform=$(uname -s | tr '[:upper:]' '[:lower:]')
    local compose_cmd="docker compose"
    
    if [[ "$platform" == "darwin" ]]; then
        # Check which docker compose command format works
        if command -v docker-compose &> /dev/null; then
            compose_cmd="docker-compose"
        fi
    elif [[ "$platform" == *"mingw"* || "$platform" == *"msys"* || "$platform" == *"cygwin"* ]]; then
        compose_cmd="docker-compose"
    fi
    
    echo "$compose_cmd $COMPOSE_FILES"
}

case "${1:-help}" in
    start)
        check_environment
        echo -e "${YELLOW}🚀 Starting OpenTranscribe...${NC}"
        COMPOSE_CMD=$(get_compose_command)
        $COMPOSE_CMD up -d
        echo -e "${GREEN}✅ OpenTranscribe started!${NC}"
        show_access_info
        ;;
    stop)
        check_environment
        echo -e "${YELLOW}🛑 Stopping OpenTranscribe...${NC}"
        COMPOSE_CMD=$(get_compose_command)
        $COMPOSE_CMD down
        echo -e "${GREEN}✅ OpenTranscribe stopped${NC}"
        ;;
    restart)
        check_environment
        echo -e "${YELLOW}🔄 Restarting OpenTranscribe...${NC}"
        COMPOSE_CMD=$(get_compose_command)
        $COMPOSE_CMD down
        $COMPOSE_CMD up -d
        echo -e "${GREEN}✅ OpenTranscribe restarted!${NC}"
        show_access_info
        ;;
    status)
        check_environment
        echo -e "${BLUE}📊 Container Status:${NC}"
        COMPOSE_CMD=$(get_compose_command)
        $COMPOSE_CMD ps
        ;;
    logs)
        check_environment
        service=${2:-}
        COMPOSE_CMD=$(get_compose_command)
        
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
        COMPOSE_CMD=$(get_compose_command)
        $COMPOSE_CMD down
        $COMPOSE_CMD pull
        $COMPOSE_CMD up -d
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
            COMPOSE_CMD=$(get_compose_command)
            $COMPOSE_CMD down -v
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
        COMPOSE_CMD=$(get_compose_command)
        $COMPOSE_CMD exec "$service" /bin/bash || $COMPOSE_CMD exec "$service" /bin/sh
        ;;
    config)
        check_environment
        echo -e "${BLUE}⚙️  Current Configuration:${NC}"
        echo "Environment file (.env):"
        grep -E "^[A-Z]" .env | head -20
        echo ""
        echo "Docker Compose configuration:"
        COMPOSE_CMD=$(get_compose_command)
        if $COMPOSE_CMD config > /dev/null 2>&1; then
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
        COMPOSE_CMD=$(get_compose_command)
        $COMPOSE_CMD ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"
        
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
        COMPOSE_CMD=$(get_compose_command)
        if $COMPOSE_CMD exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
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
    if $DOCKER_COMPOSE_CMD config &> /dev/null; then
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
    echo "  • ./opentranscribe.sh config  # Show current config"
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
    create_configuration_files
    configure_environment
    create_management_script
    validate_setup
    display_summary
}

# Execute main function
main