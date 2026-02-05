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

if ! docker network ls | grep -q "photos-files-stack_default"; then
    echo -e "${RED}✗${NC} Photos/files stack not running. Run 10-photos-files.sh first."
    echo "   Nanobot needs Immich's PostgreSQL for memory storage."
    exit 1
fi

if ! docker network ls | grep -q "smart-home-stack_default"; then
    echo -e "${YELLOW}⚠${NC} Smart home stack not running. Home Assistant integration will be unavailable."
    echo "   Run 11-smart-home.sh to enable."
fi

if ! docker network ls | grep -q "voice-stack_default"; then
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

    # Ask about Home Assistant
    echo ""
    read -p "Do you have a Home Assistant token? (y/N): " has_ha
    if [[ "$has_ha" =~ ^[Yy]$ ]]; then
        read -p "Enter Home Assistant token: " ha_token
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|HA_TOKEN=eyJ...|HA_TOKEN=${ha_token}|" .env
        else
            sed -i "s|HA_TOKEN=eyJ...|HA_TOKEN=${ha_token}|" .env
        fi
        echo -e "  ${GREEN}✓${NC} Home Assistant configured"
    else
        echo -e "  ${YELLOW}⚠${NC} Home Assistant skipped (can configure later in .env)"
    fi
else
    echo -e "  ${GREEN}✓${NC} Using existing .env configuration"
fi

# Run database migration
echo ""
echo -e "${BLUE}==>${NC} Running database migration..."

# Copy migration to postgres container and execute
docker cp migrations/001_butler_schema.sql immich-postgres:/tmp/
if ! docker exec immich-postgres psql -U postgres -d immich -f /tmp/001_butler_schema.sql 2>&1 | grep -v "already exists"; then
    echo -e "${YELLOW}⚠${NC} Migration may have encountered issues"
fi

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
echo "  Database:"
echo "    - Schema: butler (in Immich's PostgreSQL)"
echo "    - Tables: users, user_facts, conversation_history, scheduled_tasks"
echo ""
echo "  Custom Tools Loaded:"
echo "    - RememberFactTool: Store facts about users"
echo "    - RecallFactsTool: Retrieve stored facts"
echo "    - GetUserTool: Fetch user profile"
echo "    - HomeAssistantTool: Control smart home"
echo "    - ListEntitiesByDomainTool: List HA entities"
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
echo "  2. Add voice API endpoints (issue #30):"
echo "     - /api/voice/process, /api/auth/token"
echo ""
echo "  3. Build LiveKit Agents worker (issue #29):"
echo "     - Connects voice stack to Nanobot"
echo ""
echo "  4. Connect PWA to LiveKit (issue #31):"
echo "     - Enable voice in Butler app"
echo ""
echo "See docs/VOICE_ARCHITECTURE.md for the full voice integration plan."
