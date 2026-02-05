#!/bin/bash
#
# Mac Mini Home Server Bootstrap Script
# Run with: curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/bootstrap.sh | bash
#
# This script:
# 1. Enables SSH (Remote Login)
# 2. Installs Homebrew
# 3. Installs Tailscale
# 4. Configures Mac to stay awake 24/7
#

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() {
    echo -e "\n${BLUE}==>${NC} ${1}"
}

print_success() {
    echo -e "${GREEN}✓${NC} ${1}"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} ${1}"
}

print_error() {
    echo -e "${RED}✗${NC} ${1}"
}

# Check we're on macOS
if [[ "$(uname)" != "Darwin" ]]; then
    print_error "This script is for macOS only"
    exit 1
fi

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║         Mac Mini Home Server Bootstrap Script             ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Get current user
CURRENT_USER=$(whoami)
echo "Running as: ${CURRENT_USER}"
echo "Hostname: $(hostname)"
echo ""

# ============================================================================
# Step 1: Enable SSH (Remote Login)
# ============================================================================
print_step "Enabling SSH (Remote Login)..."

# Check if SSH is already enabled
if sudo systemsetup -getremotelogin 2>/dev/null | grep -q "On"; then
    print_success "SSH is already enabled"
else
    # Enable Remote Login
    sudo systemsetup -setremotelogin on
    print_success "SSH enabled"
fi

# Show connection info
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "unknown")
echo ""
echo "  You can now connect via:"
echo "    ssh ${CURRENT_USER}@${LOCAL_IP}"
echo "    ssh ${CURRENT_USER}@$(hostname).local"

# ============================================================================
# Step 2: Install Homebrew
# ============================================================================
print_step "Checking Homebrew..."

if command -v brew &>/dev/null; then
    print_success "Homebrew already installed"
    brew --version | head -1
else
    print_warning "Installing Homebrew (this may take a few minutes)..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Add Homebrew to PATH for Apple Silicon
    if [[ -f "/opt/homebrew/bin/brew" ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"

        # Add to shell profile for future sessions
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
        print_success "Homebrew installed and added to PATH"
    fi
fi

# Ensure brew is in PATH for this session
if [[ -f "/opt/homebrew/bin/brew" ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

# ============================================================================
# Step 3: Install Tailscale
# ============================================================================
print_step "Installing Tailscale..."

if command -v tailscale &>/dev/null; then
    print_success "Tailscale already installed"
    tailscale --version
else
    brew install --cask tailscale
    print_success "Tailscale installed"
fi

# ============================================================================
# Step 4: Configure Mac to Stay Awake
# ============================================================================
print_step "Configuring power settings (stay awake 24/7)..."

# Prevent sleep
sudo pmset -a sleep 0
sudo pmset -a disksleep 0

# Wake for network access
sudo pmset -a womp 1

# Restart after power failure
sudo pmset -a autorestart 1

print_success "Power settings configured"
echo "  - Sleep disabled"
echo "  - Disk sleep disabled"
echo "  - Wake on network access enabled"
echo "  - Auto-restart after power failure enabled"

# ============================================================================
# Step 5: Create SSH directory and set permissions
# ============================================================================
print_step "Preparing SSH directory..."

mkdir -p ~/.ssh
chmod 700 ~/.ssh
touch ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

print_success "SSH directory ready for authorized keys"

# ============================================================================
# Summary
# ============================================================================
echo ""
echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                    Setup Complete!                        ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo "Next steps:"
echo ""
echo "  1. ${YELLOW}Start Tailscale:${NC}"
echo "     Open Tailscale from Applications and sign in"
echo "     Or: open -a Tailscale"
echo ""
echo "  2. ${YELLOW}From your MacBook, copy your SSH key:${NC}"
echo "     ssh-copy-id -i ~/.ssh/id_ed25519_macmini.pub ${CURRENT_USER}@${LOCAL_IP}"
echo ""
echo "  3. ${YELLOW}Add to MacBook's ~/.ssh/config:${NC}"
echo "     Host macmini"
echo "       HostName $(hostname).local  # or Tailscale hostname after setup"
echo "       User ${CURRENT_USER}"
echo "       IdentityFile ~/.ssh/id_ed25519_macmini"
echo ""
echo "  4. ${YELLOW}Test SSH from MacBook:${NC}"
echo "     ssh macmini"
echo ""
echo "  5. ${YELLOW}Clone the home-server repo:${NC}"
echo "     git clone https://github.com/noble1911/home-server.git"
echo ""

# Show IP addresses
echo "Connection info:"
echo "  Local IP: ${LOCAL_IP}"
echo "  Hostname: $(hostname).local"
if command -v tailscale &>/dev/null && tailscale status &>/dev/null; then
    TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "not connected")
    echo "  Tailscale IP: ${TAILSCALE_IP}"
fi
echo ""
