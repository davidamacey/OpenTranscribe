#!/bin/bash
set -e

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

function show_help {
    echo -e "${BLUE}OpenTranscribe Management Script${NC}"
    echo ""
    echo "Usage: ./opentranscribe.sh [command]"
    echo ""
    echo "Commands:"
    echo "  start       Start all services"
    echo "  stop        Stop all services"
    echo "  restart     Restart all services"
    echo "  status      Show container status"
    echo "  logs [svc]  View logs (all or specific service)"
    echo "  update      Pull latest Docker images"
    echo "  clean       Remove all volumes and data (⚠️ CAUTION)"
    echo "  shell [svc] Open shell in container (default: backend)"
    echo "  config      Show current configuration"
    echo "  health      Check service health"
    echo "  help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./opentranscribe.sh start"
    echo "  ./opentranscribe.sh logs backend"
    echo "  ./opentranscribe.sh shell backend"
    echo ""
}

check_environment() {
    if [ ! -f .env ]; then
        echo -e "${RED}❌ .env file not found${NC}"
        echo "Please run the setup script first."
        exit 1
    fi
    
    if [ ! -f docker-compose.yml ]; then
        echo -e "${RED}❌ docker-compose.yml not found${NC}"
        echo "Please run the setup script first."
        exit 1
    fi
}

show_access_info() {
    # Source .env to get port values
    source .env 2>/dev/null || true
    
    echo -e "${GREEN}🌐 Access Information:${NC}"
    echo "  • Web Interface:     http://localhost:${FRONTEND_PORT:-5173}"
    echo "  • API Documentation: http://localhost:${BACKEND_PORT:-5174}/docs"
    echo "  • API Endpoint:      http://localhost:${BACKEND_PORT:-5174}/api"
    echo "  • Flower Dashboard:  http://localhost:${FLOWER_PORT:-5175}/flower"
    echo "  • MinIO Console:     http://localhost:${MINIO_CONSOLE_PORT:-5179}"
    echo ""
    echo -e "${YELLOW}⏳ Please wait a moment for all services to initialize...${NC}"
}

case "${1:-help}" in
    start)
        check_environment
        echo -e "${YELLOW}🚀 Starting OpenTranscribe...${NC}"
        # Use override file if it exists for development features
        if [ -f docker-compose.override.yml ]; then
            docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
        else
            docker compose up -d
        fi
        echo -e "${GREEN}✅ OpenTranscribe started!${NC}"
        show_access_info
        ;;
    stop)
        check_environment
        echo -e "${YELLOW}🛑 Stopping OpenTranscribe...${NC}"
        if [ -f docker-compose.override.yml ]; then
            docker compose -f docker-compose.yml -f docker-compose.override.yml down
        else
            docker compose down
        fi
        echo -e "${GREEN}✅ OpenTranscribe stopped${NC}"
        ;;
    restart)
        check_environment
        echo -e "${YELLOW}🔄 Restarting OpenTranscribe...${NC}"
        if [ -f docker-compose.override.yml ]; then
            docker compose -f docker-compose.yml -f docker-compose.override.yml down
            docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
        else
            docker compose down
            docker compose up -d
        fi
        echo -e "${GREEN}✅ OpenTranscribe restarted!${NC}"
        show_access_info
        ;;
    status)
        check_environment
        echo -e "${BLUE}📊 Container Status:${NC}"
        if [ -f docker-compose.override.yml ]; then
            docker compose -f docker-compose.yml -f docker-compose.override.yml ps
        else
            docker compose ps
        fi
        ;;
    logs)
        check_environment
        service=${2:-}
        COMPOSE_CMD="docker compose"
        if [ -f docker-compose.override.yml ]; then
            COMPOSE_CMD="docker compose -f docker-compose.yml -f docker-compose.override.yml"
        fi
        
        if [ -z "$service" ]; then
            echo -e "${BLUE}📋 Showing all logs (Ctrl+C to exit):${NC}"
            $COMPOSE_CMD logs -f
        else
            echo -e "${BLUE}📋 Showing logs for $service (Ctrl+C to exit):${NC}"
            $COMPOSE_CMD logs -f "$service"
        fi
        ;;
    update)
        check_environment
        echo -e "${YELLOW}📥 Updating to latest images...${NC}"
        if [ -f docker-compose.override.yml ]; then
            docker compose -f docker-compose.yml -f docker-compose.override.yml down
            docker compose -f docker-compose.yml -f docker-compose.override.yml pull
            docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
        else
            docker compose down
            docker compose pull
            docker compose up -d
        fi
        echo -e "${GREEN}✅ OpenTranscribe updated!${NC}"
        show_access_info
        ;;
    clean)
        check_environment
        echo -e "${RED}⚠️  WARNING: This will remove ALL data including transcriptions!${NC}"
        read -p "Are you sure you want to continue? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}🗑️  Removing all data...${NC}"
            docker compose down -v
            docker system prune -f
            echo -e "${GREEN}✅ All data removed${NC}"
        else
            echo -e "${GREEN}✅ Operation cancelled${NC}"
        fi
        ;;
    shell)
        check_environment
        service=${2:-backend}
        echo -e "${BLUE}🔧 Opening shell in $service container...${NC}"
        docker compose exec "$service" /bin/bash || docker compose exec "$service" /bin/sh
        ;;
    config)
        check_environment
        echo -e "${BLUE}⚙️  Current Configuration:${NC}"
        echo "Environment file (.env):"
        grep -E "^[A-Z]" .env | head -20
        echo ""
        echo "Docker Compose configuration:"
        if docker compose config > /dev/null 2>&1; then
            echo "  ✅ Valid"
        else
            echo "  ❌ Invalid"
        fi
        ;;
    health)
        check_environment
        echo -e "${BLUE}🩺 Health Check:${NC}"
        
        # Check container status
        echo "Container Status:"
        docker compose ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"
        
        echo ""
        echo "Service Health:"
        
        # Source .env to get port values
        source .env 2>/dev/null || true
        
        # Backend health
        if curl -s http://localhost:${BACKEND_PORT:-5174}/health > /dev/null 2>&1; then
            echo "  ✅ Backend: Healthy"
        else
            echo "  ❌ Backend: Unhealthy"
        fi
        
        # Frontend health  
        if curl -s http://localhost:${FRONTEND_PORT:-5173} > /dev/null 2>&1; then
            echo "  ✅ Frontend: Healthy"
        else
            echo "  ❌ Frontend: Unhealthy"
        fi
        
        # Database health
        if docker compose exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
            echo "  ✅ Database: Healthy"
        else
            echo "  ❌ Database: Unhealthy"
        fi
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}❌ Unknown command: $1${NC}"
        show_help
        exit 1
        ;;
esac
