#!/bin/bash

# OpenTranscribe Utility Script
# A comprehensive script for all OpenTranscribe operations
# Usage: ./opentr.sh [command] [options]

# Source common functions
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
  echo "  start [dev|prod]    - Start the application (dev mode by default)"
  echo "  stop                - Stop all containers"
  echo "  status              - Show container status"
  echo "  logs [service]      - View logs (all services by default)"
  echo ""
  echo "Reset & Database Commands:"
  echo "  reset [dev|prod]    - Reset and reinitialize (deletes all data!)"
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
  echo "Advanced Commands:"
  echo "  clean               - Clean up unused containers, images, volumes"
  echo "  init-db             - Initialize the database without resetting containers"
  echo "  health              - Check health status of all services"
  echo "  help                - Show this help menu"
  echo ""
  echo "Examples:"
  echo "  ./opentr.sh start           # Start in development mode"
  echo "  ./opentr.sh start prod      # Start in production mode"
  echo "  ./opentr.sh logs backend    # View backend logs"
  echo "  ./opentr.sh restart-backend # Restart backend services only"
  echo ""
}

# Function to start the environment
start_app() {
  ENVIRONMENT=${1:-dev}
  
  echo "🚀 Starting OpenTranscribe in ${ENVIRONMENT} mode..."
  
  # Ensure Docker is running
  check_docker
  
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
}

# Function to reset and initialize the environment
reset_and_init() {
  ENVIRONMENT=${1:-dev}
  
  echo "🔄 Running reset and initialize for OpenTranscribe in ${ENVIRONMENT} mode..."
  
  # Ensure Docker is running
  check_docker
  
  echo "🛑 Stopping all containers and removing volumes..."
  docker compose down -v
  
  # Create necessary directories
  create_required_dirs
  
  # Start infrastructure services in a single command for efficiency
  echo "🚀 Starting infrastructure services (postgres, redis, minio, opensearch)..."
  docker compose up -d --build postgres redis minio opensearch
  
  # Wait a bit for infrastructure services to be ready - reduced from multiple sleeps
  echo "⏳ Waiting for infrastructure services to initialize..."
  sleep 5
  
  # Start application services
  if [ "$ENVIRONMENT" == "prod" ]; then
    echo "🚀 Starting application services (backend, celery-worker, frontend-prod, flower)..."
    docker compose up -d --build backend celery-worker frontend-prod flower
    FRONTEND_SERVICE="frontend-prod"
  else
    echo "🚀 Starting application services (backend, celery-worker, frontend, flower)..."
    docker compose up -d --build backend celery-worker frontend flower
    FRONTEND_SERVICE="frontend"
  fi
  
  # Wait for backend to be ready for database operations
  echo "⏳ Waiting for backend to be ready..."
  wait_for_backend_health
  
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
}

# Function to backup the database
backup_database() {
  TIMESTAMP=$(date +%Y%m%d_%H%M%S)
  BACKUP_FILE="opentranscribe_backup_${TIMESTAMP}.sql"
  
  echo "📦 Creating database backup: ${BACKUP_FILE}..."
  mkdir -p ./backups
  
  docker compose exec -T postgres pg_dump -U postgres opentranscribe > ./backups/${BACKUP_FILE}
  
  if [ $? -eq 0 ]; then
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
  cat $BACKUP_FILE | docker compose exec -T postgres psql -U postgres opentranscribe
  
  if [ $? -eq 0 ]; then
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
  
  # Determine environment
  if docker compose ps | grep -q "frontend-prod"; then
    ENV="prod"
    FRONTEND_SERVICE="frontend-prod"
  else
    ENV="dev"
    FRONTEND_SERVICE="frontend"
  fi
  
  # Restart frontend in place
  docker compose restart $FRONTEND_SERVICE
  
  echo "✅ Frontend service restarted successfully."
  
  # Display container status
  echo "📊 Container status:"
  docker compose ps
}

# Function to restart all services without resetting the database
restart_all() {
  echo "🔄 Restarting all services without database reset..."
  
  # Determine environment
  if docker compose ps | grep -q "frontend-prod"; then
    ENV="prod"
    FRONTEND_SERVICE="frontend-prod"
  else
    ENV="dev"
    FRONTEND_SERVICE="frontend"
  fi
  
  # First restart infrastructure services
  echo "🔄 Restarting infrastructure services (redis, minio, opensearch)..."
  docker compose restart redis minio opensearch
  
  # Then restart application services
  echo "🔄 Restarting application services..."
  docker compose restart backend celery-worker flower $FRONTEND_SERVICE
  
  echo "✅ All services restarted successfully."
  
  # Display container status
  echo "📊 Container status:"
  docker compose ps
}

# Function to initialize the database without resetting containers
init_db() {
  echo "🗄️ Initializing database..."
  
  # Execute SQL dump file to initialize the database
  docker compose exec -T postgres psql -U postgres -d opentranscribe < ./database/init_db.sql
  
  echo "👤 Creating admin user..."
  docker compose exec backend python -m app.initial_data
  
  echo "✅ Database initialization complete."
}

# Function to clean up unused containers, images, and volumes
clean_system() {
  echo "🧹 Cleaning up the system..."
  
  echo "🗑️ Removing unused containers..."
  docker container prune -f
  
  echo "🗑️ Removing unused images..."
  docker image prune -f
  
  echo "🗑️ Removing unused volumes..."
  docker volume prune -f
  
  echo "✅ System cleanup complete."
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
    start_app $ENV
    ;;
    
  stop)
    echo "🛑 Stopping all containers..."
    docker compose down
    echo "✅ All containers stopped."
    ;;
    
  reset)
    ENV=${2:-dev}
    echo "⚠️ Warning: This will delete all data! Continue? (y/n)"
    read -r confirm
    if [[ $confirm =~ ^[Yy]$ ]]; then
      reset_and_init $ENV
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
      docker compose logs -f $SERVICE
    fi
    ;;
    
  status)
    echo "📊 Container status:"
    docker compose ps
    ;;
    
  shell)
    SERVICE=${2:-backend}
    echo "🔧 Opening shell in $SERVICE container..."
    docker compose exec $SERVICE /bin/bash || docker compose exec $SERVICE /bin/sh
    ;;
    
  backup)
    backup_database
    ;;
    
  restore)
    restore_database $2
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
    docker compose up -d --build backend celery-worker flower
    echo "✅ Backend services rebuilt successfully."
    ;;
    
  rebuild-frontend)
    # Determine environment
    if docker compose ps | grep -q "frontend-prod"; then
      ENV="prod"
      FRONTEND_SERVICE="frontend-prod"
    else
      ENV="dev"
      FRONTEND_SERVICE="frontend"
    fi
    
    echo "🔨 Rebuilding frontend service..."
    docker compose up -d --build $FRONTEND_SERVICE
    echo "✅ Frontend service rebuilt successfully."
    ;;
    
  init-db)
    init_db
    ;;
    
  clean)
    clean_system
    ;;
    
  health)
    check_health
    ;;
    
  build)
    echo "🔨 Rebuilding containers..."
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
