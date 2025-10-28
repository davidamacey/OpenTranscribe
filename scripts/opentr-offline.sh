#!/bin/bash

# OpenTranscribe Offline Management Script
# Wrapper around standard OpenTranscribe operations for offline deployments
# Usage: ./opentr-offline.sh [command] [options]

# Installation directory
INSTALL_DIR="/opt/opentranscribe"
# Use base + offline override pattern
COMPOSE_FILES="-f $INSTALL_DIR/docker-compose.yml -f $INSTALL_DIR/docker-compose.offline.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

#######################
# HELPER FUNCTIONS
#######################

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Display help menu
show_help() {
    echo -e "${CYAN}🚀 OpenTranscribe Offline Management${NC}"
    echo "-------------------------------"
    echo "Usage: ./opentr.sh [command] [options]"
    echo ""
    echo "Basic Commands:"
    echo "  start               - Start all services"
    echo "  stop                - Stop all services"
    echo "  restart             - Restart all services"
    echo "  status              - Show service status"
    echo "  logs [service]      - View logs (all services by default)"
    echo ""
    echo "Service Management:"
    echo "  restart-backend     - Restart backend services only"
    echo "  restart-frontend    - Restart frontend only"
    echo "  shell [service]     - Open shell in a service container"
    echo ""
    echo "Maintenance:"
    echo "  health              - Check health status of all services"
    echo "  clean               - Clean up stopped containers and unused volumes"
    echo "  backup              - Create database backup"
    echo "  help                - Show this help menu"
    echo ""
    echo "Examples:"
    echo "  ./opentr.sh start"
    echo "  ./opentr.sh logs backend"
    echo "  ./opentr.sh restart-backend"
    echo ""
}

# Check if running from correct directory
check_location() {
    if [ ! -f "$INSTALL_DIR/docker-compose.yml" ] || [ ! -f "$INSTALL_DIR/docker-compose.offline.yml" ]; then
        print_error "Docker Compose files not found in: $INSTALL_DIR"
        print_info "Required: docker-compose.yml and docker-compose.offline.yml"
        exit 1
    fi
}

# Check if .env file exists and has required values
check_env() {
    if [ ! -f "$INSTALL_DIR/.env" ]; then
        print_error "Configuration file not found: $INSTALL_DIR/.env"
        exit 1
    fi

    # Check for offline mode (HF_HUB_OFFLINE=1 means models are pre-installed, no token needed)
    # shellcheck source=/dev/null  # Runtime .env file, not available during static analysis
    source "$INSTALL_DIR/.env"

    # In offline mode, HuggingFace token is NOT required (models are pre-downloaded)
    if [ "${HF_HUB_OFFLINE}" != "1" ]; then
        # Not in offline mode - check if token is set
        if [ -z "$HUGGINGFACE_TOKEN" ]; then
            print_warning "HUGGINGFACE_TOKEN is not set in .env file"
            print_warning "Speaker diarization will not work without it"
            print_info "Get your token at: https://huggingface.co/settings/tokens"
        fi
    fi
}

# Compose command wrapper
dc() {
    docker compose $COMPOSE_FILES "$@"
}

#######################
# COMMANDS
#######################

cmd_start() {
    print_info "Starting OpenTranscribe..."
    check_env

    dc up -d

    print_success "OpenTranscribe started"
    print_info "Access the application at: http://localhost:5173"
    print_info "View logs with: ./opentr.sh logs"
}

cmd_stop() {
    print_info "Stopping OpenTranscribe..."

    dc down

    print_success "OpenTranscribe stopped"
}

cmd_restart() {
    print_info "Restarting OpenTranscribe..."

    dc restart

    print_success "OpenTranscribe restarted"
}

cmd_status() {
    print_info "Service Status:"
    echo ""

    dc ps
}

cmd_logs() {
    local service="${1:-}"

    if [ -n "$service" ]; then
        print_info "Viewing logs for: $service"
        dc logs -f "$service"
    else
        print_info "Viewing logs for all services (Ctrl+C to exit)"
        dc logs -f
    fi
}

cmd_restart_backend() {
    print_info "Restarting backend services..."

    dc restart backend celery-worker flower

    print_success "Backend services restarted"
}

cmd_restart_frontend() {
    print_info "Restarting frontend..."

    dc restart frontend

    print_success "Frontend restarted"
}

cmd_shell() {
    local service="${1:-backend}"

    print_info "Opening shell in $service container..."

    dc exec "$service" /bin/bash
}

cmd_health() {
    print_info "Checking service health..."
    echo ""

    # Check each service
    local services=("postgres" "redis" "minio" "opensearch" "backend" "celery-worker" "frontend" "flower")

    for service in "${services[@]}"; do
        if dc ps "$service" | grep -q "Up"; then
            local health
            health=$(dc ps "$service" | grep "$service" | awk '{print $6}')
            if [[ "$health" == *"healthy"* ]]; then
                echo -e "  ${GREEN}✓${NC} $service - healthy"
            elif [[ "$health" == *"unhealthy"* ]]; then
                echo -e "  ${RED}✗${NC} $service - unhealthy"
            else
                echo -e "  ${YELLOW}⚠${NC} $service - running (no health check)"
            fi
        else
            echo -e "  ${RED}✗${NC} $service - not running"
        fi
    done
    echo ""
}

cmd_clean() {
    print_warning "This will remove OpenTranscribe containers and volumes"
    print_warning "All data will be lost (database, uploads, models cache)"
    read -p "Continue? (y/N) " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Cancelled"
        exit 0
    fi

    print_info "Stopping OpenTranscribe services..."
    dc down

    print_info "Removing OpenTranscribe containers and volumes..."
    dc down -v

    print_success "Cleanup complete - OpenTranscribe containers and volumes removed"
    print_info "Models cache preserved at: ${MODEL_CACHE_DIR:-/opt/opentranscribe/models}"
}

cmd_backup() {
    print_info "Creating database backup..."

    local backup_dir="$INSTALL_DIR/backups"
    mkdir -p "$backup_dir"

    local backup_file
    backup_file="$backup_dir/opentranscribe_backup_$(date +%Y%m%d_%H%M%S).sql"

    if dc exec -T postgres pg_dump -U postgres opentranscribe > "$backup_file"; then
        print_success "Backup created: $backup_file"
        local size
        size=$(du -sh "$backup_file" | cut -f1)
        print_info "Backup size: $size"
    else
        print_error "Backup failed"
        exit 1
    fi
}

#######################
# MAIN
#######################

main() {
    # Check if we're in the right location
    check_location

    # Get command
    local command="${1:-help}"
    shift || true

    case "$command" in
        start)
            cmd_start
            ;;
        stop)
            cmd_stop
            ;;
        restart)
            cmd_restart
            ;;
        status)
            cmd_status
            ;;
        logs)
            cmd_logs "$@"
            ;;
        restart-backend)
            cmd_restart_backend
            ;;
        restart-frontend)
            cmd_restart_frontend
            ;;
        shell)
            cmd_shell "$@"
            ;;
        health)
            cmd_health
            ;;
        clean)
            cmd_clean
            ;;
        backup)
            cmd_backup
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "Unknown command: $command"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
