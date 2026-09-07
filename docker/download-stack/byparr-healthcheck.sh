#!/bin/sh
# Health check for the byparr (flaresolverr) container. Mounted read-only at
# /healthcheck.sh and run by Docker on the schedule in docker-compose.yml.
#
# Exit 0 = healthy, 1 = unhealthy. Three unhealthy results in a row make Docker
# mark the container unhealthy, and autoheal then restarts it. So this script
# must only return 1 when a restart would actually help.
#
# History: byparr's own /health does a real Firefox navigation to google.com.
# When DNS stalled on the Mac (2026-09-05 and 2026-09-06, VM-wide, Prowlarr saw
# it too) that navigation hung or failed with NS_ERROR_UNKNOWN_HOST, the plain
# `curl -f /health` check tripped, and autoheal restarted a container that was
# serving Prowlarr fine. Eight restarts in two hours, none of them useful.

PORT="${PORT:-8191}"

# 1. Liveness: is the FastAPI process answering at all? No browser involved.
if ! curl -fsS -m 5 -o /dev/null "http://127.0.0.1:${PORT}/openapi.json"; then
  echo "api not answering"
  exit 1
fi

# 2. Deep check: can the browser load a page? (byparr's /health -> google.com)
code=$(curl -sS -m 45 -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/health")
if [ "$code" = "200" ]; then
  exit 0
fi

# 3. /health failed: 502 = target unreachable, 000 = timed out, 500 = non-200 page.
#    Work out whose fault it is. If curl can't reach the internet either, the
#    network/DNS is down and restarting byparr fixes nothing: report healthy so
#    we don't churn. Only when the network is fine and the browser still can't
#    load a page is byparr itself wedged.
if curl -fsS -m 8 -o /dev/null https://www.google.com/; then
  echo "browser check failed (http $code) while network is fine"
  exit 1
fi
echo "network unreachable (http $code), not byparr's fault"
exit 0
