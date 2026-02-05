#!/bin/bash
# Step 10: Deploy Photos & Files Stack (Immich + Nextcloud)
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
DRIVE_PATH="${DRIVE_PATH:-/Volumes/HomeServer}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="${SCRIPT_DIR}/../docker/photos-files-stack"

echo -e "${BLUE}==>${NC} Deploying Photos & Files Stack..."

# Check prerequisites
if ! command -v docker &>/dev/null || ! docker info &>/dev/null 2>&1; then
    echo -e "${RED}✗${NC} Docker is not running. Run 05-orbstack.sh first."
    exit 1
fi

if [[ ! -d "$DRIVE_PATH/Photos" ]]; then
    echo -e "${RED}✗${NC} Drive not configured. Run 06-external-drive.sh first."
    exit 1
fi

# Export for docker-compose
export DRIVE_PATH

# Deploy containers
echo -e "${BLUE}==>${NC} Starting containers..."
cd "$COMPOSE_DIR"
docker compose up -d

# Wait for services (Immich takes longer due to ML model loading)
echo -e "${BLUE}==>${NC} Waiting for services to start (this may take a minute)..."
sleep 30

# Check health
echo ""
echo -e "${BLUE}==>${NC} Checking services..."

if curl -s http://localhost:2283/api/server-info/ping &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Immich running at http://localhost:2283"
else
    echo -e "  ${YELLOW}⚠${NC} Immich may still be starting..."
fi

if curl -s http://localhost:8080 &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Nextcloud running at http://localhost:8080"
else
    echo -e "  ${YELLOW}⚠${NC} Nextcloud may still be starting..."
fi

if docker exec immich-postgres pg_isready &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} PostgreSQL running (port 5432)"
else
    echo -e "  ${YELLOW}⚠${NC} PostgreSQL may still be starting..."
fi

echo ""
echo -e "${GREEN}✓${NC} Photos & Files stack deployed"
echo ""
echo -e "${YELLOW}Initial Setup Required:${NC}"
echo ""
echo "  1. Immich (http://localhost:2283):"
echo "     - Create admin account on first visit"
echo "     - Install mobile app (iOS/Android)"
echo "     - Enable auto-backup in app settings"
echo "     - ML processing runs automatically for face recognition"
echo ""
echo "  2. Nextcloud (http://localhost:8080):"
echo "     - Create admin account on first visit"
echo "     - Install desktop sync client"
echo "     - Install mobile app for file access"
echo ""
echo -e "${YELLOW}PostgreSQL shared database:${NC}"
echo "  - Host: localhost:5432 or immich-postgres:5432 (from containers)"
echo "  - Immich DB: immich"
echo "  - Nextcloud DB: nextcloud"
echo "  - Butler schema will be added later (issue #12)"
echo ""
echo -e "${YELLOW}Next:${NC} Deploy smart home stack with:"
echo "  ./scripts/11-smart-home.sh"
