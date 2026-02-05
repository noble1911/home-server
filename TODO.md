# Implementation TODO

> **Goal:** Run `setup.sh` on fresh Mac Mini → Everything works
>
> Track progress by checking boxes. Each session, start here to see what's next.

---

## Phase 1: Foundation Scripts ✅

Scripts that prepare the Mac Mini for server use.

- [x] `setup.sh` - Orchestrator that runs all scripts
- [x] `scripts/01-homebrew.sh` - Install Homebrew
- [x] `scripts/02-tailscale.sh` - Install Tailscale
- [x] `scripts/03-power-settings.sh` - Configure 24/7 operation
- [x] `scripts/04-ssh.sh` - Enable SSH (optional)
- [x] `docs/01-homebrew.md` - Manual instructions
- [x] `docs/02-tailscale.md` - Manual instructions
- [x] `docs/03-power-settings.md` - Manual instructions
- [x] `docs/04-ssh.md` - Manual instructions

---

## Phase 2: Docker Infrastructure

Install OrbStack and prepare Docker environment.

- [ ] `scripts/05-orbstack.sh` - Install OrbStack (Docker)
- [ ] `docs/05-orbstack.md` - Manual instructions
- [ ] `scripts/06-directory-structure.sh` - Create folder structure on external drive
- [ ] `docs/06-directory-structure.md` - Manual instructions
- [ ] Update `setup.sh` to include new scripts

---

## Phase 3: Core Services (Docker Compose)

Create Docker Compose files for each service category.

### Database
- [ ] `docker/postgres/docker-compose.yml` - PostgreSQL with vector extensions
- [ ] `docker/postgres/init-butler-schema.sql` - Butler schema setup
- [ ] `docs/07-postgres.md` - Database setup guide

### Download Infrastructure
- [ ] `docker/downloads/docker-compose.yml` - qBittorrent + Prowlarr
- [ ] `docs/08-downloads.md` - Setup guide

### Media Stack
- [ ] `docker/media/docker-compose.yml` - Jellyfin + Radarr + Sonarr + Bazarr
- [ ] `docs/09-media.md` - Setup guide

### Books & Audio
- [ ] `docker/books/docker-compose.yml` - Calibre-Web + Audiobookshelf + Readarr
- [ ] `docs/10-books.md` - Setup guide

### Photos & Files
- [ ] `docker/photos/docker-compose.yml` - Immich
- [ ] `docker/files/docker-compose.yml` - Nextcloud
- [ ] `docs/11-photos.md` - Setup guide
- [ ] `docs/12-files.md` - Setup guide

### Smart Home
- [ ] `docker/smarthome/docker-compose.yml` - Home Assistant
- [ ] `docker/smarthome/cloudflared/` - Cloudflare Tunnel config
- [ ] `docs/13-smarthome.md` - Setup guide
- [ ] `docs/14-haaska.md` - AWS Lambda + Alexa setup guide

---

## Phase 4: AI Butler

The voice assistant and its components.

### Voice Pipeline
- [ ] `docker/voice/docker-compose.yml` - LiveKit + Whisper + Kokoro
- [ ] `docs/15-voice-pipeline.md` - Setup guide

### Butler Agent (Nanobot)
- [ ] `butler/` - Nanobot fork/configuration
- [ ] `butler/config.yml` - Main Nanobot config
- [ ] `butler/users.json` - User definitions (or DB seed)
- [ ] `docs/16-butler-agent.md` - Setup guide

### Memory MCP Server
- [ ] `butler/mcp-servers/memory/` - Memory MCP server
- [ ] `butler/mcp-servers/memory/server.py` - Main server code
- [ ] `butler/mcp-servers/memory/tools.py` - remember_fact, recall_facts, etc.
- [ ] `docs/17-memory-system.md` - How memory works

### Service MCP Servers
- [ ] `butler/mcp-servers/home-assistant/` - HA integration
- [ ] `butler/mcp-servers/jellyfin/` - Media control
- [ ] `butler/mcp-servers/radarr-sonarr/` - Media requests
- [ ] `butler/mcp-servers/immich/` - Photo search
- [ ] `butler/mcp-servers/calendar/` - Google Calendar (read-only)
- [ ] `butler/mcp-servers/weather/` - Weather API

### Notifications
- [ ] `docker/notifications/docker-compose.yml` - WhatsApp Web.js
- [ ] `butler/mcp-servers/whatsapp/` - WhatsApp MCP
- [ ] `docs/18-notifications.md` - Setup guide

---

## Phase 5: Client App (PWA)

Web app for voice interaction.

- [ ] `app/` - React + Vite PWA
- [ ] `app/src/components/VoiceButton.tsx` - Push-to-talk UI
- [ ] `app/src/hooks/useLiveKit.ts` - LiveKit integration
- [ ] `app/src/pages/Settings.tsx` - User preferences
- [ ] `docs/19-client-app.md` - Setup guide

---

## Phase 6: Automation & Backup

Scripts for maintenance and data protection.

- [ ] `scripts/backup-databases.sh` - Daily DB backup script
- [ ] `scripts/backup-configs.sh` - Config backup script
- [ ] `docker/backup/docker-compose.yml` - Backup container (optional)
- [ ] `docs/20-backups.md` - Backup strategy guide

---

## Phase 7: Master Setup Script

Update `setup.sh` to orchestrate everything.

- [ ] Add Phase 2 scripts to `setup.sh`
- [ ] Create `setup-services.sh` - Docker Compose orchestrator
- [ ] Create `setup-butler.sh` - Butler-specific setup
- [ ] End-to-end testing on fresh macOS

---

## Documentation

- [x] `README.md` - Quick start
- [x] `HOMESERVER_PLAN.md` - Full architecture
- [x] `CLAUDE.md` - Session context
- [x] `TODO.md` - This file
- [ ] `docs/TROUBLESHOOTING.md` - Common issues
- [ ] `docs/ARCHITECTURE.md` - Technical deep-dive

---

## Current Status

**Last Updated:** 2025-02-05

**What's Done:**
- Foundation scripts (Phase 1) complete
- Architecture and planning documents
- Memory system design with PostgreSQL

**What's Next:**
- Phase 2: OrbStack + directory structure scripts

**Blockers:**
- Mac Mini hardware not yet arrived

---

## Quick Reference

```bash
# Run full setup
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/setup.sh | bash

# Run individual step
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/05-orbstack.sh | bash

# Start all services (after setup)
cd ~/home-server/docker && docker compose up -d
```
