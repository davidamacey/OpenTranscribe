#!/bin/bash

# OpenTranscribe Utility Script
# A comprehensive script for all OpenTranscribe operations
# Usage: ./opentr.sh [command] [options]

# Source common functions
# shellcheck source=scripts/common.sh
source ./scripts/common.sh

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
  echo "  start [dev|prod] [--build]  - Start the application (dev mode by default)"
  echo "                                --build: Build prod images locally (test before push)"
  echo "  stop                        - Stop OpenTranscribe containers"
  echo "  status                      - Show container status"
  echo "  logs [service]              - View logs (all services by default)"
  echo ""
  echo "Reset & Database Commands:"
  echo "  reset [dev|prod] [--build]  - Reset and reinitialize (deletes all data!)"
  echo "                                --build: Build prod images locally (test before push)"
  echo "  backup              - Create a database backup"
  echo "  restore [file]      - Restore database from backup"
  echo ""
  echo "Development Commands:"
  echo "  restart-backend     - Restart backend, celery & flower without database reset"
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
  echo "Examples:"
  echo "  ./opentr.sh start                # Start in development mode"
  echo "  ./opentr.sh start prod           # Start in production mode (pulls from Docker Hub)"
  echo "  ./opentr.sh start prod --build   # Test production build locally (before pushing)"
  echo "  ./opentr.sh reset dev            # Reset development environment"
  echo "  ./opentr.sh logs backend         # View backend logs"
  echo "  ./opentr.sh restart-backend      # Restart backend services only"
  echo ""
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
  export BACKEND_DOCKERFILE="Dockerfile.multiplatform"
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
  BUILD_FLAG=${2:-}

  echo "🚀 Starting OpenTranscribe in ${ENVIRONMENT} mode..."

  # Ensure Docker is running
  check_docker

  # Detect and configure hardware
  detect_and_configure_hardware

  # Set build environment
  export BUILD_ENV="$ENVIRONMENT"

  # Create necessary directories
  create_required_dirs

  # Fix model cache permissions for non-root container
  fix_model_cache_permissions

  if [ "$ENVIRONMENT" = "prod" ]; then
    # Production: Use base + prod override files
    # Note: INIT_DB_PATH uses default ./database/init_db.sql (same for all modes)

    if [ "$BUILD_FLAG" = "--build" ]; then
      echo "🔄 Starting services in PRODUCTION mode with LOCAL BUILD (testing before push)..."
      echo "⚠️  Note: This builds production images locally instead of pulling from Docker Hub"
      docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
    else
      echo "🔄 Starting services in PRODUCTION mode (pulling from Docker Hub)..."
      docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
    fi
  else
    # Development: Auto-loads docker-compose.override.yml (always builds)
    echo "🔄 Starting services in DEVELOPMENT mode (auto-loads docker-compose.override.yml)..."
    docker compose up -d --build
  fi

  # Display container status
  echo "📊 Container status:"
  docker compose ps

  # Print access information
  echo "✅ Services are starting up."
  print_access_info

  # Display log commands
  echo "📋 To view logs, run:"
  echo "- All logs: docker compose logs -f"
  echo "- Backend logs: docker compose logs -f backend"
  echo "- Frontend logs: docker compose logs -f frontend"
  echo "- Celery worker logs: docker compose logs -f celery-worker"

  # Print help information
  print_help_commands
}

# Function to reset and initialize the environment
reset_and_init() {
  ENVIRONMENT=${1:-dev}
  BUILD_FLAG=${2:-}

  echo "🔄 Running reset and initialize for OpenTranscribe in ${ENVIRONMENT} mode..."

  # Ensure Docker is running
  check_docker

  # Detect and configure hardware
  detect_and_configure_hardware

  # Set build environment
  export BUILD_ENV="$ENVIRONMENT"

  if [ "$ENVIRONMENT" = "prod" ]; then
    # Note: INIT_DB_PATH uses default ./database/init_db.sql (same for all modes)

    if [ "$BUILD_FLAG" = "--build" ]; then
      echo "🔄 Resetting in PRODUCTION mode with LOCAL BUILD (testing before push)..."
      echo "⚠️  Note: This builds production images locally instead of pulling from Docker Hub"
      COMPOSE_CMD="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
      BUILD_PROD=true
    else
      echo "🔄 Resetting in PRODUCTION mode (pulling from Docker Hub)..."
      COMPOSE_CMD="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
      BUILD_PROD=false
    fi
  else
    echo "🔄 Resetting in DEVELOPMENT mode (auto-loads docker-compose.override.yml)..."
    COMPOSE_CMD="docker compose"
    BUILD_PROD=false
  fi

  echo "🛑 Stopping all containers and removing volumes..."
  $COMPOSE_CMD down -v

  # Create necessary directories
  create_required_dirs

  # Fix model cache permissions for non-root container
  fix_model_cache_permissions

  # Start all services - docker compose handles dependency ordering via depends_on
  echo "🚀 Starting all services..."
  if [ "$ENVIRONMENT" = "prod" ] && [ "$BUILD_PROD" = "true" ]; then
    $COMPOSE_CMD up -d --build
  elif [ "$ENVIRONMENT" = "prod" ]; then
    $COMPOSE_CMD up -d
  else
    $COMPOSE_CMD up -d --build
  fi

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
  docker compose stop backend celery-worker

  # Restore the database
  if docker compose exec -T postgres psql -U postgres opentranscribe < "$BACKUP_FILE"; then
    echo "✅ Database restored successfully."
    echo "🔄 Restarting services..."
    docker compose start backend celery-worker
  else
    echo "❌ Database restore failed."
    echo "🔄 Restarting services anyway..."
    docker compose start backend celery-worker
    exit 1
  fi
}

# Function to restart backend services (backend, celery, flower) without database reset
restart_backend() {
  echo "🔄 Restarting backend services (backend, celery-worker, flower)..."

  # Restart backend services in place
  docker compose restart backend celery-worker flower

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
  # Note: docker compose down automatically loads docker-compose.yml + docker-compose.override.yml
  echo "🗑️ Stopping containers and removing data volumes..."
  docker compose down -v

  echo "✅ Containers and data volumes removed. Images preserved for faster rebuilds."
}

# Function to purge everything including images (most destructive)
purge_system() {
  echo "💥 Purging ALL OpenTranscribe resources including images..."

  # Stop and remove everything
  # Note: docker compose down automatically loads docker-compose.yml + docker-compose.override.yml
  echo "🗑️ Stopping and removing containers, volumes, and images..."
  docker compose down -v --rmi all

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
    ENV=${2:-dev}
    BUILD_FLAG=${3:-}
    start_app "$ENV" "$BUILD_FLAG"
    ;;

  stop)
    echo "🛑 Stopping all containers..."
    docker compose down
    echo "✅ All containers stopped."
    ;;

  reset)
    ENV=${2:-dev}
    BUILD_FLAG=${3:-}
    echo "⚠️ Warning: This will delete all data! Continue? (y/n)"
    read -r confirm
    if [[ $confirm =~ ^[Yy]$ ]]; then
      reset_and_init "$ENV" "$BUILD_FLAG"
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
    docker compose up -d --build backend celery-worker flower
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
    docker compose build
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
