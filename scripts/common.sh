#!/bin/bash

# Common functions for OpenTranscribe shell scripts

# Check if Docker is running
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

# Print access information
print_access_info() {
  echo "🌐 Access the application at:"
  echo "   - Frontend: http://localhost:5173"
  echo "   - API: http://localhost:8080/api"
  echo "   - API Documentation: http://localhost:8080/docs"
  echo "   - MinIO Console: http://localhost:9091"
  echo "   - Flower Dashboard: http://localhost:5555/flower"
}

# Start containers based on environment
start_environment() {
  local environment=$1
  
  echo "🔄 Starting containers in ${environment} mode..."
  if [ "$environment" == "prod" ]; then
    # Start with production configuration (using frontend-prod service)
    docker compose up -d --build backend postgres redis minio opensearch celery-worker frontend-prod flower
    FRONTEND_SERVICE="frontend-prod"
    echo "💼 Production mode: Using optimized build with NGINX"
  else
    # Start with development configuration (using frontend service for hot reload)
    docker compose up -d --build
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

# Display help commands
print_help_commands() {
  echo "🔄 To reset the environment completely: ./reset_and_init.sh [dev|prod]"
  echo "🛑 To stop all services: docker compose down"
  echo "📋 To view logs: docker compose logs -f [service_name]"
}
