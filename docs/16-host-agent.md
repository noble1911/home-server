# Step 16: Host Agent (bare-metal metrics, both drives, move jobs)

Butler API runs inside the OrbStack Linux VM. From there it can only see the
VM's CPU and RAM, and only the drives that are bind-mounted into the container.
The **host agent** is a small Python service that runs on the Mac itself (via
launchd) and gives the dashboard what the container can't see:

- Real Mac CPU, RAM, swap and load, plus the native apps (Jellyfin, Ollama,
  OrbStack) and per-container `docker stats`.
- Every drive — Mac SSD, HomeServer, HomeServer2 — with usage and a cached
  size per category folder (symlinked folders are reported as links, not
  double-counted).
- Move jobs: copy-verify-delete a folder from an allow-listed source
  (`Downloads/Complete`) into an allow-listed library root, with progress.
  Used by the media inbox for items Sonarr/Radarr don't recognise.

Port **7101**, token in the `X-Agent-Token` header. Registered in `registry/`.

## Automated

```bash
cd ~/home-server && ./scripts/16-host-agent.sh
cd butler && docker compose up -d butler-api   # picks up HOST_AGENT_TOKEN
```

The script reuses `HOST_AGENT_TOKEN` from `butler/.env` or mints one and
appends it, creates `docker/host-agent/.venv` with `aiohttp` + `psutil`,
installs `~/Library/LaunchAgents/uk.noblehaus.host-agent.plist` and waits for
`/health`.

## Manual

1. `python3 -m venv docker/host-agent/.venv && docker/host-agent/.venv/bin/pip install aiohttp psutil`
2. Copy `docker/host-agent/host-agent.plist` to `~/Library/LaunchAgents/`,
   replace `REPLACE_WITH_RANDOM_SECRET` with `openssl rand -hex 32`, and set
   the same value as `HOST_AGENT_TOKEN` in `butler/.env`.
3. `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/uk.noblehaus.host-agent.plist`
4. `curl localhost:7101/health` → `{"status":"ok","authenticated":true,...}`

## Verify

```bash
curl -H "X-Agent-Token: $TOKEN" localhost:7101/metrics | jq .cpu
curl -H "X-Agent-Token: $TOKEN" localhost:7101/storage | jq '.drives[].name'
tail -f /tmp/host-agent.log
```

## Configuration

Environment variables in the plist:

| Variable | Default | Purpose |
|---|---|---|
| `HOST_AGENT_TOKEN` | — | required; everything but `/health` refuses without it |
| `HOST_AGENT_PORT` | `7101` | |
| `HOST_AGENT_DRIVES` | built-in list | JSON list of `{name, path, role, categories}` |
| `HOST_AGENT_MOVE_SOURCES` | `/Volumes/HomeServer/Downloads/Complete` | colon-separated allow-list |
| `HOST_AGENT_MOVE_DESTINATIONS` | `/Volumes/HomeServer2/Media:/Volumes/HomeServer/Media:/Volumes/HomeServer/Downloads/Trash` | colon-separated allow-list. `Downloads/Trash` is the inbox's holding pen for duplicates and leftover folders; nothing empties it automatically |

Move jobs refuse anything outside the allow-lists; there is no delete
endpoint. The category `du` runs every 15 minutes in the background so
`/storage` is always instant.

---

Next: none — this is the last step. Back to [README](../README.md).
