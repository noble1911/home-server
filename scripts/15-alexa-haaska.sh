#!/bin/bash
# Step 15: Configure Alexa Integration (haaska)
# Downloads haaska, generates config template, and guides through manual steps.
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="${SCRIPT_DIR}/../docker/smart-home-stack"
HAASKA_DIR="${SCRIPT_DIR}/../haaska-config"
HAASKA_VERSION="1.1.0"
HAASKA_URL="https://github.com/mike-grant/haaska/releases/download/${HAASKA_VERSION}/haaska_${HAASKA_VERSION}.zip"

echo -e "${BLUE}==>${NC} Configuring Alexa Integration (haaska)..."
echo ""

# Check prerequisites
echo -e "${BLUE}==>${NC} Checking prerequisites..."

PREREQ_FAIL=0

if ! command -v docker &>/dev/null || ! docker info &>/dev/null 2>&1; then
    echo -e "${RED}✗${NC} Docker is not running. Run 05-orbstack.sh first."
    PREREQ_FAIL=1
fi

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^homeassistant$"; then
    echo -e "${GREEN}✓${NC} Home Assistant is running"
else
    echo -e "${RED}✗${NC} Home Assistant is not running. Run 11-smart-home.sh first."
    PREREQ_FAIL=1
fi

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^cloudflared$"; then
    echo -e "${GREEN}✓${NC} Cloudflare Tunnel is running"
else
    echo -e "${YELLOW}⚠${NC} Cloudflare Tunnel is not running."
    echo "    You'll need the tunnel for Alexa to reach Home Assistant."
    echo "    See docs/11-smart-home.md for Cloudflare Tunnel setup."
fi

if curl -s -o /dev/null -w "%{http_code}" http://localhost:8123 2>/dev/null | grep -q "200\|401"; then
    echo -e "${GREEN}✓${NC} Home Assistant is responding on port 8123"
else
    echo -e "${YELLOW}⚠${NC} Home Assistant may still be starting (not responding on :8123)"
fi

if [ "$PREREQ_FAIL" -eq 1 ]; then
    echo ""
    echo -e "${RED}Prerequisites not met. Fix the above issues and re-run.${NC}"
    exit 1
fi

echo ""

# Download haaska
echo -e "${BLUE}==>${NC} Downloading haaska v${HAASKA_VERSION}..."
mkdir -p "$HAASKA_DIR"

if [ -f "${HAASKA_DIR}/haaska.zip" ]; then
    echo -e "${YELLOW}⚠${NC} haaska.zip already exists in ${HAASKA_DIR}"
    echo "    Delete it and re-run to download fresh."
else
    if curl -fsSL -o "${HAASKA_DIR}/haaska.zip" "$HAASKA_URL"; then
        echo -e "${GREEN}✓${NC} Downloaded haaska.zip to ${HAASKA_DIR}/"
    else
        echo -e "${YELLOW}⚠${NC} Failed to download pre-built haaska."
        echo "    You can build from source instead:"
        echo "    git clone https://github.com/mike-grant/haaska.git /tmp/haaska-src"
        echo "    cd /tmp/haaska-src && make"
    fi
fi

# Generate config template
if [ -f "${HAASKA_DIR}/config.json" ]; then
    echo -e "${YELLOW}⚠${NC} config.json already exists — not overwriting"
else
    cat > "${HAASKA_DIR}/config.json" << 'CONFIGEOF'
{
    "url": "https://ha.yourdomain.com",
    "bearer_token": "YOUR_LONG_LIVED_ACCESS_TOKEN",
    "ssl_verify": true,
    "debug": false
}
CONFIGEOF
    echo -e "${GREEN}✓${NC} Generated config template at ${HAASKA_DIR}/config.json"
fi

echo ""
echo -e "${GREEN}✓${NC} haaska files ready in ${HAASKA_DIR}/"
echo ""

# Print manual steps
echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  Manual Steps Required (AWS & Amazon Developer Consoles)${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "  1. Edit ${HAASKA_DIR}/config.json"
echo "     - Set 'url' to your Cloudflare Tunnel URL for HA"
echo "     - Set 'bearer_token' to your HA Long-Lived Access Token"
echo ""
echo "  2. Create AWS account (if needed):"
echo "     https://aws.amazon.com"
echo ""
echo "  3. Create IAM role 'lambda_basic_execution':"
echo "     AWS Console → IAM → Roles → Create role"
echo "     Attach: AWSLambdaBasicExecutionRole"
echo ""
echo "  4. Register Login with Amazon security profile:"
echo "     https://developer.amazon.com/loginwithamazon/console/site/lwa/overview.html"
echo "     Save the Client ID and Client Secret"
echo ""
echo "  5. Create Alexa Smart Home skill:"
echo "     https://developer.amazon.com/alexa/console/ask"
echo "     Type: Smart Home | Copy the Skill ID"
echo ""
echo "  6. Create Lambda function (region: eu-west-1 for UK):"
echo "     AWS Console → Lambda → Create function"
echo "     Upload haaska.zip + config.json"
echo "     Handler: haaska.event_handler | Timeout: 30s"
echo "     Add Alexa Smart Home trigger with your Skill ID"
echo ""
echo "  7. Link Lambda ARN to Alexa skill endpoint"
echo ""
echo "  8. Configure account linking in Alexa skill:"
echo "     Authorization URI: https://www.amazon.com/ap/oa"
echo "     Access Token URI:  https://api.amazon.com/auth/o2/token"
echo "     Add redirect URLs to Login with Amazon"
echo ""
echo "  9. Enable skill in Alexa app → Link Account → Discover Devices"
echo ""
echo -e "${BLUE}Full guide:${NC} docs/15-alexa-haaska.md"
echo ""
