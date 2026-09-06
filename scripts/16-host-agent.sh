#!/bin/bash
# 16-host-agent.sh — install the host agent (bare-metal metrics, multi-drive
# storage, and move jobs for the Butler dashboard).
#
# Butler API runs in Docker and can only see the OrbStack VM. The agent runs on
# the Mac itself via launchd and answers on :7101 for butler-api
# (host.docker.internal:7101). See docs/16-host-agent.md.
#
# Idempotent: re-run to update the code or rotate nothing (the token is kept).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
AGENT_DIR="${REPO_DIR}/docker/host-agent"
AGENT_VENV="${AGENT_DIR}/.venv"
PLIST_SRC="${AGENT_DIR}/host-agent.plist"
PLIST_LABEL="uk.noblehaus.host-agent"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
BUTLER_ENV="${REPO_DIR}/butler/.env"

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${BLUE}==>${NC} Host agent"

# 1. Shared secret — reuse the one in butler/.env, or mint one and add it there.
TOKEN=""
if [[ -f "$BUTLER_ENV" ]]; then
    TOKEN="$(grep -E '^HOST_AGENT_TOKEN=' "$BUTLER_ENV" | head -1 | cut -d= -f2- || true)"
fi
if [[ -z "$TOKEN" ]]; then
    TOKEN="$(openssl rand -hex 32)"
    if [[ -f "$BUTLER_ENV" ]]; then
        printf '\n# Host agent (docker/host-agent) — bare-metal metrics + drive stats for the dashboard\nHOST_AGENT_TOKEN=%s\n' "$TOKEN" >> "$BUTLER_ENV"
        echo -e "  ${GREEN}✓${NC} Added HOST_AGENT_TOKEN to butler/.env (recreate butler-api to pick it up)"
    else
        echo -e "  ${YELLOW}⚠${NC} butler/.env not found — set HOST_AGENT_TOKEN=${TOKEN} on butler-api yourself"
    fi
else
    echo -e "  ${GREEN}✓${NC} Using existing HOST_AGENT_TOKEN from butler/.env"
fi

# 2. Python venv with aiohttp + psutil
PYTHON="$(command -v python3.12 || command -v python3)"
if [[ ! -d "$AGENT_VENV" ]]; then
    echo -e "${BLUE}==>${NC} Creating venv with ${PYTHON}..."
    "$PYTHON" -m venv "$AGENT_VENV"
fi
"$AGENT_VENV/bin/pip" install --quiet --upgrade pip aiohttp psutil
echo -e "  ${GREEN}✓${NC} aiohttp + psutil installed"

# 3. launchd plist with the token filled in
sed -e "s|REPLACE_WITH_RANDOM_SECRET|${TOKEN}|" \
    -e "s|/Users/ron/home-server|${REPO_DIR}|g" \
    "$PLIST_SRC" > "$PLIST_DEST"
chmod 600 "$PLIST_DEST"
launchctl bootout "gui/$(id -u)/${PLIST_LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"
launchctl enable "gui/$(id -u)/${PLIST_LABEL}"
echo -e "  ${GREEN}✓${NC} ${PLIST_LABEL} registered with launchd"

# 4. Verify (and check macOS let it read the external drives)
for _ in $(seq 1 20); do
    if HEALTH="$(curl -sf --max-time 2 http://localhost:7101/health 2>/dev/null)"; then
        echo -e "  ${GREEN}✓${NC} host-agent answering on :7101"
        if echo "$HEALTH" | grep -q '"diskAccess": {[^}]*false'; then
            PYBIN="$(echo "$HEALTH" | sed -n 's/.*"pythonBin": "\([^"]*\)".*/\1/p')"
            echo -e "  ${YELLOW}⚠${NC} macOS is blocking the agent from reading an external drive."
            echo "     System Settings → Privacy & Security → Full Disk Access → + → ⌘⇧G →"
            echo "     ${PYBIN}"
            echo "     then: launchctl kickstart -k gui/$(id -u)/${PLIST_LABEL}"
        fi
        exit 0
    fi
    sleep 1
done
echo -e "  ${YELLOW}⚠${NC} host-agent not answering yet — check /tmp/host-agent.err"
exit 1
