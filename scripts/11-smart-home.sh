#!/bin/bash
# Step 11: Deploy Smart Home Stack (Home Assistant + Cloudflare Tunnel)
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="${SCRIPT_DIR}/../docker/smart-home-stack"

echo -e "${BLUE}==>${NC} Deploying Smart Home Stack..."

# Check prerequisites
if ! command -v docker &>/dev/null || ! docker info &>/dev/null 2>&1; then
    echo -e "${RED}✗${NC} Docker is not running. Run 05-orbstack.sh first."
    exit 1
fi

# Deploy Home Assistant first (Cloudflare needs manual setup)
echo -e "${BLUE}==>${NC} Starting Home Assistant..."
cd "$COMPOSE_DIR"

# Start only Home Assistant initially (cloudflared needs token)
echo -e "${BLUE}==>${NC} Starting Home Assistant (waiting for health check)..."
if docker compose up -d homeassistant --wait --wait-timeout 120; then
    echo -e "  ${GREEN}✓${NC} Home Assistant healthy"
else
    echo -e "  ${YELLOW}⚠${NC} Home Assistant may still be starting..."
fi

# Check health
echo ""
if curl -s http://localhost:8123 &>/dev/null; then
    echo -e "${GREEN}✓${NC} Home Assistant running at http://localhost:8123"
else
    echo -e "${YELLOW}⚠${NC} Home Assistant may still be starting..."
fi

echo ""
echo -e "${GREEN}✓${NC} Home Assistant deployed"
echo ""
echo -e "${YELLOW}Initial Setup Required:${NC}"
echo ""
echo "  1. Home Assistant (http://localhost:8123):"
echo "     - Create admin account"
echo "     - Configure location and units"
echo "     - Add integrations for your smart devices"
echo ""
echo "  2. Generate Long-Lived Access Token:"
echo "     - Profile (bottom left) > Long-Lived Access Tokens"
echo "     - Create token, save it for haaska setup"
echo ""
echo -e "${YELLOW}Cloudflare Tunnel (for Alexa):${NC}"
echo ""
echo "  The tunnel enables Alexa to reach Home Assistant without opening ports."
echo "  To set it up:"
echo ""
echo "  1. Create free Cloudflare account: https://dash.cloudflare.com"
echo "  2. Go to Zero Trust > Networks > Tunnels"
echo "  3. Create a tunnel, copy the token"
echo "  4. Run:"
echo "     export CLOUDFLARE_TUNNEL_TOKEN='your-token-here'"
echo "     cd docker/smart-home-stack"
echo "     docker compose up -d cloudflared"
echo ""
echo "  5. In Cloudflare, route tunnel to: http://homeassistant:8123"
echo ""
echo "  See docs/15-alexa-haaska.md for full haaska + Alexa setup guide."
echo ""
echo -e "${YELLOW}Next:${NC} Deploy voice stack with:"
echo "  ./scripts/12-voice-stack.sh"
