#!/bin/bash

# OpenTranscribe Utility Script
# A comprehensive script for all OpenTranscribe operations
# Usage: ./opentr.sh [command] [options]

# Source common functions
# shellcheck source=scripts/common.sh
source ./scripts/common.sh

# Load environment variables from .env if present
if [ -f ".env" ]; then
  set -a
  # shellcheck source=.env
  source ./.env
  set +a
fi

# Maximum compose files list for stopping/removing all containers
# Includes all possible compose files to ensure all containers are stopped
MAX_COMPOSE_FILES="-f docker-compose.yml -f docker-compose.override.yml -f docker-compose.prod.yml -f docker-compose.gpu.yml -f docker-compose.gpu-scale.yml -f docker-compose.lite.yml -f docker-compose.nginx.yml -f docker-compose.offline.yml"

#######################
# HELPER FUNCTIONS
#######################

# Display help menu
show_help() {
  echo "🚀 OpenTranscribe Utility Script"
  echo "-------------------------------"
  echo "Usage: ./opentr.sh [command] [options]"
  echo ""
  echo "Basic Commands:"
  echo "  start [dev|prod] [--build] [--pull] [--gpu-scale] [--lite]  - Start the application (dev mode by default)"
  echo "                                                        --build: Build prod images locally (test before push)"
  echo "                                                        --pull:  Force pull prod images from Docker Hub"
  echo "                                                        --gpu-scale: Enable multi-GPU worker scaling"
  echo "                                                        --lite:  Cloud-only ASR mode (no GPU required)"
  echo "  stop                                       - Stop OpenTranscribe containers"
  echo "  status                                     - Show container status"
  echo "  logs [service]                             - View logs (all services by default)"
  echo ""
  echo "Reset & Database Commands:"
  echo "  reset [dev|prod] [--build] [--pull] [--gpu-scale] [--lite]  - Reset and reinitialize (deletes all data!)"
  echo "                                                        --build: Build prod images locally (test before push)"
  echo "                                                        --pull:  Force pull prod images from Docker Hub"
  echo "                                                        --gpu-scale: Enable multi-GPU worker scaling"
  echo "                                                        --lite:  Cloud-only ASR mode (no GPU required)"
  echo "  backup              - Create a database backup"
  echo "  restore [file]      - Restore database from backup"
  echo ""
  echo "Development Commands:"
  echo "  restart-backend     - Restart backend, celery-worker, celery-beat & flower without database reset"
  echo "  restart-frontend    - Restart frontend without affecting backend services"
  echo "  restart-all         - Restart all services without resetting database"
  echo "  rebuild-backend     - Rebuild and update backend services with code changes"
  echo "  rebuild-frontend    - Rebuild and update frontend with code changes"
  echo "  shell [service]     - Open a shell in a container"
  echo "  build               - Rebuild all containers without starting"
  echo ""
  echo "Cleanup Commands:"
  echo "  remove              - Stop containers and remove data volumes"
  echo "  purge               - Remove everything including images (most destructive)"
  echo ""
  echo "Advanced Commands:"
  echo "  health              - Check health status of all services"
  echo "  help                - Show this help menu"
  echo ""
  echo "HTTPS/SSL Setup (for microphone recording from other devices):"
  echo "  1. Generate certificates: ./scripts/generate-ssl-cert.sh opentranscribe.local --auto-ip"
  echo "  2. Add to .env: NGINX_SERVER_NAME=opentranscribe.local"
  echo "  3. Start normally: ./opentr.sh start dev"
  echo "  See docs/NGINX_SETUP.md for full instructions"
  echo ""
  echo "Examples:"
  echo "  ./opentr.sh start                    # Start in development mode"
  echo "  ./opentr.sh start dev --gpu-scale    # Start with multi-GPU scaling enabled"
  echo "  ./opentr.sh start dev --lite         # Start in cloud-only ASR mode (no GPU)"
  echo "  ./opentr.sh start prod               # Start in production mode (pulls from Docker Hub)"
  echo "  ./opentr.sh start prod --build       # Test production build locally (before pushing)"
  echo "  ./opentr.sh reset dev                # Reset development environment"
  echo "  ./opentr.sh reset dev --lite         # Reset in cloud-only ASR mode"
  echo "  ./opentr.sh logs backend             # View backend logs"
  echo "  ./opentr.sh restart-backend          # Restart backend services only"
  echo ""
}

# Build production images locally (backend + frontend)
build_prod_images() {
  echo "🥽 Building production Docker images locally..."

  echo "🧱 Building backend image (davidamacey/opentranscribe-backend:latest)..."
  docker build -t davidamacey/opentranscribe-backend:latest -f backend/Dockerfile.prod backend || {
    echo "❌ Backend image build failed"
    exit 1
  }

  echo "🧱 Building frontend image (davidamacey/opentranscribe-frontend:latest)..."
  docker build -t davidamacey/opentranscribe-frontend:latest -f frontend/Dockerfile.prod frontend || {
    echo "❌ Frontend image build failed"
    exit 1
  }

  echo "✅ Local production images built successfully"
}

# Function to detect and configure hardware
detect_and_configure_hardware() {
  echo "🔍 Detecting hardware configuration..."

  # Detect platform
  PLATFORM=$(uname -s | tr '[:upper:]' '[:lower:]')
  ARCH=$(uname -m)

  # Initialize default values
  export TORCH_DEVICE="auto"
  export COMPUTE_TYPE="auto"
  export USE_GPU="auto"
  export DOCKER_RUNTIME=""
  export BACKEND_DOCKERFILE="Dockerfile.prod"
  export BUILD_ENV="development"

  # Check for NVIDIA GPU
  if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    echo "✅ NVIDIA GPU detected"
    export DOCKER_RUNTIME="nvidia"
    export TORCH_DEVICE="cuda"
    export COMPUTE_TYPE="float16"
    export USE_GPU="true"

    # Check for NVIDIA Container Toolkit (efficient method)
    if docker info 2>/dev/null | grep -q nvidia; then
      echo "✅ NVIDIA Container Toolkit available"
    else
      echo "⚠️  NVIDIA GPU detected but Container Toolkit not available"
      echo "   Falling back to CPU mode"
      export DOCKER_RUNTIME=""
      export TORCH_DEVICE="cpu"
      export COMPUTE_TYPE="int8"
      export USE_GPU="false"
    fi
  elif [[ "$PLATFORM" == "darwin" && "$ARCH" == "arm64" ]]; then
    echo "✅ Apple Silicon detected"
    export TORCH_DEVICE="mps"
    export COMPUTE_TYPE="float32"
    export USE_GPU="false"
  else
    echo "ℹ️  Using CPU processing"
    export TORCH_DEVICE="cpu"
    export COMPUTE_TYPE="int8"
    export USE_GPU="false"
  fi

  # Set additional environment variables
  TARGETPLATFORM="linux/$([[ "$ARCH" == "arm64" ]] && echo "arm64" || echo "amd64")"
  export TARGETPLATFORM

  echo "📋 Hardware Configuration:"
  echo "  Platform: $PLATFORM"
  echo "  Architecture: $ARCH"
  echo "  Device: $TORCH_DEVICE"
  echo "  Compute Type: $COMPUTE_TYPE"
  echo "  Docker Runtime: ${DOCKER_RUNTIME:-default}"
}

# Function to start the environment
start_app() {
  ENVIRONMENT=${1:-dev}
  shift || true  # Remove first argument

  # Parse optional flags
  BUILD_FLAG=""
  GPU_SCALE_FLAG=""
  PULL_FLAG=""
  LITE_FLAG=""

  while [ $# -gt 0 ]; do
    case "$1" in
      --build)
        BUILD_FLAG="--build"
        shift
        ;;
      --pull)
        PULL_FLAG="--pull"
        shift
        ;;
      --gpu-scale)
        GPU_SCALE_FLAG="--gpu-scale"
        shift
        ;;
      --lite)
        LITE_FLAG="--lite"
        shift
        ;;
      *)
        echo "⚠️  Unknown flag: $1"
        shift
        ;;
    esac
  done

  if [ -n "$GPU_SCALE_FLAG" ]; then
    export COMPOSE_PROFILES="gpu-scale"
  fi

  echo "🚀 Starting OpenTranscribe in ${ENVIRONMENT} mode..."

  if [ -n "$GPU_SCALE_FLAG" ]; then
    echo "🎯 Multi-GPU scaling enabled"
  fi

  if [ -n "$LITE_FLAG" ]; then
    echo "☁️  Lite mode enabled (cloud-only ASR, no GPU required)"
  fi

  # Ensure Docker is running
  check_docker

  # Detect and configure hardware (skipped in lite mode — no GPU needed)
  if [ -z "$LITE_FLAG" ]; then
    detect_and_configure_hardware
  else
    echo "ℹ️  Skipping GPU detection (lite mode uses cloud ASR providers)"
    export DOCKER_RUNTIME=""
    export TORCH_DEVICE="cpu"
    export COMPUTE_TYPE="int8"
    export USE_GPU="false"
  fi

  # Set build environment
  export BUILD_ENV="$ENVIRONMENT"

  # Create necessary directories
  create_required_dirs

  # Fix model cache permissions for non-root container
  fix_model_cache_permissions

  # Build compose file list based on environment and flags
  COMPOSE_FILES="-f docker-compose.yml"

  if [ "$ENVIRONMENT" = "prod" ]; then
    # Production: Use base + prod override files
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.prod.yml"

    # Note: INIT_DB_PATH uses default ./database/init_db.sql (same for all modes)

    if [ "$PULL_FLAG" = "--pull" ]; then
      echo "⬇️  Forcing pull of latest production images from Docker Hub..."
      # shellcheck disable=SC2086
      docker compose $COMPOSE_FILES pull || {
        echo "❌ Failed to pull production images"
        exit 1
      }
    fi

    if [ "$BUILD_FLAG" = "--build" ]; then
      echo "🔄 Starting services in PRODUCTION mode with LOCAL BUILD (testing before push)..."
      echo "⚠️  Building backend and frontend images locally instead of pulling from Docker Hub"
      build_prod_images
      # Add local override to prevent pulling from Docker Hub (overrides pull_policy: always)
      COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.local.yml"
      BUILD_CMD=""
    else
      echo "🔄 Starting services in PRODUCTION mode (pulling from Docker Hub)..."
      BUILD_CMD=""
    fi
  else
    # Development: Auto-loads docker-compose.override.yml (always builds)
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.override.yml"
    echo "🔄 Starting services in DEVELOPMENT mode (auto-loads docker-compose.override.yml)..."
    BUILD_CMD="--build"
  fi

  # Add GPU overlay if NVIDIA GPU is detected and Container Toolkit is available
  if [ "$DOCKER_RUNTIME" = "nvidia" ] && [ -f "docker-compose.gpu.yml" ]; then
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu.yml"
    echo "🎯 Adding GPU overlay (docker-compose.gpu.yml) for NVIDIA acceleration"
  fi

  # Add GPU scaling overlay if requested
  if [ -n "$GPU_SCALE_FLAG" ]; then
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu-scale.yml"
    echo "🎯 Adding GPU scaling overlay (docker-compose.gpu-scale.yml)"
  fi

  # Add lite overlay if requested (cloud-only ASR, no GPU)
  if [ -n "$LITE_FLAG" ]; then
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.lite.yml"
    echo "☁️  Adding lite overlay (docker-compose.lite.yml)"
  fi

  # Add NGINX reverse proxy if NGINX_SERVER_NAME is set
  if [ -n "$NGINX_SERVER_NAME" ]; then
    if [ -f "docker-compose.nginx.yml" ]; then
      # Check for SSL certificates
      CERT_FILE="${NGINX_CERT_FILE:-./nginx/ssl/server.crt}"
      KEY_FILE="${NGINX_CERT_KEY:-./nginx/ssl/server.key}"

      if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
        echo ""
        echo "⚠️  SSL certificates not found!"
        echo "   Expected: $CERT_FILE and $KEY_FILE"
        echo ""
        echo "   Generate certificates with:"
        echo "   ./scripts/generate-ssl-cert.sh $NGINX_SERVER_NAME --auto-ip"
        echo ""
        echo "   Or disable NGINX by commenting out NGINX_SERVER_NAME in .env"
        exit 1
      fi

      COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.nginx.yml"
      echo "🔒 Adding NGINX reverse proxy (HTTPS enabled)"
      echo "   Server name: $NGINX_SERVER_NAME"
      echo "   Access URL: https://$NGINX_SERVER_NAME"
    else
      echo "⚠️  NGINX_SERVER_NAME is set but docker-compose.nginx.yml not found"
    fi
  fi

  # Start services with appropriate compose files
  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES up -d $BUILD_CMD

  # Display container status
  echo "📊 Container status:"
  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES ps

  # Print access information
  echo "✅ Services are starting up."
  print_access_info

  # Display log commands
  echo "📋 To view logs, run:"
  echo "- All logs: docker compose logs -f"
  echo "- Backend logs: docker compose logs -f backend"
  echo "- Frontend logs: docker compose logs -f frontend"
  if [ -n "$GPU_SCALE_FLAG" ]; then
    echo "- GPU scaled workers: docker compose logs -f celery-worker-gpu-scaled"
  elif [ -n "$LITE_FLAG" ]; then
    echo "- Cloud ASR worker logs: docker compose logs -f celery-cloud-worker"
  else
    echo "- Celery worker logs: docker compose logs -f celery-worker"
  fi
  echo "- Celery beat logs: docker compose logs -f celery-beat"

  # Print help information
  print_help_commands
}

# Function to reset and initialize the environment
reset_and_init() {
  ENVIRONMENT=${1:-dev}
  shift || true  # Remove first argument

  # Parse optional flags
  BUILD_FLAG=""
  GPU_SCALE_FLAG=""
  PULL_FLAG=""
  LITE_FLAG=""

  while [ $# -gt 0 ]; do
    case "$1" in
      --build)
        BUILD_FLAG="--build"
        shift
        ;;
      --pull)
        PULL_FLAG="--pull"
        shift
        ;;
      --gpu-scale)
        GPU_SCALE_FLAG="--gpu-scale"
        shift
        ;;
      --lite)
        LITE_FLAG="--lite"
        shift
        ;;
      *)
        echo "⚠️  Unknown flag: $1"
        shift
        ;;
    esac
  done

  if [ -n "$GPU_SCALE_FLAG" ]; then
    export COMPOSE_PROFILES="gpu-scale"
  fi

  echo "🔄 Running reset and initialize for OpenTranscribe in ${ENVIRONMENT} mode..."

  if [ -n "$GPU_SCALE_FLAG" ]; then
    echo "🎯 Multi-GPU scaling enabled"
  fi

  if [ -n "$LITE_FLAG" ]; then
    echo "☁️  Lite mode enabled (cloud-only ASR, no GPU required)"
  fi

  # Ensure Docker is running
  check_docker

  # Detect and configure hardware (skipped in lite mode — no GPU needed)
  if [ -z "$LITE_FLAG" ]; then
    detect_and_configure_hardware
  else
    echo "ℹ️  Skipping GPU detection (lite mode uses cloud ASR providers)"
    export DOCKER_RUNTIME=""
    export TORCH_DEVICE="cpu"
    export COMPUTE_TYPE="int8"
    export USE_GPU="false"
  fi

  # Set build environment
  export BUILD_ENV="$ENVIRONMENT"

  # Build compose file list based on environment and flags
  COMPOSE_FILES="-f docker-compose.yml"

  if [ "$ENVIRONMENT" = "prod" ]; then
    # Production: Use base + prod override files
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.prod.yml"
    # Note: INIT_DB_PATH uses default ./database/init_db.sql (same for all modes)

    if [ "$PULL_FLAG" = "--pull" ]; then
      echo "⬇️  Forcing pull of latest production images from Docker Hub..."
      # shellcheck disable=SC2086
      docker compose $COMPOSE_FILES pull || {
        echo "❌ Failed to pull production images"
        exit 1
      }
    fi

    if [ "$BUILD_FLAG" = "--build" ]; then
      echo "🔄 Resetting in PRODUCTION mode with LOCAL BUILD (testing before push)..."
      echo "⚠️  Building backend and frontend images locally instead of pulling from Docker Hub"
      build_prod_images
      # Add local override to prevent pulling from Docker Hub (overrides pull_policy: always)
      COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.local.yml"
      BUILD_CMD=""
    else
      echo "🔄 Resetting in PRODUCTION mode (pulling from Docker Hub)..."
      BUILD_CMD=""
    fi
  else
    # Development: Auto-loads docker-compose.override.yml (always builds)
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.override.yml"
    echo "🔄 Resetting in DEVELOPMENT mode (auto-loads docker-compose.override.yml)..."
    BUILD_CMD="--build"
  fi

  # Add GPU overlay if NVIDIA GPU is detected and Container Toolkit is available
  if [ "$DOCKER_RUNTIME" = "nvidia" ] && [ -f "docker-compose.gpu.yml" ]; then
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu.yml"
    echo "🎯 Adding GPU overlay (docker-compose.gpu.yml) for NVIDIA acceleration"
  fi

  # Add GPU scaling overlay if requested
  if [ -n "$GPU_SCALE_FLAG" ]; then
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu-scale.yml"
    echo "🎯 Adding GPU scaling overlay (docker-compose.gpu-scale.yml)"
  fi

  # Add lite overlay if requested (cloud-only ASR, no GPU)
  if [ -n "$LITE_FLAG" ]; then
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.lite.yml"
    echo "☁️  Adding lite overlay (docker-compose.lite.yml)"
  fi

  # Add NGINX reverse proxy if NGINX_SERVER_NAME is set
  if [ -n "$NGINX_SERVER_NAME" ]; then
    if [ -f "docker-compose.nginx.yml" ]; then
      # Check for SSL certificates
      CERT_FILE="${NGINX_CERT_FILE:-./nginx/ssl/server.crt}"
      KEY_FILE="${NGINX_CERT_KEY:-./nginx/ssl/server.key}"

      if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
        echo ""
        echo "⚠️  SSL certificates not found!"
        echo "   Expected: $CERT_FILE and $KEY_FILE"
        echo ""
        echo "   Generate certificates with:"
        echo "   ./scripts/generate-ssl-cert.sh $NGINX_SERVER_NAME --auto-ip"
        echo ""
        echo "   Or disable NGINX by commenting out NGINX_SERVER_NAME in .env"
        exit 1
      fi

      COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.nginx.yml"
      echo "🔒 Adding NGINX reverse proxy (HTTPS enabled)"
      echo "   Server name: $NGINX_SERVER_NAME"
      echo "   Access URL: https://$NGINX_SERVER_NAME"
    else
      echo "⚠️  NGINX_SERVER_NAME is set but docker-compose.nginx.yml not found"
    fi
  fi

  echo "🛑 Stopping all containers and removing volumes..."
  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES down -v

  # Create necessary directories
  create_required_dirs

  # Fix model cache permissions for non-root container
  fix_model_cache_permissions

  # Start all services - docker compose handles dependency ordering via depends_on
  echo "🚀 Starting all services..."
  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES up -d $BUILD_CMD

  # Wait for backend to be ready for database operations
  echo "⏳ Waiting for backend to be ready..."
  wait_for_backend_health

  # Note: Database tables, admin user, and default tags are automatically created
  # by PostgreSQL's entrypoint from /docker-entrypoint-initdb.d/init_db.sql
  # on first container start (when postgres_data volume is empty after 'down -v')

  echo "✅ Setup complete!"

  # Print access information
  print_access_info
}

# Function to backup the database
backup_database() {
  TIMESTAMP=$(date +%Y%m%d_%H%M%S)
  BACKUP_FILE="opentranscribe_backup_${TIMESTAMP}.sql"

  echo "📦 Creating database backup: ${BACKUP_FILE}..."
  mkdir -p ./backups

  if docker compose exec -T postgres pg_dump -U postgres opentranscribe > "./backups/${BACKUP_FILE}"; then
    echo "✅ Backup created successfully: ./backups/${BACKUP_FILE}"
  else
    echo "❌ Backup failed."
    exit 1
  fi
}

# Function to restore database from backup
restore_database() {
  BACKUP_FILE=$1

  if [ -z "$BACKUP_FILE" ]; then
    echo "❌ Error: Backup file not specified."
    echo "Usage: ./opentr.sh restore [backup_file]"
    exit 1
  fi

  if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Error: Backup file not found: $BACKUP_FILE"
    exit 1
  fi

  echo "🔄 Restoring database from ${BACKUP_FILE}..."

  # Stop services that use the database
  docker compose stop backend celery-worker celery-beat

  # Restore the database
  if docker compose exec -T postgres psql -U postgres opentranscribe < "$BACKUP_FILE"; then
    echo "✅ Database restored successfully."
    echo "🔄 Restarting services..."
    docker compose start backend celery-worker celery-beat
  else
    echo "❌ Database restore failed."
    echo "🔄 Restarting services anyway..."
    docker compose start backend celery-worker celery-beat
    exit 1
  fi
}

# Function to restart backend services (backend, celery, flower) without database reset
restart_backend() {
  echo "🔄 Restarting backend services (backend, celery-worker, celery-beat, flower)..."

  # Restart backend services in place
  docker compose restart backend celery-worker celery-beat flower

  echo "✅ Backend services restarted successfully."

  # Display container status
  echo "📊 Container status:"
  docker compose ps
}

# Function to restart frontend only
restart_frontend() {
  echo "🔄 Restarting frontend service..."

  # Restart frontend in place
  docker compose restart frontend

  echo "✅ Frontend service restarted successfully."

  # Display container status
  echo "📊 Container status:"
  docker compose ps
}

# Function to restart all services without resetting the database
restart_all() {
  echo "🔄 Restarting all services without database reset..."

  # Restart all services in place - docker compose handles dependency ordering
  docker compose restart

  echo "✅ All services restarted successfully."

  # Display container status
  echo "📊 Container status:"
  docker compose ps
}

# Function to remove containers and data volumes (but preserve images)
remove_system() {
  echo "🗑️ Removing OpenTranscribe containers and data volumes..."

  # Stop and remove containers and volumes
  # Use MAX_COMPOSE_FILES to ensure all containers from all compose files are stopped
  echo "🗑️ Stopping containers and removing data volumes..."
  # shellcheck disable=SC2086
  docker compose $MAX_COMPOSE_FILES down -v

  echo "✅ Containers and data volumes removed. Images preserved for faster rebuilds."
}

# Function to purge everything including images (most destructive)
purge_system() {
  echo "💥 Purging ALL OpenTranscribe resources including images..."

  # Stop and remove everything
  # Use MAX_COMPOSE_FILES to ensure all containers from all compose files are stopped
  echo "🗑️ Stopping and removing containers, volumes, and images..."
  # shellcheck disable=SC2086
  docker compose $MAX_COMPOSE_FILES down -v --rmi all

  # Remove any remaining OpenTranscribe images
  echo "🗑️ Removing any remaining OpenTranscribe images..."
  docker images --filter "reference=transcribe-app*" -q | xargs -r docker rmi -f
  docker images --filter "reference=*opentranscribe*" -q | xargs -r docker rmi -f

  echo "✅ Complete purge finished. Everything removed."
}

# Function to check health of all services
check_health() {
  echo "🩺 Checking health of all services..."

  # Check if services are running
  docker compose ps

  # Check specific service health if available
  echo "📋 Backend health:"
  docker compose exec -T backend curl -s http://localhost:8080/health || echo "⚠️ Backend health check failed."

  echo "📋 Redis health:"
  docker compose exec -T redis redis-cli ping || echo "⚠️ Redis health check failed."

  echo "📋 Postgres health:"
  docker compose exec -T postgres pg_isready -U postgres || echo "⚠️ Postgres health check failed."

  echo "📋 OpenSearch health:"
  docker compose exec -T opensearch curl -s http://localhost:9200 > /dev/null && echo "OK" || echo "⚠️ OpenSearch health check failed."

  echo "📋 MinIO health:"
  docker compose exec -T minio curl -s http://localhost:9000/minio/health/live > /dev/null && echo "OK" || echo "⚠️ MinIO health check failed."

  # NGINX health (only if configured)
  if [ -n "$NGINX_SERVER_NAME" ]; then
    echo "📋 NGINX health:"
    if curl -s -k https://localhost:${NGINX_HTTPS_PORT:-443}/health > /dev/null 2>&1 || \
       curl -s http://localhost:${NGINX_HTTP_PORT:-80}/health > /dev/null 2>&1; then
      echo "OK (https://$NGINX_SERVER_NAME)"
    else
      # Check if container is running but not responding
      if docker compose ps nginx 2>/dev/null | grep -q "Up"; then
        echo "⚠️ NGINX running but not responding"
      else
        echo "⚠️ NGINX not running"
      fi
    fi
  fi

  echo "✅ Health check complete."
}

#######################
# MAIN SCRIPT
#######################

# Process commands
if [ $# -eq 0 ]; then
  show_help
  exit 0
fi

# Check Docker is available for all commands
check_docker

# Process the command
case "$1" in
  start)
    shift  # Remove 'start' command
    start_app "$@"  # Pass all remaining arguments
    ;;

  stop)
    echo "🛑 Stopping all containers..."
    # Use MAX_COMPOSE_FILES to ensure all containers from all compose files are stopped
    # shellcheck disable=SC2086
    docker compose $MAX_COMPOSE_FILES down
    echo "✅ All containers stopped."
    ;;

  reset)
    shift  # Remove 'reset' command
    echo "⚠️ Warning: This will delete all data! Continue? (y/n)"
    read -r confirm
    if [[ $confirm =~ ^[Yy]$ ]]; then
      reset_and_init "$@"  # Pass all remaining arguments
    else
      echo "❌ Reset cancelled."
    fi
    ;;

  logs)
    SERVICE=${2:-}
    if [ -z "$SERVICE" ]; then
      echo "📋 Showing logs for all services... (press Ctrl+C to exit)"
      docker compose logs -f
    else
      echo "📋 Showing logs for $SERVICE... (press Ctrl+C to exit)"
      docker compose logs -f "$SERVICE"
    fi
    ;;

  status)
    echo "📊 Container status:"
    docker compose ps
    ;;

  shell)
    SERVICE=${2:-backend}
    echo "🔧 Opening shell in $SERVICE container..."
    docker compose exec "$SERVICE" /bin/bash || docker compose exec "$SERVICE" /bin/sh
    ;;

  backup)
    backup_database
    ;;

  restore)
    restore_database "$2"
    ;;

  restart-backend)
    restart_backend
    ;;

  restart-frontend)
    restart_frontend
    ;;

  restart-all)
    restart_all
    ;;

  rebuild-backend)
    echo "🔨 Rebuilding backend services..."
    detect_and_configure_hardware

    # Build compose file list
    COMPOSE_FILES="-f docker-compose.yml -f docker-compose.override.yml"

    # Add GPU overlay if NVIDIA GPU is detected
    if [ "$DOCKER_RUNTIME" = "nvidia" ] && [ -f "docker-compose.gpu.yml" ]; then
      COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu.yml"
    fi

    # shellcheck disable=SC2086
    docker compose $COMPOSE_FILES up -d --build backend celery-worker celery-beat flower
    echo "✅ Backend services rebuilt successfully."
    ;;

  rebuild-frontend)
    echo "🔨 Rebuilding frontend service..."
    docker compose up -d --build frontend
    echo "✅ Frontend service rebuilt successfully."
    ;;

  remove)
    echo "⚠️ Warning: This will remove all data volumes! Continue? (y/n)"
    read -r confirm
    if [[ $confirm =~ ^[Yy]$ ]]; then
      remove_system
    else
      echo "❌ Remove cancelled."
    fi
    ;;

  purge)
    echo "⚠️ WARNING: This will remove EVERYTHING including images! Continue? (y/n)"
    read -r confirm
    if [[ $confirm =~ ^[Yy]$ ]]; then
      purge_system
    else
      echo "❌ Purge cancelled."
    fi
    ;;

  health)
    check_health
    ;;

  build)
    echo "🔨 Rebuilding containers..."
    detect_and_configure_hardware

    # Build compose file list
    COMPOSE_FILES="-f docker-compose.yml -f docker-compose.override.yml"

    # Add GPU overlay if NVIDIA GPU is detected
    if [ "$DOCKER_RUNTIME" = "nvidia" ] && [ -f "docker-compose.gpu.yml" ]; then
      COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu.yml"
      echo "🎯 Including GPU overlay for build"
    fi

    # shellcheck disable=SC2086
    docker compose $COMPOSE_FILES build
    echo "✅ Build complete. Use './opentr.sh start' to start the application."
    ;;

  help|--help|-h)
    show_help
    ;;

  *)
    echo "❌ Unknown command: $1"
    show_help
    exit 1
    ;;
esac

exit 0
