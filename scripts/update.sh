#!/bin/bash
# Home Server Update Script
#
# Pulls latest changes from GitHub and rebuilds only the Docker stacks
# that have changed. Can be run manually or called by Butler.
#
# Usage:
#   bash ~/home-server/scripts/update.sh          # check & update
#   bash ~/home-server/scripts/update.sh --check   # check only, no rebuild
#   bash ~/home-server/scripts/update.sh --force   # rebuild all stacks

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

REPO_DIR="${REPO_DIR:-$HOME/home-server}"
CHECK_ONLY=false
FORCE=false

for arg in "$@"; do
    case $arg in
        --check) CHECK_ONLY=true ;;
        --force) FORCE=true ;;
    esac
done

if [[ ! -d "$REPO_DIR/.git" ]]; then
    echo "Error: Repo not found at $REPO_DIR"
    echo "Run: git clone https://github.com/noble1911/home-server.git $REPO_DIR"
    exit 1
fi

cd "$REPO_DIR"

# Ensure we're on the main branch
CURRENT_BRANCH=$(git branch --show-current)
if [[ "$CURRENT_BRANCH" != "main" ]]; then
    echo -e "${YELLOW}⚠${NC} Not on main branch (on ${CURRENT_BRANCH}), switching..."
    git checkout main --quiet
fi

# Fetch latest without merging
git fetch origin main --quiet

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [[ "$LOCAL" == "$REMOTE" ]] && [[ "$FORCE" == "false" ]]; then
    echo -e "${GREEN}✓${NC} Already up to date"
    exit 0
fi

# Show what changed
COMMITS=$(git log --oneline HEAD..origin/main 2>/dev/null || true)
COMMIT_COUNT=$(echo "$COMMITS" | grep -c . || echo 0)

echo -e "${BLUE}==>${NC} ${COMMIT_COUNT} new commit(s) available:"
echo "$COMMITS" | head -10
if [[ "$COMMIT_COUNT" -gt 10 ]]; then
    echo "  ... and $((COMMIT_COUNT - 10)) more"
fi

# Determine which stacks need rebuilding
CHANGED_FILES=$(git diff --name-only HEAD..origin/main 2>/dev/null)

# Map changed files to their docker-compose stacks
# (parallel arrays for bash 3 compatibility — macOS ships with bash 3.2)
STACK_DIRS=(
    "docker/media-stack"
    "docker/download-stack"
    "docker/books-stack"
    "docker/photos-files-stack"
    "docker/smart-home-stack"
    "docker/voice-stack"
    "docker/messaging-stack"
    "butler"
    "app"
)
STACK_FILES=(
    "docker/media-stack/docker-compose.yml"
    "docker/download-stack/docker-compose.yml"
    "docker/books-stack/docker-compose.yml"
    "docker/photos-files-stack/docker-compose.yml"
    "docker/smart-home-stack/docker-compose.yml"
    "docker/voice-stack/docker-compose.yml"
    "docker/messaging-stack/docker-compose.yml"
    "butler/docker-compose.yml"
    "app/docker-compose.yml"
)

REBUILD_STACKS=()

i=0
while [[ $i -lt ${#STACK_DIRS[@]} ]]; do
    stack_dir="${STACK_DIRS[$i]}"
    compose_file="${STACK_FILES[$i]}"
    if [[ "$FORCE" == "true" ]]; then
        if [[ -f "$compose_file" ]]; then
            REBUILD_STACKS+=("$compose_file")
        fi
    else
        if echo "$CHANGED_FILES" | grep -q "^${stack_dir}/"; then
            if [[ -f "$compose_file" ]]; then
                REBUILD_STACKS+=("$compose_file")
            fi
        fi
    fi
    i=$((i + 1))
done

# Detect if the Claude Code shim needs restarting (runs on host, not Docker)
SHIM_CHANGED=false
if [[ "$FORCE" == "true" ]] || echo "$CHANGED_FILES" | grep -q "^docker/claude-code-shim/"; then
    SHIM_CHANGED=true
fi

# Also rebuild butler if scripts/lib changed (shared helpers)
if echo "$CHANGED_FILES" | grep -q "^scripts/lib/"; then
    echo -e "  ${YELLOW}⚠${NC} Shared helpers changed — review scripts manually"
fi

echo ""
if [[ ${#REBUILD_STACKS[@]} -eq 0 ]]; then
    echo -e "${GREEN}✓${NC} No Docker stacks need rebuilding (only non-Docker files changed)"
else
    echo -e "${BLUE}==>${NC} Stacks to rebuild:"
    for f in "${REBUILD_STACKS[@]}"; do
        echo "    - $f"
    done
fi

if [[ "$SHIM_CHANGED" == "true" ]]; then
    echo -e "  ${BLUE}==>${NC} Claude Code shim will be restarted"
fi

if [[ "$CHECK_ONLY" == "true" ]]; then
    echo ""
    echo "Run without --check to apply updates."
    exit 0
fi

# Pull changes
echo ""
echo -e "${BLUE}==>${NC} Pulling changes..."
if ! git pull --ff-only origin main; then
    echo -e "${YELLOW}⚠${NC} Fast-forward pull failed — local main may have diverged."
    echo "  Run 'cd $REPO_DIR && git status' to investigate."
    exit 1
fi

# Rebuild affected stacks
if [[ ${#REBUILD_STACKS[@]} -gt 0 ]]; then
    echo ""
    for compose_file in "${REBUILD_STACKS[@]}"; do
        stack_name=$(dirname "$compose_file")
        echo -e "${BLUE}==>${NC} Updating ${stack_name}..."
        if [[ "$compose_file" == "app/docker-compose.yml" ]]; then
            # Butler PWA: pull pre-built image from GHCR (built by CI)
            docker compose -f "$compose_file" pull
            docker compose -f "$compose_file" up -d --remove-orphans
        else
            # All other stacks: rebuild locally
            docker compose -f "$compose_file" up -d --build --remove-orphans
        fi
        echo -e "  ${GREEN}✓${NC} ${stack_name} updated"
    done
fi

# Restart Claude Code shim if its files changed (host-side launchd service)
if [[ "$SHIM_CHANGED" == "true" ]]; then
    SHIM_LABEL="uk.noblehaus.claude-code-shim"
    echo ""
    echo -e "${BLUE}==>${NC} Restarting Claude Code shim..."
    if launchctl kickstart -k "gui/$(id -u)/${SHIM_LABEL}" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} Claude Code shim restarted"
    else
        echo -e "  ${YELLOW}⚠${NC} Could not restart shim — try: launchctl kickstart -k gui/\$(id -u)/${SHIM_LABEL}"
    fi
fi

echo ""
echo -e "${GREEN}✓${NC} Update complete ($(git rev-parse --short HEAD))"
