#!/bin/bash

# Script to test WebSocket connections in both development and production mode

# Define colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== WebSocket Connection Test Utility ===${NC}"

# Function to check if a command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# Check for required tools
if ! command_exists curl; then
  echo -e "${RED}Error: curl is not installed. Please install it first.${NC}"
  exit 1
fi

if ! command_exists docker; then
  echo -e "${RED}Error: docker is not installed. Please install it first.${NC}"
  exit 1
fi

# Ensure we're in the main project directory
cd "$(dirname "$0")"

# Function to test WebSocket connection using curl
test_websocket() {
  local mode=$1
  local port=$2
  local jwt_token=$3
  
  echo -e "${YELLOW}Testing WebSocket connection in $mode mode (port: $port)...${NC}"
  
  # Get a token from the login API
  if [ -z "$jwt_token" ]; then
    echo -e "${YELLOW}Obtaining authentication token...${NC}"
    response=$(curl -s -X POST -H "Content-Type: application/json" \
      -d '{"username": "admin@example.com", "password": "admin"}' \
      http://localhost:8080/api/auth/login)
    
    # Extract token from response
    jwt_token=$(echo "$response" | grep -o '"access_token":"[^"]*' | sed 's/"access_token":"//')
    
    if [ -z "$jwt_token" ]; then
      echo -e "${RED}Failed to obtain authentication token. Please check backend service.${NC}"
      return 1
    fi
    echo -e "${GREEN}Successfully obtained token${NC}"
  fi
  
  # Display token info for debugging
  echo -e "${YELLOW}Token (first 15 chars): ${jwt_token:0:15}...${NC}"
  
  # Show backend logs for WebSocket connections
  echo -e "${YELLOW}Watching backend logs for WebSocket connections...${NC}"
  echo -e "${YELLOW}Try connecting to the WebSocket in your browser now${NC}"
  echo -e "${YELLOW}Open your browser to http://localhost:$port${NC}"
  echo -e "${YELLOW}Press Ctrl+C to exit log view${NC}"
  
  # Display WebSocket-related logs
  docker compose logs --tail=0 -f backend | grep -E "WebSocket|token|connection" 
}

# Parse command line arguments
MODE=${1:-"dev"}

if [ "$MODE" == "dev" ] || [ "$MODE" == "development" ]; then
  echo -e "${GREEN}Setting up development environment (Node.js)${NC}"
  ./opentr.sh restart-all dev
  test_websocket "development" 5173
elif [ "$MODE" == "prod" ] || [ "$MODE" == "production" ]; then
  echo -e "${GREEN}Setting up production environment (Nginx)${NC}"
  ./opentr.sh restart-all prod
  test_websocket "production" 5173
elif [ "$MODE" == "help" ]; then
  echo -e "Usage: $0 [dev|prod]"
  echo -e "  dev  - Test WebSocket in development mode (Node.js)"
  echo -e "  prod - Test WebSocket in production mode (Nginx)"
  exit 0
else
  echo -e "${RED}Invalid mode: $MODE${NC}"
  echo -e "Usage: $0 [dev|prod]"
  exit 1
fi
