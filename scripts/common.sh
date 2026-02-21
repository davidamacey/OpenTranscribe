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
  local docker_output
  docker_output=$(docker info 2>&1)
  if [ $? -eq 0 ]; then
    return 0
  fi

  if echo "$docker_output" | grep -qi "permission denied"; then
    echo ""
    echo "❌ Error: Permission denied accessing Docker."
    echo ""
    echo "Your user ($USER) is not in the 'docker' group."
    echo "Run the following commands, then log out and back in:"
    echo ""
    echo "  sudo usermod -aG docker \$USER"
    echo "  newgrp docker"
    echo ""
    echo "Or re-run this script with sudo."
  elif echo "$docker_output" | grep -qi "cannot connect\|is the docker daemon running\|no such file"; then
    echo ""
    echo "❌ Error: Docker daemon is not running."
    echo ""
    echo "Start it with:"
    echo "  sudo systemctl start docker"
    echo ""
    echo "To start on boot:  sudo systemctl enable docker"
  else
    echo ""
    echo "❌ Error: Failed to connect to Docker."
    echo "Details: $docker_output"
  fi
  exit 1
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

  # Ensure all required subdirectories exist
  mkdir -p "$MODEL_CACHE_DIR/huggingface" "$MODEL_CACHE_DIR/torch" "$MODEL_CACHE_DIR/nltk_data" "$MODEL_CACHE_DIR/sentence-transformers" "$MODEL_CACHE_DIR/opensearch-ml" 2>/dev/null

  # Check ownership of parent AND all subdirectories (subdirs may be root-owned
  # even if the parent is correctly owned by UID 1000)
  local needs_fix=false
  for dir in "$MODEL_CACHE_DIR" "$MODEL_CACHE_DIR"/*/; do
    [ -d "$dir" ] || continue
    local owner
    owner=$(stat -c '%u' "$dir" 2>/dev/null || stat -f '%u' "$dir" 2>/dev/null || echo "unknown")
    if [ "$owner" != "1000" ]; then
      needs_fix=true
      break
    fi
  done

  if [ "$needs_fix" = true ]; then
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

# Ensure OpenSearch neural models are downloaded for offline capability
ensure_opensearch_models() {
  # Read MODEL_CACHE_DIR from .env if it exists
  local MODEL_CACHE_DIR=""
  if [ -f .env ]; then
    MODEL_CACHE_DIR=$(grep 'MODEL_CACHE_DIR' .env | grep -v '^#' | cut -d'#' -f1 | cut -d'=' -f2 | tr -d ' "' | head -1)
  fi

  # Use default if not set
  MODEL_CACHE_DIR="${MODEL_CACHE_DIR:-./models}"

  # Check if OpenSearch neural models directory exists and has content
  local opensearch_models_dir="$MODEL_CACHE_DIR/opensearch-ml"

  # Check if default model exists (all-MiniLM-L6-v2)
  if [ -d "$opensearch_models_dir/all-MiniLM-L6-v2" ] && [ -n "$(ls -A "$opensearch_models_dir/all-MiniLM-L6-v2" 2>/dev/null)" ]; then
    echo "✅ OpenSearch neural models found"
    return 0
  fi

  # Models not found - try to download them
  echo "📥 OpenSearch neural models not found - attempting download..."
  echo "   (Default model: all-MiniLM-L6-v2, ~80MB)"

  # Check if download-models.py exists
  if [ ! -f "./scripts/download-models.py" ]; then
    echo "⚠️  Warning: download-models.py not found - models will download on first use"
    return 1
  fi

  # Check if Docker is available
  if ! command -v docker &> /dev/null; then
    echo "⚠️  Warning: Docker not found - models will download on first use"
    return 1
  fi

  # Check if backend Docker image exists (pull if not)
  if ! docker image inspect davidamacey/opentranscribe-backend:latest > /dev/null 2>&1; then
    echo "   Backend Docker image not found locally - pulling from Docker Hub..."
    if ! docker pull davidamacey/opentranscribe-backend:latest > /dev/null 2>&1; then
      echo "⚠️  Warning: Could not pull backend image - models will download on first use"
      return 1
    fi
  fi

  # Set environment to download only default OpenSearch model
  export OPENSEARCH_MODELS="all-MiniLM-L6-v2"

  # Run download script (only for OpenSearch models - others handled separately)
  echo "📥 Downloading OpenSearch neural model (all-MiniLM-L6-v2)..."

  # Get Hugging Face token from .env if available
  local HF_TOKEN=""
  if [ -f .env ]; then
    HF_TOKEN=$(grep '^HUGGINGFACE_TOKEN=' .env | grep -v '^#' | cut -d'=' -f2 | tr -d ' "' | head -1)
  fi

  # Detect GPU
  local use_gpu="false"
  local gpu_args=""
  if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    use_gpu="true"
    if [ -n "$GPU_DEVICE_ID" ]; then
      gpu_args="--gpus device=${GPU_DEVICE_ID}"
    else
      gpu_args="--gpus all"
    fi
  fi

  # Create opensearch-ml directory if needed
  mkdir -p "$opensearch_models_dir"

  # Download OpenSearch models using Docker (same approach as transcription models)
  # shellcheck disable=SC2086
  docker run --rm \
      $gpu_args \
      -e CUDA_VISIBLE_DEVICES=0 \
      -e HUGGINGFACE_TOKEN="${HF_TOKEN}" \
      -e USE_GPU="${use_gpu}" \
      -e OPENSEARCH_MODELS="all-MiniLM-L6-v2" \
      -v "$(realpath "$opensearch_models_dir"):/home/appuser/.cache/opensearch-ml" \
      -v "./scripts/download-models.py:/app/download-models.py:ro" \
      davidamacey/opentranscribe-backend:latest \
      python /app/download-models.py 2>&1 | grep -E "(Downloading|Downloaded|ERROR|WARNING|Success)" || true

  # Check if model was actually downloaded
  if [ -d "$opensearch_models_dir/all-MiniLM-L6-v2" ] && [ -n "$(ls -A "$opensearch_models_dir/all-MiniLM-L6-v2" 2>/dev/null)" ]; then
    echo "✅ OpenSearch neural model downloaded and cached"
    return 0
  else
    echo ""
    echo "⚠️  OpenSearch model download was unsuccessful"
    echo "   Don't worry - models will auto-download during backend startup"
    echo "   This is normal and search will work correctly"
    echo ""
    return 1
  fi
}

#######################
# INFO FUNCTIONS
#######################

# Print access information for all services
# Detects NGINX configuration and shows appropriate URLs
print_access_info() {
  # Check if NGINX is configured (via NGINX_SERVER_NAME env var or .env file)
  # In dev mode, NGINX is never used (Vite serves frontend directly)
  local domain=""
  local protocol="https"
  local https_port="${NGINX_HTTPS_PORT:-443}"

  # Only show NGINX info in production mode
  if [ "$ENVIRONMENT" != "dev" ]; then
    # Check environment variable first
    if [ -n "$NGINX_SERVER_NAME" ]; then
      domain="$NGINX_SERVER_NAME"
    # Then check .env file
    elif [ -f .env ]; then
      domain=$(grep '^NGINX_SERVER_NAME=' .env | grep -v '^#' | cut -d'=' -f2 | tr -d ' "' | head -1)
      https_port=$(grep '^NGINX_HTTPS_PORT=' .env | grep -v '^#' | cut -d'=' -f2 | tr -d ' "' | head -1)
      https_port="${https_port:-443}"
    fi
  fi

  echo ""
  if [ -n "$domain" ]; then
    # NGINX reverse proxy mode - single entry point with HTTPS
    local port_suffix=""
    if [ "$https_port" != "443" ]; then
      port_suffix=":$https_port"
    fi

    echo "🔒 NGINX Reverse Proxy Mode (HTTPS)"
    echo "🌐 Access the application at:"
    echo "   - Frontend:          ${protocol}://${domain}${port_suffix}"
    echo "   - API:               ${protocol}://${domain}${port_suffix}/api"
    echo "   - API Documentation: ${protocol}://${domain}${port_suffix}/api/docs"
    echo "   - Flower Dashboard:  ${protocol}://${domain}${port_suffix}/flower/"
    echo "   - MinIO Console:     ${protocol}://${domain}${port_suffix}/minio/"
    echo ""
    echo "📝 Note: Browser microphone recording is now available via HTTPS!"
    echo "   If you see certificate warnings, trust the certificate on your device."
    echo "   See: docs/NGINX_SETUP.md for instructions"
  else
    # Direct container access mode (development default)
    echo "🌐 Access the application at:"
    echo "   - Frontend:            http://localhost:5173"
    echo "   - API:                 http://localhost:5174/api"
    echo "   - API Documentation:   http://localhost:5174/docs"
    echo "   - MinIO Console:       http://localhost:5179"
    echo "   - Flower Dashboard:    http://localhost:5175/flower"
    echo "   - OpenSearch:          http://localhost:5180"
    echo ""
    echo "📝 Note: Microphone recording only works on localhost in this mode."
    echo "   For HTTPS access from other devices, set NGINX_SERVER_NAME in .env"
    echo "   See: docs/NGINX_SETUP.md for instructions"
  fi
  echo ""
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
