#!/bin/bash
# Step 2: Install Tailscale
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Ensure brew is in PATH
if [[ -f "/opt/homebrew/bin/brew" ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

echo -e "${BLUE}==>${NC} Installing Tailscale..."

if command -v tailscale &>/dev/null; then
    echo -e "${GREEN}✓${NC} Tailscale already installed"
    tailscale --version
else
    brew install --cask tailscale
    echo -e "${GREEN}✓${NC} Tailscale installed"
fi

echo ""
echo -e "${YELLOW}Next:${NC} Open Tailscale and sign in:"
echo "  open -a Tailscale"
