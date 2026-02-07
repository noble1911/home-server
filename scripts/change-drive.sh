#!/bin/bash
# Change HomeServer Drive Path
#
# Interactive script to migrate data from one drive to another.
# Auto-detects current path from $DRIVE_PATH (default: /Volumes/HomeServer).
#
# Usage:
#   ./scripts/change-drive.sh
#
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${SCRIPT_DIR}/.."

# Drive-dependent stacks in deployment order (name:compose-dir-relative-to-repo)
DRIVE_STACKS=(
    "download-stack:docker/download-stack"
    "media-stack:docker/media-stack"
    "books-stack:docker/books-stack"
    "photos-files-stack:docker/photos-files-stack"
    "nanobot:nanobot"
)

# Directory structure (matches 06-external-drive.sh)
DIRECTORIES=(
    "Media/Movies/4K"
    "Media/Movies/HD"
    "Media/TV/4K"
    "Media/TV/HD"
    "Media/Anime/Movies"
    "Media/Anime/Series"
    "Media/Music"
    "Books/eBooks/Calibre Library"
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

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

prompt() {
    local msg="$1"
    local var="$2"
    echo -ne "$msg" > /dev/tty
    read -r "$var" < /dev/tty
}

human_size() {
    # Convert kilobytes to human-readable
    local kb="$1"
    if (( kb >= 1073741824 )); then
        echo "$(( kb / 1073741824 )) TB"
    elif (( kb >= 1048576 )); then
        echo "$(( kb / 1048576 )) GB"
    elif (( kb >= 1024 )); then
        echo "$(( kb / 1024 )) MB"
    else
        echo "${kb} KB"
    fi
}

# Check if a stack has running containers
stack_is_running() {
    local compose_dir="$1"
    local full_dir="${REPO_DIR}/${compose_dir}"
    if [[ ! -f "${full_dir}/docker-compose.yml" ]]; then
        return 1
    fi
    local running
    running=$(docker compose -f "${full_dir}/docker-compose.yml" ps -q --status running 2>/dev/null | wc -l | tr -d ' ')
    [[ "$running" -gt 0 ]]
}

# ─────────────────────────────────────────────
# Phase 1: Detect current path
# ─────────────────────────────────────────────

OLD_PATH="${DRIVE_PATH:-/Volumes/HomeServer}"

echo -e "${GREEN}"
echo "  ════════════════════════════════════════════"
echo "    HomeServer Drive Migration"
echo "  ════════════════════════════════════════════"
echo -e "${NC}"

echo -e "  Current drive path: ${BLUE}${OLD_PATH}${NC}"

if [[ -d "$OLD_PATH" ]]; then
    OLD_SIZE_KB=$(du -sk "$OLD_PATH" 2>/dev/null | awk '{print $1}')
    if [[ "$OLD_SIZE_KB" -gt 0 ]]; then
        echo -e "  Status: $(human_size "$OLD_SIZE_KB") used"
    else
        echo -e "  Status: empty"
    fi
    HAS_DATA=true
else
    echo -e "  Status: ${YELLOW}path does not exist${NC} (no data to copy)"
    HAS_DATA=false
    OLD_SIZE_KB=0
fi

echo ""

# ─────────────────────────────────────────────
# Phase 2: Ask for new path
# ─────────────────────────────────────────────

echo -e "  Where would you like to move the data?"
echo ""

# Collect available volumes (excluding system volumes)
VOLUMES=()
while IFS= read -r vol; do
    [[ -z "$vol" ]] && continue
    vol_path="/Volumes/${vol}"
    # Skip if it's the current path
    [[ "$vol_path" == "$OLD_PATH" ]] && continue
    VOLUMES+=("$vol_path")
done < <(ls -1 /Volumes/ 2>/dev/null | grep -v "Macintosh HD")

# Display numbered list
idx=1
for vol in "${VOLUMES[@]}"; do
    free_kb=$(df -k "$vol" 2>/dev/null | tail -1 | awk '{print $4}')
    echo -e "    ${idx}) ${vol}    ($(human_size "$free_kb") free)"
    (( idx++ ))
done
echo -e "    ${idx}) Enter a custom path"
echo ""

prompt "  Select [1-${idx}]: " choice

if [[ "$choice" -eq "$idx" ]] 2>/dev/null; then
    prompt "  Enter path: " NEW_PATH
elif [[ "$choice" -ge 1 && "$choice" -lt "$idx" ]] 2>/dev/null; then
    NEW_PATH="${VOLUMES[$((choice - 1))]}"
else
    echo -e "  ${RED}Invalid selection${NC}"
    exit 1
fi

# Expand ~ and resolve path
NEW_PATH="${NEW_PATH/#\~/$HOME}"

# Validate: same path?
if [[ "$OLD_PATH" == "$NEW_PATH" ]]; then
    echo -e "\n  ${RED}New path is the same as current path.${NC}"
    exit 1
fi

# Create if doesn't exist
if [[ ! -d "$NEW_PATH" ]]; then
    prompt "  Path ${NEW_PATH} does not exist. Create it? [Y/n]: " create_it
    if [[ "$create_it" =~ ^[Nn] ]]; then
        echo -e "  ${RED}Aborted.${NC}"
        exit 1
    fi
    mkdir -p "$NEW_PATH"
    echo -e "  ${GREEN}✓${NC} Created ${NEW_PATH}"
fi

# Validate: writable?
if ! touch "${NEW_PATH}/.write-test" 2>/dev/null; then
    echo -e "\n  ${RED}Cannot write to ${NEW_PATH}. Check permissions.${NC}"
    exit 1
fi
rm -f "${NEW_PATH}/.write-test"

echo ""

# ─────────────────────────────────────────────
# Phase 3: Pre-flight checks
# ─────────────────────────────────────────────

SKIP_COPY=false

if [[ "$HAS_DATA" == true && "$OLD_SIZE_KB" -gt 0 ]]; then
    # Check target has enough space
    TARGET_FREE_KB=$(df -k "$NEW_PATH" | tail -1 | awk '{print $4}')
    REQUIRED_KB=$(( OLD_SIZE_KB * 11 / 10 ))  # 1.1x buffer

    if [[ "$TARGET_FREE_KB" -lt "$REQUIRED_KB" ]]; then
        echo -e "  ${RED}Not enough space on target drive.${NC}"
        echo -e "  Data size:     $(human_size "$OLD_SIZE_KB")"
        echo -e "  Required:      $(human_size "$REQUIRED_KB") (with 10% buffer)"
        echo -e "  Available:     $(human_size "$TARGET_FREE_KB")"
        exit 1
    fi
else
    SKIP_COPY=true
fi

# ─────────────────────────────────────────────
# Phase 4: Discover running stacks
# ─────────────────────────────────────────────

RUNNING_STACKS=()
ALL_STACK_STATUS=()

for entry in "${DRIVE_STACKS[@]}"; do
    IFS=: read -r name dir <<< "$entry"
    if stack_is_running "$dir"; then
        RUNNING_STACKS+=("${name}:${dir}")
        ALL_STACK_STATUS+=("running:${name}")
    else
        ALL_STACK_STATUS+=("stopped:${name}")
    fi
done

RUNNING_COUNT=${#RUNNING_STACKS[@]}

# ─────────────────────────────────────────────
# Phase 5: Show plan + confirm
# ─────────────────────────────────────────────

echo -e "  ${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Migration Plan"
echo -e "  ${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "    From:  ${OLD_PATH} ($(human_size "$OLD_SIZE_KB"))"

TARGET_FREE_KB=$(df -k "$NEW_PATH" 2>/dev/null | tail -1 | awk '{print $4}')
echo -e "    To:    ${NEW_PATH} ($(human_size "$TARGET_FREE_KB") free)"
echo ""
echo "    Stacks to restart:"
for status_entry in "${ALL_STACK_STATUS[@]}"; do
    IFS=: read -r status name <<< "$status_entry"
    if [[ "$status" == "running" ]]; then
        echo -e "      ${GREEN}●${NC} ${name}  (running)"
    else
        echo -e "      ○ ${name}  (not running)"
    fi
done

echo ""
echo "    Steps:"
step=1
if [[ "$RUNNING_COUNT" -gt 0 ]]; then
    echo "      ${step}. Stop ${RUNNING_COUNT} running stack(s)"
    (( step++ ))
fi
echo "      ${step}. Create directory structure on new path"
(( step++ ))
if [[ "$SKIP_COPY" == false ]]; then
    echo "      ${step}. Copy data ($(human_size "$OLD_SIZE_KB"))"
    (( step++ ))
fi
if [[ "$RUNNING_COUNT" -gt 0 ]]; then
    echo "      ${step}. Restart ${RUNNING_COUNT} stack(s) with new path"
fi

echo ""
prompt "  Proceed? [y/N]: " confirm
if [[ ! "$confirm" =~ ^[Yy] ]]; then
    echo -e "  ${YELLOW}Aborted.${NC}"
    exit 0
fi

echo ""

# ─────────────────────────────────────────────
# Phase 6: Stop running stacks (reverse order)
# ─────────────────────────────────────────────

if [[ "$RUNNING_COUNT" -gt 0 ]]; then
    echo -e "${BLUE}==>${NC} Stopping stacks..."

    # Reverse the RUNNING_STACKS array for shutdown
    REVERSED=()
    for (( i=${#RUNNING_STACKS[@]}-1; i>=0; i-- )); do
        REVERSED+=("${RUNNING_STACKS[$i]}")
    done

    export DRIVE_PATH="$OLD_PATH"

    for entry in "${REVERSED[@]}"; do
        IFS=: read -r name dir <<< "$entry"
        echo -ne "  Stopping ${name}..."
        cd "${REPO_DIR}/${dir}"
        if docker compose down --timeout 30 &>/dev/null; then
            echo -e " ${GREEN}✓${NC}"
        else
            echo -e " ${YELLOW}⚠${NC} (may already be stopped)"
        fi
    done

    echo ""
fi

# ─────────────────────────────────────────────
# Phase 7: Create directory structure
# ─────────────────────────────────────────────

echo -e "${BLUE}==>${NC} Creating directory structure on ${NEW_PATH}..."

for dir in "${DIRECTORIES[@]}"; do
    full_path="${NEW_PATH}/${dir}"
    if [[ ! -d "$full_path" ]]; then
        mkdir -p "$full_path"
        echo -e "  ${GREEN}+${NC} ${dir}"
    fi
done

echo -e "  ${GREEN}✓${NC} Directory structure ready"
echo ""

# ─────────────────────────────────────────────
# Phase 8: Copy data
# ─────────────────────────────────────────────

if [[ "$SKIP_COPY" == false ]]; then
    echo -e "${BLUE}==>${NC} Copying data from ${OLD_PATH} to ${NEW_PATH}..."
    echo -e "  This may take a while for large media libraries."
    echo ""

    # Check if rsync supports --info=progress2 (macOS system rsync is too old)
    RSYNC_FLAGS="-avh --partial"
    if rsync --info=progress2 --version &>/dev/null; then
        RSYNC_FLAGS="${RSYNC_FLAGS} --info=progress2"
    else
        RSYNC_FLAGS="${RSYNC_FLAGS} --progress"
    fi

    # shellcheck disable=SC2086
    if rsync $RSYNC_FLAGS "${OLD_PATH}/" "${NEW_PATH}/"; then
        echo ""
        echo -e "  ${GREEN}✓${NC} Data copy complete"
    else
        echo ""
        echo -e "  ${RED}✗${NC} Data copy failed or was interrupted."
        echo ""
        echo "  Stacks have been stopped but NOT restarted."
        echo "  To resume the copy, re-run this script."
        echo "  rsync will pick up where it left off (--partial)."
        echo ""
        echo "  To restart stacks with the OLD path manually:"
        for entry in "${RUNNING_STACKS[@]}"; do
            IFS=: read -r name dir <<< "$entry"
            echo "    cd ${REPO_DIR}/${dir} && DRIVE_PATH=${OLD_PATH} docker compose up -d"
        done
        exit 1
    fi

    echo ""
fi

# ─────────────────────────────────────────────
# Phase 9: Restart stacks (deployment order)
# ─────────────────────────────────────────────

if [[ "$RUNNING_COUNT" -gt 0 ]]; then
    echo -e "${BLUE}==>${NC} Restarting stacks with new path..."

    export DRIVE_PATH="$NEW_PATH"

    for entry in "${RUNNING_STACKS[@]}"; do
        IFS=: read -r name dir <<< "$entry"
        echo -ne "  Starting ${name}..."
        cd "${REPO_DIR}/${dir}"
        if docker compose up -d --wait --wait-timeout 120 &>/dev/null; then
            echo -e " ${GREEN}✓${NC}"
        else
            echo -e " ${YELLOW}⚠${NC} (may still be starting)"
        fi
    done

    echo ""
fi

# ─────────────────────────────────────────────
# Phase 10: Summary
# ─────────────────────────────────────────────

echo -e "${GREEN}  ════════════════════════════════════════════${NC}"
echo -e "${GREEN}    Migration Complete${NC}"
echo -e "${GREEN}  ════════════════════════════════════════════${NC}"
echo ""
echo -e "  New drive path: ${BLUE}${NEW_PATH}${NC}"
if [[ "$RUNNING_COUNT" -gt 0 ]]; then
    echo ""
    echo "  Restarted stacks:"
    for entry in "${RUNNING_STACKS[@]}"; do
        IFS=: read -r name _ <<< "$entry"
        echo -e "    ${GREEN}✓${NC} ${name}"
    done
fi
echo ""
if [[ "$HAS_DATA" == true && "$SKIP_COPY" == false ]]; then
    echo -e "  ${YELLOW}Note:${NC} Old data at ${OLD_PATH} has NOT been deleted."
    echo "  Once you verify everything works, clean up with:"
    echo "    rm -rf \"${OLD_PATH}\"/{Media,Books,Photos,Documents,Downloads,Backups}"
fi
echo ""
echo -e "  ${YELLOW}Tip:${NC} To run deployment scripts with the new path:"
echo "    DRIVE_PATH=\"${NEW_PATH}\" ./scripts/07-download-stack.sh"
echo ""
