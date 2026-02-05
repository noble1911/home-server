#!/bin/bash
# Step 8: Deploy Media Stack (Jellyfin + Radarr + Sonarr + Bazarr)
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
DRIVE_PATH="${DRIVE_PATH:-/Volumes/HomeServer}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="${SCRIPT_DIR}/../docker/media-stack"

echo -e "${BLUE}==>${NC} Deploying Media Stack..."

# Check prerequisites
if ! command -v docker &>/dev/null || ! docker info &>/dev/null 2>&1; then
    echo -e "${RED}✗${NC} Docker is not running. Run 05-orbstack.sh first."
    exit 1
fi

if [[ ! -d "$DRIVE_PATH/Media" ]]; then
    echo -e "${RED}✗${NC} Drive not configured. Run 06-external-drive.sh first."
    exit 1
fi

# Export for docker-compose
export DRIVE_PATH

# Deploy containers
echo -e "${BLUE}==>${NC} Starting containers..."
cd "$COMPOSE_DIR"
docker compose up -d

# Wait for services
echo -e "${BLUE}==>${NC} Waiting for services to start..."
sleep 15

# Check health
echo ""
echo -e "${BLUE}==>${NC} Checking services..."

services=(
    "Jellyfin:8096"
    "Radarr:7878"
    "Sonarr:8989"
    "Bazarr:6767"
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
echo -e "${GREEN}✓${NC} Media stack deployed"
echo ""
echo -e "${YELLOW}Initial Setup Required:${NC}"
echo ""
echo "  1. Jellyfin (http://localhost:8096):"
echo "     - Create admin account"
echo "     - Add libraries: Movies → /media/Movies, TV → /media/TV"
echo ""
echo "  2. Radarr (http://localhost:7878):"
echo "     - Settings > Media Management > Root Folder: /movies"
echo "     - Settings > Download Clients > Add qBittorrent (host: qbittorrent)"
echo "     - Settings > General > Copy Prowlarr API key for indexer sync"
echo ""
echo "  3. Sonarr (http://localhost:8989):"
echo "     - Settings > Media Management > Root Folder: /tv"
echo "     - Settings > Download Clients > Add qBittorrent (host: qbittorrent)"
echo "     - Settings > General > Copy Prowlarr API key for indexer sync"
echo ""
echo "  4. Bazarr (http://localhost:6767):"
echo "     - Settings > Sonarr/Radarr > Add connections"
echo "     - Settings > Providers > Add subtitle providers"
echo ""
echo "  5. Prowlarr (http://localhost:9696):"
echo "     - Settings > Apps > Add Radarr and Sonarr"
echo "     - Use container names as hosts (radarr, sonarr)"
echo ""
echo -e "${YELLOW}Next:${NC} Deploy books stack with:"
echo "  ./scripts/09-books-stack.sh"
