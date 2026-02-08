#!/bin/bash
# Step 4: Enable SSH (Optional)
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

CURRENT_USER=$(whoami)

echo -e "${BLUE}==>${NC} Enabling SSH..."

if sudo systemsetup -getremotelogin 2>/dev/null | grep -q "On"; then
    echo -e "${GREEN}✓${NC} SSH already enabled"
else
    if sudo systemsetup -setremotelogin on 2>/dev/null; then
        echo -e "${GREEN}✓${NC} SSH enabled"
    else
        echo -e "${YELLOW}⚠${NC} Could not enable SSH via systemsetup (requires Full Disk Access)."
        echo ""
        echo "  Please enable SSH manually:"
        echo "    System Settings → General → Sharing → Remote Login → ON"
        echo ""
        echo "  Or grant Full Disk Access to Terminal, then re-run this script:"
        echo "    System Settings → Privacy & Security → Full Disk Access → add Terminal.app"
        echo ""
        read -rp "  Press Enter once you've enabled Remote Login to continue..." < /dev/tty
    fi
fi

# Prepare SSH directory
mkdir -p ~/.ssh
chmod 700 ~/.ssh
touch ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

echo -e "${GREEN}✓${NC} SSH directory ready"

LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "unknown")
echo ""
echo "Connect via:"
echo "  ssh ${CURRENT_USER}@${LOCAL_IP}"
echo "  ssh ${CURRENT_USER}@$(hostname).local"
