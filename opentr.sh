#!/bin/bash

# OpenTranscribe Utility Script
# A convenience script for common operations
# Usage: ./opentr.sh [command] [options]

# Source common functions
source ./scripts/common.sh

# Display help menu
show_help() {
  echo "🚀 OpenTranscribe Utility Script"
  echo "-------------------------------"
  echo "Usage: ./opentr.sh [command] [options]"
  echo ""
  echo "Commands:"
  echo "  start [dev|prod]    - Start the application (dev mode by default)"
  echo "  stop                - Stop all containers"
  echo "  reset [dev|prod]    - Reset and reinitialize (deletes all data!)"
  echo "  logs [service]      - View logs (all services by default)"
  echo "  status              - Show container status"
  echo "  shell [service]     - Open a shell in a container"
  echo "  backup              - Create a database backup"
  echo "  restore [file]      - Restore database from backup"
  echo "  build               - Rebuild containers without starting"
  echo "  help                - Show this help menu"
  echo ""
  echo "Examples:"
  echo "  ./opentr.sh start           # Start in development mode"
  echo "  ./opentr.sh start prod      # Start in production mode"
  echo "  ./opentr.sh logs backend    # View backend logs"
  echo "  ./opentr.sh shell postgres  # Open shell in postgres container"
  echo ""
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
    ./start.sh $ENV
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
      ./reset_and_init.sh $ENV
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
