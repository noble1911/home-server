#!/bin/bash
# Step 12: Deploy Voice Stack (LiveKit + Whisper + Kokoro TTS)
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="${SCRIPT_DIR}/../docker/voice-stack"

echo -e "${BLUE}==>${NC} Deploying Voice Stack..."

# Check prerequisites
if ! command -v docker &>/dev/null || ! docker info &>/dev/null 2>&1; then
    echo -e "${RED}✗${NC} Docker is not running. Run 05-orbstack.sh first."
    exit 1
fi

# Deploy containers
echo -e "${BLUE}==>${NC} Starting containers..."
echo -e "${YELLOW}Note:${NC} First run will download ML models (~2-3GB). This may take several minutes."
echo ""
cd "$COMPOSE_DIR"
docker compose up -d

# Wait for services (ML models take time to load)
echo -e "${BLUE}==>${NC} Waiting for services to start (ML models loading)..."
sleep 45

# Check health
echo ""
echo -e "${BLUE}==>${NC} Checking services..."

# LiveKit
if curl -s http://localhost:7880 &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} LiveKit running at http://localhost:7880"
else
    echo -e "  ${YELLOW}⚠${NC} LiveKit may still be starting..."
fi

# Whisper
if curl -s http://localhost:9000/health &>/dev/null 2>&1 || curl -s http://localhost:9000 &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Whisper (STT) running at http://localhost:9000"
else
    echo -e "  ${YELLOW}⚠${NC} Whisper may still be loading model..."
fi

# Kokoro
if curl -s http://localhost:8880/health &>/dev/null 2>&1 || curl -s http://localhost:8880 &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Kokoro (TTS) running at http://localhost:8880"
else
    echo -e "  ${YELLOW}⚠${NC} Kokoro may still be loading model..."
fi

echo ""
echo -e "${GREEN}✓${NC} Voice stack deployed"
echo ""
echo -e "${YELLOW}Service Endpoints:${NC}"
echo ""
echo "  LiveKit Server:"
echo "    - WebSocket: ws://localhost:7880"
echo "    - API Key: devkey"
echo "    - API Secret: secret"
echo "    - ⚠️  Generate production keys before deploying!"
echo ""
echo "  Whisper (Speech-to-Text):"
echo "    - URL: http://localhost:9000"
echo "    - Model: small (good balance of speed/accuracy)"
echo "    - Test: curl -X POST http://localhost:9000/asr -F 'audio_file=@test.wav'"
echo ""
echo "  Kokoro (Text-to-Speech):"
echo "    - URL: http://localhost:8880"
echo "    - Voices: Multiple natural voices available"
echo "    - Test: See docs/12-voice-stack.md"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo "  1. Generate production LiveKit keys:"
echo "     docker run --rm livekit/generate"
echo ""
echo "  2. Test STT/TTS endpoints"
echo ""
echo "  3. Deploy Nanobot (issue #11) to connect everything"
echo ""
echo "  4. Build the PWA client to talk to LiveKit"
echo ""
echo "See HOMESERVER_PLAN.md for the full Butler architecture."
