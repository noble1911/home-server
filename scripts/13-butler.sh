#!/bin/bash
# Step 13: Deploy Butler API
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUTLER_DIR="${SCRIPT_DIR}/../butler"

# Source shared helpers and load DRIVE_PATH + credentials
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/configure-helpers.sh"
load_credentials || true
DRIVE_PATH="${DRIVE_PATH:-/Volumes/HomeServer}"
export DRIVE_PATH

# ──────────────────────────────────────────────────
# Helper functions (idempotent key=value operations)
# ──────────────────────────────────────────────────

# Cross-platform sed -i
sed_inplace() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "$@"
    else
        sed -i "$@"
    fi
}

# Get current value of a key from .env
get_env_val() {
    grep "^${1}=" .env 2>/dev/null | head -1 | cut -d'=' -f2-
}

# Set key=value in .env (idempotent — replaces entire line by key)
set_env_val() {
    if grep -q "^${1}=" .env 2>/dev/null; then
        sed_inplace "s|^${1}=.*|${1}=${2}|" .env
    else
        echo "${1}=${2}" >> .env
    fi
}

# Check if a value is a placeholder or empty
is_placeholder() {
    [[ -z "$1" || "$1" == *"..."* || "$1" == "change-me"* || "$1" == "devkey" || "$1" == "secret" ]]
}

# Mask a value for display (first 4 + last 4 chars)
mask_val() {
    local val="$1"
    if [ ${#val} -gt 12 ]; then
        echo "${val:0:4}****${val: -4}"
    else
        echo "****"
    fi
}

echo -e "${BLUE}==>${NC} Deploying Butler API..."

# Check prerequisites
if ! command -v docker &>/dev/null || ! docker info &>/dev/null 2>&1; then
    echo -e "${RED}✗${NC} Docker is not running. Run 05-orbstack.sh first."
    exit 1
fi

# Check required networks exist
echo -e "${BLUE}==>${NC} Checking required services..."

if ! docker network ls | grep -q "homeserver"; then
    echo -e "${RED}✗${NC} Shared 'homeserver' Docker network not found."
    echo "   Run 10-photos-files.sh first (it creates the network and starts PostgreSQL)."
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -q "homeassistant"; then
    echo -e "${YELLOW}⚠${NC} Home Assistant not running. Smart home integration will be unavailable."
    echo "   Run 11-smart-home.sh to enable."
fi

if ! docker ps --format '{{.Names}}' | grep -q "livekit"; then
    echo -e "${YELLOW}⚠${NC} Voice stack not running. Voice features will be unavailable."
    echo "   Run 12-voice-stack.sh to enable."
fi

# Check PostgreSQL is accessible
if ! docker exec immich-postgres pg_isready -U postgres &>/dev/null; then
    echo -e "${RED}✗${NC} PostgreSQL (immich-postgres) is not ready."
    echo "   Make sure the photos-files stack is running."
    exit 1
fi
echo -e "  ${GREEN}✓${NC} PostgreSQL ready"

cd "$BUTLER_DIR"

# ──────────────────────────────────────────────────
# .env setup (idempotent — safe to re-run)
# ──────────────────────────────────────────────────

if [ ! -f .env ]; then
    echo ""
    echo -e "${BLUE}==>${NC} Creating initial configuration..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "  ${GREEN}✓${NC} Created .env from template"
    else
        echo -e "${RED}✗${NC} .env.example not found"
        exit 1
    fi
else
    echo -e "  ${GREEN}✓${NC} Existing .env found — checking configuration..."
fi

# --- Anthropic API Key (required) ---
current_val=$(get_env_val "ANTHROPIC_API_KEY")
if is_placeholder "$current_val"; then
    echo ""
    echo -e "${YELLOW}Anthropic API Key Required${NC}"
    echo "Get one at: https://console.anthropic.com/settings/keys"
    echo ""
    read -p "Enter your Anthropic API key (sk-ant-...): " api_key

    if [ -z "$api_key" ]; then
        echo -e "${RED}✗${NC} API key is required."
        echo "   Edit butler/.env and add your ANTHROPIC_API_KEY"
        exit 1
    fi

    set_env_val "ANTHROPIC_API_KEY" "$api_key"
    echo -e "  ${GREEN}✓${NC} API key configured"
else
    echo -e "  ${GREEN}✓${NC} Anthropic API key already set ($(mask_val "$current_val"))"
fi

# --- Auto-generate security secrets ---
echo ""
echo -e "${BLUE}==>${NC} Checking security secrets..."

for key_name in JWT_SECRET INTERNAL_API_KEY; do
    current_val=$(get_env_val "$key_name")
    if is_placeholder "$current_val"; then
        new_val=$(openssl rand -hex 32)
        set_env_val "$key_name" "$new_val"
        echo -e "  ${GREEN}✓${NC} ${key_name} generated"
    else
        echo -e "  ${GREEN}✓${NC} ${key_name} already set"
    fi
done

# LiveKit keys — generate only if placeholders
lk_key=$(get_env_val "LIVEKIT_API_KEY")
lk_secret=$(get_env_val "LIVEKIT_API_SECRET")
if is_placeholder "$lk_key" || is_placeholder "$lk_secret"; then
    LIVEKIT_KEY_VAL=$(openssl rand -hex 16)
    LIVEKIT_SECRET_VAL=$(openssl rand -hex 32)
    set_env_val "LIVEKIT_API_KEY" "$LIVEKIT_KEY_VAL"
    set_env_val "LIVEKIT_API_SECRET" "$LIVEKIT_SECRET_VAL"
    echo -e "  ${GREEN}✓${NC} LIVEKIT_API_KEY/SECRET generated"
else
    LIVEKIT_KEY_VAL="$lk_key"
    LIVEKIT_SECRET_VAL="$lk_secret"
    echo -e "  ${GREEN}✓${NC} LIVEKIT_API_KEY/SECRET already set"
fi

# Sync voice-stack .env (always — ensures consistency)
VOICE_ENV="${SCRIPT_DIR}/../docker/voice-stack/.env"
mkdir -p "$(dirname "$VOICE_ENV")"
{
    echo "LIVEKIT_API_KEY=${LIVEKIT_KEY_VAL}"
    echo "LIVEKIT_API_SECRET=${LIVEKIT_SECRET_VAL}"
    echo "INTERNAL_API_KEY=$(get_env_val "INTERNAL_API_KEY")"
} > "$VOICE_ENV"

# Update livekit.yaml with production keys
LIVEKIT_YAML="${SCRIPT_DIR}/../docker/voice-stack/livekit.yaml"
if [ -f "$LIVEKIT_YAML" ]; then
    if grep -q "devkey: secret" "$LIVEKIT_YAML"; then
        sed_inplace "s|  devkey: secret|  ${LIVEKIT_KEY_VAL}: ${LIVEKIT_SECRET_VAL}|" "$LIVEKIT_YAML"
        echo -e "  ${GREEN}✓${NC} livekit.yaml updated with production keys"
    elif ! grep -q "  ${LIVEKIT_KEY_VAL}: ${LIVEKIT_SECRET_VAL}" "$LIVEKIT_YAML"; then
        # Keys were replaced on a prior run but with different values — update them
        sed_inplace "s|^  [a-f0-9]\{16,\}: [a-f0-9]\{16,\}|  ${LIVEKIT_KEY_VAL}: ${LIVEKIT_SECRET_VAL}|" "$LIVEKIT_YAML"
        echo -e "  ${GREEN}✓${NC} livekit.yaml synced with current keys"
    else
        echo -e "  ${GREEN}✓${NC} livekit.yaml already up to date"
    fi
fi
echo -e "  ${GREEN}✓${NC} Voice stack .env synced"

# --- Host system info (for accurate dashboard stats inside Docker) ---
echo ""
echo -e "${BLUE}==>${NC} Detecting host system info..."
set_env_val "HOST_PLATFORM" "macOS"
CHIP_NAME=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "Apple Silicon")
set_env_val "HOST_ARCHITECTURE" "$CHIP_NAME"
MEM_GB=$(($(sysctl -n hw.memsize 2>/dev/null || echo "0") / 1073741824))
set_env_val "HOST_MEMORY_TOTAL_GB" "$MEM_GB"
# Detect external drive: paths under /Volumes/ are external
if [[ "$DRIVE_PATH" == /Volumes/* ]]; then
    set_env_val "HAS_EXTERNAL_DRIVE" "true"
    echo -e "  ${GREEN}✓${NC} External drive detected at $DRIVE_PATH"
else
    set_env_val "HAS_EXTERNAL_DRIVE" "false"
    echo -e "  ${GREEN}✓${NC} No external drive (data on Mac SSD)"
fi
echo -e "  ${GREEN}✓${NC} Host: macOS ${CHIP_NAME}, ${MEM_GB}GB RAM"

# Auto-populate *arr API keys from credentials file (generated by setup.sh Phase 0)
CREDENTIALS_FILE="$HOME/.homeserver-credentials"
if [[ -f "$CREDENTIALS_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$CREDENTIALS_FILE"
    echo ""
    echo -e "${BLUE}==>${NC} Syncing *arr API keys from credentials file..."

    [[ -n "$RADARR_API_KEY" ]] && set_env_val "RADARR_API_KEY" "$RADARR_API_KEY"
    [[ -n "$SONARR_API_KEY" ]] && set_env_val "SONARR_API_KEY" "$SONARR_API_KEY"
    [[ -n "$READARR_API_KEY" ]] && set_env_val "READARR_API_KEY" "$READARR_API_KEY"
    [[ -n "$PROWLARR_API_KEY" ]] && set_env_val "PROWLARR_API_KEY" "$PROWLARR_API_KEY"
    [[ -n "$JELLYFIN_API_KEY" ]] && set_env_val "JELLYFIN_API_KEY" "$JELLYFIN_API_KEY"

    echo -e "  ${GREEN}✓${NC} *arr API keys synced to butler .env"

    # Sync service admin credentials for user provisioning
    echo -e "${BLUE}==>${NC} Syncing service admin credentials for user provisioning..."

    [[ -n "$NEXTCLOUD_ADMIN_USER" ]] && set_env_val "NEXTCLOUD_ADMIN_USER" "$NEXTCLOUD_ADMIN_USER"
    [[ -n "$NEXTCLOUD_ADMIN_PASS" ]] && set_env_val "NEXTCLOUD_ADMIN_PASSWORD" "$NEXTCLOUD_ADMIN_PASS"

    echo -e "  ${GREEN}✓${NC} Service admin credentials synced to butler .env"
fi

# Ensure service URLs have Docker-network defaults (idempotent)
echo ""
echo -e "${BLUE}==>${NC} Setting service URL defaults..."
for pair in \
    "IMMICH_URL=http://immich-server:2283" \
    "AUDIOBOOKSHELF_URL=http://audiobookshelf:80" \
    "NEXTCLOUD_URL=http://nextcloud:80" \
    "PROWLARR_URL=http://prowlarr:9696"; do
    key="${pair%%=*}"
    default="${pair#*=}"
    current_val=$(get_env_val "$key")
    if [ -z "$current_val" ]; then
        set_env_val "$key" "$default"
    fi
done
echo -e "  ${GREEN}✓${NC} Service URL defaults set"

# Home Assistant token
echo ""
current_val=$(get_env_val "HA_TOKEN")
if is_placeholder "$current_val"; then
    echo -e "  ${YELLOW}⚠${NC} Home Assistant token: configure after setup"
    echo "   Open http://localhost:8123 → create account → Profile > Security > Long-Lived Access Token"
    echo "   Then add HA_TOKEN=<your-token> to butler/.env and restart"
else
    echo -e "  ${GREEN}✓${NC} Home Assistant token already set"
fi

# --- Groq API Key (optional — for voice) ---
current_val=$(get_env_val "GROQ_API_KEY")
if is_placeholder "$current_val"; then
    echo ""
    echo -e "${YELLOW}Groq API Key (for Voice)${NC}"
    echo "Free tier — sign up at: https://console.groq.com/keys"
    echo "Provides fast cloud speech-to-text via Groq Whisper. Required for voice features."
    echo ""
    read -p "Enter your Groq API key (gsk_...) or press Enter to skip: " groq_key

    if [ -n "$groq_key" ]; then
        set_env_val "GROQ_API_KEY" "$groq_key"
        echo -e "  ${GREEN}✓${NC} Groq API key configured"
        echo "GROQ_API_KEY=${groq_key}" >> "$VOICE_ENV"
        echo -e "  ${GREEN}✓${NC} Voice stack configured with Groq key"
    else
        echo -e "  ${YELLOW}⚠${NC} Groq skipped — voice STT will not work until configured"
        echo "   Add GROQ_API_KEY to butler/.env and docker/voice-stack/.env later"
    fi
else
    echo -e "  ${GREEN}✓${NC} Groq API key already set ($(mask_val "$current_val"))"
    # Ensure voice-stack has the Groq key too
    echo "GROQ_API_KEY=${current_val}" >> "$VOICE_ENV"
fi

# --- OpenWeatherMap API Key (optional) ---
current_val=$(get_env_val "OPENWEATHERMAP_API_KEY")
if is_placeholder "$current_val"; then
    echo ""
    echo -e "${YELLOW}OpenWeatherMap API Key (optional)${NC}"
    echo "Free tier — 1000 calls/day at: https://openweathermap.org/api"
    echo "Enables weather queries via Butler."
    echo ""
    read -p "Enter your OpenWeatherMap API key or press Enter to skip: " owm_key

    if [ -n "$owm_key" ]; then
        set_env_val "OPENWEATHERMAP_API_KEY" "$owm_key"
        echo -e "  ${GREEN}✓${NC} OpenWeatherMap configured"
    else
        echo -e "  ${YELLOW}⚠${NC} Weather skipped (can configure later in .env)"
    fi
else
    echo -e "  ${GREEN}✓${NC} OpenWeatherMap already set"
fi

# --- Google Calendar (optional) ---
google_id=$(get_env_val "GOOGLE_CLIENT_ID")
google_secret=$(get_env_val "GOOGLE_CLIENT_SECRET")
if [ -z "$google_id" ] && [ -z "$google_secret" ]; then
    echo ""
    echo -e "${YELLOW}Google Calendar Integration (optional)${NC}"
    echo "Lets Butler check your calendar. Requires a Google Cloud OAuth app."
    echo "See docs/google-oauth-setup.md for setup instructions."
    echo ""
    read -p "Do you have Google OAuth credentials? (y/N): " has_google
    if [[ "$has_google" =~ ^[Yy]$ ]]; then
        read -p "Enter Google Client ID: " google_client_id
        read -p "Enter Google Client Secret: " google_client_secret
        if [ -n "$google_client_id" ] && [ -n "$google_client_secret" ]; then
            set_env_val "GOOGLE_CLIENT_ID" "$google_client_id"
            set_env_val "GOOGLE_CLIENT_SECRET" "$google_client_secret"
            echo -e "  ${GREEN}✓${NC} Google OAuth configured"
        else
            echo -e "  ${YELLOW}⚠${NC} Missing credentials, skipping Google OAuth"
        fi
    else
        echo -e "  ${YELLOW}⚠${NC} Google Calendar skipped (can configure later in .env)"
    fi
else
    echo -e "  ${GREEN}✓${NC} Google OAuth already configured"
fi

# --- Cloudflare Tunnel (optional — for Alexa) ---
current_val=$(get_env_val "CLOUDFLARE_TUNNEL_TOKEN")
if [ -z "$current_val" ]; then
    echo ""
    echo -e "${YELLOW}Cloudflare Tunnel Token (optional — for Alexa integration)${NC}"
    echo "Enables Alexa → Home Assistant via haaska without opening ports."
    echo "Create at: Cloudflare Zero Trust > Networks > Tunnels"
    echo ""
    read -p "Enter your Cloudflare Tunnel token or press Enter to skip: " cf_token

    if [ -n "$cf_token" ]; then
        set_env_val "CLOUDFLARE_TUNNEL_TOKEN" "$cf_token"
        # Also write to smart-home-stack .env
        SMART_HOME_ENV="${SCRIPT_DIR}/../docker/smart-home-stack/.env"
        mkdir -p "$(dirname "$SMART_HOME_ENV")"
        echo "CLOUDFLARE_TUNNEL_TOKEN=${cf_token}" > "$SMART_HOME_ENV"
        echo -e "  ${GREEN}✓${NC} Cloudflare Tunnel configured"
    else
        echo -e "  ${YELLOW}⚠${NC} Cloudflare Tunnel skipped (can configure later in .env)"
    fi
else
    echo -e "  ${GREEN}✓${NC} Cloudflare Tunnel already set"
fi

# --- Admin invite code ---
current_val=$(get_env_val "INVITE_CODES")
if [ -z "$current_val" ] || [ "$current_val" = "BUTLER-001" ]; then
    echo ""
    echo -e "  ${BLUE}Admin invite code:${NC} The first person to log in with this code becomes the admin."
    echo -e "  ${BLUE}                  ${NC} The admin can then generate invite codes for others from Settings."
    read -p "Set your admin invite code (default: BUTLER-001): " invite_code
    if [ -n "$invite_code" ]; then
        set_env_val "INVITE_CODES" "$invite_code"
        echo -e "  ${GREEN}✓${NC} Admin invite code set to: ${invite_code}"
    else
        echo -e "  ${GREEN}✓${NC} Using default admin invite code: BUTLER-001"
    fi
else
    echo -e "  ${GREEN}✓${NC} Admin invite code already customized"
fi

# ──────────────────────────────────────────────────
# Validate critical configuration
# ──────────────────────────────────────────────────
echo ""
echo -e "${BLUE}==>${NC} Validating configuration..."
CONFIG_VALID=true
for key in ANTHROPIC_API_KEY JWT_SECRET INTERNAL_API_KEY LIVEKIT_API_KEY LIVEKIT_API_SECRET; do
    val=$(get_env_val "$key")
    if is_placeholder "$val"; then
        echo -e "  ${RED}✗${NC} ${key} is not configured"
        CONFIG_VALID=false
    fi
done
if [ "$CONFIG_VALID" = false ]; then
    echo -e "${RED}✗${NC} Critical configuration missing. Edit butler/.env and re-run this script."
    exit 1
fi
echo -e "  ${GREEN}✓${NC} All critical variables verified"

# Run database migration
echo ""
echo -e "${BLUE}==>${NC} Running database migration..."

# Copy and run all migration files in order
for migration in migrations/*.sql; do
    migration_name=$(basename "$migration")
    docker cp "$migration" "immich-postgres:/tmp/${migration_name}"
    if ! docker exec immich-postgres psql -U postgres -d immich -f "/tmp/${migration_name}" 2>&1 | grep -v "already exists"; then
        echo -e "${YELLOW}⚠${NC} Migration ${migration_name} may have encountered issues"
    fi
done

# Verify schema was created
if docker exec immich-postgres psql -U postgres -d immich -c "SELECT 1 FROM butler.users LIMIT 0" &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Butler schema verified"
else
    echo -e "${RED}✗${NC} Butler schema not found. Migration may have failed."
    echo "   Check: docker exec immich-postgres psql -U postgres -d immich -c '\\dn'"
    exit 1
fi

# Build and deploy
echo ""
echo -e "${BLUE}==>${NC} Building and deploying Butler API..."
docker compose build
docker compose up -d

# Wait for startup with health check retry loop
echo -e "${BLUE}==>${NC} Waiting for Butler API to start..."

HEALTH_OK=false
for i in {1..30}; do
    if curl -s http://localhost:8000/health 2>/dev/null | grep -q "ok"; then
        HEALTH_OK=true
        break
    fi
    echo -n "."
    sleep 1
done
echo ""

# Report health status
echo ""
echo -e "${BLUE}==>${NC} Checking health..."

if [ "$HEALTH_OK" = true ]; then
    echo -e "  ${GREEN}✓${NC} Butler API running at http://localhost:8000"
    echo -e "  ${GREEN}✓${NC} Health check passed"
else
    echo -e "  ${YELLOW}⚠${NC} Butler API may still be starting (health check timed out after 30s)"
    echo "   Check logs with: docker logs butler-api"
fi

# ──────────────────────────────────────────────────
# Build and deploy Butler PWA
# ──────────────────────────────────────────────────
echo ""
echo -e "${BLUE}==>${NC} Building and deploying Butler PWA..."
APP_DIR="${SCRIPT_DIR}/../app"
cd "$APP_DIR"
docker compose build
docker compose up -d

# Wait for PWA health check
PWA_OK=false
for i in {1..20}; do
    if curl -s http://localhost:3000/health 2>/dev/null | grep -q "ok\|OK\|healthy\|<!DOCTYPE"; then
        PWA_OK=true
        break
    fi
    echo -n "."
    sleep 1
done
echo ""

if [ "$PWA_OK" = true ]; then
    echo -e "  ${GREEN}✓${NC} Butler PWA running at http://localhost:3000"
else
    echo -e "  ${YELLOW}⚠${NC} Butler PWA may still be starting"
    echo "   Check logs with: docker logs butler-app"
fi

echo ""
echo -e "${GREEN}✓${NC} Butler deployed"
echo ""
echo -e "${YELLOW}Service Details:${NC}"
echo ""
echo "  Butler PWA:"
echo "    - URL: http://localhost:3000"
echo ""
echo "  Butler API:"
echo "    - URL: http://localhost:8000"
echo "    - Health: http://localhost:8000/health"
echo "    - Voice (batch): POST /api/voice/process"
echo "    - Voice (stream): POST /api/voice/stream"
echo "    - Auth: POST /api/auth/redeem-invite"
echo ""
echo "  Database:"
echo "    - Schema: butler (in Immich's PostgreSQL)"
echo "    - Tables: users, user_facts, conversation_history, scheduled_tasks, oauth_tokens"
echo ""
echo "  Custom Tools Loaded:"
echo "    - RememberFactTool: Store facts about users"
echo "    - RecallFactsTool: Retrieve stored facts"
echo "    - GetUserTool: Fetch user profile"
echo "    - HomeAssistantTool: Control smart home"
echo "    - ListEntitiesByDomainTool: List HA entities"
echo "    - GoogleCalendarTool: Check user's calendar (requires OAuth setup)"
echo ""
echo -e "${YELLOW}Test Commands:${NC}"
echo ""
echo "  # Check health"
echo "  curl http://localhost:8000/health"
echo ""
echo "  # View logs"
echo "  docker logs butler-api -f"
echo ""
echo "  # Query butler database"
echo "  docker exec immich-postgres psql -U postgres -d immich -c 'SELECT * FROM butler.users;'"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo "  1. Build additional tools (issues #5-#9):"
echo "     - Radarr, Sonarr, Jellyfin, Google Calendar"
echo ""
echo "  2. Connect PWA to LiveKit (issue #31):"
echo "     - Enable voice in Butler app"
echo ""
echo "  3. If you skipped the Groq API key, add it later:"
echo "     - Edit butler/.env and docker/voice-stack/.env"
echo "     - Get a free key at: https://console.groq.com/keys"
echo ""
echo "See docs/VOICE_ARCHITECTURE.md for the full voice integration plan."

# ──────────────────────────────────────────────────
# Claude Code shim (optional)
# Enables Claude Code mode in Butler chat — runs `claude --print`
# on the host and streams the response back to Butler via SSE.
# ──────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}Claude Code Mode (optional)${NC}"
echo "Adds a toggle in Butler chat that sends messages to Claude Code CLI"
echo "instead of the Claude API. Uses your Claude Max/Pro subscription."
echo ""
read -rp "Set up Claude Code mode? (y/N): " setup_cc < /dev/tty

if [[ "$setup_cc" =~ ^[Yy]$ ]]; then
    SHIM_DIR="${SCRIPT_DIR}/../docker/claude-code-shim"
    SHIM_VENV="${SHIM_DIR}/.venv"
    PLIST_SRC="${SHIM_DIR}/claude-code-shim.plist"
    PLIST_DEST="$HOME/Library/LaunchAgents/claude-code-shim.plist"

    # Step 1: Ensure Node.js is installed
    if ! command -v node &>/dev/null; then
        echo -e "${BLUE}==>${NC} Installing Node.js via Homebrew..."
        /opt/homebrew/bin/brew install node
        echo -e "  ${GREEN}✓${NC} Node.js installed"
    else
        echo -e "  ${GREEN}✓${NC} Node.js already installed ($(node --version))"
    fi

    # Step 2: Ensure Claude Code CLI is installed
    CLAUDE_BIN="/opt/homebrew/bin/claude"
    if [[ ! -x "$CLAUDE_BIN" ]]; then
        CLAUDE_BIN=$(command -v claude 2>/dev/null || true)
    fi

    if [[ -z "$CLAUDE_BIN" ]]; then
        echo -e "${BLUE}==>${NC} Installing Claude Code CLI..."
        /opt/homebrew/bin/npm install -g @anthropic-ai/claude-code
        CLAUDE_BIN=$(command -v claude 2>/dev/null || "/opt/homebrew/bin/claude")
        echo -e "  ${GREEN}✓${NC} Claude Code CLI installed"
    else
        echo -e "  ${GREEN}✓${NC} Claude Code CLI already installed ($CLAUDE_BIN)"
    fi

    # Step 3: Create venv and install aiohttp
    if [[ ! -d "$SHIM_VENV" ]]; then
        echo -e "${BLUE}==>${NC} Creating Python venv for shim..."
        python3 -m venv "$SHIM_VENV"
        echo -e "  ${GREEN}✓${NC} Venv created at ${SHIM_VENV}"
    else
        echo -e "  ${GREEN}✓${NC} Venv already exists"
    fi

    echo -e "${BLUE}==>${NC} Installing aiohttp..."
    "$SHIM_VENV/bin/pip" install --quiet aiohttp
    echo -e "  ${GREEN}✓${NC} aiohttp installed"

    # Step 4: Install and load launchd plist (auto-start on boot, restart on crash)
    if [[ -f "$PLIST_SRC" ]]; then
        cp "$PLIST_SRC" "$PLIST_DEST"

        # Unload first in case it's already registered (idempotent)
        launchctl unload "$PLIST_DEST" 2>/dev/null || true
        launchctl load "$PLIST_DEST"
        echo -e "  ${GREEN}✓${NC} Claude Code shim registered with launchd (auto-starts on boot)"
    else
        echo -e "  ${YELLOW}⚠${NC} Plist not found at ${PLIST_SRC} — skipping launchd setup"
    fi

    # Step 5: Verify shim is reachable
    echo -e "${BLUE}==>${NC} Waiting for shim to start..."
    SHIM_OK=false
    for i in {1..10}; do
        if curl -s http://localhost:7100/health 2>/dev/null | grep -q "ok"; then
            SHIM_OK=true
            break
        fi
        sleep 1
        echo -n "."
    done
    echo ""

    if [[ "$SHIM_OK" == "true" ]]; then
        echo -e "  ${GREEN}✓${NC} Claude Code shim running at http://localhost:7100"
    else
        echo -e "  ${YELLOW}⚠${NC} Shim not yet responding — it may still be starting"
        echo "   Check: curl http://localhost:7100/health"
        echo "   Logs:  tail /tmp/claude-code-shim.log"
    fi

    echo ""
    echo -e "  ${YELLOW}Action required:${NC} Log in to Claude (one-time, opens browser)"
    echo "  Run: claude login"
    echo ""
    echo -e "  ${GREEN}✓${NC} Claude Code mode ready"
    echo "  The terminal icon toggle will appear in Butler chat for admin users."
else
    echo -e "  ${YELLOW}⚠${NC} Claude Code mode skipped (can set up later — see README section 4.3)"
fi
