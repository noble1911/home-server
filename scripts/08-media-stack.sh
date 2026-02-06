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

# Source shared helpers
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/configure-helpers.sh"
load_credentials || true

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

# ─────────────────────────────────────────────
# Pre-seed configs (before containers start)
# ─────────────────────────────────────────────
echo -e "${BLUE}==>${NC} Pre-seeding app configs..."

if [[ -n "$RADARR_API_KEY" ]] && ! volume_has_data "radarr-config"; then
    CONFIG_XML=$(sed "s/__API_KEY__/${RADARR_API_KEY}/; s/__PORT__/7878/" \
        "$SCRIPT_DIR/lib/seed-configs/arr-config.xml.template")
    seed_volume_file "radarr-config" "config.xml" "$CONFIG_XML"
    echo -e "  ${GREEN}✓${NC} Radarr config.xml seeded"
else
    echo -e "  ${GREEN}✓${NC} Radarr config already exists (or no API key available)"
fi

if [[ -n "$SONARR_API_KEY" ]] && ! volume_has_data "sonarr-config"; then
    CONFIG_XML=$(sed "s/__API_KEY__/${SONARR_API_KEY}/; s/__PORT__/8989/" \
        "$SCRIPT_DIR/lib/seed-configs/arr-config.xml.template")
    seed_volume_file "sonarr-config" "config.xml" "$CONFIG_XML"
    echo -e "  ${GREEN}✓${NC} Sonarr config.xml seeded"
else
    echo -e "  ${GREEN}✓${NC} Sonarr config already exists (or no API key available)"
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
wait_for_healthy "http://localhost:8096" 30 2 "Jellyfin"
wait_for_healthy "http://localhost:7878" 30 2 "Radarr"
wait_for_healthy "http://localhost:8989" 30 2 "Sonarr"
wait_for_healthy "http://localhost:6767" 30 2 "Bazarr"

# ─────────────────────────────────────────────
# Jellyfin Startup Wizard
# ─────────────────────────────────────────────
echo ""
echo -e "${BLUE}==>${NC} Configuring Jellyfin..."

STARTUP_DONE=$(curl -sf http://localhost:8096/System/Info/Public 2>/dev/null \
    | grep -o '"StartupWizardCompleted":[a-z]*' | cut -d: -f2)

if [[ "$STARTUP_DONE" == "true" ]]; then
    echo -e "  ${GREEN}✓${NC} Jellyfin already configured"
elif [[ -n "$JELLYFIN_ADMIN_USER" ]] && [[ -n "$JELLYFIN_ADMIN_PASS" ]]; then
    # Step 1: Language/locale
    curl -sf -X POST http://localhost:8096/Startup/Configuration \
        -H "Content-Type: application/json" \
        -d '{"UICulture":"en-GB","MetadataCountryCode":"GB","PreferredMetadataLanguage":"en"}' > /dev/null

    # Step 2: Create admin user (use jq for safe JSON encoding of passwords)
    curl -sf -X POST http://localhost:8096/Startup/User \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg u "$JELLYFIN_ADMIN_USER" --arg p "$JELLYFIN_ADMIN_PASS" \
            '{Name: $u, Password: $p}')" > /dev/null

    # Step 3: Remote access
    curl -sf -X POST http://localhost:8096/Startup/RemoteAccess \
        -H "Content-Type: application/json" \
        -d '{"EnableRemoteAccess":true,"EnableAutomaticPortMapping":false}' > /dev/null

    # Step 4: Complete wizard
    curl -sf -X POST http://localhost:8096/Startup/Complete > /dev/null
    echo -e "  ${GREEN}✓${NC} Jellyfin startup wizard completed"

    # Step 5: Authenticate to add libraries
    AUTH_RESPONSE=$(curl -sf -X POST http://localhost:8096/Users/AuthenticateByName \
        -H "Content-Type: application/json" \
        -H 'X-Emby-Authorization: MediaBrowser Client="Setup", Device="Script", DeviceId="setup-sh", Version="1.0"' \
        -d "$(jq -n --arg u "$JELLYFIN_ADMIN_USER" --arg p "$JELLYFIN_ADMIN_PASS" \
            '{Username: $u, Pw: $p}')" 2>/dev/null)
    JELLYFIN_TOKEN=$(echo "$AUTH_RESPONSE" | grep -o '"AccessToken":"[^"]*"' | cut -d'"' -f4)

    if [[ -n "$JELLYFIN_TOKEN" ]]; then
        JF_AUTH="X-Emby-Token: ${JELLYFIN_TOKEN}"

        # Add Movies library
        curl -sf -X POST "http://localhost:8096/Library/VirtualFolders?name=Movies&collectionType=movies&refreshLibrary=false" \
            -H "$JF_AUTH" -H "Content-Type: application/json" \
            -d '{"LibraryOptions":{},"PathInfos":[{"Path":"/media/Movies"}]}' > /dev/null 2>&1 || true

        # Add TV Shows library
        curl -sf -X POST "http://localhost:8096/Library/VirtualFolders?name=TV%20Shows&collectionType=tvshows&refreshLibrary=false" \
            -H "$JF_AUTH" -H "Content-Type: application/json" \
            -d '{"LibraryOptions":{},"PathInfos":[{"Path":"/media/TV"}]}' > /dev/null 2>&1 || true

        # Add Music library
        curl -sf -X POST "http://localhost:8096/Library/VirtualFolders?name=Music&collectionType=music&refreshLibrary=false" \
            -H "$JF_AUTH" -H "Content-Type: application/json" \
            -d '{"LibraryOptions":{},"PathInfos":[{"Path":"/media/Music"}]}' > /dev/null 2>&1 || true

        echo -e "  ${GREEN}✓${NC} Jellyfin libraries added (Movies, TV Shows, Music)"

        # Save Jellyfin API key to credentials file for Butler
        JELLYFIN_API_KEY="$JELLYFIN_TOKEN"
        if [[ -f "$CREDENTIALS_FILE" ]] && ! grep -q "JELLYFIN_API_KEY" "$CREDENTIALS_FILE"; then
            echo "" >> "$CREDENTIALS_FILE"
            echo "# Jellyfin API key (from admin auth)" >> "$CREDENTIALS_FILE"
            echo "JELLYFIN_API_KEY=${JELLYFIN_API_KEY}" >> "$CREDENTIALS_FILE"
        fi
    else
        echo -e "  ${YELLOW}⚠${NC} Could not authenticate to Jellyfin — libraries must be added manually"
    fi
else
    echo -e "  ${YELLOW}⚠${NC} No Jellyfin credentials available — configure manually at http://localhost:8096"
fi

# ─────────────────────────────────────────────
# Radarr: Root folder + download client
# ─────────────────────────────────────────────
echo ""
echo -e "${BLUE}==>${NC} Configuring Radarr..."

if [[ -n "$RADARR_API_KEY" ]]; then
    # Root folder
    EXISTING_RF=$(arr_api_get "http://localhost:7878/api/v3/rootfolder" "$RADARR_API_KEY")
    if echo "$EXISTING_RF" | grep -q '"/movies"'; then
        echo -e "  ${GREEN}✓${NC} Radarr root folder already set"
    else
        arr_api_post "http://localhost:7878/api/v3/rootfolder" "$RADARR_API_KEY" \
            '{"path":"/movies","accessible":true}' > /dev/null
        echo -e "  ${GREEN}✓${NC} Radarr root folder: /movies"
    fi

    # Download client
    EXISTING_DC=$(arr_api_get "http://localhost:7878/api/v3/downloadclient" "$RADARR_API_KEY")
    if echo "$EXISTING_DC" | grep -q 'QBittorrent'; then
        echo -e "  ${GREEN}✓${NC} Radarr download client already set"
    else
        arr_api_post "http://localhost:7878/api/v3/downloadclient" "$RADARR_API_KEY" \
            '{"name":"qBittorrent","implementation":"QBittorrent","configContract":"QBittorrentSettings","protocol":"torrent","enable":true,"fields":[{"name":"host","value":"qbittorrent"},{"name":"port","value":8081},{"name":"username","value":"admin"},{"name":"password","value":"adminadmin"},{"name":"movieCategory","value":"movies"}]}' > /dev/null
        echo -e "  ${GREEN}✓${NC} Radarr download client: qBittorrent"
    fi
else
    echo -e "  ${YELLOW}⚠${NC} No Radarr API key — configure manually at http://localhost:7878"
fi

# ─────────────────────────────────────────────
# Sonarr: Root folder + download client
# ─────────────────────────────────────────────
echo ""
echo -e "${BLUE}==>${NC} Configuring Sonarr..."

if [[ -n "$SONARR_API_KEY" ]]; then
    # Root folder
    EXISTING_RF=$(arr_api_get "http://localhost:8989/api/v3/rootfolder" "$SONARR_API_KEY")
    if echo "$EXISTING_RF" | grep -q '"/tv"'; then
        echo -e "  ${GREEN}✓${NC} Sonarr root folder already set"
    else
        arr_api_post "http://localhost:8989/api/v3/rootfolder" "$SONARR_API_KEY" \
            '{"path":"/tv","accessible":true}' > /dev/null
        echo -e "  ${GREEN}✓${NC} Sonarr root folder: /tv"
    fi

    # Download client
    EXISTING_DC=$(arr_api_get "http://localhost:8989/api/v3/downloadclient" "$SONARR_API_KEY")
    if echo "$EXISTING_DC" | grep -q 'QBittorrent'; then
        echo -e "  ${GREEN}✓${NC} Sonarr download client already set"
    else
        arr_api_post "http://localhost:8989/api/v3/downloadclient" "$SONARR_API_KEY" \
            '{"name":"qBittorrent","implementation":"QBittorrent","configContract":"QBittorrentSettings","protocol":"torrent","enable":true,"fields":[{"name":"host","value":"qbittorrent"},{"name":"port","value":8081},{"name":"username","value":"admin"},{"name":"password","value":"adminadmin"},{"name":"tvCategory","value":"tv"}]}' > /dev/null
        echo -e "  ${GREEN}✓${NC} Sonarr download client: qBittorrent"
    fi
else
    echo -e "  ${YELLOW}⚠${NC} No Sonarr API key — configure manually at http://localhost:8989"
fi

# ─────────────────────────────────────────────
# Bazarr: Connect to Radarr + Sonarr
# ─────────────────────────────────────────────
echo ""
echo -e "${BLUE}==>${NC} Configuring Bazarr..."

# Bazarr generates its own API key on first boot. We need to read it.
BAZARR_API_KEY=$(curl -sf http://localhost:6767/api/system/settings 2>/dev/null \
    | grep -o '"apikey":"[^"]*"' | cut -d'"' -f4)

if [[ -n "$BAZARR_API_KEY" ]] && [[ -n "$RADARR_API_KEY" ]] && [[ -n "$SONARR_API_KEY" ]]; then
    # Bazarr settings API uses a PATCH-like approach
    curl -sf -X POST "http://localhost:6767/api/system/settings" \
        -H "x-api-key: ${BAZARR_API_KEY}" \
        -H "Content-Type: application/json" \
        -d "{\"settings\":{\"radarr\":{\"ip\":\"radarr\",\"port\":7878,\"apikey\":\"${RADARR_API_KEY}\",\"enabled\":true},\"sonarr\":{\"ip\":\"sonarr\",\"port\":8989,\"apikey\":\"${SONARR_API_KEY}\",\"enabled\":true}}}" > /dev/null 2>&1 \
        && echo -e "  ${GREEN}✓${NC} Bazarr connected to Radarr + Sonarr" \
        || echo -e "  ${YELLOW}⚠${NC} Bazarr connection may need manual setup at http://localhost:6767"
else
    echo -e "  ${YELLOW}⚠${NC} Bazarr API not available yet — configure manually at http://localhost:6767"
fi

# ─────────────────────────────────────────────
# Prowlarr: Connect to Radarr + Sonarr
# (Prowlarr was deployed in step 07, these apps are now available)
# ─────────────────────────────────────────────
echo ""
echo -e "${BLUE}==>${NC} Connecting Prowlarr to *arr apps..."

if [[ -n "$PROWLARR_API_KEY" ]]; then
    EXISTING_APPS=$(arr_api_get "http://localhost:9696/api/v1/applications" "$PROWLARR_API_KEY")

    # Prowlarr → Radarr
    if [[ -n "$RADARR_API_KEY" ]]; then
        if echo "$EXISTING_APPS" | grep -q 'Radarr'; then
            echo -e "  ${GREEN}✓${NC} Prowlarr → Radarr already connected"
        else
            arr_api_post "http://localhost:9696/api/v1/applications" "$PROWLARR_API_KEY" \
                "{\"name\":\"Radarr\",\"syncLevel\":\"fullSync\",\"implementation\":\"Radarr\",\"configContract\":\"RadarrSettings\",\"fields\":[{\"name\":\"prowlarrUrl\",\"value\":\"http://prowlarr:9696\"},{\"name\":\"baseUrl\",\"value\":\"http://radarr:7878\"},{\"name\":\"apiKey\",\"value\":\"${RADARR_API_KEY}\"}]}" > /dev/null
            echo -e "  ${GREEN}✓${NC} Prowlarr → Radarr connected"
        fi
    fi

    # Prowlarr → Sonarr
    if [[ -n "$SONARR_API_KEY" ]]; then
        if echo "$EXISTING_APPS" | grep -q 'Sonarr'; then
            echo -e "  ${GREEN}✓${NC} Prowlarr → Sonarr already connected"
        else
            arr_api_post "http://localhost:9696/api/v1/applications" "$PROWLARR_API_KEY" \
                "{\"name\":\"Sonarr\",\"syncLevel\":\"fullSync\",\"implementation\":\"Sonarr\",\"configContract\":\"SonarrSettings\",\"fields\":[{\"name\":\"prowlarrUrl\",\"value\":\"http://prowlarr:9696\"},{\"name\":\"baseUrl\",\"value\":\"http://sonarr:8989\"},{\"name\":\"apiKey\",\"value\":\"${SONARR_API_KEY}\"}]}" > /dev/null
            echo -e "  ${GREEN}✓${NC} Prowlarr → Sonarr connected"
        fi
    fi
else
    echo -e "  ${YELLOW}⚠${NC} No Prowlarr API key — configure manually at http://localhost:9696"
fi

echo ""
echo -e "${GREEN}✓${NC} Media stack deployed and configured"
echo ""
echo -e "${YELLOW}Next:${NC} Deploy books stack with:"
echo "  ./scripts/09-books-stack.sh"
