#!/bin/bash
# Step 5: Install OrbStack (Docker)
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Ensure brew is in PATH
if [[ -f "/opt/homebrew/bin/brew" ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

echo -e "${BLUE}==>${NC} Installing OrbStack..."

if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Docker already available"
    docker --version
    exit 0
fi

# Install OrbStack
brew install --cask orbstack

# Start OrbStack
echo -e "${BLUE}==>${NC} Starting OrbStack..."
open -a OrbStack

# Wait for Docker to be ready (up to 60 seconds)
echo -e "${BLUE}==>${NC} Waiting for Docker daemon..."
for i in {1..60}; do
    if docker info &>/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Docker is ready"
        docker --version
        exit 0
    fi
    sleep 1
done

echo -e "${YELLOW}⚠${NC} Docker not ready yet. OrbStack may still be starting."
echo "  Run 'docker info' to check status."
