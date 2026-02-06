#!/bin/bash
# Step 13: Deploy Nanobot AI Agent
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NANOBOT_DIR="${SCRIPT_DIR}/../nanobot"

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

echo -e "${BLUE}==>${NC} Deploying Nanobot AI Agent..."

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

cd "$NANOBOT_DIR"

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
        echo "   Edit nanobot/.env and add your ANTHROPIC_API_KEY"
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

# Home Assistant token
echo ""
current_val=$(get_env_val "HA_TOKEN")
if is_placeholder "$current_val"; then
    echo -e "  ${YELLOW}⚠${NC} Home Assistant token: configure after setup"
    echo "   Open http://localhost:8123 → create account → Profile > Security > Long-Lived Access Token"
    echo "   Then add HA_TOKEN=<your-token> to nanobot/.env and restart"
else
    echo -e "  ${GREEN}✓${NC} Home Assistant token already set"
fi

# --- Groq API Key (optional — for voice) ---
current_val=$(get_env_val "GROQ_API_KEY")
if is_placeholder "$current_val"; then
    echo ""
    echo -e "${YELLOW}Groq API Key (for Voice)${NC}"
    echo "Free tier — sign up at: https://console.groq.com/keys"
    echo "Provides fast speech-to-text via Whisper. Required for voice features."
    echo ""
    read -p "Enter your Groq API key (gsk_...) or press Enter to skip: " groq_key

    if [ -n "$groq_key" ]; then
        set_env_val "GROQ_API_KEY" "$groq_key"
        echo -e "  ${GREEN}✓${NC} Groq API key configured"
        echo "GROQ_API_KEY=${groq_key}" >> "$VOICE_ENV"
        echo -e "  ${GREEN}✓${NC} Voice stack configured with Groq key"
    else
        echo -e "  ${YELLOW}⚠${NC} Groq skipped — voice STT will not work until configured"
        echo "   Add GROQ_API_KEY to nanobot/.env and docker/voice-stack/.env later"
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
    echo -e "${RED}✗${NC} Critical configuration missing. Edit nanobot/.env and re-run this script."
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
echo -e "${BLUE}==>${NC} Building and deploying Nanobot..."
docker compose build
docker compose up -d

# Wait for startup with health check retry loop
echo -e "${BLUE}==>${NC} Waiting for Nanobot to start..."

HEALTH_OK=false
for i in {1..30}; do
    if curl -s http://localhost:8100/health 2>/dev/null | grep -q "ok"; then
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
    echo -e "  ${GREEN}✓${NC} Nanobot running at http://localhost:8100"
    echo -e "  ${GREEN}✓${NC} Health check passed"
else
    echo -e "  ${YELLOW}⚠${NC} Nanobot may still be starting (health check timed out after 30s)"
    echo "   Check logs with: docker logs nanobot"
fi

echo ""
echo -e "${GREEN}✓${NC} Nanobot deployed"
echo ""
echo -e "${YELLOW}Service Details:${NC}"
echo ""
echo "  Nanobot Gateway:"
echo "    - URL: http://localhost:8100"
echo "    - Health: http://localhost:8100/health"
echo "    - Model: claude-sonnet-4"
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
echo "  curl http://localhost:8100/health"
echo ""
echo "  # View logs"
echo "  docker logs nanobot -f"
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
echo "     - Edit nanobot/.env and docker/voice-stack/.env"
echo "     - Get a free key at: https://console.groq.com/keys"
echo ""
echo "See docs/VOICE_ARCHITECTURE.md for the full voice integration plan."
