#!/bin/bash
# Step 7: Deploy Download Stack (qBittorrent + Prowlarr)
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
DRIVE_PATH="${DRIVE_PATH:-/Volumes/HomeServer}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="${SCRIPT_DIR}/../docker/download-stack"

echo -e "${BLUE}==>${NC} Deploying Download Stack..."

# Check prerequisites
if ! command -v docker &>/dev/null || ! docker info &>/dev/null 2>&1; then
    echo -e "${RED}✗${NC} Docker is not running. Run 05-orbstack.sh first."
    exit 1
fi

if [[ ! -d "$DRIVE_PATH/Downloads" ]]; then
    echo -e "${RED}✗${NC} Drive not configured. Run 06-external-drive.sh first."
    exit 1
fi

# Export for docker-compose
export DRIVE_PATH

# Create shared network for cross-stack communication
echo -e "${BLUE}==>${NC} Creating shared Docker network..."
if docker network inspect homeserver &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Network 'homeserver' already exists"
else
    docker network create homeserver
    echo -e "  ${GREEN}✓${NC} Network 'homeserver' created"
fi

# Deploy containers and wait for health checks
echo -e "${BLUE}==>${NC} Starting containers (waiting for health checks)..."
cd "$COMPOSE_DIR"
if docker compose up -d --wait --wait-timeout 120; then
    echo -e "  ${GREEN}✓${NC} All services healthy"
else
    echo -e "  ${YELLOW}⚠${NC} Some services may still be starting..."
fi

# Check health
echo ""
echo -e "${BLUE}==>${NC} Checking services..."

if curl -s http://localhost:8081 &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} qBittorrent running at http://localhost:8081"
else
    echo -e "  ${YELLOW}⚠${NC} qBittorrent may still be starting..."
fi

if curl -s http://localhost:9696 &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Prowlarr running at http://localhost:9696"
else
    echo -e "  ${YELLOW}⚠${NC} Prowlarr may still be starting..."
fi

echo ""
echo -e "${GREEN}✓${NC} Download stack deployed"
echo ""
echo -e "${YELLOW}Initial Setup Required:${NC}"
echo ""
echo "  1. qBittorrent (http://localhost:8081):"
echo "     - Default login: admin / adminadmin"
echo "     - Settings > Downloads > Default Save Path: /downloads/Complete"
echo "     - Settings > Downloads > Keep incomplete in: /downloads/Incomplete"
echo ""
echo "  2. Prowlarr (http://localhost:9696):"
echo "     - Add your preferred indexers"
echo "     - Will connect to *arr apps in later steps"
echo ""
echo -e "${YELLOW}Next:${NC} Deploy media stack with:"
echo "  ./scripts/08-media-stack.sh"
