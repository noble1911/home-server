# Step 8: Deploy Media Stack

Deploy Jellyfin (media server) and the *arr apps for movie/TV automation.

## Automated

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/08-media-stack.sh | bash
```

## Manual

### 1. Start Services

```bash
cd docker/media-stack
docker compose up -d
```

### 2. Verify Running

```bash
docker compose ps
```

## Services

| Service | URL | Purpose |
|---------|-----|---------|
| Jellyfin | http://localhost:8096 | Media streaming server |
| Radarr | http://localhost:7878 | Movie automation |
| Sonarr | http://localhost:8989 | TV series automation |
| Bazarr | http://localhost:6767 | Subtitle automation |

## Initial Configuration

### Jellyfin

1. Open http://localhost:8096
2. Complete the setup wizard:
   - Create admin username/password
   - Add library: **Movies** → `/media/Movies`
   - Add library: **TV Shows** → `/media/TV`
   - Configure language/metadata preferences
3. Install apps on your devices (iOS, Android, TV, etc.)

### Radarr

1. Open http://localhost:7878
2. **Settings > Media Management:**
   - Add Root Folder: `/movies`
   - Enable "Rename Movies"
3. **Settings > Download Clients:**
   - Add qBittorrent:
     - Host: `qbittorrent`
     - Port: `8081`
     - Category: `movies`
4. **Settings > General:**
   - Copy the API Key (needed for Prowlarr)

### Sonarr

1. Open http://localhost:8989
2. **Settings > Media Management:**
   - Add Root Folder: `/tv`
   - Enable "Rename Episodes"
3. **Settings > Download Clients:**
   - Add qBittorrent:
     - Host: `qbittorrent`
     - Port: `8081`
     - Category: `tv`
4. **Settings > General:**
   - Copy the API Key (needed for Prowlarr)

### Bazarr

1. Open http://localhost:6767
2. **Settings > Sonarr:**
   - Enable, Host: `sonarr`, API Key from Sonarr
3. **Settings > Radarr:**
   - Enable, Host: `radarr`, API Key from Radarr
4. **Settings > Providers:**
   - Add subtitle providers (OpenSubtitles, etc.)
5. **Settings > Languages:**
   - Configure preferred subtitle languages

### Connect Prowlarr to *arr Apps

In Prowlarr (http://localhost:9696):

1. **Settings > Apps > Add Application:**
   - **Radarr:**
     - Prowlarr Server: `http://prowlarr:9696`
     - Radarr Server: `http://radarr:7878`
     - API Key: (from Radarr Settings > General)
   - **Sonarr:**
     - Prowlarr Server: `http://prowlarr:9696`
     - Sonarr Server: `http://sonarr:8989`
     - API Key: (from Sonarr Settings > General)

2. Prowlarr will now sync all your indexers to both apps automatically!

## Volume Mappings

| Service | Container Path | Host Path |
|---------|----------------|-----------|
| Jellyfin | `/media` | `/Volumes/HomeServer/Media` (read-only) |
| Radarr | `/movies` | `/Volumes/HomeServer/Media/Movies` |
| Radarr | `/downloads` | `/Volumes/HomeServer/Downloads` |
| Sonarr | `/tv` | `/Volumes/HomeServer/Media/TV` |
| Sonarr | `/downloads` | `/Volumes/HomeServer/Downloads` |
| Bazarr | `/movies`, `/tv` | Media folders |

## The Download Flow

```
You search in Radarr/Sonarr
        ↓
Prowlarr provides indexers
        ↓
Radarr/Sonarr sends to qBittorrent
        ↓
qBittorrent downloads to /Downloads/Complete/Movies (or TV)
        ↓
Radarr/Sonarr moves to /Media/Movies (or TV)
        ↓
Jellyfin sees it in library
```

## Quality Profiles

Recommended profiles for a good balance of quality vs storage:

**Radarr (Movies):**
- 4K for new releases and favorites
- 1080p Bluray for everything else

**Sonarr (TV):**
- 1080p HDTV/WEB for ongoing shows
- 1080p Bluray for completed series you love

## Docker Commands

```bash
# View logs
docker logs jellyfin
docker logs radarr

# Restart all
cd docker/media-stack
docker compose restart

# Update images
docker compose pull
docker compose up -d
```

## Troubleshooting

### Radarr/Sonarr can't connect to qBittorrent

Make sure containers are on the shared `homeserver` network:
```bash
docker network ls
docker network inspect homeserver
```

The *arr apps should use container names (`qbittorrent`) not `localhost`.

> **Note:** The `homeserver` network is created by the download-stack script (Step 7). If it doesn't exist, create it manually: `docker network create homeserver`

### Jellyfin not seeing new media

- Check the library scan settings
- Trigger manual scan: Dashboard > Libraries > Scan

### Permission issues

Verify PUID/PGID match your Mac user:
```bash
id -u  # Should be 501
id -g  # Should be 20
```

## Next Step

→ [Step 9: Deploy Books Stack](./09-books-stack.md)
