#!/bin/bash
# Step 14: Configure Automated Backups
# Creates backup directories and installs launchd schedule for daily backups
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

BACKUP_DIR="${BACKUP_DIR:-$HOME/ServerBackups}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="${SCRIPT_DIR}/backup.sh"
PLIST_NAME="com.homeserver.backup"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo -e "${BLUE}==>${NC} Setting up HomeServer backups..."

# Check prerequisites
if ! command -v docker &>/dev/null; then
    echo -e "${RED}✗${NC} Docker is not installed. Run 05-orbstack.sh first."
    exit 1
fi

if [[ ! -x "$BACKUP_SCRIPT" ]]; then
    echo -e "${RED}✗${NC} Backup script not found at ${BACKUP_SCRIPT}"
    exit 1
fi

# ─────────────────────────────────────────────
# 1. Create backup directories
# ─────────────────────────────────────────────

echo -e "${BLUE}==>${NC} Creating backup directories..."

directories=(
    "databases"
    "configs"
    "weekly/databases"
    "weekly/configs"
)

for dir in "${directories[@]}"; do
    full_path="${BACKUP_DIR}/${dir}"
    if [[ ! -d "$full_path" ]]; then
        mkdir -p "$full_path"
        echo -e "  ${GREEN}+${NC} ${dir}"
    else
        echo -e "  ${GREEN}✓${NC} ${dir} (exists)"
    fi
done

# ─────────────────────────────────────────────
# 2. Install launchd schedule
# ─────────────────────────────────────────────

echo ""
echo -e "${BLUE}==>${NC} Installing daily backup schedule (3:00 AM)..."

mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${BACKUP_SCRIPT}</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>3</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>${BACKUP_DIR}/backup.log</string>
    <key>StandardErrorPath</key>
    <string>${BACKUP_DIR}/backup.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>BACKUP_DIR</key>
        <string>${BACKUP_DIR}</string>
    </dict>
</dict>
</plist>
EOF

echo -e "  ${GREEN}✓${NC} Created ${PLIST_PATH}"

# Load the schedule (unload first if already loaded)
if launchctl list | grep -q "$PLIST_NAME" 2>/dev/null; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi
launchctl load "$PLIST_PATH"
echo -e "  ${GREEN}✓${NC} Backup schedule activated"

# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────

echo ""
echo -e "${GREEN}✓${NC} Backup system configured"
echo ""
echo -e "${YELLOW}Schedule:${NC}"
echo "  Daily at 3:00 AM — databases + config volumes"
echo "  Weekly (Sundays) — promoted to weekly/ with 4-week retention"
echo ""
echo -e "${YELLOW}Backup location:${NC} ${BACKUP_DIR}"
echo ""
echo -e "${YELLOW}Manual commands:${NC}"
echo "  Run backup now:     ./scripts/backup.sh"
echo "  List backups:       ./scripts/restore.sh --list"
echo "  Restore a service:  ./scripts/restore.sh --service jellyfin-config --date YYYY-MM-DD"
echo "  Restore everything: ./scripts/restore.sh --all --date YYYY-MM-DD"
echo ""
echo -e "${YELLOW}Manage schedule:${NC}"
echo "  Stop:   launchctl unload ${PLIST_PATH}"
echo "  Start:  launchctl load ${PLIST_PATH}"
echo "  Status: launchctl list | grep homeserver.backup"
