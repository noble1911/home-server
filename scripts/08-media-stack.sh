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

# Deploy containers and wait for health checks
echo -e "${BLUE}==>${NC} Starting containers (waiting for health checks)..."
cd "$COMPOSE_DIR"
if docker compose up -d --wait --wait-timeout 120; then
    echo -e "  ${GREEN}✓${NC} All services healthy"
else
    echo -e "  ${YELLOW}⚠${NC} Some services may still be starting..."
fi

# ─────────────────────────────────────────────
# Jellyfin: Phase A — Startup Wizard
# ─────────────────────────────────────────────
echo ""
echo -e "${BLUE}==>${NC} Configuring Jellyfin..."

STARTUP_DONE=$(curl -sf http://localhost:8096/System/Info/Public 2>/dev/null \
    | grep -o '"StartupWizardCompleted":[a-z]*' | cut -d: -f2)

if [[ "$STARTUP_DONE" == "true" ]]; then
    echo -e "  ${GREEN}✓${NC} Jellyfin startup wizard already completed"
elif [[ -n "$JELLYFIN_ADMIN_USER" ]] && [[ -n "$JELLYFIN_ADMIN_PASS" ]]; then
    # Step 1: Language/locale
    curl -sf -X POST http://localhost:8096/Startup/Configuration \
        -H "Content-Type: application/json" \
        -d '{"UICulture":"en-GB","MetadataCountryCode":"GB","PreferredMetadataLanguage":"en"}' > /dev/null 2>&1 || true

    # Step 2: Create admin user (use jq for safe JSON encoding of passwords)
    curl -sf -X POST http://localhost:8096/Startup/User \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg u "$JELLYFIN_ADMIN_USER" --arg p "$JELLYFIN_ADMIN_PASS" \
            '{Name: $u, Password: $p}')" > /dev/null 2>&1 || true

    # Step 3: Remote access
    curl -sf -X POST http://localhost:8096/Startup/RemoteAccess \
        -H "Content-Type: application/json" \
        -d '{"EnableRemoteAccess":true,"EnableAutomaticPortMapping":false}' > /dev/null 2>&1 || true

    # Step 4: Complete wizard
    curl -sf -X POST http://localhost:8096/Startup/Complete > /dev/null 2>&1 || true
    echo -e "  ${GREEN}✓${NC} Jellyfin startup wizard completed"
else
    echo -e "  ${YELLOW}⚠${NC} No Jellyfin credentials available — configure manually at http://localhost:8096"
fi

# ─────────────────────────────────────────────
# Jellyfin: Phase B — Libraries + API Key
# (runs whenever wizard is complete and creds exist)
# ─────────────────────────────────────────────

# Re-check wizard status (may have just completed above)
STARTUP_DONE=$(curl -sf http://localhost:8096/System/Info/Public 2>/dev/null \
    | grep -o '"StartupWizardCompleted":[a-z]*' | cut -d: -f2)

if [[ "$STARTUP_DONE" == "true" ]] && [[ -n "$JELLYFIN_ADMIN_USER" ]] && [[ -n "$JELLYFIN_ADMIN_PASS" ]]; then
    # Authenticate
    AUTH_RESPONSE=$(curl -sf -X POST http://localhost:8096/Users/AuthenticateByName \
        -H "Content-Type: application/json" \
        -H 'X-Emby-Authorization: MediaBrowser Client="Setup", Device="Script", DeviceId="setup-sh", Version="1.0"' \
        -d "$(jq -n --arg u "$JELLYFIN_ADMIN_USER" --arg p "$JELLYFIN_ADMIN_PASS" \
            '{Username: $u, Pw: $p}')" 2>/dev/null) || true
    JELLYFIN_TOKEN=$(echo "$AUTH_RESPONSE" | grep -o '"AccessToken":"[^"]*"' | cut -d'"' -f4)

    if [[ -n "$JELLYFIN_TOKEN" ]]; then
        JF_AUTH="X-Emby-Token: ${JELLYFIN_TOKEN}"

        # Check existing libraries
        EXISTING_LIBS=$(curl -sf "http://localhost:8096/Library/VirtualFolders" \
            -H "$JF_AUTH" 2>/dev/null) || true

        # Add missing libraries (idempotent)
        for lib_entry in "Movies:movies:/media/movies" "TV%20Shows:tvshows:/media/tv" "Anime%20Movies:movies:/media/anime-movies" "Anime%20Series:tvshows:/media/anime-series" "Music:music:/media/music"; do
            IFS=':' read -r lib_url_name coll_type media_path <<< "$lib_entry"
            lib_display="${lib_url_name//%20/ }"
            if echo "$EXISTING_LIBS" | grep -q "\"${lib_display}\""; then
                echo -e "  ${GREEN}✓${NC} Jellyfin library '${lib_display}' already exists"
            else
                curl -sf -X POST "http://localhost:8096/Library/VirtualFolders?name=${lib_url_name}&collectionType=${coll_type}&refreshLibrary=false" \
                    -H "$JF_AUTH" -H "Content-Type: application/json" \
                    -d "{\"LibraryOptions\":{},\"PathInfos\":[{\"Path\":\"${media_path}\"}]}" > /dev/null 2>&1 || true
                echo -e "  ${GREEN}✓${NC} Jellyfin library '${lib_display}' created"
            fi
        done

        # Generate a server-level API key for Butler (persists across restarts)
        if [[ -f "$CREDENTIALS_FILE" ]] && ! grep -q "JELLYFIN_API_KEY" "$CREDENTIALS_FILE"; then
            curl -sf -X POST "http://localhost:8096/Auth/Keys?app=Butler" \
                -H "$JF_AUTH" > /dev/null 2>&1 || true
            # Fetch the key we just created
            ALL_KEYS=$(curl -sf "http://localhost:8096/Auth/Keys" \
                -H "$JF_AUTH" 2>/dev/null) || true
            BUTLER_KEY=$(echo "$ALL_KEYS" | jq -r '.Items[] | select(.AppName == "Butler") | .AccessToken' 2>/dev/null | tail -1)
            if [[ -n "$BUTLER_KEY" ]]; then
                echo "" >> "$CREDENTIALS_FILE"
                echo "# Jellyfin server API key (for Butler)" >> "$CREDENTIALS_FILE"
                echo "JELLYFIN_API_KEY=${BUTLER_KEY}" >> "$CREDENTIALS_FILE"
                echo -e "  ${GREEN}✓${NC} Jellyfin API key saved to credentials"
            else
                echo -e "  ${YELLOW}⚠${NC} Could not retrieve Jellyfin API key — create one manually in Dashboard > API Keys"
            fi
        elif grep -q "JELLYFIN_API_KEY" "$CREDENTIALS_FILE" 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} Jellyfin API key already in credentials"
        fi
    else
        echo -e "  ${YELLOW}⚠${NC} Could not authenticate to Jellyfin — libraries must be added manually"
    fi
fi

# ─────────────────────────────────────────────
# Radarr: Root folder + download client
# ─────────────────────────────────────────────
echo ""
echo -e "${BLUE}==>${NC} Configuring Radarr..."

if [[ -n "$RADARR_API_KEY" ]]; then
    # Root folders
    EXISTING_RF=$(arr_api_get "http://localhost:7878/api/v3/rootfolder" "$RADARR_API_KEY")
    if echo "$EXISTING_RF" | grep -q '"/movies"'; then
        echo -e "  ${GREEN}✓${NC} Radarr root folder /movies already set"
    else
        arr_api_post "http://localhost:7878/api/v3/rootfolder" "$RADARR_API_KEY" \
            '{"path":"/movies","accessible":true}' > /dev/null 2>&1 || true
        echo -e "  ${GREEN}✓${NC} Radarr root folder: /movies"
    fi

    if echo "$EXISTING_RF" | grep -q '"/anime-movies"'; then
        echo -e "  ${GREEN}✓${NC} Radarr root folder /anime-movies already set"
    else
        arr_api_post "http://localhost:7878/api/v3/rootfolder" "$RADARR_API_KEY" \
            '{"path":"/anime-movies","accessible":true}' > /dev/null 2>&1 || true
        echo -e "  ${GREEN}✓${NC} Radarr root folder: /anime-movies"
    fi

    # Download client
    EXISTING_DC=$(arr_api_get "http://localhost:7878/api/v3/downloadclient" "$RADARR_API_KEY")
    if echo "$EXISTING_DC" | grep -q 'QBittorrent'; then
        echo -e "  ${GREEN}✓${NC} Radarr download client already set"
    else
        arr_api_post "http://localhost:7878/api/v3/downloadclient" "$RADARR_API_KEY" \
            '{"name":"qBittorrent","implementation":"QBittorrent","configContract":"QBittorrentSettings","protocol":"torrent","enable":true,"fields":[{"name":"host","value":"qbittorrent"},{"name":"port","value":8081},{"name":"username","value":"admin"},{"name":"password","value":"adminadmin"},{"name":"movieCategory","value":"movies"}]}' > /dev/null 2>&1 || true
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
    # Root folders
    EXISTING_RF=$(arr_api_get "http://localhost:8989/api/v3/rootfolder" "$SONARR_API_KEY")
    if echo "$EXISTING_RF" | grep -q '"/tv"'; then
        echo -e "  ${GREEN}✓${NC} Sonarr root folder /tv already set"
    else
        arr_api_post "http://localhost:8989/api/v3/rootfolder" "$SONARR_API_KEY" \
            '{"path":"/tv","accessible":true}' > /dev/null 2>&1 || true
        echo -e "  ${GREEN}✓${NC} Sonarr root folder: /tv"
    fi

    if echo "$EXISTING_RF" | grep -q '"/anime-series"'; then
        echo -e "  ${GREEN}✓${NC} Sonarr root folder /anime-series already set"
    else
        arr_api_post "http://localhost:8989/api/v3/rootfolder" "$SONARR_API_KEY" \
            '{"path":"/anime-series","accessible":true}' > /dev/null 2>&1 || true
        echo -e "  ${GREEN}✓${NC} Sonarr root folder: /anime-series"
    fi

    # Download client
    EXISTING_DC=$(arr_api_get "http://localhost:8989/api/v3/downloadclient" "$SONARR_API_KEY")
    if echo "$EXISTING_DC" | grep -q 'QBittorrent'; then
        echo -e "  ${GREEN}✓${NC} Sonarr download client already set"
    else
        arr_api_post "http://localhost:8989/api/v3/downloadclient" "$SONARR_API_KEY" \
            '{"name":"qBittorrent","implementation":"QBittorrent","configContract":"QBittorrentSettings","protocol":"torrent","enable":true,"fields":[{"name":"host","value":"qbittorrent"},{"name":"port","value":8081},{"name":"username","value":"admin"},{"name":"password","value":"adminadmin"},{"name":"tvCategory","value":"tv"}]}' > /dev/null 2>&1 || true
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
                "{\"name\":\"Radarr\",\"syncLevel\":\"fullSync\",\"implementation\":\"Radarr\",\"configContract\":\"RadarrSettings\",\"fields\":[{\"name\":\"prowlarrUrl\",\"value\":\"http://prowlarr:9696\"},{\"name\":\"baseUrl\",\"value\":\"http://radarr:7878\"},{\"name\":\"apiKey\",\"value\":\"${RADARR_API_KEY}\"}]}" > /dev/null 2>&1 || true
            echo -e "  ${GREEN}✓${NC} Prowlarr → Radarr connected"
        fi
    fi

    # Prowlarr → Sonarr
    if [[ -n "$SONARR_API_KEY" ]]; then
        if echo "$EXISTING_APPS" | grep -q 'Sonarr'; then
            echo -e "  ${GREEN}✓${NC} Prowlarr → Sonarr already connected"
        else
            arr_api_post "http://localhost:9696/api/v1/applications" "$PROWLARR_API_KEY" \
                "{\"name\":\"Sonarr\",\"syncLevel\":\"fullSync\",\"implementation\":\"Sonarr\",\"configContract\":\"SonarrSettings\",\"fields\":[{\"name\":\"prowlarrUrl\",\"value\":\"http://prowlarr:9696\"},{\"name\":\"baseUrl\",\"value\":\"http://sonarr:8989\"},{\"name\":\"apiKey\",\"value\":\"${SONARR_API_KEY}\"}]}" > /dev/null 2>&1 || true
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
