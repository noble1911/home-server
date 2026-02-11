#!/bin/bash
# Step 9: Deploy Books Stack (Audiobookshelf + LazyLibrarian)
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

# Source shared helpers
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/configure-helpers.sh"
load_credentials || true

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

# Ensure directories exist
mkdir -p "${DRIVE_PATH}/Books/eBooks"
mkdir -p "${DRIVE_PATH}/Books/Audiobooks"

# Deploy containers and wait for health checks
echo -e "${BLUE}==>${NC} Starting containers (waiting for health checks)..."
cd "$COMPOSE_DIR"
if docker compose up -d --wait --wait-timeout 120; then
    echo -e "  ${GREEN}✓${NC} All services healthy"
else
    echo -e "  ${YELLOW}⚠${NC} Some services may still be starting..."
fi

# ─────────────────────────────────────────────
# Audiobookshelf: Init admin + create libraries
# ─────────────────────────────────────────────
echo ""
echo -e "${BLUE}==>${NC} Configuring Audiobookshelf..."

ABS_STATUS=$(curl -sf http://localhost:13378/status 2>/dev/null)

if echo "$ABS_STATUS" | grep -q '"isInit":true'; then
    echo -e "  ${GREEN}✓${NC} Audiobookshelf already initialized"
elif [[ -n "$ABS_ADMIN_USER" ]] && [[ -n "$ABS_ADMIN_PASS" ]]; then
    # Create root admin user
    curl -sf -X POST http://localhost:13378/init \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg u "$ABS_ADMIN_USER" --arg p "$ABS_ADMIN_PASS" \
            '{newRoot: {username: $u, password: $p}}')" > /dev/null 2>&1 || true

    # Login to get token for library creation
    ABS_LOGIN=$(curl -sf -X POST http://localhost:13378/login \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg u "$ABS_ADMIN_USER" --arg p "$ABS_ADMIN_PASS" \
            '{username: $u, password: $p}')" 2>/dev/null)
    ABS_TOKEN=$(echo "$ABS_LOGIN" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

    if [[ -n "$ABS_TOKEN" ]]; then
        # Create audiobooks library
        curl -sf -X POST http://localhost:13378/api/libraries \
            -H "Authorization: Bearer ${ABS_TOKEN}" \
            -H "Content-Type: application/json" \
            -d '{"name":"Audiobooks","folders":[{"fullPath":"/audiobooks"}],"mediaType":"book"}' > /dev/null 2>&1 || true

        # Create ebooks library
        curl -sf -X POST http://localhost:13378/api/libraries \
            -H "Authorization: Bearer ${ABS_TOKEN}" \
            -H "Content-Type: application/json" \
            -d '{"name":"eBooks","folders":[{"fullPath":"/books"}],"mediaType":"book"}' > /dev/null 2>&1 || true

        echo -e "  ${GREEN}✓${NC} Audiobookshelf initialized with admin + libraries (Audiobooks, eBooks)"
    else
        echo -e "  ${YELLOW}⚠${NC} Audiobookshelf init succeeded but login failed — add libraries manually"
    fi
else
    echo -e "  ${YELLOW}⚠${NC} No Audiobookshelf credentials — configure manually at http://localhost:13378"
fi

echo ""
echo -e "${GREEN}✓${NC} Books stack deployed and configured"
echo ""
echo -e "${YELLOW}LazyLibrarian Setup Required:${NC}"
echo ""
echo "  Open LazyLibrarian at http://localhost:5299 and configure:"
echo ""
echo "  1. Config > Downloaders > qBittorrent:"
echo "     - Host: qbittorrent"
echo "     - Port: 8081"
echo "     - Username: admin"
echo "     - Password: (your qBittorrent password)"
echo ""
echo "  2. Config > Processing:"
echo "     - eBook destination: /books"
echo "     - Audiobook destination: /audiobooks"
echo ""
echo "  3. In Prowlarr (http://localhost:9696):"
echo "     - Settings > Apps > Add > LazyLibrarian"
echo "     - URL: http://lazylibrarian:5299"
echo "     - API Key: (from LazyLibrarian Config > Interface)"
echo ""
echo -e "${YELLOW}Next:${NC} Deploy photos stack with:"
echo "  ./scripts/10-photos-files.sh"
