# Home Server

Self-hosted media server with AI voice assistant on Mac Mini M4.

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

---

## Setup Guide

| Step | Script | Manual | Description |
|------|--------|--------|-------------|
| 1 | [01-homebrew.sh](scripts/01-homebrew.sh) | [docs](docs/01-homebrew.md) | Install Homebrew package manager |
| 2 | [02-tailscale.sh](scripts/02-tailscale.sh) | [docs](docs/02-tailscale.md) | Install Tailscale for secure remote access |
| 3 | [03-power-settings.sh](scripts/03-power-settings.sh) | [docs](docs/03-power-settings.md) | Configure Mac to stay awake 24/7 |
| 4 | [04-ssh.sh](scripts/04-ssh.sh) | [docs](docs/04-ssh.md) | Enable SSH *(optional)* |
| 5 | [05-orbstack.sh](scripts/05-orbstack.sh) | [docs](docs/05-orbstack.md) | Install OrbStack (Docker) |
| 6 | [06-external-drive.sh](scripts/06-external-drive.sh) | [docs](docs/06-external-drive.md) | Configure external drive & directories |
| 7 | [07-download-stack.sh](scripts/07-download-stack.sh) | [docs](docs/07-download-stack.md) | Deploy qBittorrent + Prowlarr |
| 8 | [08-media-stack.sh](scripts/08-media-stack.sh) | [docs](docs/08-media-stack.md) | Deploy Jellyfin + Radarr + Sonarr + Bazarr |
| 9 | [09-books-stack.sh](scripts/09-books-stack.sh) | [docs](docs/09-books-stack.md) | Deploy Calibre-Web + Audiobookshelf + Readarr |
| 10 | [10-photos-files.sh](scripts/10-photos-files.sh) | [docs](docs/10-photos-files.md) | Deploy Immich + Nextcloud |
| 11 | [11-smart-home.sh](scripts/11-smart-home.sh) | [docs](docs/11-smart-home.md) | Deploy Home Assistant + Cloudflare Tunnel |
| 12 | [12-voice-stack.sh](scripts/12-voice-stack.sh) | [docs](docs/12-voice-stack.md) | Deploy LiveKit + Whisper + Kokoro TTS |

Run individual steps:
```bash
# Example: just install Tailscale
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/02-tailscale.sh | bash
```

Or follow the manual docs for step-by-step instructions.

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
| [Tailscale](https://tailscale.com/) | Secure mesh VPN for remote access |
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
| Cloudflare Tunnel | Secure access for Alexa | - |

### Voice Assistant
| Component | Purpose | Port |
|-----------|---------|------|
| [LiveKit](https://livekit.io/) | WebRTC server | 7880 |
| [Whisper](https://github.com/openai/whisper) | Speech-to-text | 9000 |
| [Kokoro TTS](https://github.com/remsky/Kokoro-FastAPI) | Text-to-speech | 8880 |

### Integrations (optional)
| Component | Purpose | Setup |
|-----------|---------|-------|
| Google Calendar | Calendar queries via Butler | [setup guide](docs/google-oauth-setup.md) |

---

## Repository Structure

```
home-server/
├── README.md                 # This file
├── HOMESERVER_PLAN.md        # Complete architecture plan
├── CLAUDE.md                 # Context for Claude agents
├── setup.sh                  # Run all setup steps
├── scripts/
│   ├── 01-homebrew.sh        # Foundation scripts
│   ├── 02-tailscale.sh
│   ├── 03-power-settings.sh
│   ├── 04-ssh.sh
│   ├── 05-orbstack.sh
│   ├── 06-external-drive.sh
│   ├── 07-download-stack.sh  # Docker deployment scripts
│   ├── 08-media-stack.sh
│   ├── 09-books-stack.sh
│   ├── 10-photos-files.sh
│   ├── 11-smart-home.sh
│   └── 12-voice-stack.sh
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
    └── 12-voice-stack.md
```

---

## Monthly Costs

| Configuration | Cost |
|---------------|------|
| Base (no cloud backup) | ~£7.21 (Claude API + electricity) |
| With iCloud 2TB backup | ~£14.20 |

See [HOMESERVER_PLAN.md](HOMESERVER_PLAN.md) for detailed cost breakdown.
