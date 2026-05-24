#!/usr/bin/env bash
# Cross-check the registry (services.yaml) against live containers.
# Run on the server:  cd ~/home-server/registry && ./doctor.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER="${DOCKER:-/usr/local/bin/docker}"
command -v "$DOCKER" >/dev/null 2>&1 || DOCKER=docker

declared=$(grep -oE 'host_port:[[:space:]]*[0-9]+' "$DIR/services.yaml" \
            | grep -oE '[0-9]+' | sort -n -u)
live=$("$DOCKER" ps --format '{{.Ports}}' 2>/dev/null \
            | grep -oE '0\.0\.0\.0:[0-9]+' | cut -d: -f2 | sort -n -u)

echo "== Declared host ports (services.yaml) =="
echo "$declared" | tr '\n' ' '; echo
echo
echo "== Live published host ports (docker ps) =="
echo "$live" | tr '\n' ' '; echo

echo
echo "== Live but NOT in registry (undocumented — add to services.yaml) =="
undoc=$(comm -13 <(echo "$declared") <(echo "$live"))
[ -n "$undoc" ] && echo "$undoc" || echo "  (none — registry covers all live ports)"

echo
echo "== In registry but NOT live (stopped/stale/planned) =="
stale=$(comm -23 <(echo "$declared") <(echo "$live"))
[ -n "$stale" ] && echo "$stale" || echo "  (none)"

echo
echo "Tip: tunnel routes live in the Cloudflare dashboard — doctor.sh can't see them."
