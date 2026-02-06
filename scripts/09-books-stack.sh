#!/bin/bash
# Step 9: Deploy Books Stack (Calibre-Web + Audiobookshelf + Readarr)
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
DRIVE_PATH="${DRIVE_PATH:-/Volumes/HomeServer}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="${SCRIPT_DIR}/../docker/books-stack"

echo -e "${BLUE}==>${NC} Deploying Books Stack..."

# Check prerequisites
if ! command -v docker &>/dev/null || ! docker info &>/dev/null 2>&1; then
    echo -e "${RED}✗${NC} Docker is not running. Run 05-orbstack.sh first."
    exit 1
fi

if [[ ! -d "$DRIVE_PATH/Books" ]]; then
    echo -e "${RED}✗${NC} Drive not configured. Run 06-external-drive.sh first."
    exit 1
fi

# Export for docker-compose
export DRIVE_PATH

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

services=(
    "Calibre-Web:8083"
    "Audiobookshelf:13378"
    "Readarr:8787"
)

for service in "${services[@]}"; do
    name="${service%%:*}"
    port="${service##*:}"
    if curl -s "http://localhost:${port}" &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} ${name} running at http://localhost:${port}"
    else
        echo -e "  ${YELLOW}⚠${NC} ${name} may still be starting..."
    fi
done

echo ""
echo -e "${GREEN}✓${NC} Books stack deployed"
echo ""
echo -e "${YELLOW}Initial Setup Required:${NC}"
echo ""
echo "  1. Calibre-Web (http://localhost:8083):"
echo "     - Default login: admin / admin123"
echo "     - Set database location: /books/Calibre Library/metadata.db"
echo "     - Enable uploads and Kindle email sending"
echo ""
echo "  2. Audiobookshelf (http://localhost:13378):"
echo "     - Create admin account"
echo "     - Add library: Audiobooks → /audiobooks"
echo "     - Install mobile app for offline listening"
echo ""
echo "  3. Readarr (http://localhost:8787):"
echo "     - Settings > Media Management > Root Folders:"
echo "       - /books/eBooks (for ebooks)"
echo "       - /books/Audiobooks (for audiobooks)"
echo "     - Settings > Download Clients > Add qBittorrent"
echo "     - Settings > General > Copy API key for Prowlarr"
echo ""
echo "  4. Prowlarr (http://localhost:9696):"
echo "     - Settings > Apps > Add Readarr"
echo ""
echo -e "${YELLOW}Next:${NC} Deploy photos stack with:"
echo "  ./scripts/10-photos-files.sh"
