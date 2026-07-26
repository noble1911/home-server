#!/bin/bash
# OrbStack socket monitor (read-only)
#
# Records how many host-side sockets OrbStack's port-forwarding proxy is
# holding, so we can tell whether a given OrbStack version leaks half-closed
# peer sockets over time.
#
# Background: qBittorrent's inbound torrent port is published through OrbStack's
# host proxy. When the proxy fails to reap FIN_WAIT_2 sockets from dropped
# BitTorrent peers, they accumulate over days/weeks and eventually exhaust the
# macOS ephemeral port range (~16k), which starves the host of new outbound
# connections ("Server connections interrupted", Jellyfin falsely shows down).
# See OrbStack issues #2144 / #1933. Upgraded to 2.2.1 on 2026-07-26 to test
# whether that stops the leak — this logger is how we measure it.
#
# This script ONLY observes and logs. It never restarts anything.
# Run hourly via launchd (uk.noblehaus.orbstack-socket-monitor.plist).

set -eo pipefail

LOG="${ORBSTACK_MONITOR_LOG:-$HOME/Library/Logs/orbstack-socket-monitor.log}"
mkdir -p "$(dirname "$LOG")"

# Ephemeral port range on macOS is 49152-65535 (~16384 ports). Once the proxy's
# stranded sockets fill it, the host can't open new outbound connections.
netstat_out="$(netstat -an -p tcp 2>/dev/null || true)"

fin_wait_2=$(printf '%s\n' "$netstat_out" | grep -c 'FIN_WAIT_2' || true)
close_wait=$(printf '%s\n' "$netstat_out" | grep -c 'CLOSE_WAIT' || true)
time_wait=$(printf '%s\n' "$netstat_out" | grep -c 'TIME_WAIT' || true)
established=$(printf '%s\n' "$netstat_out" | grep -c 'ESTABLISHED' || true)
total=$(printf '%s\n' "$netstat_out" | grep -cE 'tcp[46]' || true)

orb_ver=$(defaults read /Applications/OrbStack.app/Contents/Info CFBundleShortVersionString 2>/dev/null || echo '?')
ts=$(date '+%Y-%m-%dT%H:%M:%S%z')

printf '%s orb=%s FIN_WAIT_2=%s CLOSE_WAIT=%s TIME_WAIT=%s ESTABLISHED=%s total_tcp=%s\n' \
  "$ts" "$orb_ver" "$fin_wait_2" "$close_wait" "$time_wait" "$established" "$total" >> "$LOG"
