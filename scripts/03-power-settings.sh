#!/bin/bash
# Step 3: Configure Power Settings
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}==>${NC} Configuring power settings..."

# Prevent sleep
sudo pmset -a sleep 0
sudo pmset -a disksleep 0

# Wake on network
sudo pmset -a womp 1

# Auto-restart after power failure
sudo pmset -a autorestart 1

echo -e "${GREEN}✓${NC} Power settings configured:"
echo "  - Sleep disabled"
echo "  - Disk sleep disabled"
echo "  - Wake on network enabled"
echo "  - Auto-restart after power failure enabled"
