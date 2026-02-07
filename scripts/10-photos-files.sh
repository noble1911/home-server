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

# Source shared helpers
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/configure-helpers.sh"
load_credentials || true

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

# Deploy containers and wait for health checks
echo -e "${BLUE}==>${NC} Starting containers (waiting for health checks — Immich ML may take a minute)..."
cd "$COMPOSE_DIR"
if docker compose up -d --wait --wait-timeout 180; then
    echo -e "  ${GREEN}✓${NC} All services healthy"
else
    echo -e "  ${YELLOW}⚠${NC} Some services may still be starting..."
fi

echo ""
if docker exec immich-postgres pg_isready &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} PostgreSQL running (port 5432)"
else
    echo -e "  ${YELLOW}⚠${NC} PostgreSQL may still be starting..."
fi

# Initialize Butler schema for Nanobot memory
echo ""
echo -e "${BLUE}==>${NC} Setting up Butler schema for AI memory..."
"$SCRIPT_DIR/init-butler-schema.sh"

# ─────────────────────────────────────────────
# Nextcloud: Auto-install via occ CLI
# ─────────────────────────────────────────────
echo ""
echo -e "${BLUE}==>${NC} Configuring Nextcloud..."

NC_STATUS=$(docker exec -u www-data nextcloud php occ status --output=json 2>/dev/null || echo '{}')

if echo "$NC_STATUS" | grep -q '"installed":true'; then
    echo -e "  ${GREEN}✓${NC} Nextcloud already installed"
elif [[ -n "$NEXTCLOUD_ADMIN_USER" ]] && [[ -n "$NEXTCLOUD_ADMIN_PASS" ]]; then
    docker exec -u www-data nextcloud php occ maintenance:install \
        --database=pgsql \
        --database-host=immich-postgres \
        --database-name=nextcloud \
        --database-user=postgres \
        --database-pass=postgres \
        --admin-user="${NEXTCLOUD_ADMIN_USER}" \
        --admin-pass="${NEXTCLOUD_ADMIN_PASS}" \
        --data-dir=/var/www/html/data \
        2>/dev/null \
        && echo -e "  ${GREEN}✓${NC} Nextcloud installed with admin account" \
        || echo -e "  ${YELLOW}⚠${NC} Nextcloud install may have failed — check http://localhost:8080"

    # Set trusted domains (localhost + container name + common LAN access)
    docker exec -u www-data nextcloud php occ config:system:set trusted_domains 0 --value="localhost" 2>/dev/null
    docker exec -u www-data nextcloud php occ config:system:set trusted_domains 1 --value="nextcloud" 2>/dev/null
    docker exec -u www-data nextcloud php occ config:system:set trusted_domains 2 --value="localhost:8080" 2>/dev/null
    echo -e "  ${GREEN}✓${NC} Nextcloud trusted domains configured"
else
    echo -e "  ${YELLOW}⚠${NC} No Nextcloud credentials — configure manually at http://localhost:8080"
fi

echo ""
echo -e "${GREEN}✓${NC} Photos & Files stack deployed"
echo ""
echo -e "${YELLOW}Still needs manual setup:${NC}"
echo ""
echo "  1. Immich (http://localhost:2283):"
echo "     - Create admin account on first visit"
echo "     - Install mobile app (iOS/Android)"
echo "     - Enable auto-backup in app settings"
echo ""
echo -e "${YELLOW}Next:${NC} Deploy smart home stack with:"
echo "  ./scripts/11-smart-home.sh"
