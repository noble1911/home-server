#!/bin/bash
# Step 1: Install Homebrew
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}==>${NC} Installing Homebrew..."

if command -v brew &>/dev/null; then
    echo -e "${GREEN}✓${NC} Homebrew already installed"
    brew --version | head -1
    exit 0
fi

/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Add to PATH for Apple Silicon
if [[ -f "/opt/homebrew/bin/brew" ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
    echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
fi

echo -e "${GREEN}✓${NC} Homebrew installed"
brew --version | head -1
