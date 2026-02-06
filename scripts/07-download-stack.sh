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

# Source shared helpers
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/configure-helpers.sh"
load_credentials || true

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

# ─────────────────────────────────────────────
# Pre-seed configs (before containers start)
# ─────────────────────────────────────────────
echo -e "${BLUE}==>${NC} Pre-seeding app configs..."

if [[ -n "$PROWLARR_API_KEY" ]] && ! volume_has_data "prowlarr-config"; then
    CONFIG_XML=$(sed "s/__API_KEY__/${PROWLARR_API_KEY}/; s/__PORT__/9696/" \
        "$SCRIPT_DIR/lib/seed-configs/arr-config.xml.template")
    seed_volume_file "prowlarr-config" "config.xml" "$CONFIG_XML"
    echo -e "  ${GREEN}✓${NC} Prowlarr config.xml seeded (API key pre-set)"
else
    echo -e "  ${GREEN}✓${NC} Prowlarr config already exists (or no API key available)"
fi

if ! volume_has_data "qbittorrent-config"; then
    QB_CONF=$(cat "$SCRIPT_DIR/lib/seed-configs/qbittorrent.conf.template")
    seed_volume_file "qbittorrent-config" "qBittorrent/qBittorrent.conf" "$QB_CONF"
    echo -e "  ${GREEN}✓${NC} qBittorrent config seeded (download paths pre-set)"
else
    echo -e "  ${GREEN}✓${NC} qBittorrent config already exists"
fi

# ─────────────────────────────────────────────
# Deploy containers
# ─────────────────────────────────────────────
echo -e "${BLUE}==>${NC} Starting containers..."
cd "$COMPOSE_DIR"
docker compose up -d

# ─────────────────────────────────────────────
# Wait for healthy
# ─────────────────────────────────────────────
echo -e "${BLUE}==>${NC} Waiting for services..."
wait_for_healthy "http://localhost:8081" 30 2 "qBittorrent"
wait_for_healthy "http://localhost:9696" 30 2 "Prowlarr"

echo ""
echo -e "${GREEN}✓${NC} Download stack deployed"
echo ""
echo -e "${YELLOW}Note:${NC} Prowlarr indexers must be added manually at http://localhost:9696"
echo ""
echo -e "${YELLOW}Next:${NC} Deploy media stack with:"
echo "  ./scripts/08-media-stack.sh"
