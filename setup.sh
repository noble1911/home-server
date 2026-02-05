#!/bin/bash
#
# Mac Mini Home Server Setup Script
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/setup.sh | bash
#
# Options:
#   --no-ssh    Skip SSH setup (if managing Mac Mini directly)
#

set -e

# Base URL for scripts
BASE_URL="https://raw.githubusercontent.com/noble1911/home-server/main/scripts"

# Parse arguments
ENABLE_SSH=true
for arg in "$@"; do
    case $arg in
        --no-ssh)
            ENABLE_SSH=false
            ;;
    esac
done

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║            Mac Mini Home Server Setup                     ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Run each step
curl -fsSL "${BASE_URL}/01-homebrew.sh" | bash
curl -fsSL "${BASE_URL}/02-tailscale.sh" | bash
curl -fsSL "${BASE_URL}/03-power-settings.sh" | bash

if [[ "$ENABLE_SSH" == "true" ]]; then
    curl -fsSL "${BASE_URL}/04-ssh.sh" | bash
else
    echo -e "\n${GREEN}==>${NC} Skipping SSH setup (--no-ssh flag)"
    echo "  To enable later: sudo systemsetup -setremotelogin on"
fi

# Summary
echo ""
echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                    Setup Complete!                        ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo "Next steps:"
echo ""
echo "  1. Open Tailscale and sign in:"
echo "     open -a Tailscale"
echo ""
echo "  2. Clone the repo:"
echo "     git clone https://github.com/noble1911/home-server.git"
echo ""
