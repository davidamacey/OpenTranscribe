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

# Start services one by one for better debugging
echo "🚀 Starting database service..."
docker compose up -d --build postgres
sleep 5

echo "🚀 Starting Redis service..."
docker compose up -d --build redis
sleep 3

echo "🚀 Starting MinIO service..."
docker compose up -d --build minio
sleep 3

echo "🚀 Starting OpenSearch service..."
docker compose up -d --build opensearch
sleep 5

echo "🚀 Starting backend service..."
docker compose up -d --build backend
sleep 5

# Check if backend is healthy
if ! docker compose ps | grep backend | grep "(healthy)" > /dev/null; then
  echo "⚠️ Backend might not be fully healthy yet, but continuing..."
  docker compose logs backend --tail 20
fi

echo "🚀 Starting Celery worker..."
docker compose up -d --build celery-worker
sleep 3

echo "🚀 Starting frontend service..."
if [ "$ENVIRONMENT" == "prod" ]; then
  docker compose up -d --build frontend-prod
  FRONTEND_SERVICE="frontend-prod"
else
  docker compose up -d --build frontend
  FRONTEND_SERVICE="frontend"
fi

echo "🚀 Starting Flower service..."
docker compose up -d --build flower

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
