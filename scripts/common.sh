#!/bin/bash

# Common functions for OpenTranscribe shell scripts
# These functions are used by opentr.sh to provide common functionality
#
# Usage: source ./scripts/common.sh

#######################
# UTILITY FUNCTIONS
#######################

# Check if Docker is running and exit if not
check_docker() {
  if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running. Please start Docker and try again."
    exit 1
  fi
}

# Create required directories
create_required_dirs() {
  # Check if the models directory exists and create it if needed
  if [ ! -d "./backend/models" ]; then
    echo "📁 Creating models directory..."
    mkdir -p ./backend/models
  fi

  # Check if the temp directory exists and create it if needed
  if [ ! -d "./backend/temp" ]; then
    echo "📁 Creating temp directory..."
    mkdir -p ./backend/temp
  fi
}

# Fix model cache permissions for non-root container user
fix_model_cache_permissions() {
  # Read MODEL_CACHE_DIR from .env if it exists
  local MODEL_CACHE_DIR=""
  if [ -f .env ]; then
    MODEL_CACHE_DIR=$(grep 'MODEL_CACHE_DIR' .env | grep -v '^#' | cut -d'#' -f1 | cut -d'=' -f2 | tr -d ' "' | head -1)
  fi

  # Use default if not set
  MODEL_CACHE_DIR="${MODEL_CACHE_DIR:-./models}"

  # Check if model cache directory exists
  if [ ! -d "$MODEL_CACHE_DIR" ]; then
    echo "📁 Creating model cache directory: $MODEL_CACHE_DIR"
    mkdir -p "$MODEL_CACHE_DIR/huggingface" "$MODEL_CACHE_DIR/torch" "$MODEL_CACHE_DIR/nltk_data" "$MODEL_CACHE_DIR/sentence-transformers"
  fi

  # Check current ownership
  local current_owner
  current_owner=$(stat -c '%u' "$MODEL_CACHE_DIR" 2>/dev/null || stat -f '%u' "$MODEL_CACHE_DIR" 2>/dev/null || echo "unknown")

  # If directory is owned by root (0) or doesn't match container user (1000), fix permissions
  if [ "$current_owner" = "0" ] || [ "$current_owner" != "1000" ]; then
    echo "🔧 Fixing model cache permissions for non-root container (UID 1000)..."

    # Try using Docker to fix permissions (works without sudo)
    if command -v docker &> /dev/null; then
      if docker run --rm -v "$MODEL_CACHE_DIR:/models" busybox:latest sh -c "chown -R 1000:1000 /models && chmod -R 755 /models" > /dev/null 2>&1; then
        echo "✅ Model cache permissions fixed using Docker"
        return 0
      fi
    fi

    # Fallback: try direct chown if user has permissions
    if chown -R 1000:1000 "$MODEL_CACHE_DIR" > /dev/null 2>&1 && chmod -R 755 "$MODEL_CACHE_DIR" > /dev/null 2>&1; then
      echo "✅ Model cache permissions fixed"
      return 0
    fi

    # If both methods fail, show warning
    echo "⚠️  Warning: Could not automatically fix model cache permissions"
    echo "   If you encounter permission errors, run: ./scripts/fix-model-permissions.sh"
    return 1
  fi

  return 0
}

#######################
# INFO FUNCTIONS
#######################

# Print access information for all services
print_access_info() {
  echo "🌐 Access the application at:"
  echo "   - Frontend: http://localhost:5173"
  echo "   - API: http://localhost:5174/api"
  echo "   - API Documentation: http://localhost:5174/docs"
  echo "   - MinIO Console: http://localhost:5179"
  echo "   - Flower Dashboard: http://localhost:5175/flower"
  echo "   - OpenSearch Dashboards: http://localhost:5182"
}

#######################
# DOCKER FUNCTIONS
#######################

# Wait for backend to be healthy with timeout
# Uses $COMPOSE_CMD if set (for prod mode), otherwise uses 'docker compose' (for dev mode)
wait_for_backend_health() {
  TIMEOUT=60
  INTERVAL=2
  ELAPSED=0

  # Use COMPOSE_CMD if set (prod mode), otherwise default to 'docker compose' (dev mode)
  local CMD="${COMPOSE_CMD:-docker compose}"

  while [ $ELAPSED -lt $TIMEOUT ]; do
    if $CMD ps | grep backend | grep "(healthy)" > /dev/null; then
      echo "✅ Backend is healthy!"
      return 0
    fi
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
    echo "⏳ Waiting for backend... ($ELAPSED/$TIMEOUT seconds)"
  done

  echo "⚠️ Backend health check timed out, but continuing anyway..."
  $CMD logs backend --tail 20
  return 1
}

# Display quick reference commands
print_help_commands() {
  echo "⚡ Quick Commands Reference:"
  echo "   - Reset environment: ./opentr.sh reset [dev|prod]"
  echo "   - Stop all services: ./opentr.sh stop"
  echo "   - View logs: ./opentr.sh logs [service_name]"
  echo "   - Restart backend: ./opentr.sh restart-backend"
  echo "   - Rebuild after code changes: ./opentr.sh rebuild-backend or ./opentr.sh rebuild-frontend"
}
