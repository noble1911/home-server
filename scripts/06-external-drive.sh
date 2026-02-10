#!/bin/bash
# Step 6: Configure External Drive
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Default drive name (can be overridden with --drive-name)
DRIVE_NAME="${DRIVE_NAME:-HomeServer}"
DRIVE_PATH="/Volumes/${DRIVE_NAME}"

# Parse arguments
for arg in "$@"; do
    case $arg in
        --drive-name=*)
            DRIVE_NAME="${arg#*=}"
            DRIVE_PATH="/Volumes/${DRIVE_NAME}"
            ;;
    esac
done

echo -e "${BLUE}==>${NC} Configuring external drive at ${DRIVE_PATH}..."

# Check if drive is mounted
if [[ ! -d "$DRIVE_PATH" ]]; then
    echo -e "${RED}✗${NC} Drive not found at ${DRIVE_PATH}"
    echo ""
    echo "Available volumes:"
    ls -1 /Volumes/ | grep -v "Macintosh HD" | sed 's/^/  /'
    echo ""
    echo "Options:"
    echo "  1. Connect your external drive"
    echo "  2. Run with different name: DRIVE_NAME=YourDrive ./06-external-drive.sh"
    echo "  3. Or: curl ... | bash -s -- --drive-name=YourDrive"
    exit 1
fi

echo -e "${GREEN}✓${NC} Drive found at ${DRIVE_PATH}"

# Create directory structure
echo -e "${BLUE}==>${NC} Creating directory structure..."

directories=(
    "Media/Movies/4K"
    "Media/Movies/HD"
    "Media/TV/4K"
    "Media/TV/HD"
    "Media/Anime/Movies"
    "Media/Anime/Series"
    "Media/Music"
    "Books/eBooks"
    "Books/Audiobooks"
    "Photos/Immich/library"
    "Photos/Immich/upload"
    "Photos/Immich/thumbs"
    "Documents/Nextcloud"
    "Downloads/Complete/Movies"
    "Downloads/Complete/TV"
    "Downloads/Complete/Anime"
    "Downloads/Complete/Books"
    "Downloads/Incomplete"
    "Backups/Databases/immich"
    "Backups/Databases/jellyfin"
    "Backups/Databases/homeassistant"
    "Backups/Databases/arr-stack"
    "Backups/Configs"
)

for dir in "${directories[@]}"; do
    full_path="${DRIVE_PATH}/${dir}"
    if [[ ! -d "$full_path" ]]; then
        mkdir -p "$full_path"
        echo -e "  ${GREEN}+${NC} ${dir}"
    else
        echo -e "  ${GREEN}✓${NC} ${dir} (exists)"
    fi
done

echo ""
echo -e "${GREEN}✓${NC} Directory structure created"
echo ""
echo -e "${YELLOW}Drive summary:${NC}"
df -h "$DRIVE_PATH" | tail -1 | awk '{print "  Size: " $2 "  Used: " $3 "  Available: " $4}'
echo ""
echo -e "${YELLOW}Next:${NC} Deploy Docker services with:"
echo "  ./scripts/07-download-stack.sh"
