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

# Setup .env file
if [ ! -f .env ]; then
    echo ""
    echo -e "${BLUE}==>${NC} Setting up configuration..."

    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "  ${GREEN}✓${NC} Created .env from template"
    else
        echo -e "${RED}✗${NC} .env.example not found"
        exit 1
    fi

    # Prompt for required API key
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

    # Update .env with the API key
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s|ANTHROPIC_API_KEY=sk-ant-...|ANTHROPIC_API_KEY=${api_key}|" .env
    else
        sed -i "s|ANTHROPIC_API_KEY=sk-ant-...|ANTHROPIC_API_KEY=${api_key}|" .env
    fi
    echo -e "  ${GREEN}✓${NC} API key configured"

    # Auto-generate security secrets
    echo ""
    echo -e "${BLUE}==>${NC} Generating security secrets..."

    JWT_SECRET_VAL=$(openssl rand -hex 32)
    INTERNAL_API_KEY_VAL=$(openssl rand -hex 32)
    LIVEKIT_KEY_VAL=$(openssl rand -hex 16)
    LIVEKIT_SECRET_VAL=$(openssl rand -hex 32)

    sed_inplace() {
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "$@"
        else
            sed -i "$@"
        fi
    }

    sed_inplace "s|^JWT_SECRET=.*|JWT_SECRET=${JWT_SECRET_VAL}|" .env
    sed_inplace "s|^INTERNAL_API_KEY=.*|INTERNAL_API_KEY=${INTERNAL_API_KEY_VAL}|" .env
    sed_inplace "s|^LIVEKIT_API_KEY=.*|LIVEKIT_API_KEY=${LIVEKIT_KEY_VAL}|" .env
    sed_inplace "s|^LIVEKIT_API_SECRET=.*|LIVEKIT_API_SECRET=${LIVEKIT_SECRET_VAL}|" .env

    # Write LiveKit keys to voice-stack .env so agent uses the same keys
    VOICE_ENV="${SCRIPT_DIR}/../docker/voice-stack/.env"
    mkdir -p "$(dirname "$VOICE_ENV")"
    echo "LIVEKIT_API_KEY=${LIVEKIT_KEY_VAL}" > "$VOICE_ENV"
    echo "LIVEKIT_API_SECRET=${LIVEKIT_SECRET_VAL}" >> "$VOICE_ENV"
    echo "INTERNAL_API_KEY=${INTERNAL_API_KEY_VAL}" >> "$VOICE_ENV"

    # Update livekit.yaml with the generated keys
    LIVEKIT_YAML="${SCRIPT_DIR}/../docker/voice-stack/livekit.yaml"
    if [ -f "$LIVEKIT_YAML" ]; then
        sed_inplace "s|  devkey: secret|  ${LIVEKIT_KEY_VAL}: ${LIVEKIT_SECRET_VAL}|" "$LIVEKIT_YAML"
        echo -e "  ${GREEN}✓${NC} livekit.yaml updated with production keys"
    fi

    echo -e "  ${GREEN}✓${NC} JWT_SECRET generated"
    echo -e "  ${GREEN}✓${NC} INTERNAL_API_KEY generated"
    echo -e "  ${GREEN}✓${NC} LIVEKIT_API_KEY/SECRET generated"
    echo -e "  ${GREEN}✓${NC} Voice stack .env synced"

    # Ask about Home Assistant
    echo ""
    read -p "Do you have a Home Assistant token? (y/N): " has_ha
    if [[ "$has_ha" =~ ^[Yy]$ ]]; then
        read -p "Enter Home Assistant token: " ha_token
        sed_inplace "s|HA_TOKEN=eyJ...|HA_TOKEN=${ha_token}|" .env
        echo -e "  ${GREEN}✓${NC} Home Assistant configured"
    else
        echo -e "  ${YELLOW}⚠${NC} Home Assistant skipped (can configure later in .env)"
    fi

    # Ask about Groq (for voice features)
    echo ""
    echo -e "${YELLOW}Groq API Key (for Voice)${NC}"
    echo "Free tier — sign up at: https://console.groq.com/keys"
    echo "Provides fast speech-to-text via Whisper. Required for voice features."
    echo ""
    read -p "Enter your Groq API key (gsk_...) or press Enter to skip: " groq_key

    if [ -n "$groq_key" ]; then
        sed_inplace "s|GROQ_API_KEY=gsk_...|GROQ_API_KEY=${groq_key}|" .env
        echo -e "  ${GREEN}✓${NC} Groq API key configured"

        # Also write to voice-stack .env for livekit-agent container
        echo "GROQ_API_KEY=${groq_key}" >> "$VOICE_ENV"
        echo -e "  ${GREEN}✓${NC} Voice stack configured with Groq key"
    else
        echo -e "  ${YELLOW}⚠${NC} Groq skipped — voice STT will not work until configured"
        echo "   Add GROQ_API_KEY to nanobot/.env and docker/voice-stack/.env later"
    fi

    # Ask about OpenWeatherMap
    echo ""
    echo -e "${YELLOW}OpenWeatherMap API Key (optional)${NC}"
    echo "Free tier — 1000 calls/day at: https://openweathermap.org/api"
    echo "Enables weather queries via Butler."
    echo ""
    read -p "Enter your OpenWeatherMap API key or press Enter to skip: " owm_key

    if [ -n "$owm_key" ]; then
        sed_inplace "s|^OPENWEATHERMAP_API_KEY=.*|OPENWEATHERMAP_API_KEY=${owm_key}|" .env
        echo -e "  ${GREEN}✓${NC} OpenWeatherMap configured"
    else
        echo -e "  ${YELLOW}⚠${NC} Weather skipped (can configure later in .env)"
    fi

    # Ask about Google Calendar
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
            sed_inplace "s|^GOOGLE_CLIENT_ID=.*|GOOGLE_CLIENT_ID=${google_client_id}|" .env
            sed_inplace "s|^GOOGLE_CLIENT_SECRET=.*|GOOGLE_CLIENT_SECRET=${google_client_secret}|" .env
            echo -e "  ${GREEN}✓${NC} Google OAuth configured"
        else
            echo -e "  ${YELLOW}⚠${NC} Missing credentials, skipping Google OAuth"
        fi
    else
        echo -e "  ${YELLOW}⚠${NC} Google Calendar skipped (can configure later in .env)"
    fi

    # Ask about Cloudflare Tunnel (for Alexa)
    echo ""
    echo -e "${YELLOW}Cloudflare Tunnel Token (optional — for Alexa integration)${NC}"
    echo "Enables Alexa → Home Assistant via haaska without opening ports."
    echo "Create at: Cloudflare Zero Trust > Networks > Tunnels"
    echo ""
    read -p "Enter your Cloudflare Tunnel token or press Enter to skip: " cf_token

    if [ -n "$cf_token" ]; then
        sed_inplace "s|^CLOUDFLARE_TUNNEL_TOKEN=.*|CLOUDFLARE_TUNNEL_TOKEN=${cf_token}|" .env
        # Also write to smart-home-stack .env
        SMART_HOME_ENV="${SCRIPT_DIR}/../docker/smart-home-stack/.env"
        mkdir -p "$(dirname "$SMART_HOME_ENV")"
        echo "CLOUDFLARE_TUNNEL_TOKEN=${cf_token}" > "$SMART_HOME_ENV"
        echo -e "  ${GREEN}✓${NC} Cloudflare Tunnel configured"
    else
        echo -e "  ${YELLOW}⚠${NC} Cloudflare Tunnel skipped (can configure later in .env)"
    fi

    # Ask about invite code customization
    echo ""
    read -p "Custom invite code for household registration? (default: BUTLER-001): " invite_code
    if [ -n "$invite_code" ]; then
        sed_inplace "s|^INVITE_CODES=.*|INVITE_CODES=${invite_code}|" .env
        echo -e "  ${GREEN}✓${NC} Invite code set to: ${invite_code}"
    else
        echo -e "  ${GREEN}✓${NC} Using default invite code: BUTLER-001"
    fi
else
    echo -e "  ${GREEN}✓${NC} Using existing .env configuration"
fi

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
