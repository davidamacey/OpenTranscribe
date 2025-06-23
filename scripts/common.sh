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
}

#######################
# DOCKER FUNCTIONS
#######################

# Wait for backend to be healthy with timeout
wait_for_backend_health() {
  TIMEOUT=60
  INTERVAL=2
  ELAPSED=0
  
  while [ $ELAPSED -lt $TIMEOUT ]; do
    if docker compose ps | grep backend | grep "(healthy)" > /dev/null; then
      echo "✅ Backend is healthy!"
      return 0
    fi
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
    echo "⏳ Waiting for backend... ($ELAPSED/$TIMEOUT seconds)"
  done
  
  echo "⚠️ Backend health check timed out, but continuing anyway..."
  docker compose logs backend --tail 20
  return 1
}

# Start containers based on environment
start_environment() {
  local environment=$1
  
  echo "🔄 Starting containers in ${environment} mode..."
  if [ "$environment" == "prod" ]; then
    # Start with production configuration (using frontend-prod service)
    # Start base infrastructure services first with a single command
    echo "🚀 Starting infrastructure services (postgres, redis, minio, opensearch)..."
    docker compose up -d --build postgres redis minio opensearch
    
    # Then start the application services that depend on infrastructure
    echo "🚀 Starting application services (backend, celery-worker, frontend-prod, flower)..."
    docker compose up -d --build backend celery-worker frontend-prod flower
    FRONTEND_SERVICE="frontend-prod"
    echo "💼 Production mode: Using optimized build with NGINX"
  else
    # Start with development configuration (using frontend service for hot reload)
    # Start base infrastructure services first with a single command
    echo "🚀 Starting infrastructure services (postgres, redis, minio, opensearch)..."
    docker compose up -d --build postgres redis minio opensearch
    
    # Then start the application services that depend on infrastructure
    echo "🚀 Starting application services (backend, celery-worker, frontend, flower)..."
    docker compose up -d --build backend celery-worker frontend flower
    FRONTEND_SERVICE="frontend"
    echo "🧪 Development mode: Hot reload enabled for faster development"
  fi
  
  # Return the frontend service name
  echo $FRONTEND_SERVICE
}

# Start log tailing in background
start_logs() {
  local frontend_service=$1
  
  echo "📋 Opening logs in separate terminal windows..."
  # Open backend logs in a new terminal window (use & to run in background)
  docker compose logs -f backend &

  # Open frontend logs in a new terminal window
  docker compose logs -f $frontend_service &

  # Open celery worker logs
  docker compose logs -f celery-worker &
  
  echo "📊 Log tailing started in background."
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
