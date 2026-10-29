# Step 8: Deploy Media Stack

Deploy Jellyfin (media server), the *arr apps for movie/TV automation, and Seerr for media requests.

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
| Seerr | http://localhost:5055 | Media request management |
| Dispatcharr | http://localhost:9191 | IPTV / live TV manager (feeds Jellyfin Live TV) |

## Initial Configuration

### Jellyfin

> **Note:** The setup script auto-configures Jellyfin libraries. The manual steps below are only needed if auto-configuration was skipped.

1. Open http://localhost:8096
2. Complete the setup wizard:
   - Create admin username/password
   - Add library: **Movies** → `/media/movies`
   - Add library: **TV Shows** → `/media/tv`
   - Add library: **Anime Movies** → `/media/anime-movies`
   - Add library: **Anime Series** → `/media/anime-series`
   - Add library: **Music** → `/media/music`
   - Configure language/metadata preferences
3. Install apps on your devices (iOS, Android, TV, etc.)

### Radarr

1. Open http://localhost:7878
2. **Settings > Media Management:**
   - Add Root Folder: `/movies` (regular movies)
   - Add Root Folder: `/anime-movies` (anime films)
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
   - Add Root Folder: `/tv` (regular TV shows)
   - Add Root Folder: `/anime-series` (anime series)
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

### Seerr

1. Open http://localhost:5055
2. Sign in with your Jellyfin admin account
3. **Radarr Settings:**
   - Host: `radarr`
   - Port: `7878`
   - API Key: (from Radarr Settings > General)
4. **Sonarr Settings:**
   - Host: `sonarr`
   - Port: `8989`
   - API Key: (from Sonarr Settings > General)
5. Copy the **API Key** from Settings > General for Butler integration
6. Optionally enable auto-approval for admin users

### Dispatcharr (Live TV)

Dispatcharr manages IPTV playlists (M3U / Xtream Codes) and guide data (EPG), then re-serves
the channels you pick as a virtual HDHomeRun tuner that Jellyfin can play and record.

1. Open http://localhost:9191 and create the admin account (first visit only — allowed from the LAN).
   Then in Butler, **Settings > Live TV provider**, enter your IPTV login; Butler pushes it into
   Dispatcharr as the "Butler IPTV" playlist. Butler signs in to Dispatcharr with your service login,
   or with the **Dispatcharr sign-in** fields there if your Dispatcharr password differs.
2. **M3U & EPG Manager:** add your playlist (M3U URL or Xtream Codes login) and an EPG/XMLTV source.
3. **Channels:** create channels from the imported streams and match them to EPG entries.
4. In Jellyfin (**Dashboard > Live TV**):
   - **Tuner Devices > Add > HD Homerun:** `http://localhost:9191/hdhr` (Jellyfin is the native
     app on the same Mac, so `localhost` reaches the container's published port).
     Alternatively add an **M3U Tuner** with `http://localhost:9191/output/m3u`.
   - **TV Guide Data Providers > Add > XMLTV:** `http://localhost:9191/output/epg`.

**Recording:** Jellyfin's Live TV saves recordings to `Media/Recordings` on the external drive
(Dashboard > Live TV > Recording path; subfolders on, 2 min before / 5 min after padding). Never
leave it on the default, which is inside Jellyfin's data folder on the internal SSD. HD channels run
about 2.5 GB per hour. Recording and watching live each use one of the plan's simultaneous
streams (the limit is set in Butler's Live TV provider settings).

Butler's dashboard and `server_health` tool probe `/hdhr/discover.json` (Media group). Data
(settings, channels, its bundled Postgres + Redis) lives in the `dispatcharr-data` volume,
which the daily backup includes.

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
| Jellyfin | `/media/movies` | `Media/Movies` (read-only) |
| Jellyfin | `/media/tv` | `Media/TV` (read-only) |
| Jellyfin | `/media/anime-movies` | `Media/Anime/Movies` (read-only) |
| Jellyfin | `/media/anime-series` | `Media/Anime/Series` (read-only) |
| Jellyfin | `/media/music` | `Media/Music` (read-only) |
| Radarr | `/movies` | `Media/Movies` |
| Radarr | `/anime-movies` | `Media/Anime/Movies` |
| Radarr | `/downloads` | `Downloads` |
| Sonarr | `/tv` | `Media/TV` |
| Sonarr | `/anime-series` | `Media/Anime/Series` |
| Sonarr | `/downloads` | `Downloads` |
| Bazarr | `/movies`, `/tv`, `/anime-movies`, `/anime-series` | Matching media folders |
| Dispatcharr | `/data` | `dispatcharr-data` volume |

## The Download Flow

```
You (or household members) request in Seerr
        ↓
Seerr sends to Radarr/Sonarr
        ↓
Or you search directly in Radarr/Sonarr
        ↓
Prowlarr provides indexers
        ↓
Radarr/Sonarr sends to qBittorrent
        ↓
qBittorrent downloads to /Downloads/Complete/{Movies,TV,Anime}
        ↓
Radarr/Sonarr moves to /Media/{Movies,TV,Anime/Movies,Anime/Series}
        ↓
Jellyfin sees it in the matching library
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
