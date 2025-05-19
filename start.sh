#!/bin/bash

# OpenTranscribe Environment Startup Script
# Usage: ./start.sh [dev|prod]
# Default is development mode if no argument is provided

# Source common functions
source ./scripts/common.sh

# Default to development mode unless specified
ENVIRONMENT=${1:-dev}

echo "🚀 Starting OpenTranscribe in ${ENVIRONMENT} mode..."

# Ensure Docker is running
check_docker

# Stop any existing containers
echo "🛑 Stopping any existing containers..."
docker compose down

# Create necessary directories
create_required_dirs

# Start environment and get frontend service name
echo "🔄 Rebuilding and starting services in ${ENVIRONMENT} mode..."
FRONTEND_SERVICE=$(start_environment $ENVIRONMENT)

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
echo "- Frontend logs: docker compose logs -f $FRONTEND_SERVICE"
echo "- Celery worker logs: docker compose logs -f celery-worker"

# Print help information
print_help_commands
