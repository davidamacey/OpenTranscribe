#!/bin/bash
#
# Start OpenTranscribe with PKI/mTLS support in production mode
#
# This script:
# 1. Generates test certificates if needed
# 2. Generates server certificate for Nginx
# 3. Starts the stack with PKI support
#
# Usage: ./scripts/pki/start-pki-prod.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PKI_DIR="${SCRIPT_DIR}/test-certs"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

cd "$PROJECT_DIR"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  OpenTranscribe PKI Production Setup${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Step 1: Generate test certificates if needed
if [ ! -f "${PKI_DIR}/ca/ca.crt" ]; then
    echo -e "${YELLOW}Step 1: Generating test certificates...${NC}"
    ./scripts/pki/setup-test-pki.sh
else
    echo -e "${GREEN}Step 1: Test certificates already exist${NC}"
fi

# Step 2: Generate server certificate for Nginx
echo ""
if [ ! -f "${PKI_DIR}/nginx/server.crt" ]; then
    echo -e "${YELLOW}Step 2: Generating server certificate for Nginx...${NC}"
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "${PKI_DIR}/nginx/server.key" \
        -out "${PKI_DIR}/nginx/server.crt" \
        -subj "/CN=localhost" 2>/dev/null
    echo -e "${GREEN}✓ Server certificate created${NC}"
else
    echo -e "${GREEN}Step 2: Server certificate already exists${NC}"
fi

# Step 3: Check .env settings
echo ""
echo -e "${YELLOW}Step 3: Checking PKI settings in .env...${NC}"

if grep -q "PKI_ENABLED=true" .env 2>/dev/null; then
    echo -e "${GREEN}✓ PKI_ENABLED=true${NC}"
else
    echo -e "${RED}✗ PKI_ENABLED is not set to true in .env${NC}"
    echo -e "  Add: PKI_ENABLED=true"
fi

if grep -q "PKI_ADMIN_DNS=" .env 2>/dev/null; then
    echo -e "${GREEN}✓ PKI_ADMIN_DNS is configured${NC}"
else
    echo -e "${YELLOW}! PKI_ADMIN_DNS is not set (no admin users via PKI)${NC}"
fi

# Step 4: Start the stack
echo ""
echo -e "${YELLOW}Step 4: Starting OpenTranscribe with PKI support...${NC}"
echo ""

docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.pki.yml up -d

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  PKI Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${CYAN}Access URLs:${NC}"
echo "  HTTP:  http://localhost:${FRONTEND_PORT:-5173}"
echo "  HTTPS: https://localhost:${PKI_HTTPS_PORT:-8443}  (PKI/mTLS enabled)"
echo ""
echo -e "${CYAN}Browser Setup:${NC}"
echo "  1. Import a client certificate into your browser:"
echo "     Location: ${PKI_DIR}/clients/*.p12"
echo "     Password: changeit"
echo ""
echo "  2. Open https://localhost:${PKI_HTTPS_PORT:-8443}"
echo "     (Accept the self-signed certificate warning)"
echo ""
echo "  3. Click 'Sign in with Certificate'"
echo "     Browser will prompt you to select a certificate"
echo ""
echo -e "${CYAN}Available test certificates:${NC}"
for p12 in "${PKI_DIR}"/clients/*.p12; do
    if [ -f "$p12" ]; then
        name=$(basename "$p12" .p12)
        echo "  - ${name}.p12"
    fi
done
echo ""
echo -e "${YELLOW}Note: The 'admin' certificate will get admin role.${NC}"
echo ""
