---
name: media-status
description: Check status of all media services, download queues, active torrents, and Cloudflare tunnel health. Use when the user asks about downloads, what's happening on the server, or if something is working.
---

# Media Server Status Check

Check the health and status of all media services on the home server.

## Steps

SSH into the server for all commands: `ssh -i ~/.ssh/id_ed25519_homeserver 192.168.1.117`

Prefix all docker/curl commands with: `export PATH=$PATH:/opt/orbstack/bin:/usr/local/bin`

### 1. Container Health

```bash
docker ps --format '{{.Names}}\t{{.Status}}' | sort
```

Report any containers that are not "Up" or "(healthy)".

### 2. Download Queue (Sonarr)

- Get API key: `docker exec sonarr cat /config/config.xml` → extract `<ApiKey>`
- Get queue: `curl -s "http://localhost:8989/api/v3/queue?pageSize=50" -H "X-Api-Key: <key>"`
- Show unique downloads (deduplicate by `downloadId`) with title, status, and progress percentage

### 3. Download Queue (Radarr)

- Get API key: `docker exec radarr cat /config/config.xml` → extract `<ApiKey>`
- Get queue: `curl -s "http://localhost:7878/api/v3/queue?pageSize=50" -H "X-Api-Key: <key>"`
- Show unique downloads with title, status, and progress

### 4. Active Torrents (qBittorrent)

- Login: `curl -s -c /tmp/qbt_cookies.txt "http://localhost:8081/api/v2/auth/login" -d "username=admin&password=adminadmin"`
- Active downloads: `curl -s -b /tmp/qbt_cookies.txt "http://localhost:8081/api/v2/torrents/info?filter=downloading"`
- Show name, progress, size, seeds, and download speed

### 5. Cloudflare Tunnel

```bash
docker logs cloudflared --since 2m 2>&1 | tail -15
```

- Count ERR lines vs "Registered tunnel" lines
- If errors > 0 and no recent registrations → tunnel is down
- If errors > 0 with registrations → tunnel is unstable/reconnecting
- If no errors → tunnel is healthy

### 6. Disk Usage (optional)

```bash
df -h /Volumes/HomeServer 2>/dev/null
```

## Output format

Present a concise summary with status indicators:
- Use checkmarks for healthy services
- Use warnings for degraded services
- Use X for down services
- Show download progress as percentages
