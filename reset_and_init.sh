#!/bin/bash
# Script to reset OpenTranscribe: stop containers, remove volumes, restart, and initialize DB

# Source common functions
source ./scripts/common.sh

# Default to development mode unless specified
ENVIRONMENT=${1:-dev}

echo "🔄 Running reset and initialize for OpenTranscribe in ${ENVIRONMENT} mode..."

# Ensure Docker is running
check_docker

echo "🛑 Stopping all containers..."
docker compose down

echo "🗑️ Removing volumes..."
docker compose down -v

# Create necessary directories
create_required_dirs

# Start environment and get frontend service name
FRONTEND_SERVICE=$(start_environment $ENVIRONMENT)

echo "⏳ Waiting for database to be ready..."
sleep 10

echo "🗄️ Setting up database..."
# Execute SQL dump file to initialize the database
docker compose exec -T postgres psql -U postgres -d opentranscribe < ./database/init_db.sql

echo "👤 Creating admin user..."
docker compose exec backend python -m app.initial_data

echo "✅ Setup complete!"

# Start log tailing
start_logs $FRONTEND_SERVICE

echo "📊 Log tailing started in background. You can now test the application."
# Print access information
print_access_info
