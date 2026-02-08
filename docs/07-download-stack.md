# Step 7: Deploy Download Stack

Deploy qBittorrent (torrent client) and Prowlarr (indexer manager).

> **Note:** This script also creates the shared `homeserver` Docker network used by all stacks for cross-container communication.

## Automated

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/07-download-stack.sh | bash
```

## Manual

### 1. Create Docker Compose File

The compose file is at `docker/download-stack/docker-compose.yml`.

### 2. Start Services

```bash
cd docker/download-stack
docker compose up -d
```

### 3. Verify Running

```bash
docker compose ps
# Should show qbittorrent and prowlarr as "running"
```

## Services

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| qBittorrent | http://localhost:8081 | admin / adminadmin |
| Prowlarr | http://localhost:9696 | (set on first visit) |

## Initial Configuration

### qBittorrent

1. Open http://localhost:8081
2. Login with `admin` / `adminadmin`
3. Go to **Settings** (gear icon):

**Downloads tab:**
- Default Save Path: `/downloads/Complete`
- Keep incomplete torrents in: `/downloads/Incomplete`

**Categories (optional but recommended):**
- Create category `movies` → Save path: `/downloads/Complete/Movies`
- Create category `tv` → Save path: `/downloads/Complete/TV`
- Create category `books` → Save path: `/downloads/Complete/Books`

**Web UI tab:**
- Change the default password!

### Prowlarr

1. Open http://localhost:9696
2. Set up authentication on first visit
3. Add indexers and connect to *arr apps — see the **[Prowlarr Indexer Setup Guide](./prowlarr-indexers.md)** for detailed instructions

## Volume Mappings

| Container Path | Host Path | Purpose |
|----------------|-----------|---------|
| `/downloads` | `/Volumes/HomeServer/Downloads` | All downloads |
| `/config` | Docker volume (SSD) | App configuration |

## Docker Commands

```bash
# View logs
docker logs qbittorrent
docker logs prowlarr

# Restart a service
docker restart qbittorrent

# Stop all services
cd docker/download-stack
docker compose down

# Update images
docker compose pull
docker compose up -d
```

## Troubleshooting

### qBittorrent can't write to downloads

Check the PUID/PGID in docker-compose.yml match your user:
```bash
id -u  # Should be 501 on Mac
id -g  # Should be 20 on Mac
```

### Port conflicts

If port 8081 or 9696 is in use:
```bash
# Find what's using the port
lsof -i :8081

# Edit docker-compose.yml to use different ports
```

## What This Does

- **Creates `homeserver` network:** A shared Docker network enabling all containers to communicate by hostname
- **qBittorrent:** Downloads torrents to the external drive
- **Prowlarr:** Manages indexers and syncs them to *arr apps
- **Auto-configures public indexers:** 1337x, RARBG, YTS, EZTV, LimeTorrents, plus anime indexers (Nyaa.si, Tokyo Toshokan, Shana Project)

The *arr apps (Radarr, Sonarr, etc.) will tell qBittorrent what to download and where to save it.

## Shared Network

All stacks join the `homeserver` network, allowing containers to communicate using their container names as hostnames:

```
radarr → qbittorrent:8081      (download client)
prowlarr → radarr:7878         (indexer sync)
butler-api → immich-postgres:5432 (memory storage)
```

If you need to manually create the network:
```bash
docker network create homeserver
```

## Next Step

→ [Step 8: Deploy Media Stack](./08-media-stack.md)
