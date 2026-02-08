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

# ─────────────────────────────────────────────
# Pre-seed configs (before containers start)
# ─────────────────────────────────────────────
echo -e "${BLUE}==>${NC} Pre-seeding app configs..."

if [[ -n "$READARR_API_KEY" ]] && ! volume_has_data "readarr-config"; then
    CONFIG_XML=$(sed "s/__API_KEY__/${READARR_API_KEY}/; s/__PORT__/8787/" \
        "$SCRIPT_DIR/lib/seed-configs/arr-config.xml.template")
    seed_volume_file "readarr-config" "config.xml" "$CONFIG_XML"
    echo -e "  ${GREEN}✓${NC} Readarr config.xml seeded"
else
    echo -e "  ${GREEN}✓${NC} Readarr config already exists (or no API key available)"
fi

# Ensure Calibre Library directory exists (metadata.db created post-deploy via calibredb)
mkdir -p "${DRIVE_PATH}/Books/eBooks/Calibre Library"

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

# ─────────────────────────────────────────────
# Readarr: Root folders + download client
# ─────────────────────────────────────────────
echo ""
echo -e "${BLUE}==>${NC} Configuring Readarr..."

if [[ -n "$READARR_API_KEY" ]]; then
    # Metadata source: upstream api.bookinfo.club is dead, use rreading-glasses community mirror
    CURRENT_META=$(curl -sf "http://localhost:8787/api/v1/config/development" \
        -H "X-Api-Key: ${READARR_API_KEY}" 2>/dev/null)
    if echo "$CURRENT_META" | grep -q '"metadataSource":"https://api.bookinfo.pro"'; then
        echo -e "  ${GREEN}✓${NC} Readarr metadata source already set"
    else
        DEV_CONFIG=$(echo "$CURRENT_META" | sed 's/"metadataSource":"[^"]*"/"metadataSource":"https:\/\/api.bookinfo.pro"/')
        curl -sf -X PUT "http://localhost:8787/api/v1/config/development" \
            -H "X-Api-Key: ${READARR_API_KEY}" \
            -H "Content-Type: application/json" \
            -d "$DEV_CONFIG" > /dev/null 2>&1 || true
        echo -e "  ${GREEN}✓${NC} Readarr metadata source: api.bookinfo.pro (rreading-glasses)"
    fi

    # Root folders (Readarr uses API v1)
    EXISTING_RF=$(arr_api_get "http://localhost:8787/api/v1/rootfolder" "$READARR_API_KEY")

    if echo "$EXISTING_RF" | grep -q '"/books/eBooks"'; then
        echo -e "  ${GREEN}✓${NC} Readarr eBooks root folder already set"
    else
        arr_api_post "http://localhost:8787/api/v1/rootfolder" "$READARR_API_KEY" \
            '{"path":"/books/eBooks","name":"eBooks","defaultMetadataProfileId":1,"defaultQualityProfileId":1}' > /dev/null 2>&1 || true
        echo -e "  ${GREEN}✓${NC} Readarr root folder: /books/eBooks"
    fi

    if echo "$EXISTING_RF" | grep -q '"/books/Audiobooks"'; then
        echo -e "  ${GREEN}✓${NC} Readarr Audiobooks root folder already set"
    else
        arr_api_post "http://localhost:8787/api/v1/rootfolder" "$READARR_API_KEY" \
            '{"path":"/books/Audiobooks","name":"Audiobooks","defaultMetadataProfileId":1,"defaultQualityProfileId":1}' > /dev/null 2>&1 || true
        echo -e "  ${GREEN}✓${NC} Readarr root folder: /books/Audiobooks"
    fi

    # Download client
    EXISTING_DC=$(arr_api_get "http://localhost:8787/api/v1/downloadclient" "$READARR_API_KEY")
    if echo "$EXISTING_DC" | grep -q 'QBittorrent'; then
        echo -e "  ${GREEN}✓${NC} Readarr download client already set"
    else
        arr_api_post "http://localhost:8787/api/v1/downloadclient" "$READARR_API_KEY" \
            '{"name":"qBittorrent","implementation":"QBittorrent","configContract":"QBittorrentSettings","protocol":"torrent","priority":1,"enable":true,"fields":[{"name":"host","value":"qbittorrent"},{"name":"port","value":8081},{"name":"username","value":"admin"},{"name":"password","value":"adminadmin"},{"name":"bookCategory","value":"books"}]}' > /dev/null 2>&1 || true
        echo -e "  ${GREEN}✓${NC} Readarr download client: qBittorrent"
    fi
else
    echo -e "  ${YELLOW}⚠${NC} No Readarr API key — configure manually at http://localhost:8787"
fi

# ─────────────────────────────────────────────
# Calibre-Web: Create library + set path
# ─────────────────────────────────────────────
echo ""
echo -e "${BLUE}==>${NC} Configuring Calibre-Web..."

# Calibre-Web needs a moment to create its app.db on first boot
sleep 3

# Create a proper Calibre metadata.db if missing (requires full schema).
# The calibre-web container has the complete Calibre toolkit via DOCKER_MODS.
if ! docker exec calibre-web test -f "/books/Calibre Library/metadata.db" 2>/dev/null; then
    # calibredb auto-creates a valid library with all required tables
    docker exec calibre-web calibredb --with-library "/books/Calibre Library" \
        list_categories > /dev/null 2>&1 || true
    echo -e "  ${GREEN}✓${NC} Calibre metadata.db created (via calibredb)"
else
    echo -e "  ${GREEN}✓${NC} Calibre metadata.db already exists"
fi

CALIBRE_CONFIGURED=$(docker exec calibre-web sh -c \
    'sqlite3 /config/app.db "SELECT config_calibre_dir FROM settings WHERE id=1;" 2>/dev/null' 2>/dev/null)

if [[ "$CALIBRE_CONFIGURED" == "/books/Calibre Library" ]]; then
    echo -e "  ${GREEN}✓${NC} Calibre-Web library path already set"
elif docker exec calibre-web sh -c \
    'sqlite3 /config/app.db "UPDATE settings SET config_calibre_dir = \"/books/Calibre Library\" WHERE id = 1;" 2>/dev/null' 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Calibre-Web library path set to /books/Calibre Library"
    echo -e "  ${YELLOW}⚠${NC} Default login: admin / admin123 — change the password!"
else
    echo -e "  ${YELLOW}⚠${NC} Could not configure Calibre-Web — set library path manually"
    echo "     Login at http://localhost:8083 (admin/admin123)"
    echo "     Set database location to: /books/Calibre Library/metadata.db"
fi

# ─────────────────────────────────────────────
# Calibre-Web: SMTP for Kindle email delivery
# ─────────────────────────────────────────────
echo ""
echo -e "${BLUE}==>${NC} Configuring Calibre-Web SMTP..."

if [[ -n "$CALIBRE_SMTP_SERVER" ]]; then
    CURRENT_SMTP=$(docker exec calibre-web sh -c \
        'sqlite3 /config/app.db "SELECT config_mail_server FROM settings WHERE id=1;" 2>/dev/null' 2>/dev/null)

    if [[ -n "$CURRENT_SMTP" ]] && [[ "$CURRENT_SMTP" != "None" ]]; then
        echo -e "  ${GREEN}✓${NC} Calibre-Web SMTP already configured (${CURRENT_SMTP})"
    else
        SMTP_PORT="${CALIBRE_SMTP_PORT:-587}"
        SMTP_TYPE="${CALIBRE_SMTP_ENCRYPTION:-1}"

        if docker exec calibre-web sh -c \
            "sqlite3 /config/app.db \"UPDATE settings SET \
                config_mail_server = '${CALIBRE_SMTP_SERVER}', \
                config_mail_port = ${SMTP_PORT}, \
                config_mail_login = '${CALIBRE_SMTP_LOGIN}', \
                config_mail_password = '${CALIBRE_SMTP_PASSWORD}', \
                config_mail_from = '${CALIBRE_SMTP_FROM}', \
                config_mail_size = 25600000, \
                config_mail_server_type = ${SMTP_TYPE} \
            WHERE id = 1;\"" 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} Calibre-Web SMTP configured (${CALIBRE_SMTP_SERVER})"
        else
            echo -e "  ${YELLOW}⚠${NC} Could not configure SMTP — set up manually"
            echo "     See docs/kindle-email-setup.md"
        fi
    fi
else
    echo -e "  ${YELLOW}⚠${NC} No SMTP credentials — Kindle email not configured"
    echo "     See docs/kindle-email-setup.md for setup instructions"
fi

# ─────────────────────────────────────────────
# Prowlarr: Connect to Readarr
# ─────────────────────────────────────────────
echo ""
echo -e "${BLUE}==>${NC} Connecting Prowlarr to Readarr..."

if [[ -n "$PROWLARR_API_KEY" ]] && [[ -n "$READARR_API_KEY" ]]; then
    EXISTING_APPS=$(arr_api_get "http://localhost:9696/api/v1/applications" "$PROWLARR_API_KEY")

    if echo "$EXISTING_APPS" | grep -q 'Readarr'; then
        echo -e "  ${GREEN}✓${NC} Prowlarr → Readarr already connected"
    else
        arr_api_post "http://localhost:9696/api/v1/applications" "$PROWLARR_API_KEY" \
            "{\"name\":\"Readarr\",\"syncLevel\":\"fullSync\",\"implementation\":\"Readarr\",\"configContract\":\"ReadarrSettings\",\"fields\":[{\"name\":\"prowlarrUrl\",\"value\":\"http://prowlarr:9696\"},{\"name\":\"baseUrl\",\"value\":\"http://readarr:8787\"},{\"name\":\"apiKey\",\"value\":\"${READARR_API_KEY}\"}]}" > /dev/null 2>&1 || true
        echo -e "  ${GREEN}✓${NC} Prowlarr → Readarr connected"
    fi
else
    echo -e "  ${YELLOW}⚠${NC} Missing API keys — configure Prowlarr → Readarr manually"
fi

echo ""
echo -e "${GREEN}✓${NC} Books stack deployed and configured"
echo ""
echo -e "${YELLOW}Next:${NC} Deploy photos stack with:"
echo "  ./scripts/10-photos-files.sh"
