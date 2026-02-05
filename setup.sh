#!/bin/bash
#
# Mac Mini Home Server Setup Script
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/setup.sh | bash
#
# Options:
#   --no-ssh           Skip SSH setup (if managing Mac Mini directly)
#   --drive-name=NAME  Use a different external drive name (default: HomeServer)
#   --skip-voice       Skip voice stack (if not using voice features)
#   --skip-nanobot     Skip Nanobot AI agent deployment
#

set -e

# Base URL for scripts
BASE_URL="https://raw.githubusercontent.com/noble1911/home-server/main/scripts"

# Parse arguments
ENABLE_SSH=true
DRIVE_NAME="HomeServer"
SKIP_VOICE=false
SKIP_NANOBOT=false

for arg in "$@"; do
    case $arg in
        --no-ssh)
            ENABLE_SSH=false
            ;;
        --drive-name=*)
            DRIVE_NAME="${arg#*=}"
            ;;
        --skip-voice)
            SKIP_VOICE=true
            ;;
        --skip-nanobot)
            SKIP_NANOBOT=true
            ;;
    esac
done

export DRIVE_NAME
export DRIVE_PATH="/Volumes/${DRIVE_NAME}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║            Mac Mini Home Server Setup                     ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Phase 1: Foundation
echo -e "\n${GREEN}Phase 1: Foundation${NC}"
curl -fsSL "${BASE_URL}/01-homebrew.sh" | bash
curl -fsSL "${BASE_URL}/02-tailscale.sh" | bash
curl -fsSL "${BASE_URL}/03-power-settings.sh" | bash

if [[ "$ENABLE_SSH" == "true" ]]; then
    curl -fsSL "${BASE_URL}/04-ssh.sh" | bash
else
    echo -e "\n${GREEN}==>${NC} Skipping SSH setup (--no-ssh flag)"
fi

curl -fsSL "${BASE_URL}/05-orbstack.sh" | bash
curl -fsSL "${BASE_URL}/06-external-drive.sh" | bash -s -- --drive-name="$DRIVE_NAME"

# Phase 2: Download Infrastructure
echo -e "\n${GREEN}Phase 2: Download Infrastructure${NC}"
curl -fsSL "${BASE_URL}/07-download-stack.sh" | bash

# Phase 3: Media Stack
echo -e "\n${GREEN}Phase 3: Media Stack${NC}"
curl -fsSL "${BASE_URL}/08-media-stack.sh" | bash

# Phase 4: Books & Audio
echo -e "\n${GREEN}Phase 4: Books & Audio${NC}"
curl -fsSL "${BASE_URL}/09-books-stack.sh" | bash

# Phase 5: Photos & Files
echo -e "\n${GREEN}Phase 5: Photos & Files${NC}"
curl -fsSL "${BASE_URL}/10-photos-files.sh" | bash

# Phase 6: Smart Home
echo -e "\n${GREEN}Phase 6: Smart Home${NC}"
curl -fsSL "${BASE_URL}/11-smart-home.sh" | bash

# Phase 7: Voice (optional)
if [[ "$SKIP_VOICE" == "false" ]]; then
    echo -e "\n${GREEN}Phase 7: Voice Stack${NC}"
    curl -fsSL "${BASE_URL}/12-voice-stack.sh" | bash
else
    echo -e "\n${YELLOW}==>${NC} Skipping voice stack (--skip-voice flag)"
fi

# Phase 8: AI Agent
if [[ "$SKIP_NANOBOT" == "false" ]]; then
    echo -e "\n${GREEN}Phase 8: AI Agent (Nanobot)${NC}"
    curl -fsSL "${BASE_URL}/13-nanobot.sh" | bash
else
    echo -e "\n${YELLOW}==>${NC} Skipping Nanobot (--skip-nanobot flag)"
fi

# Summary
echo ""
echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                    Setup Complete!                        ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo "Services deployed:"
echo ""
echo "  Media & Downloads:"
echo "    - Jellyfin:        http://localhost:8096"
echo "    - Radarr:          http://localhost:7878"
echo "    - Sonarr:          http://localhost:8989"
echo "    - Bazarr:          http://localhost:6767"
echo "    - Prowlarr:        http://localhost:9696"
echo "    - qBittorrent:     http://localhost:8081"
echo ""
echo "  Books:"
echo "    - Calibre-Web:     http://localhost:8083"
echo "    - Audiobookshelf:  http://localhost:13378"
echo "    - Readarr:         http://localhost:8787"
echo ""
echo "  Photos & Files:"
echo "    - Immich:          http://localhost:2283"
echo "    - Nextcloud:       http://localhost:8080"
echo ""
echo "  Smart Home:"
echo "    - Home Assistant:  http://localhost:8123"
echo ""
if [[ "$SKIP_VOICE" == "false" ]]; then
echo "  Voice:"
echo "    - LiveKit:         ws://localhost:7880"
echo "    - Whisper:         http://localhost:9000"
echo "    - Kokoro TTS:      http://localhost:8880"
echo ""
fi
if [[ "$SKIP_NANOBOT" == "false" ]]; then
echo "  AI Agent:"
echo "    - Nanobot:         http://localhost:8100"
echo ""
fi
echo -e "${YELLOW}Next steps:${NC}"
echo ""
echo "  1. Open Tailscale and sign in:"
echo "     open -a Tailscale"
echo ""
echo "  2. Configure each service (see docs/ for guides)"
echo ""
echo "  3. Set up Cloudflare Tunnel for Alexa (see docs/11-smart-home.md)"
echo ""
echo "  4. Install mobile apps (Jellyfin, Immich, Audiobookshelf)"
echo ""
if [[ "$SKIP_NANOBOT" == "false" ]]; then
echo "  5. Access Butler PWA at http://localhost:3000 (after building)"
if [[ "$SKIP_VOICE" == "false" ]]; then
echo "     See docs/VOICE_ARCHITECTURE.md for voice integration details"
fi
echo ""
fi
