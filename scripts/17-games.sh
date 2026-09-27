#!/bin/bash
# 17-games.sh — the games site: games.noblehaus.uk (a hub page, and each game under its own path).
#
# A Caddy gateway (games/) on the homeserver network serves the hub at / and routes /<name>/ to
# each game. The games are their own projects (their own containers, or static files in
# ~/games-static/<name>/); this only routes to them. See docs/17-games.md.
#
# Idempotent: re-run after editing games/Caddyfile or games/site/ (it reloads the config).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
GAMES_DIR="${REPO_DIR}/games"
DOCKER="$(command -v docker || echo /usr/local/bin/docker)"
LAN_PORT=3010

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${BLUE}==>${NC} Games site"

mkdir -p "$HOME/games-static"
"$DOCKER" network inspect homeserver >/dev/null 2>&1 || "$DOCKER" network create homeserver >/dev/null

"$DOCKER" compose -f "${GAMES_DIR}/docker-compose.yml" up -d
# `up -d` leaves a running gateway alone when only the mounted Caddyfile changed: reload it.
"$DOCKER" exec games-gateway caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || true

for _ in $(seq 1 20); do
    curl -fsS "http://localhost:${LAN_PORT}/healthz" >/dev/null 2>&1 && break
    sleep 1
done
if ! curl -fsS "http://localhost:${LAN_PORT}/healthz" >/dev/null 2>&1; then
    echo -e "  ${YELLOW}⚠${NC} games-gateway isn't answering on :${LAN_PORT} — docker logs games-gateway"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} games-gateway up — http://localhost:${LAN_PORT}/"

# Each game in the hub's list, through the gateway.
python3 - "${GAMES_DIR}/site/games.json" <<'PY' | while read -r path name; do
import json, sys
for g in json.load(open(sys.argv[1])):
    print(g["path"], g["name"])
PY
    code="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${LAN_PORT}/${path}")"
    if [[ "$code" == "200" ]]; then
        echo -e "  ${GREEN}✓${NC} /${path} ${name}"
    else
        echo -e "  ${YELLOW}⚠${NC} /${path} ${name} — HTTP ${code} (is its container running?)"
    fi
done

echo ""
echo "Public address: https://games.noblehaus.uk/ — needs one Cloudflare public hostname,"
echo "games.noblehaus.uk → HTTP games-gateway:80 (see docs/17-games.md)."
