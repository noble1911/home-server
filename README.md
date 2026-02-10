# Home Server

Self-hosted media server with AI voice assistant on Mac Mini M4.

---

## Installation Guide

This guide walks through everything needed to set up your home server from scratch. There are four phases:

1. **Hardware Prep** — plug in, format drive
2. **External Accounts** — create accounts and API keys that `setup.sh` will prompt for
3. **Run setup.sh** — the automated installation
4. **Post-Setup** — first-time login for each service, mobile apps, Alexa

> **Time estimate:** Phase 2 takes ~30-45 minutes of web-based setup. Phase 3 runs for ~15-20 minutes (mostly unattended). Phase 4 takes ~20-30 minutes.

---

## Phase 1: Hardware Prep

### 1.1 External Drive

> **No external drive?** Pass `--skip-drive` to `setup.sh` and data will be stored at `~/HomeServer` on the internal SSD instead. You can migrate to an external drive later with `scripts/change-drive.sh`. Skip to [1.2 Network](#12-network).

Plug in your external USB drive and format it:

1. Open **Disk Utility** (Spotlight → search "Disk Utility")
2. Select your external drive in the sidebar
3. Click **Erase**
4. Set:
   - **Name:** `HomeServer` (or your choice — pass `--drive-name=YourName` to setup.sh later)
   - **Format:** APFS (recommended) or Mac OS Extended (Journaled)
5. Click **Erase** and wait for it to finish

Verify it appears at `/Volumes/HomeServer` (or your chosen name).

### 1.2 Network

Connect the Mac Mini to your router via **Ethernet cable** (recommended over Wi-Fi for media streaming).

### 1.3 Find Your Local IP

You'll need this throughout setup:

```bash
ipconfig getifaddr en0
```

Note this IP — all services will be accessible at `http://<this-ip>:<port>`.

---

## Phase 2: External Accounts & API Keys

Set up these accounts **before** running `setup.sh`. The script will prompt for each key interactively.

> **Tip:** Open a notes app and paste each key as you go — you'll enter them all at once during Phase 3.

### Step 1: Anthropic API Key (Required)

Butler's AI brain runs on Claude. You need an API key with credit loaded.

1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Create an account or sign in
3. Go to **Settings → API Keys**
4. Click **Create Key**, name it `butler`
5. Copy the key (starts with `sk-ant-...`)
6. Go to **Settings → Billing** and add credit (£5-10 to start)

> **Cost:** ~£7/month for typical household use (~500 requests/month with multi-turn history).

### Step 2: Groq API Key (Recommended)

Groq provides free speech-to-text for the voice assistant.

1. Go to [console.groq.com](https://console.groq.com/)
2. Create an account
3. Go to **API Keys** in the sidebar
4. Click **Create API Key**, name it `butler`
5. Copy the key (starts with `gsk_...`)

> **Cost:** Free tier gives 8 hours of audio transcription per day — more than enough.

### Step 3: Cloudflare Tunnel (Recommended)

Cloudflare Tunnel lets you access all services remotely (phone, laptop, anywhere) without opening ports.

#### 3a. Create Cloudflare Account

1. Go to [dash.cloudflare.com](https://dash.cloudflare.com/)
2. Sign up for a free account

#### 3b. Add a Domain (optional but recommended)

If you own a domain, add it to Cloudflare:

1. Click **Add a site** in the dashboard
2. Enter your domain and follow the setup steps
3. Update your domain's nameservers to Cloudflare's

> If you don't have a domain, Cloudflare can generate a free `*.cfargotunnel.com` subdomain — but a custom domain is nicer for URLs like `jellyfin.yourdomain.com`.

#### 3c. Create the Tunnel

1. In the Cloudflare dashboard, go to **Zero Trust → Networks → Tunnels**
2. Click **Create a tunnel**
3. Choose **Cloudflared** as the connector type
4. Name it `homeserver`
5. On the "Install connector" step, copy the **tunnel token** (a long string)
6. Don't close this page yet — you'll add routes after setup.sh runs

#### 3d. Plan Your Subdomains

Decide which services you want accessible remotely. Example mapping:

| Subdomain | Service | Port |
|-----------|---------|------|
| `butler.yourdomain.com` | Butler PWA | 3000 |
| `jellyfin.yourdomain.com` | Jellyfin | 8096 |
| `photos.yourdomain.com` | Immich | 2283 |
| `books.yourdomain.com` | Audiobookshelf | 13378 |
| `files.yourdomain.com` | Nextcloud | 8080 |
| `ha.yourdomain.com` | Home Assistant | 8123 |
| `shelfarr.yourdomain.com` | Shelfarr | 5056 |
| `requests.yourdomain.com` | Seerr | 5055 |

You'll configure these routes in the Cloudflare dashboard after `setup.sh` has deployed the services.

### Step 4: Google OAuth Credentials (Optional)

Required if you want Butler to read your Google Calendar and Gmail.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project called `Butler Home Server`
3. Go to **APIs & Services → Library**
4. Enable **Google Calendar API** and **Gmail API**
5. Go to **APIs & Services → OAuth consent screen**
6. Choose **External**, fill in app name (`Butler`), your email
7. Add scopes:
   - `https://www.googleapis.com/auth/calendar.readonly`
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/userinfo.email`
8. Add your household Google accounts as **test users**
9. Go to **APIs & Services → Credentials**
10. Click **Create Credentials → OAuth client ID**
11. Choose **Web application**, name it `Butler Web`
12. Add **Authorized redirect URIs**:
    - `http://localhost:8000/api/oauth/google/callback`
    - `https://butler.yourdomain.com/api/oauth/google/callback` (if using Cloudflare Tunnel)
13. Copy the **Client ID** and **Client Secret**

> See [docs/google-oauth-setup.md](docs/google-oauth-setup.md) for detailed walkthrough with screenshots.

### Step 5: OpenWeatherMap API Key (Optional)

Required if you want Butler to answer weather questions.

1. Go to [openweathermap.org/api](https://openweathermap.org/api)
2. Sign up for a free account
3. Go to **API keys** in your profile
4. Copy your API key

> **Cost:** Free tier gives 1,000 API calls/day — plenty for personal use.

### Checklist Before Running setup.sh

Confirm you have these ready:

| Item | Status |
|------|--------|
| External drive plugged in and formatted (or use `--skip-drive`) | ☐ |
| Mac Mini connected via Ethernet | ☐ |
| Anthropic API key | ☐ |
| Groq API key (or skip voice) | ☐ |
| Cloudflare Tunnel token (or skip remote access) | ☐ |
| Google OAuth Client ID + Secret (optional) | ☐ |
| OpenWeatherMap API key (optional) | ☐ |

---

## Phase 3: Run setup.sh

### Quick Start

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/setup.sh | bash
```

The script will:

1. **Prompt for admin credentials** — usernames/passwords for Jellyfin, Audiobookshelf, and Nextcloud
2. **Install Homebrew** and CLI tools
3. **Configure power settings** — prevent sleep, auto-restart after power failure
4. **Install OrbStack** — Docker runtime optimized for Apple Silicon
5. **Set up external drive** — create directory structure on `/Volumes/HomeServer` (or `~/HomeServer` with `--skip-drive`)
6. **Deploy all Docker stacks** — downloads images and starts containers
7. **Auto-configure services** — connects Radarr/Sonarr to Prowlarr and qBittorrent, creates admin accounts, sets up media libraries
8. **Prompt for API keys** — enter the keys you collected in Phase 2

### Options

| Flag | Description |
|------|-------------|
| `--no-ssh` | Skip SSH setup (if managing Mac Mini directly) |
| `--drive-name=NAME` | External drive name (default: `HomeServer`) |
| `--skip-voice` | Skip voice stack (LiveKit + Kokoro TTS) |
| `--skip-butler` | Skip Butler API deployment |
| `--skip-drive` | Use internal SSD instead of external drive (data at `~/HomeServer`) |

Examples:

```bash
# Skip SSH, use a different drive name
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/setup.sh | bash -s -- --no-ssh --drive-name=MyDrive

# Minimal install (no voice, no Butler)
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/setup.sh | bash -s -- --skip-voice --skip-butler

# No external drive — store everything on internal SSD
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/setup.sh | bash -s -- --skip-drive

# Later, migrate from internal SSD to an external drive:
cd ~/home-server && ./scripts/change-drive.sh
```

### What Gets Deployed

| Step | Script | Services |
|------|--------|----------|
| 1 | `01-homebrew.sh` | Homebrew package manager |
| 2 | `03-power-settings.sh` | macOS power & sleep settings |
| 3 | `04-ssh.sh` | SSH access (optional) |
| 4 | `05-orbstack.sh` | OrbStack (Docker) |
| 5 | `06-external-drive.sh` | External drive directory structure |
| 6 | `07-download-stack.sh` | qBittorrent + Prowlarr |
| 7 | `08-media-stack.sh` | Jellyfin + Radarr + Sonarr + Bazarr + Seerr |
| 8 | `09-books-stack.sh` | Audiobookshelf + Shelfarr |
| 9 | `10-photos-files.sh` | Immich + Nextcloud |
| 10 | `11-smart-home.sh` | Home Assistant + Cloudflare Tunnel |
| 11 | `12-voice-stack.sh` | LiveKit + Kokoro TTS |
| 12 | `13-butler.sh` | Butler API + PWA |

Run individual steps if needed:

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/08-media-stack.sh | bash
```

Each step also has a manual guide in [docs/](docs/).

### Credentials File

Setup generates `~/.homeserver-credentials` with admin passwords and auto-generated API keys. This file is used by the scripts and is **not committed to git**. Keep it safe.

---

## Phase 4: Post-Setup Configuration

Once `setup.sh` finishes, every service needs first-time configuration. Open each URL in a browser on the same network.

### 4.1 Configure Cloudflare Tunnel Routes

Now that services are running, go back to the Cloudflare dashboard and add routes:

1. Go to **Zero Trust → Networks → Tunnels** → click your tunnel → **Configure**
2. For each service you want remotely accessible, click **Add a public hostname**:

| Subdomain | Service (Type: HTTP) | URL |
|-----------|---------------------|-----|
| `butler` | `http://butler-app:80` | Butler PWA |
| `butler-api` | `http://butler-api:8000` | Butler API |
| `jellyfin` | `http://jellyfin:8096` | Jellyfin |
| `photos` | `http://immich-server:2283` | Immich |
| `books` | `http://audiobookshelf:80` | Audiobookshelf |
| `files` | `http://nextcloud:80` | Nextcloud |
| `ha` | `http://homeassistant:8123` | Home Assistant |
| `shelfarr` | `http://shelfarr:5056` | Shelfarr |
| `requests` | `http://seerr:5055` | Seerr |

> **Important:** Use Docker container names (not `localhost`) because `cloudflared` runs inside Docker where `localhost` refers to the container itself, not the host machine.

3. After adding routes, verify each service loads via its `https://subdomain.yourdomain.com` URL

4. **Update Butler app service URLs** — so the Services tab links to your tunnel URLs instead of LAN addresses. Create `app/.env` with your subdomains:

   ```env
   VITE_JELLYFIN_URL=https://jellyfin.yourdomain.com
   VITE_AUDIOBOOKSHELF_URL=https://books.yourdomain.com
   VITE_SHELFARR_URL=https://shelfarr.yourdomain.com
   VITE_IMMICH_URL=https://photos.yourdomain.com
   VITE_NEXTCLOUD_URL=https://files.yourdomain.com
   VITE_HOMEASSISTANT_URL=https://ha.yourdomain.com
   VITE_SEERR_URL=https://requests.yourdomain.com
   ```

   Then rebuild the Butler app: `cd app && npm run build` (or rebuild the Docker image).

> **Note:** On LAN, service URLs auto-detect from the browser hostname (e.g. `http://192.168.1.22:8096`), so no configuration is needed for local access.

### 4.2 Set Up Butler (AI Assistant)

Butler uses **invite codes** for registration. The first person to log in becomes the admin.

1. Open `http://<server-ip>:3000`
2. Enter your admin invite code (default: `BUTLER-001`, or what you chose during setup)
3. Complete onboarding (set your name, preferences)
4. To add household members: **Settings → Generate Invite Code** → share the 6-character code

### 4.3 Set Up Media Services

| Service | URL | First-Time Setup |
|---------|-----|-----------------|
| **Jellyfin** | `http://<server-ip>:8096` | Auto-configured by setup — verify libraries (Movies, TV, Music) are present |
| **Radarr** | `http://<server-ip>:7878` | Auto-configured — add password in Settings → General → Security |
| **Sonarr** | `http://<server-ip>:8989` | Auto-configured — add password in Settings → General → Security |
| **Prowlarr** | `http://<server-ip>:9696` | Auto-configured with public indexers — optionally add private indexers ([guide](docs/prowlarr-indexers.md)) |
| **qBittorrent** | `http://<server-ip>:8081` | Auto-configured — check container logs for temp password if needed |
| **Bazarr** | `http://<server-ip>:6767` | Auto-configured — connected to Radarr + Sonarr |
| **Seerr** | `http://<server-ip>:5055` | Complete setup wizard — sign in with Jellyfin, connect Radarr + Sonarr |

> Radarr, Sonarr, Prowlarr, and qBittorrent are admin-only. Household members request media through Seerr and watch via Jellyfin.

### 4.4 Set Up Books & Audio

| Service | URL | First-Time Setup |
|---------|-----|-----------------|
| **Audiobookshelf** | `http://<server-ip>:13378` | Auto-configured — create accounts for household members |
| **Shelfarr** | `http://<server-ip>:5056` | Configure Prowlarr + qBittorrent + ABS connections |

### 4.5 Set Up Photos & Files

| Service | URL | First-Time Setup |
|---------|-----|-----------------|
| **Immich** | `http://<server-ip>:2283` | Create admin account, invite household members, install mobile app and enable auto-backup |
| **Nextcloud** | `http://<server-ip>:8080` | Auto-configured — install desktop/mobile sync clients |

### 4.6 Set Up Home Assistant

1. Open `http://<server-ip>:8123`
2. Create admin account, set location/timezone/units
3. Add smart device integrations: **Settings → Devices & Services → Add Integration**
4. Generate a **Long-Lived Access Token**: click your profile (bottom left) → **Security** → **Create Token**
5. Add the token to `butler/.env` as `HA_TOKEN` and restart Butler:
   ```bash
   cd butler && docker compose down && docker compose up -d
   ```

### 4.7 Install Mobile Apps

| App | Platform | Purpose |
|-----|----------|---------|
| [Jellyfin](https://jellyfin.org/downloads/) | iOS / Android | Stream movies & TV |
| [Immich](https://immich.app/docs/features/mobile-app) | iOS / Android | Photo backup & browsing |
| [Audiobookshelf](https://audiobookshelf.org/) | iOS / Android | Audiobook streaming with offline downloads |
| [Nextcloud](https://nextcloud.com/install/#install-clients) | iOS / Android / Desktop | File sync |
| [Home Assistant](https://companion.home-assistant.io/) | iOS / Android | Smart home control |

### 4.8 Set Up Alexa Integration (Optional)

If you have Amazon Echo devices, you can control Home Assistant via Alexa for free using haaska + AWS Lambda.

```
"Alexa, turn on the lights" → Echo → AWS Lambda (haaska) → Cloudflare Tunnel → Home Assistant
```

This requires:
- A free **AWS account** (Lambda free tier)
- An **Amazon Developer account** (for the Alexa skill)
- Home Assistant running with a Cloudflare Tunnel

> See [docs/15-alexa-haaska.md](docs/15-alexa-haaska.md) for the full step-by-step guide.

### Recommended Setup Order

1. **Cloudflare Tunnel routes** — get remote access working first
2. **Butler PWA** — enter invite code, complete onboarding
3. **Jellyfin** — verify auto-configured libraries, create household accounts
4. **Immich** — create admin, install mobile apps, enable photo backup
5. **Home Assistant** — add devices, generate token for Butler
6. **Audiobookshelf** — create household accounts
7. **Prowlarr** — add private indexers if you have any
8. **Alexa** — set up haaska for voice control (optional)

---

## Configuration

All environment variables live in `butler/.env` (created from `.env.example` during setup). To reconfigure:

```bash
cd butler && nano .env
docker compose down && docker compose up -d
```

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

> Security secrets (JWT, LiveKit keys, internal API key) are auto-generated during setup.

---

## What Gets Installed

### Infrastructure

| Component | Purpose |
|-----------|---------|
| [Homebrew](https://brew.sh/) | Package manager for macOS |
| [OrbStack](https://orbstack.dev/) | Docker for macOS (optimized for Apple Silicon) |
| [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) | Secure remote access (no open ports) |

### Media & Downloads

| Component | Purpose | Port |
|-----------|---------|------|
| [Jellyfin](https://jellyfin.org/) | Media streaming server | 8096 |
| [Radarr](https://radarr.video/) | Movie automation | 7878 |
| [Sonarr](https://sonarr.tv/) | TV series automation | 8989 |
| [Bazarr](https://www.bazarr.media/) | Subtitle automation | 6767 |
| [Seerr](https://github.com/seerr-team/seerr) | Media request management | 5055 |
| [Prowlarr](https://prowlarr.com/) | Indexer manager | 9696 |
| [qBittorrent](https://www.qbittorrent.org/) | Torrent client | 8081 |

### Books & Audio

| Component | Purpose | Port |
|-----------|---------|------|
| [Audiobookshelf](https://www.audiobookshelf.org/) | Ebook + audiobook library | 13378 |
| [Shelfarr](https://github.com/Pedro-Revez-Silva/shelfarr) | Book search + download management | 5056 |

### Photos & Files

| Component | Purpose | Port |
|-----------|---------|------|
| [Immich](https://immich.app/) | Photo management with AI | 2283 |
| [Nextcloud](https://nextcloud.com/) | File sync & collaboration | 8080 |

### Smart Home

| Component | Purpose | Port |
|-----------|---------|------|
| [Home Assistant](https://www.home-assistant.io/) | Smart home hub | 8123 |

### Voice Assistant

| Component | Purpose | Port |
|-----------|---------|------|
| [LiveKit](https://livekit.io/) | WebRTC server | 7880 |
| [Groq Whisper](https://console.groq.com/) | Speech-to-text (cloud, free) | - |
| [Kokoro TTS](https://github.com/remsky/Kokoro-FastAPI) | Text-to-speech (local) | 8880 |

### AI Butler

| Component | Purpose | Port |
|-----------|---------|------|
| Butler API | FastAPI backend (chat, voice, auth, tools) | 8000 |
| Butler PWA | React web app (voice + chat interface) | 3000 |

---

## Backup

Local database backups run automatically (daily at 3am via launchd) to `~/ServerBackups/` on the Mac's internal SSD. This protects against external drive failure for configs and metadata.

Media files (movies, TV, audiobooks) don't need backup — the *arr stack can re-download them automatically.

For photos and documents, cloud backup is **optional** — see [HOMESERVER_PLAN.md](HOMESERVER_PLAN.md) for options (iCloud 2TB at £6.99/month is recommended if you want off-site protection).

---

## Updating

Pull the latest code and rebuild only the stacks that changed:

```bash
bash ~/home-server/scripts/update.sh
```

| Flag | Description |
|------|-------------|
| `--check` | Show available updates without applying them |
| `--force` | Rebuild all stacks, even if unchanged |

The script compares local and remote commits, identifies which Docker Compose stacks were affected, pulls the changes, and rebuilds only those stacks. It's safe to run at any time — if nothing changed, it exits immediately.

To migrate data to a different drive (e.g. from internal SSD to an external drive):

```bash
cd ~/home-server && ./scripts/change-drive.sh
```

This interactively stops running stacks, copies data with `rsync`, and restarts everything on the new path.

---

## Monthly Costs

| Configuration | Cost |
|---------------|------|
| Base (no cloud backup) | ~£10.70 (Claude API + electricity) |
| With iCloud 2TB backup | ~£17.69 |

---

## Documentation

- **[HOMESERVER_PLAN.md](HOMESERVER_PLAN.md)** — Complete architecture, storage layout, and resource budget
- **[docs/](docs/)** — Step-by-step manual guides for each setup script
- **[docs/google-oauth-setup.md](docs/google-oauth-setup.md)** — Google OAuth for Calendar/Gmail
- **[docs/prowlarr-indexers.md](docs/prowlarr-indexers.md)** — Adding indexers to Prowlarr
- **[docs/VOICE_ARCHITECTURE.md](docs/VOICE_ARCHITECTURE.md)** — Voice pipeline technical details

---

## Repository Structure

```
home-server/
├── README.md                 # This file
├── HOMESERVER_PLAN.md        # Complete architecture plan
├── CLAUDE.md                 # Context for Claude agents
├── setup.sh                  # Run all setup steps
├── app/                      # Butler PWA (React + Vite)
├── butler/                   # Butler API + tools
│   ├── api/                  # FastAPI server
│   ├── tools/                # Custom Python tools
│   ├── migrations/           # PostgreSQL schema
│   ├── livekit-agent/        # Voice pipeline worker
│   └── .env.example          # Configuration template
├── scripts/                  # Individual setup scripts (01-14)
├── docker/                   # Docker Compose stacks
│   ├── download-stack/
│   ├── media-stack/
│   ├── books-stack/
│   ├── photos-files-stack/
│   ├── smart-home-stack/
│   ├── messaging-stack/
│   └── voice-stack/
└── docs/                     # Manual setup guides
```
