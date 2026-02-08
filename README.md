# Home Server

Self-hosted media server with AI voice assistant on Mac Mini M4.

## Prerequisites

- **macOS on Apple Silicon** (Mac Mini M4 recommended)
- **8TB external drive** plugged in and formatted (APFS or Mac OS Extended)
- **API keys** to have ready (the setup script will prompt for each):

| Key | Required? | Where to get it |
|-----|-----------|-----------------|
| Anthropic API Key | **Yes** | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| Groq API Key | Recommended | [console.groq.com](https://console.groq.com/keys) (free — for voice STT) |
| OpenWeatherMap API Key | Optional | [openweathermap.org](https://openweathermap.org/api) (free tier) |
| Home Assistant Token | Optional | Generated in HA after setup |
| Google OAuth credentials | Optional | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) — see [setup guide](docs/google-oauth-setup.md) |
| Cloudflare Tunnel Token | **Recommended** | [Cloudflare Zero Trust](https://dash.cloudflare.com) — remote access for all services |

> Security secrets (JWT, LiveKit keys, internal API key) are **auto-generated** during setup.

## Quick Start

Run everything at once:

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/setup.sh | bash
```

Skip SSH if managing Mac Mini directly:

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/setup.sh | bash -s -- --no-ssh
```

Use a different external drive name:

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/setup.sh | bash -s -- --drive-name=MyDrive
```

Other flags:

| Flag | Description |
|------|-------------|
| `--no-ssh` | Skip SSH setup |
| `--drive-name=NAME` | External drive name (default: `HomeServer`) |
| `--skip-voice` | Skip voice stack deployment |
| `--skip-butler` | Skip Butler API deployment |

---

## Setup Guide

| Step | Script | Manual | Description |
|------|--------|--------|-------------|
| 1 | [01-homebrew.sh](scripts/01-homebrew.sh) | [docs](docs/01-homebrew.md) | Install Homebrew package manager |
| 3 | [03-power-settings.sh](scripts/03-power-settings.sh) | [docs](docs/03-power-settings.md) | Configure Mac to stay awake 24/7 |
| 4 | [04-ssh.sh](scripts/04-ssh.sh) | [docs](docs/04-ssh.md) | Enable SSH *(optional)* |
| 5 | [05-orbstack.sh](scripts/05-orbstack.sh) | [docs](docs/05-orbstack.md) | Install OrbStack (Docker) |
| 6 | [06-external-drive.sh](scripts/06-external-drive.sh) | [docs](docs/06-external-drive.md) | Configure external drive & directories |
| 7 | [07-download-stack.sh](scripts/07-download-stack.sh) | [docs](docs/07-download-stack.md) | Deploy qBittorrent + Prowlarr |
| 8 | [08-media-stack.sh](scripts/08-media-stack.sh) | [docs](docs/08-media-stack.md) | Deploy Jellyfin + Radarr + Sonarr + Bazarr |
| 9 | [09-books-stack.sh](scripts/09-books-stack.sh) | [docs](docs/09-books-stack.md) | Deploy Calibre-Web + Audiobookshelf + Readarr |
| 10 | [10-photos-files.sh](scripts/10-photos-files.sh) | [docs](docs/10-photos-files.md) | Deploy Immich + Nextcloud |
| 11 | [11-smart-home.sh](scripts/11-smart-home.sh) | [docs](docs/11-smart-home.md) | Deploy Home Assistant + Cloudflare Tunnel |
| 12 | [12-voice-stack.sh](scripts/12-voice-stack.sh) | [docs](docs/12-voice-stack.md) | Deploy LiveKit + Kokoro TTS |
| 13 | [13-butler.sh](scripts/13-butler.sh) | [docs](docs/13-butler.md) | Deploy Butler API (prompts for API keys) |

Run individual steps:
```bash
# Example: just install Homebrew
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/01-homebrew.sh | bash
```

Or follow the manual docs for step-by-step instructions.

---

## Configuration

All environment variables live in `butler/.env` (created from `.env.example` during step 13). The setup script prompts for each value interactively.

| Variable | Purpose | Auto-generated? |
|----------|---------|-----------------|
| `ANTHROPIC_API_KEY` | Claude API for Butler brain | No (prompted) |
| `JWT_SECRET` | PWA user authentication | Yes |
| `INTERNAL_API_KEY` | Service-to-service auth | Yes |
| `LIVEKIT_API_KEY` | Voice stack authentication | Yes |
| `LIVEKIT_API_SECRET` | Voice stack authentication | Yes |
| `GROQ_API_KEY` | Cloud STT via Groq Whisper | No (prompted) |
| `HA_TOKEN` | Home Assistant access | No (prompted) |
| `OPENWEATHERMAP_API_KEY` | Weather queries | No (prompted) |
| `GOOGLE_CLIENT_ID` | Google Calendar/Gmail OAuth | No (prompted) |
| `GOOGLE_CLIENT_SECRET` | Google Calendar/Gmail OAuth | No (prompted) |
| `CLOUDFLARE_TUNNEL_TOKEN` | Remote access for all services | No (prompted) |
| `INVITE_CODES` | Admin bootstrap invite code | Defaults to `BUTLER-001` |
| `DB_USER` / `DB_PASSWORD` | PostgreSQL (shared with Immich) | Defaults to `postgres` |

To reconfigure after setup, edit `butler/.env` and restart:
```bash
cd butler && docker compose down && docker compose up -d
```

---

## After Setup: First-Time Login for Each Service

Once `setup.sh` finishes, every service needs its own first-time setup. Open each URL in a browser on the same network (or remotely via your Cloudflare Tunnel domain) and create an admin account.

### Butler (AI Assistant)

Butler uses **invite codes** for registration. The first person to log in becomes the **admin**.

**First-time setup (admin):**
1. During `setup.sh`, you chose an admin invite code (default: `BUTLER-001`)
2. Open the PWA at `http://<server-ip>:3000`
3. Enter your admin invite code — this creates your account with admin privileges
4. Complete onboarding (set your name, preferences)

**Adding household members:**
1. Open **Settings** in the PWA (you must be admin)
2. Tap **Generate Invite Code** — a 6-character code is created (valid for 7 days)
3. Share the code with the person
4. They enter it at `http://<server-ip>:3000` to create their account
5. Used codes cannot be reused. You can revoke unused codes from Settings.

**Sessions & multi-device:**
- Access tokens expire after 1 hour and refresh automatically in the background
- Refresh tokens last 180 days — users stay logged in across device restarts
- No need to re-invite someone just because their session expired
- To use Butler on a new device, log in with the same invite code (admin code) or ask the admin for a new code

### Media Services

| Service | URL | First Login | Mobile App |
|---------|-----|-------------|------------|
| **Jellyfin** | `http://<server-ip>:8096` | Create admin account on first visit, then create accounts for household members | [Jellyfin](https://jellyfin.org/downloads/) (iOS/Android) |
| **Radarr** | `http://<server-ip>:7878` | No auth by default — add password in Settings > General > Security | Admin only (no mobile app) |
| **Sonarr** | `http://<server-ip>:8989` | No auth by default — add password in Settings > General > Security | Admin only (no mobile app) |
| **Prowlarr** | `http://<server-ip>:9696` | No auth by default — add password in Settings > General > Security | Admin only (no mobile app) |
| **qBittorrent** | `http://<server-ip>:8081` | Default: `admin` / check container logs for temp password | Admin only |

> **Tip:** Radarr, Sonarr, Prowlarr, and qBittorrent are admin-only tools. No need to create accounts for household members — they interact with media through Jellyfin.

### Books & Audio

| Service | URL | First Login | Mobile App |
|---------|-----|-------------|------------|
| **Audiobookshelf** | `http://<server-ip>:13378` | Create admin account on first visit, then invite household members | [Audiobookshelf](https://audiobookshelf.org/) (iOS/Android) |
| **Calibre-Web** | `http://<server-ip>:8083` | Default: `admin` / `admin123` — change immediately | Browser only |
| **Readarr** | `http://<server-ip>:8787` | No auth by default — add password in Settings | Admin only |

### Photos & Files

| Service | URL | First Login | Mobile App |
|---------|-----|-------------|------------|
| **Immich** | `http://<server-ip>:2283` | Create admin account on first visit, then invite household members | [Immich](https://immich.app/docs/features/mobile-app) (iOS/Android) — enable auto-backup |
| **Nextcloud** | `http://<server-ip>:8080` | Create admin account on first visit | [Nextcloud](https://nextcloud.com/install/#install-clients) (iOS/Android/Desktop) |

### Smart Home

| Service | URL | First Login | Mobile App |
|---------|-----|-------------|------------|
| **Home Assistant** | `http://<server-ip>:8123` | Create admin account, configure location/units, add smart devices | [Home Assistant](https://companion.home-assistant.io/) (iOS/Android) |

After setting up Home Assistant, generate a **Long-Lived Access Token** (Profile > Security) and add it to `butler/.env` as `HA_TOKEN` so Butler can control your devices.

### Recommended Setup Order

1. **Jellyfin** — create admin + household accounts
2. **Immich** — create admin, install mobile apps, enable photo backup
3. **Home Assistant** — add devices, generate token for Butler
4. **Audiobookshelf** — create admin + household accounts
5. **Butler PWA** — enter invite code, complete onboarding
6. ***arr stack** — configure indexers in Prowlarr, connect to Radarr/Sonarr/Readarr (admin only)

---

## Documentation

- **[HOMESERVER_PLAN.md](HOMESERVER_PLAN.md)** - Complete architecture and implementation plan
- **[docs/](docs/)** - Step-by-step setup guides
- **[docs/google-oauth-setup.md](docs/google-oauth-setup.md)** - Google OAuth setup for Calendar integration

---

## What Gets Installed

### Infrastructure
| Component | Purpose |
|-----------|---------|
| [Homebrew](https://brew.sh/) | Package manager for macOS |
| [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) | Secure remote access for all user-facing services |
| [OrbStack](https://orbstack.dev/) | Docker for macOS (optimized for Apple Silicon) |

### Media & Downloads
| Component | Purpose | Port |
|-----------|---------|------|
| [Jellyfin](https://jellyfin.org/) | Media streaming server | 8096 |
| [Radarr](https://radarr.video/) | Movie automation | 7878 |
| [Sonarr](https://sonarr.tv/) | TV series automation | 8989 |
| [Bazarr](https://www.bazarr.media/) | Subtitle automation | 6767 |
| [Prowlarr](https://prowlarr.com/) | Indexer manager | 9696 |
| [qBittorrent](https://www.qbittorrent.org/) | Torrent client | 8081 |

### Books & Audio
| Component | Purpose | Port |
|-----------|---------|------|
| [Calibre-Web](https://github.com/janeczku/calibre-web) | E-book library | 8083 |
| [Audiobookshelf](https://www.audiobookshelf.org/) | Audiobook streaming | 13378 |
| [Readarr](https://readarr.com/) | Book automation | 8787 |

### Photos & Files
| Component | Purpose | Port |
|-----------|---------|------|
| [Immich](https://immich.app/) | Photo management with AI | 2283 |
| [Nextcloud](https://nextcloud.com/) | File sync & collaboration | 8080 |

### Smart Home
| Component | Purpose | Port |
|-----------|---------|------|
| [Home Assistant](https://www.home-assistant.io/) | Smart home hub | 8123 |
| Cloudflare Tunnel | Secure remote access for all user-facing services | - |

### Voice Assistant
| Component | Purpose | Port |
|-----------|---------|------|
| [LiveKit](https://livekit.io/) | WebRTC server | 7880 |
| [Groq Whisper](https://console.groq.com/) | Speech-to-text (cloud, free tier) | - |
| LiveKit Agent | Voice pipeline orchestrator | - |
| [Kokoro TTS](https://github.com/remsky/Kokoro-FastAPI) | Text-to-speech | 8880 |

### AI Butler
| Component | Purpose | Port |
|-----------|---------|------|
| Butler API | FastAPI backend (chat, voice, auth, tools, OAuth) | 8000 |
| Butler PWA | React web app (voice + chat interface) | 3000 |

### Integrations (configured via Butler tools)
| Component | Purpose | Setup |
|-----------|---------|-------|
| Weather | Forecasts via OpenWeatherMap | API key in `.env` |
| Google Calendar | Calendar queries via OAuth | [setup guide](docs/google-oauth-setup.md) |
| Home Assistant | Smart home control | HA token in `.env` |
| Memory | User facts & preferences in PostgreSQL | Automatic |

---

## Repository Structure

```
home-server/
├── README.md                 # This file
├── HOMESERVER_PLAN.md        # Complete architecture plan
├── CLAUDE.md                 # Context for Claude agents
├── setup.sh                  # Run all setup steps
├── app/                      # Butler PWA (React + Vite)
│   ├── src/
│   │   ├── pages/            # Dashboard, Home, Login, Settings, etc.
│   │   ├── stores/           # Auth, user, conversation state
│   │   └── services/         # API client
│   ├── Dockerfile
│   └── docker-compose.yml
├── butler/                   # Butler API + tools
│   ├── api/                  # FastAPI server (auth, chat, voice, OAuth)
│   ├── tools/                # Custom Python tools (weather, calendar, HA, memory)
│   ├── migrations/           # PostgreSQL schema migrations
│   ├── livekit-agent/        # LiveKit Agents worker (STT → LLM → TTS)
│   ├── .env.example          # All configuration variables
│   └── docker-compose.yml    # Butler API container
├── scripts/
│   ├── 01-homebrew.sh        # Foundation scripts
│   ├── ...
│   ├── 12-voice-stack.sh
│   └── 13-butler.sh          # Butler API setup (prompts for API keys)
├── docker/
│   ├── download-stack/       # Docker Compose files
│   ├── media-stack/
│   ├── books-stack/
│   ├── photos-files-stack/
│   ├── smart-home-stack/
│   └── voice-stack/
└── docs/
    ├── 01-homebrew.md        # Manual instructions for each step
    ├── ...
    └── google-oauth-setup.md
```

---

## Monthly Costs

| Configuration | Cost |
|---------------|------|
| Base (no cloud backup) | ~£7.21 (Claude API + electricity) |
| With iCloud 2TB backup | ~£14.20 |

See [HOMESERVER_PLAN.md](HOMESERVER_PLAN.md) for detailed cost breakdown.
