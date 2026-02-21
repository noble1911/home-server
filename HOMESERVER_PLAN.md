# Home Server Master Plan

> **Hardware:** Mac Mini M4 (24GB Unified Memory, 512GB SSD) + External USB Drive
> **Goal:** Self-hosted, privacy-focused media server with AI voice assistant + Alexa
> **Monthly Cost:** ~£7.21 (API + electricity) — backup optional, Alexa via free haaska
> **Butler Engine:** Butler API (~4k lines, FastAPI + custom Python tools)
>
> ⚠️ **Note (2026-02-05):** Butler API uses a "skills" system (markdown instruction files) and custom Python tools. Skills teach the agent how to use tools; the agent then calls built-in executors (shell, filesystem, web). Custom Python tools are registered in `butler/tools/`.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Hardware Specifications](#hardware-specifications)
3. [Services by Category](#services-by-category)
4. [Resource Budget](#resource-budget)
5. [AI Butler Architecture](#ai-butler-architecture)
6. [Storage Layout](#storage-layout)
7. [Network & Communication Flow](#network--communication-flow)
8. [Implementation Phases](#implementation-phases)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MAC MINI M4 (24GB)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        ORBSTACK (Docker)                            │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │   │
│  │  │ Jellyfin │ │  Radarr  │ │  Sonarr  │ │ Prowlarr │ │  Bazarr  │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │   │
│  │  │  Seerr   │ │qBittorrent│ │  Immich  │ │Nextcloud │ │   Home   │  │   │
│  │  │          │ │          │ │          │ │          │ │Assistant │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │   │
│  │  ┌──────────┐ ┌──────────┐ ┌───────────────────────────────────┐   │   │
│  │  │Audiobook │ │  LiveKit  │ │         AI BUTLER                 │   │   │
│  │  │   Web    │ │  shelf   │ │  Agent + Kokoro TTS               │   │   │
│  │  └──────────┘ └──────────┘ └───────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    EXTERNAL DRIVE                                   │   │
│  │   /Media  /Photos  /Documents  /Books  /Downloads  /Backups         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ (Cloudflare Tunnel)
                        ┌───────────────────────┐
                        │   Remote Access       │
                        │   Phone / Laptop / TV │
                        └───────────────────────┘
```

---

## Hardware Specifications

| Component | Specification | Notes |
|-----------|---------------|-------|
| **Device** | Mac Mini M4 | Apple Silicon, excellent power efficiency |
| **RAM** | 24GB Unified Memory | Shared between CPU, GPU, Neural Engine |
| **Storage (Internal)** | 512GB SSD | OS, Docker images, databases |
| **Storage (External)** | USB External HDD (4-8TB recommended) | Media, photos, documents (see below) |
| **Connectivity** | Gigabit Ethernet | Hardwired recommended for streaming |
| **Power Draw** | ~10-30W typical | Very efficient for 24/7 operation |

### Choosing an External Drive

**Use Case:** On-demand media streaming, photo storage, document sync. Not 24/7 continuous operation.

#### Recommended Capacity

| Library Size | Capacity | Typical Use |
|-------------|----------|-------------|
| **Starter** | 4TB | Small media collection, photos, documents |
| **Standard** | 8TB | Moderate media library (200+ movies, 60+ TV seasons, photos) |
| **Large** | 12-16TB | Extensive 4K media library, RAW photography |

#### What to Look For

- **Interface:** USB 3.0 or later (USB 3.2 Gen 1 is common). HDD speeds (~150 MB/s) are well under USB 3.0 limits, so any USB 3.0+ port works fine
- **Mac compatibility:** Most external HDDs work with Mac after formatting. Check reviews to confirm
- **Form factor:** Desktop drives (3.5") offer better value per TB. Portable drives (2.5") don't need a power adapter but top out around 5TB
- **Noise:** Look for fanless models if the server will be near living spaces

> **Why consumer-grade is fine:** Your server workload is read-heavy and on-demand (stream movie → drive wakes → watch → drive sleeps). NAS-grade drives are overkill for this pattern.

**Format:** Use APFS or Mac OS Extended (Journaled) — no need for NTFS drivers.

#### Popular Options

| Brand | Series | Notes |
|-------|--------|-------|
| WD Elements / My Book | Desktop | Widely available, reliable, good value |
| Seagate Expansion / One Touch | Desktop | Competitive pricing, similar to WD |
| Toshiba Canvio | Desktop / Portable | Often cheapest per TB |
| Buffalo | Desktop | Quiet, fanless, officially Mac-supported |

> **Tip:** Prices fluctuate — check your local retailers and wait for sales. External HDDs often go on discount during Black Friday, Amazon Prime Day, etc.

---

## Services by Category

### Infrastructure Layer

| Service | Homepage | Purpose | Run Method | RAM (Idle) | RAM (Peak) | Port |
|---------|----------|---------|------------|------------|------------|------|
| [**OrbStack**](https://orbstack.dev/) | [orbstack.dev](https://orbstack.dev/) | Docker engine optimized for Apple Silicon | Native macOS app | 500MB | 1GB | - |
| [**Cloudflare Tunnel**](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) | [cloudflare.com](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) | Primary remote access for all user-facing services (no public IP) | Docker (cloudflared) | 50MB | 100MB | - |
| [**Homebrew**](https://brew.sh/) | [brew.sh](https://brew.sh/) | Package manager for CLI tools | Native macOS | - | - | - |

### Voice Assistant (Real-Time)

| Service | Homepage | Purpose | Run Method | RAM (Idle) | RAM (Peak) | Port |
|---------|----------|---------|------------|------------|------------|------|
| [**LiveKit Server**](https://livekit.io/) | [livekit.io](https://livekit.io/) | WebRTC server for real-time audio streaming | Docker container | 200MB | 500MB | 7880 |
| [**LiveKit Agents**](https://github.com/livekit/agents) | [GitHub](https://github.com/livekit/agents) | Python framework orchestrating STT→LLM→TTS | Docker container | 300MB | 500MB | - |
| [**Groq Whisper**](https://console.groq.com/) | [groq.com](https://console.groq.com/) | Cloud speech-to-text (Whisper large-v3-turbo via Groq API, free tier) | External API | 0MB | 0MB | - |
| [**Kokoro TTS**](https://github.com/remsky/Kokoro-FastAPI) | [GitHub](https://github.com/remsky/Kokoro-FastAPI) | Local text-to-speech (natural voices) | Docker container | 400MB | 800MB | 8880 |
| [**Claude API**](https://www.anthropic.com/api) | [anthropic.com](https://www.anthropic.com/api) | LLM brain for understanding & reasoning | External API | 0MB | 0MB | - |

### Agent Orchestration

| Service | Homepage | Purpose | Run Method | RAM (Idle) | RAM (Peak) | Port |
|---------|----------|---------|------------|------------|------------|------|
| **Butler API** | Self-built | FastAPI backend for PWA, voice, and chat (Claude API + custom Python tools) | Docker container | 100MB | 300MB | 8000 |
| [**APScheduler**](https://apscheduler.readthedocs.io/) | [Docs](https://apscheduler.readthedocs.io/) | Cron-style task scheduling | Part of Agent | Included | Included | - |

> **Note:** The LLM (Claude) and STT (Groq Whisper) run in the cloud to preserve local RAM. TTS (Kokoro) runs locally for low latency.

### Media & Entertainment

| Service | Homepage | Purpose | Run Method | RAM (Idle) | RAM (Peak) | Port |
|---------|----------|---------|------------|------------|------------|------|
| [**Jellyfin**](https://jellyfin.org/) | [jellyfin.org](https://jellyfin.org/) | Media streaming (4K HDR, Dolby Atmos) | Docker container | 500MB | 4GB* | 8096 |
| [**Radarr**](https://radarr.video/) | [radarr.video](https://radarr.video/) | Movie automation & management | Docker container | 300MB | 500MB | 7878 |
| [**Sonarr**](https://sonarr.tv/) | [sonarr.tv](https://sonarr.tv/) | TV series automation & management | Docker container | 300MB | 500MB | 8989 |
| [**Bazarr**](https://www.bazarr.media/) | [bazarr.media](https://www.bazarr.media/) | Subtitle automation | Docker container | 200MB | 400MB | 6767 |
| [**Seerr**](https://github.com/seerr-team/seerr) | [docs.seerr.dev](https://docs.seerr.dev/) | Media request management | Docker container | 100MB | 200MB | 5055 |

> *Jellyfin peaks during 4K transcoding. Direct play uses minimal resources.

### Books & Audio

| Service | Homepage | Purpose | Run Method | RAM (Idle) | RAM (Peak) | Port |
|---------|----------|---------|------------|------------|------------|------|
| [**Audiobookshelf**](https://www.audiobookshelf.org/) | [audiobookshelf.org](https://www.audiobookshelf.org/) | Ebook + audiobook library, reading, streaming (native mobile apps) | Docker container | 200MB | 400MB | 13378 |
| [**LazyLibrarian**](https://lazylibrarian.gitlab.io/) | [GitLab](https://gitlab.com/LazyLibrarian/LazyLibrarian) | Book search, download management, library organization | Docker container | 150MB | 300MB | 5299 |

> **Note (2026-02-11):** Calibre-Web, Readarr, and Shelfarr have been replaced by LazyLibrarian + Audiobookshelf. LazyLibrarian provides web-based book search via Prowlarr, manages downloads via qBittorrent, and organizes files into the Audiobookshelf library folders. Butler's BookTool (`butler/tools/books.py`) provides AI-driven book search/download via Open Library + Prowlarr + qBittorrent.

> **Ebook Access Methods:** Audiobookshelf serves ebooks via browser (built-in EPUB reader), native iOS/Android apps with offline downloads, and progress sync across devices. See [Ebook Reading Guide](docs/ebook-reading-guide.md) for setup.

### Photos & Files

| Service | Homepage | Purpose | Run Method | RAM (Idle) | RAM (Peak) | Port |
|---------|----------|---------|------------|------------|------------|------|
| [**Immich**](https://immich.app/) | [immich.app](https://immich.app/) | Photo management with AI face recognition | Docker container | 1GB | 4GB* | 2283 |
| [**Nextcloud**](https://nextcloud.com/) | [nextcloud.com](https://nextcloud.com/) | File sync & document collaboration | Docker container | 400MB | 1GB | 8080 |

> *Immich peaks during ML processing (face recognition, object detection).

### Smart Home

| Service | Homepage | Purpose | Run Method | RAM (Idle) | RAM (Peak) | Port |
|---------|----------|---------|------------|------------|------------|------|
| [**Home Assistant**](https://www.home-assistant.io/) | [home-assistant.io](https://www.home-assistant.io/) | Smart home hub & automation | Docker container | 400MB | 1GB | 8123 |

> **Alexa Integration:** Via [haaska](https://github.com/mike-grant/haaska) + AWS Lambda (free tier) instead of paid Home Assistant Cloud. See [Alexa Integration](#alexa-integration-free---haaska) section.

### Download Infrastructure

| Service | Homepage | Purpose | Run Method | RAM (Idle) | RAM (Peak) | Port |
|---------|----------|---------|------------|------------|------------|------|
| [**qBittorrent**](https://www.qbittorrent.org/) | [qbittorrent.org](https://www.qbittorrent.org/) | Torrent download client | Docker container | 200MB | 500MB | 8081 |
| [**Prowlarr**](https://prowlarr.com/) | [prowlarr.com](https://prowlarr.com/) | Indexer manager for *arr stack | Docker container | 200MB | 400MB | 9696 |

### Notifications

| Service | Homepage | Purpose | Run Method | RAM (Idle) | RAM (Peak) | Port |
|---------|----------|---------|------------|------------|------------|------|
| [**WhatsApp Web.js**](https://github.com/pedroslopez/whatsapp-web.js) | [GitHub](https://github.com/pedroslopez/whatsapp-web.js) | Outbound WhatsApp notifications | Docker container | 100MB | 200MB | - |

---

## Resource Budget

### Memory Allocation Summary

| Category | Services | Idle Total | Peak Total |
|----------|----------|------------|------------|
| **macOS + OrbStack** | System overhead | 3.5GB | 5GB |
| **Voice Assistant** | LiveKit, Kokoro, Butler API | 1.0GB | 2.1GB |
| **Media** | Jellyfin, *arrs, Seerr, qBit | 1.6GB | 6.1GB |
| **Photos/Files** | Immich, Nextcloud | 1.4GB | 5GB |
| **Books** | Audiobookshelf, LazyLibrarian | 0.35GB | 0.7GB |
| **Smart Home** | Home Assistant | 0.4GB | 1GB |
| **Notifications** | WhatsApp | 0.1GB | 0.2GB |
| | | | |
| **TOTAL** | | **8.85GB** | **21.6GB** |
| **Available** | 24GB | **15.15GB free** | **2.4GB free** |

### Voice Assistant RAM Breakdown

| Component | Idle | Active | Notes |
|-----------|------|--------|-------|
| LiveKit Server | 200MB | 500MB | WebRTC signaling |
| LiveKit Agent | 300MB | 500MB | Python orchestrator |
| Groq Whisper STT | 0MB | 0MB | Cloud API (free tier) |
| Kokoro TTS | 400MB | 800MB | Local TTS model |
| Butler API | 100MB | 300MB | Agent + Python tools |
| **Total Voice** | **1.0GB** | **2.1GB** | |

### Peak Scenario Analysis

| Scenario | What's Running | Estimated RAM |
|----------|----------------|---------------|
| **Idle** | All services at rest | ~9GB |
| **Normal Use** | Streaming + browsing photos | ~12-14GB |
| **Voice Active** | Real-time voice conversation | ~13-15GB |
| **Heavy Use** | 4K transcode + photo upload + voice | ~19-21GB |
| **Worst Case** | All services at peak simultaneously | ~22GB |

> ⚠️ **Recommendation:** Avoid running Immich ML processing during 4K transcoding. The voice assistant is lightweight enough to run concurrently with most activities.

---

## AI Butler Architecture

### Technology Choice: Butler API

We built our own lightweight FastAPI backend rather than adopting an existing framework:

| Factor | Butler API (self-built) | OpenClaw | Why we built our own |
|--------|------------------------|----------|----------------------|
| Codebase | ~4,000 lines | 430,000+ lines | Easy to audit and maintain |
| Auditability | Read in an afternoon | Requires significant time | Security-critical for home use |
| Tool Support | Custom Python tools | Native | Full control over integrations |
| WhatsApp | WebSocket (no public IP) | Yes | No port forwarding needed |
| Voice | Groq Whisper (free tier) | Various | Cost-effective STT |
| Scheduling | Cron + intervals | Yes | Simple and sufficient |
| Customization | Designed for our use case | Feature-complete but complex | No unnecessary abstractions |
| Security surface | Minimal | Large | Smaller attack surface |

### Design Philosophy

The Butler is built on **custom Python tools**, keeping the codebase minimal and auditable:

| Principle | Implementation |
|-----------|----------------|
| **No external dependencies for AI tools** | Skill download capability removed from codebase |
| **Custom Python tools only** | All integrations built and audited by us |
| **Network isolation** | Cloudflare Tunnel for remote access, admin services LAN-only |
| **Read-only where possible** | Calendar, email, location = read-only access |
| **Multi-user** | Supports both household members |

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BUTLER ECOSYSTEM                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │   Android       │  │   iOS           │  │   Desktop       │             │
│  │  (User 1..N)    │  │  (User 1..N)    │  │  (User 1..N)    │             │
│  │                 │  │                 │  │                 │             │
│  │  ┌───────────┐  │  │  ┌───────────┐  │  │  ┌───────────┐  │             │
│  │  │  Web App  │  │  │  │  Web App  │  │  │  │  Web App  │  │             │
│  │  │   (PWA)   │  │  │  │   (PWA)   │  │  │  │ (Browser) │  │             │
│  │  │           │  │  │  │           │  │  │  │           │  │             │
│  │  │ 🎤 ──────►│  │  │  │ 🎤 ──────►│  │  │  │ 🎤 ──────►│  │             │
│  │  │ 🔊 ◄──────│  │  │  │ 🔊 ◄──────│  │  │  │ 🔊 ◄──────│  │             │
│  │  └─────┬─────┘  │  │  └─────┬─────┘  │  │  └─────┬─────┘  │             │
│  │        │        │  │        │        │  │        │        │             │
│  │  ┌─────▼─────┐  │  │  ┌─────▼─────┐  │  │        │        │             │
│  │  │ WhatsApp  │  │  │  │ WhatsApp  │  │  │        │        │             │
│  │  │(notifications)│  │  │(notifications)│  │        │        │             │
│  │  └───────────┘  │  │  └───────────┘  │  │        │        │             │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘             │
│           │                    │                    │                       │
│           │                    │                    │                       │
│           │                    │          ┌─────────────────┐               │
│           │                    │          │  Amazon Echo    │               │
│           │                    │          │  Devices        │               │
│           │                    │          │ "Alexa, ask..." │               │
│           │                    │          └────────┬────────┘               │
│           │                    │                   │                        │
│           │  WebRTC            │                   │ AWS Lambda (haaska)    │
│           │  (Cloudflare       │                   │ + Cloudflare Tunnel    │
│           │   Tunnel)          │                   │                        │
│           └──────────┬─────────┴───────────────────┘                        │
│                      │                                                      │
│                      ▼                                                      │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                    MAC MINI (Home Server) - 24/7                      │ │
│  │                                                                       │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │ │
│  │  │                    LIVEKIT SERVER (WebRTC)                      │ │ │
│  │  │               Real-time audio streaming & rooms                 │ │ │
│  │  └───────────────────────────────┬─────────────────────────────────┘ │ │
│  │                                  │                                    │ │
│  │                                  ▼                                    │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │ │
│  │  │                    VOICE AGENT (Python)                         │ │ │
│  │  │                                                                 │ │ │
│  │  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐       │ │ │
│  │  │  │ Groq STT │ │  Claude   │ │  Kokoro   │ │ Scheduler │       │ │ │
│  │  │  │ (CLOUD)  │ │   API     │ │   TTS     │ │  (Cron)   │       │ │ │
│  │  │  │ Whisper  │ │ (Sonnet)  │ │  (LOCAL)  │ │           │       │ │ │
│  │  │  └───────────┘ └───────────┘ └───────────┘ └───────────┘       │ │ │
│  │  │                                                                 │ │ │
│  │  │  ┌───────────────────────────────────────────────────────────┐ │ │ │
│  │  │  │           BUTLER API + CUSTOM TOOLS                       │ │ │ │
│  │  │  │                                                           │ │ │ │
│  │  │  │  ╔═══════════════════════════════════════════════════╗   │ │ │ │
│  │  │  │  ║  READ-ONLY TOOLS                                   ║   │ │ │ │
│  │  │  │  ║  ┌──────────┐ ┌──────────┐ ┌──────────┐          ║   │ │ │ │
│  │  │  │  ║  │ Google   │ │  Gmail   │ │ Location │          ║   │ │ │ │
│  │  │  │  ║  │ Calendar │ │          │ │  (×N)    │          ║   │ │ │ │
│  │  │  │  ║  └──────────┘ └──────────┘ └──────────┘          ║   │ │ │ │
│  │  │  │  ║  ┌──────────┐ ┌──────────┐                       ║   │ │ │ │
│  │  │  │  ║  │ Weather  │ │  Immich  │                       ║   │ │ │ │
│  │  │  │  ║  │          │ │ (search) │                       ║   │ │ │ │
│  │  │  │  ║  └──────────┘ └──────────┘                       ║   │ │ │ │
│  │  │  │  ╚═══════════════════════════════════════════════════╝   │ │ │ │
│  │  │  │                                                           │ │ │ │
│  │  │  │  ╔═══════════════════════════════════════════════════╗   │ │ │ │
│  │  │  │  ║  READ-WRITE TOOLS                                  ║   │ │ │ │
│  │  │  │  ║  ┌──────────┐ ┌──────────┐ ┌──────────┐          ║   │ │ │ │
│  │  │  │  ║  │  Home    │ │  Radarr  │ │  Sonarr  │          ║   │ │ │ │
│  │  │  │  ║  │Assistant │ │          │ │          │          ║   │ │ │ │
│  │  │  │  ║  └──────────┘ └──────────┘ └──────────┘          ║   │ │ │ │
│  │  │  │  ║  ┌──────────┐ ┌──────────┐ ┌──────────┐          ║   │ │ │ │
│  │  │  │  ║  │  Lazy    │ │ Jellyfin │ │ WhatsApp │          ║   │ │ │ │
│  │  │  │  ║  │Librarian │ │          │ │(outbound)│          ║   │ │ │ │
│  │  │  │  ║  └──────────┘ └──────────┘ └──────────┘          ║   │ │ │ │
│  │  │  │  ╚═══════════════════════════════════════════════════╝   │ │ │ │
│  │  │  └───────────────────────────────────────────────────────────┘ │ │ │
│  │  └─────────────────────────────────────────────────────────────────┘ │ │
│  │                                                                       │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │ │
│  │  │                    HOME ASSISTANT                               │ │ │
│  │  │  • Receives Alexa commands via haaska (AWS Lambda free tier)   │ │ │
│  │  │  • Cloudflare Tunnel provides secure access (no public IP)     │ │ │
│  │  │  • Routes complex requests to Voice Agent                      │ │ │
│  │  │  • Handles direct device control (lights, heating, etc.)       │ │ │
│  │  └─────────────────────────────────────────────────────────────────┘ │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Multi-User Support

The system supports **N users** with individual settings and preferences.

#### User Identification

| Method | How It Works | Reliability |
|--------|--------------|-------------|
| **JWT Token** | Each user's app has unique token with user ID | ✅ Most reliable |
| **Device ID** | App identifies device on registration | ✅ Reliable |
| **Voice enrollment** | Optional speaker recognition | ⚠️ Future enhancement |

#### Per-User Configuration

```json
{
  "users": [
    {
      "id": "user_001",
      "name": "Ron",
      "wake_word": null,
      "start_mode": "push_to_talk",
      "devices": ["pixel_9a"],
      "tts_voice": "kokoro_male_1",
      "permissions": ["media", "home", "calendar", "location"],
      "soul": {
        "personality": "friendly and efficient",
        "formality": "casual",
        "verbosity": "concise",
        "humor": true,
        "custom_instructions": "Ron prefers audiobooks at 1.2x speed. Suggest sci-fi when asked for recommendations."
      }
    },
    {
      "id": "user_002",
      "name": "Partner",
      "wake_word": "hey jarvis",
      "start_mode": "wake_word",
      "devices": ["iphone_17"],
      "tts_voice": "kokoro_female_1",
      "permissions": ["media", "home", "calendar", "location"],
      "soul": {
        "personality": "warm and helpful",
        "formality": "casual",
        "verbosity": "detailed",
        "humor": true,
        "custom_instructions": "Prefers romance and thriller genres."
      }
    }
  ]
}
```

#### Per-User Features

| Feature | Description |
|---------|-------------|
| **Custom wake word** | Each user can set their own (or disable) |
| **Conversation mode** | Push-to-talk, wake word, or app-open listening |
| **TTS voice** | Choose preferred voice for responses |
| **Permissions** | Control what each user can access |
| **Notification preferences** | Which WhatsApp updates to receive |
| **Soul/Personality** | Custom interaction style per user |
| **Service Accounts** | Auto-provisioned app logins (Jellyfin, Audiobookshelf, Nextcloud, Immich) |

#### User Onboarding & Service Provisioning

During first-time setup, new users complete a PWA wizard that collects:
1. Their name and butler name/personality preferences
2. A **single username + password** used across all self-hosted services

Butler then **auto-provisions accounts** on each configured service:
- **`media` permission** → Jellyfin, Audiobookshelf, Immich
- **All users** → Nextcloud

Provisioning details:
- Each service is provisioned via its admin API (Jellyfin REST, Audiobookshelf REST, Nextcloud OCS, Immich REST)
- Credentials are **encrypted at rest** using Fernet (AES-128-CBC + HMAC-SHA256, keyed from JWT_SECRET)
- Stored in `butler.service_credentials` table with `UNIQUE(user_id, service)` for idempotency
- Services are skipped gracefully if admin credentials aren't configured (env vars)
- Users can view their service accounts (with show/hide password toggle) on the Settings page

### Memory System

The Butler remembers facts about users and learns from interactions.

#### Memory Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MEMORY LAYERS                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  SESSION MEMORY (Claude built-in)                                   │   │
│  │  Current conversation context - resets each session                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  SHORT-TERM MEMORY (PostgreSQL - butler.conversation_history)       │   │
│  │  Recent conversations, summaries, last 7 days                       │   │
│  │  "Yesterday you asked about the Dune audiobook"                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  LONG-TERM MEMORY (PostgreSQL - butler.user_facts)                  │   │
│  │  Persistent facts, preferences, learned patterns                    │   │
│  │  "Ron's favorite author is Brandon Sanderson"                       │   │
│  │  "Partner doesn't like horror movies"                               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  SOUL CONFIG (PostgreSQL - butler.users)                            │   │
│  │  Personality settings, custom instructions                          │   │
│  │  Loaded into system prompt at conversation start                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

> **Note:** We use the same PostgreSQL instance as Immich (already in our stack) with a separate `butler` schema. No additional database to manage.
>
> **Vector Search:** Immich's PostgreSQL image (`ghcr.io/immich-app/postgres`) includes **VectorChord**, **pgvector**, and **pgvecto.rs** extensions. We can use these for semantic memory search (e.g., "find facts similar to this question") without any extra setup.

#### Memory Database Schema

```sql
-- Create butler schema (separate from Immich)
CREATE SCHEMA IF NOT EXISTS butler;

-- User configuration and soul settings
CREATE TABLE butler.users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    wake_word TEXT,
    start_mode TEXT DEFAULT 'push_to_talk',
    tts_voice TEXT DEFAULT 'kokoro_male_1',
    permissions JSONB DEFAULT '["media", "home"]',
    soul JSONB DEFAULT '{}',  -- personality, formality, verbosity, humor, custom_instructions
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- User facts (long-term memory)
CREATE TABLE butler.user_facts (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES butler.users(id),
    fact TEXT NOT NULL,
    category TEXT,  -- 'preference', 'routine', 'personal', 'media'
    confidence REAL DEFAULT 1.0,
    source TEXT DEFAULT 'explicit',  -- 'explicit' (user said) or 'inferred'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_referenced TIMESTAMPTZ,
    embedding VECTOR(768)   -- nomic-embed-text via Ollama (see tools/embeddings.py)
);

-- Conversation history (short-term memory)
CREATE TABLE butler.conversation_history (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES butler.users(id),
    role TEXT NOT NULL,  -- 'user' or 'assistant'
    content TEXT NOT NULL,
    summary TEXT,        -- AI-generated summary (historical; context now uses full messages)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-provisioned service account credentials (encrypted)
CREATE TABLE butler.service_credentials (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES butler.users(id) ON DELETE CASCADE,
    service TEXT NOT NULL,       -- 'jellyfin', 'audiobookshelf', 'nextcloud', 'immich'
    username TEXT NOT NULL,
    password_encrypted TEXT,     -- Fernet-encrypted, decrypted only at runtime
    external_id TEXT,            -- service-specific user ID
    status TEXT NOT NULL DEFAULT 'active',  -- 'active', 'failed', 'decrypt_error'
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, service)
);

-- Indexes for fast retrieval
CREATE INDEX idx_facts_user ON butler.user_facts(user_id);
CREATE INDEX idx_facts_category ON butler.user_facts(user_id, category);
CREATE INDEX idx_history_user_date ON butler.conversation_history(user_id, created_at DESC);

-- Auto-cleanup: delete conversation history older than 30 days
-- (Run via pg_cron or application-level job)
```

#### How Memory Works

1. **On conversation start:**
   - Load user's soul config into system prompt
   - Load recent conversation messages as multi-turn history (last 20 messages, 7-day window) — passed as actual message objects in the Claude API messages array, not as text in the system prompt
   - Fetch relevant long-term facts via hybrid search: semantic similarity (pgvector embedding of current message) + highest-confidence facts, deduplicated

2. **During conversation:**
   - Store each exchange in conversation_history
   - Extract and store new facts ("I love sci-fi" → user_facts)

3. **After conversation:**
   - Update fact confidence scores based on usage

#### Example System Prompt & Messages

The system prompt contains personality and facts only. Conversation history is passed as actual messages in the Claude API messages array for proper multi-turn context:

**System Prompt:**
```
You are Butler, a helpful AI assistant. You are speaking with Ron.

PERSONALITY:
- Style: friendly and efficient
- Verbosity: concise
- Humor: yes

WHAT YOU KNOW ABOUT RON:
- [preference] Prefers audiobooks at 1.2x speed
- [media] Favorite author: Brandon Sanderson
- [routine] Listens to audiobooks during commute (8am, 6pm)
- [media] Recently asked about the Dune series

RULES:
- Be concise in voice responses (1-2 sentences unless asked for detail)
- Use remember_fact to store important information about the user
- For home automation, confirm before executing destructive actions
```

**Messages Array (multi-turn history + current message):**
```json
[
  {"role": "user", "content": "What's the weather tomorrow?"},
  {"role": "assistant", "content": "Tomorrow looks sunny, around 18°C."},
  {"role": "user", "content": "Download 'The Way of Kings' audiobook"},
  {"role": "assistant", "content": "Done! Added to your library."},
  {"role": "user", "content": "Will I need an umbrella this weekend?"}
]
```

#### Memory Tools

Custom Python tools interface directly with PostgreSQL (not Butler API's built-in `memory.py`):

| Tool | Purpose |
|------|---------|
| `remember_fact` | Store a new fact about the user |
| `recall_facts` | Retrieve relevant facts for context |
| `get_recent_conversations` | Get recent conversation messages |
| `update_soul` | Modify user's personality settings |

#### Adding New Users

1. Create user entry in configuration
2. Generate JWT token for user
3. Install app on user's device
4. Scan QR code or enter token to authenticate
5. User configures preferences in app

### Voice Interface

**Design Goal:** Natural, real-time conversation like ChatGPT Voice - not voice messages.

#### Voice Architecture (LiveKit-based)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        REAL-TIME VOICE FLOW                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Mobile App (iOS/Android)                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  You speak naturally → Audio streams in real-time → AI responds     │  │
│   │                        (no recording, no sending, no waiting)       │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│         │                                                    ▲              │
│         │ WebRTC (via Cloudflare Tunnel)                     │              │
│         ▼                                                    │              │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                     MAC MINI SERVER                                 │  │
│   │                                                                     │  │
│   │   Audio In ──► Groq STT ──► Claude API ──► Butler ──► Kokoro ──►   │  │
│   │                (CLOUD)       (CLOUD)       Tools      (LOCAL)       │  │
│   │                Whisper        Brain      Orchestrate    TTS         │  │
│   │                                                                     │  │
│   │   Latency: ~650ms round-trip (conversational)                      │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Input Channels

| Channel | Voice | Text | Notifications | How It Works |
|---------|-------|------|---------------|--------------|
| **Mobile App** | ✅ Real-time | ✅ | ✅ Push | Custom app with LiveKit SDK |
| **Alexa** | ✅ | ❌ | ❌ | Alexa → AWS Lambda (haaska) → Cloudflare Tunnel → HA → Voice Agent |
| **WhatsApp** | ❌ | ❌ | ✅ Outbound only | Butler sends notifications |

#### Conversation Start Modes (Per-User Configurable)

| Mode | How It Works | Best For |
|------|--------------|----------|
| **Push-to-talk** | Tap button → speak → release | Reliability, no false triggers |
| **App-open listening** | Open app → AI immediately listening | Most natural (like ChatGPT Voice) |
| **Custom wake word** | Say personalized phrase → AI responds | Hands-free use |

> **Default:** Push-to-talk (most reliable). Users can enable wake word or app-open listening in settings.

#### Client App: Progressive Web App (PWA)

**Why PWA instead of native apps:**
- Single codebase works on iOS, Android, Windows, Mac, Linux
- No app store approval or delays
- Instant updates (just refresh)
- LiveKit's primary SDK is JavaScript/React

| Platform | Access Method | Install |
|----------|---------------|---------|
| **iOS (Safari)** | Visit URL → Add to Home Screen | PWA |
| **Android (Chrome)** | Visit URL → Install App prompt | PWA |
| **Desktop** | Visit URL or install as app | Browser/PWA |

**Tech Stack:**

| Component | Technology | Purpose |
|-----------|------------|---------|
| Framework | [React](https://react.dev/) + [Vite](https://vitejs.dev/) | Fast, modern web app |
| Voice | [@livekit/components-react](https://docs.livekit.io/realtime/client-sdks/react/) | Pre-built voice UI |
| Styling | [Tailwind CSS](https://tailwindcss.com/) | Responsive design |
| PWA | [Vite PWA Plugin](https://vite-pwa-org.netlify.app/) | Installable, offline-capable |
| Markdown | [react-markdown](https://github.com/remarkjs/react-markdown) + [rehype-highlight](https://github.com/rehypejs/rehype-highlight) | Rich text & code highlighting |

**Features:**
- Push-to-talk (hold button to speak)
- Tap-to-talk (toggle on/off)
- Voice activity visualization
- Markdown chat rendering (code blocks, lists, links)
- Conversation history
- User settings & preferences
- PWA install prompt

### Integrations (Custom Skills & Tools)

> **Note:** These are implemented as custom Python tools in the `butler/tools/` directory.

#### Read-Only Integrations

| Integration | Purpose | Access Level |
|-------------|---------|--------------|
| **Google Calendar** | Know schedule, holidays, return dates | Read-only |
| **Gmail** | Flight confirmations, delivery notifications | Read-only |
| **Phone Location** (×2) | Know if home/away, enable geofencing | Read-only |
| **Weather API** | Forecasts for automation decisions | Read-only |

#### Read-Write Integrations

| Integration | Purpose | Access Level |
|-------------|---------|--------------|
| **Home Assistant** | Control heating, lights, devices | Read-write |
| **Radarr/Sonarr** | Add movies & TV to library | Read-write |
| **BookTool** | Search & download books (Open Library + Prowlarr + qBit) | Read-write |
| **Jellyfin** | Playback control | Read-write |
| **Immich** | Photo search | Read-only |
| **WhatsApp** | Send notifications to users | Write-only (outbound) |

### Example Use Cases

| Command | What Happens |
|---------|--------------|
| *"Turn the heating on 2 days before I get back from Japan"* | Reads calendar → finds return date → schedules HA automation |
| *"Find the new Dune audiobook"* | BookTool search (Open Library) → Prowlarr → qBittorrent → WhatsApp notification when done |
| *"Is anyone home?"* | Checks both phone locations → responds accordingly |
| *"What's the weather like for my trip?"* | Reads calendar for trip dates → fetches weather forecast |
| *"Dim the living room lights"* | Calls Home Assistant → adjusts lights |

### Proactive Notifications (WhatsApp)

The Butler can message you without being asked:

| Trigger | Message |
|---------|---------|
| Download complete | "Dune audiobook is ready in your library" |
| Scheduled task done | "Heating has been turned on - you return in 2 days" |
| Calendar reminder | "Flight to Japan tomorrow - have you packed?" |
| Weather alert | "Heavy rain forecast for your commute tomorrow" |

### Alexa Integration (Free - haaska)

Instead of the paid Home Assistant Cloud (£5/month), we use the community-maintained **haaska** project with AWS Lambda free tier and Cloudflare Tunnel for secure access.

```
"Alexa, ask home to find the new Dune movie"
        │
        ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  Amazon Echo  │────►│  AWS Lambda   │────►│  Cloudflare   │────►│ Home Assistant│
│               │     │   (haaska)    │     │    Tunnel     │     │               │
└───────────────┘     │   FREE TIER   │     │   FREE TIER   │     └───────┬───────┘
                      └───────────────┘     └───────────────┘             │
                                                                          ▼
                                                                  ┌───────────────┐
                                                                  │   Butler API     │
                                                                  │   Butler      │
                                                                  └───────────────┘
```

**Components:**

| Component | Purpose | Cost |
|-----------|---------|------|
| [haaska](https://github.com/mike-grant/haaska) | Alexa Smart Home skill adapter for Home Assistant | Free (open source) |
| AWS Lambda | Serverless hosting for haaska function | Free (1M requests/month) |
| Cloudflare Tunnel | Secure access to HA without public IP exposure | Free tier |

**Setup Overview:**
1. Create free AWS account
2. Deploy haaska Lambda function (ZIP upload)
3. Create Alexa Smart Home skill in Amazon Developer Console
4. Configure Cloudflare Tunnel to expose HA API endpoint
5. Link Alexa skill to Lambda, Lambda to HA via tunnel
6. Generate HA Long-Lived Access Token for Lambda authentication

**Security Notes:**
- ✅ No public ports opened on Mac Mini
- ✅ Cloudflare Tunnel provides encrypted access
- ✅ HA Long-Lived Access Token for Lambda authentication
- ✅ Same security posture as paid HA Cloud, but free

**Alexa Invocation Options:**
- `"Alexa, ask Home to..."` - triggers Home Assistant skill
- `"Alexa, tell Butler to..."` - can create custom invocation name
- Simple commands go direct to HA; complex ones routed to Butler API

### Security Approach

Butler API is already minimal (~4k lines), but we further harden it:

| Butler API Feature | Our Configuration |
|-----------------|-------------------|
| External skill loading | ❌ Disabled in config |
| Tool directory | ⚠️ Locked to our custom Python tools only |
| Shell execution | ⚠️ Removed or restricted to allowlist |
| File system access | ⚠️ Restricted to specific paths |
| Network access | ⚠️ Cloudflare Tunnel (no public ports) |
| LLM providers | ✅ Claude API only |
| WhatsApp | ✅ WebSocket mode (no public IP) |
| Scheduler | ✅ Cron for automations |
| User allowlist | ✅ Only specified phone numbers |

**Why Butler API security approach:**
- 99% smaller attack surface (4k vs 430k lines)
- Entire codebase readable in an afternoon
- Research-focused = clean, auditable code
- No feature bloat = fewer vectors

### Why Cloud LLM vs Local LLM

| Factor | Local LLM (Ollama) | Cloud LLM (Claude API) |
|--------|-------------------|------------------------|
| **RAM Required** | 4-12GB | 0GB |
| **Response Quality** | Limited reasoning | Excellent reasoning |
| **Monthly Cost** | £0 | ~£3.50 |
| **Latency** | ~2-5s on M4 | ~1-2s |
| **Context-aware** | Limited | Excellent (calendar, location, etc.) |
| **Recommendation** | ❌ Not viable with this setup | ✅ Use this |

---

## Storage Layout

### Drive Characteristics & Limitations

#### Internal SSD (512GB) - Apple Silicon NVMe

| Property | Value | Notes |
|----------|-------|-------|
| **Type** | NVMe SSD | Integrated into Mac Mini |
| **Speed** | ~3,000 MB/s read | Extremely fast random access |
| **Best For** | OS, apps, databases, Docker | Anything needing fast I/O |
| **Avoid** | Large media files | Wastes precious SSD space |
| **Health Rule** | Keep 10-15% free | macOS needs breathing room |

#### External Drive (USB HDD)

| Property | Value | Notes |
|----------|-------|-------|
| **Type** | Spinning HDD (5400-7200 RPM typical) | Slower random access than SSD |
| **Interface** | USB 3.0+ | Real-world ~150 MB/s (HDD bottleneck, not USB) |
| **Format** | APFS or Mac OS Extended | Native Mac format |
| **Best For** | Media, photos, backups | Large sequential files |
| **Avoid** | Databases, app data | Poor random I/O performance |

##### External HDD Considerations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| **Spin-down** | Drive sleeps after inactivity, causes 2-5s delay on wake | Accept delay or schedule periodic activity |
| **Single drive** | No redundancy — if drive fails, data is lost | Cloud backup for irreplaceable data (photos/docs) |
| **USB disconnect** | macOS can unmount on sleep/wake | Enable "Prevent sleep" or use Amphetamine app |
| **Seek times** | Slow for random file access (~10ms vs 0.1ms SSD) | Keep databases on SSD |

---

### Internal SSD Budget (512GB)

| Component | Size | Running Total | Notes |
|-----------|------|---------------|-------|
| **macOS Sonoma** | 30GB | 30GB | Base system |
| **System Data & Cache** | 15GB | 45GB | Logs, caches, updates |
| **OrbStack Engine** | 5GB | 50GB | Docker runtime |
| **Docker Images** | 40GB | 90GB | All container images |
| **Service Databases** | | | |
| ├─ Immich (PostgreSQL) | 10GB | 100GB | Grows with photo metadata |
| ├─ Jellyfin SQLite | 2GB | 102GB | Media metadata & watch history |
| ├─ *arr stack SQLite (×5) | 5GB | 107GB | Movie/TV/Book databases |
| ├─ Home Assistant SQLite | 2GB | 109GB | Automation history |
| └─ Nextcloud (MySQL/SQLite) | 3GB | 112GB | File metadata |
| **ML Models** | | | |
| ├─ Immich ML models | 5GB | 117GB | Face recognition, CLIP |
| └─ Kokoro TTS model | 1GB | 118GB | Text-to-speech |
| **Docker Volumes (configs)** | 5GB | 123GB | Service configurations |
| **Homebrew packages** | 4GB | 127GB | CLI tools |
| **User Applications** | 20GB | 147GB | OrbStack GUI, etc. |
| | | | |
| **Total Used** | **~147GB** | | |
| **Reserved (30%)** | **~150GB** | | macOS health + future growth |
| **Available** | **~203GB** | | Buffer for unexpected needs |

#### 🔴 Critical: What MUST Stay on SSD

| Data | Why |
|------|-----|
| All databases (PostgreSQL, SQLite, MySQL) | Random I/O performance |
| Docker images | Container startup speed |
| ML models | Model loading speed |
| Service config volumes | Frequent small reads/writes |

#### 🟢 What Goes on External HDD

| Data | Why |
|------|-----|
| Media files (movies, TV, music) | Large sequential reads |
| Photos (Immich originals) | Large sequential reads |
| Audiobooks & eBooks | Large sequential reads |
| Downloads (in-progress & complete) | Write once, read once |
| Backups | Infrequent access |

---

### External HDD Budget

#### Usable Space Calculation

Manufacturers advertise capacity in decimal (base-10), but your OS reports binary (base-2). Expect ~9% less usable space than advertised:

| Advertised | Actual Formatted | Usable (after overhead) |
|------------|-----------------|------------------------|
| 4TB | 3.64 TB | ~3.6 TB |
| 8TB | 7.27 TB | ~7.2 TB |
| 12TB | 10.91 TB | ~10.8 TB |
| 16TB | 14.55 TB | ~14.4 TB |

#### Suggested Space Allocation

Percentages scale to any drive size. Example values shown for an 8TB (~7.2TB usable) drive:

| Category | % of Total | Example (8TB) | Contents |
|----------|-----------|---------------|----------|
| **Movies** | 41% | 3,000 GB | ~75 4K movies OR ~300 1080p movies |
| **TV Shows** | 28% | 2,000 GB | ~40 4K seasons OR ~200 1080p seasons |
| **Photos** | 14% | 1,000 GB | ~50,000 RAW or ~250,000 JPEG |
| **Audiobooks** | 4% | 300 GB | ~600 audiobooks |
| **eBooks** | <1% | 50 GB | ~10,000 eBooks |
| **Documents** | 3% | 200 GB | Nextcloud files |
| **Downloads Buffer** | 5% | 400 GB | In-progress downloads |
| **Backups** | 3% | 200 GB | Database & config backups |
| **Reserved** | <1% | ~50 GB | Breathing room |

> Adjust percentages based on your priorities. Heavy media users should shift allocation toward Movies/TV; photographers toward Photos.

---

### Content Capacity Estimates

#### Movies (3TB Allocation)

| Quality | Avg Size | How Many Fit | Notes |
|---------|----------|--------------|-------|
| 4K HDR Remux | 50-80 GB | ~40-60 | Full quality, huge files |
| 4K HDR (compressed) | 15-25 GB | ~120-200 | Good balance |
| 1080p High Quality | 8-15 GB | ~200-375 | Most common choice |
| 1080p Standard | 2-5 GB | ~600-1500 | Streaming quality |

> **Recommendation:** Target 4K compressed (15-25GB) for favorites, 1080p (8-15GB) for casual viewing. ~150-200 movies is realistic.

#### TV Shows (2TB Allocation)

| Quality | Avg Episode | 10-Episode Season | Seasons That Fit |
|---------|-------------|-------------------|------------------|
| 4K HDR | 5-10 GB | 50-100 GB | ~20-40 seasons |
| 1080p High | 2-4 GB | 20-40 GB | ~50-100 seasons |
| 1080p Standard | 500MB-1.5GB | 5-15 GB | ~130-400 seasons |

> **Recommendation:** 4K for prestige shows, 1080p for binge content. ~60-80 seasons is realistic.

#### Photos (1TB Allocation)

| Format | Avg Size | How Many Fit |
|--------|----------|--------------|
| iPhone HEIC | 2-4 MB | ~250,000-500,000 |
| JPEG High Quality | 4-8 MB | ~125,000-250,000 |
| RAW (24MP) | 20-30 MB | ~33,000-50,000 |
| RAW (50MP+) | 50-100 MB | ~10,000-20,000 |

> **Note:** 1TB = roughly 10-20 years of personal photos for most people.

#### Books (350GB Total Allocation)

| Type | Avg Size | How Many Fit |
|------|----------|--------------|
| eBook (EPUB/MOBI) | 1-5 MB | ~10,000-50,000 |
| Audiobook (standard) | 300-600 MB | ~500-1,000 |
| Audiobook (high quality) | 800MB-1.5GB | ~200-400 |

---

### Directory Structure

Data lives on the external drive by default, or on the internal SSD when
`--skip-drive` is used (`~/HomeServer`). The repo is always cloned to
`~/home-server` for scripts, Docker Compose files, and configs.

```
~/home-server/                          # Cloned repo (code & configs)
    ├── scripts/                        # Setup scripts (01-15)
    ├── docker/                         # Docker Compose stacks
    ├── butler/                         # Butler API source
    └── app/                            # PWA source

/Volumes/HomeServer/ (or ~/HomeServer)  # Data directory
│
├── Media/                              # 5TB allocated
│   ├── Movies/                         # Radarr root folder (flat — movies at root)
│   ├── TV/                             # Sonarr root folder (flat — shows at root)
│   ├── Anime/                          # Separate anime libraries
│   │   ├── Movies/                     # Radarr root folder (anime films)
│   │   └── Series/                     # Sonarr root folder (anime series)
│   └── Music/                          # Future: Lidarr
│
├── Books/                              # 350GB allocated
│   ├── eBooks/                         # Audiobookshelf + LazyLibrarian ebook library
│   └── Audiobooks/                     # Audiobookshelf audiobook library
│       └── Author Name/                # Organized by author
│           └── Book Title/
│
├── Photos/                             # 1TB allocated
│   └── Immich/                         # Immich library root
│       ├── library/                    # Original photos
│       ├── upload/                     # Upload processing
│       └── thumbs/                     # Generated thumbnails
│
├── Documents/                          # 200GB allocated
│   └── Nextcloud/                      # Nextcloud data directory
│       └── user/files/                 # User files
│
├── Downloads/                          # 400GB allocated
│   ├── Complete/                       # qBittorrent completed
│   │   ├── Movies/                     # Radarr picks up from here
│   │   ├── TV/                         # Sonarr picks up from here
│   │   ├── Anime/                      # Radarr/Sonarr picks up anime
│   │   └── Books/                      # LazyLibrarian/BookTool picks up from here
│   └── Incomplete/                     # qBittorrent in-progress
│
└── Backups/                            # 200GB allocated
    ├── Databases/                      # Nightly database dumps
    │   ├── immich/
    │   ├── jellyfin/
    │   ├── homeassistant/
    │   └── arr-stack/
    ├── Configs/                        # Docker volume backups
    └── TimeMachine/                    # Optional: Mac backup slice
```

---

### Storage Growth & Monitoring

#### Estimated Monthly Growth

| Category | Growth Rate | Notes |
|----------|-------------|-------|
| Movies | +50-150 GB | Depends on acquisition rate |
| TV Shows | +20-80 GB | Seasonal variation |
| Photos | +5-20 GB | Family photo uploads |
| Audiobooks | +5-15 GB | ~10-30 books/month |
| Documents | +1-5 GB | Generally stable |
| Databases | +500 MB | Metadata growth |
| | | |
| **Total** | **~80-270 GB/month** | |

#### Time to Full (Estimates)

| Usage Pattern | Monthly Growth | Time to 80% Full |
|---------------|----------------|------------------|
| Light | ~80 GB | ~6 years |
| Moderate | ~150 GB | ~3 years |
| Heavy | ~270 GB | ~1.5 years |

#### 🚨 Storage Alerts to Configure

| Threshold | Action |
|-----------|--------|
| **70% full** | Review and clean up |
| **80% full** | Stop auto-downloads, audit library |
| **90% full** | Emergency: delete or expand storage |

---

### Backup Strategy & Philosophy

#### ⚠️ Off-Site Backup is OPTIONAL

> **Default configuration:** No cloud backup. User accepts data loss risk for photos/documents.
>
> **Why?** To minimize monthly costs. You can always add cloud backup later.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     THE BACKUP DECISION FRAMEWORK                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Is this data IRREPLACEABLE?                                          │
│         │                                                               │
│         ├── YES (photos, documents, configs)                           │
│         │     └── OPTIONAL: Configure cloud backup if you want         │
│         │         iCloud 2TB (£6.99/mo) or Google One 2TB (£7.99/mo)  │
│         │                                                               │
│         └── NO (movies, TV shows, audiobooks, ebooks)                  │
│               └── DO NOT backup                                         │
│                   The *arr stack IS your backup                        │
│                   Re-download takes hours, not money                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Why This Makes Sense

| Data Type | If Drive Fails... | Backup Needed? |
|-----------|-------------------|----------------|
| **Movies/TV** | Re-download via Radarr/Sonarr (automated) | ❌ No |
| **Audiobooks** | Re-download via LazyLibrarian/BookTool | ❌ No |
| **eBooks** | Re-download via LazyLibrarian/BookTool | ❌ No |
| **Photos** | **GONE FOREVER** - irreplaceable memories | ⚠️ Optional (user choice) |
| **Documents** | **GONE FOREVER** - personal/work files | ⚠️ Optional (user choice) |
| **Service configs** | Hours of reconfiguration work | ✅ Local backup (free) |
| **Databases** | Lose watch history, metadata, settings | ✅ Local backup (free) |

**The key insight:** Media files are *inventory*, not *memories*. Your *arr stack is effectively a "backup" that can recreate your library on-demand.

#### What Actually Needs Backup

| Priority | Data | Size Estimate | Backup Method |
|----------|------|---------------|---------------|
| ⚠️ **Optional** | Photos (Immich) | ~500GB-1TB | User configures iCloud/Google/Backblaze if desired |
| ⚠️ **Optional** | Documents (Nextcloud) | ~50-200GB | User configures iCloud/Google Drive if desired |
| 🟡 **Important** | Service databases | ~5-10GB | Local backup to Mac SSD (free) |
| 🟡 **Important** | Docker configs | ~1GB | Local backup + Git repo (free) |
| 🟢 **Replaceable** | Media files (5TB+) | N/A | **NO BACKUP** - re-download if needed |

#### The Economics

| Scenario | Cost | Notes |
|----------|------|-------|
| **No cloud backup (default)** | £0/month | Accept risk for photos/documents |
| Add iCloud 2TB | +£6.99/month | Apple ecosystem, seamless |
| Add Google One 2TB | +£7.99/month | Good mobile apps, cross-platform |
| Backup EVERYTHING (~7TB) | ~£50-70/month | Defeats purpose of self-hosting |

**Default approach:** No cloud backup. Local database backups to Mac SSD provide protection against external drive failure for configs/metadata. User can add iCloud or Google One later if they want photo/document protection.

#### Disaster Recovery Plan

**If external drive fails:**

| Data | Recovery Method | Time to Recover |
|------|-----------------|-----------------|
| Photos | Restore from iCloud/Google Photos | Hours |
| Documents | Restore from iCloud/Google Drive | Hours |
| Databases | Restore from local backup on Mac SSD | Minutes |
| Docker configs | Restore from Git repo or local backup | Minutes |
| Movies/TV | Radarr/Sonarr auto-re-downloads | Days (background) |
| Audiobooks/eBooks | Re-download via LazyLibrarian/BookTool | Hours (background) |

**Total downtime:** A few hours to get services running. Library rebuilds in background over days.

#### Local Backup Setup (For Databases & Configs)

Keep a rolling backup ON THE MAC'S INTERNAL SSD (not the external drive).

**Implemented:** `scripts/backup.sh` (daily via launchd), `scripts/restore.sh`, `scripts/14-backup.sh`

```
~/ServerBackups/
├── databases/
│   └── immich-db-YYYY-MM-DD.sql.gz          # Daily pg_dumpall (Immich + Nextcloud)
├── configs/
│   ├── jellyfin-config-YYYY-MM-DD.tar.gz    # Daily per-volume tarballs
│   ├── radarr-config-YYYY-MM-DD.tar.gz
│   ├── sonarr-config-YYYY-MM-DD.tar.gz
│   ├── homeassistant-config-YYYY-MM-DD.tar.gz
│   └── ... (13 volumes total)
├── weekly/
│   ├── databases/                            # Sunday backups promoted here
│   └── configs/
├── backup.log
└── retention: 7 daily, 4 weekly
```

**Scheduling:** launchd (`com.homeserver.backup`) runs daily at 3:00 AM.

This protects against: external drive failure, accidental deletion, service corruption.
This does NOT protect against: Mac Mini theft/fire (use cloud for that).

#### Off-site Backup Options (OPTIONAL - User Configures Later)

> **Note:** These are NOT included in the default setup. Add if you want cloud protection for photos/documents.

| Service | UK Cost | Capacity | Best For |
|---------|---------|----------|----------|
| **iCloud** | £6.99/mo | 2TB | Apple ecosystem, seamless |
| **Google One** | £7.99/mo | 2TB | Good mobile apps, Google Photos integration |
| **Backblaze B2** | ~£4/TB/mo | Pay-per-use | Technical users, cheapest per GB |
| **Backblaze Personal** | £7/mo | Unlimited | Full Mac backup (not just selected folders) |

> **User choice:** If you want off-site backup, iCloud 2TB (£6.99/month) offers seamless Mac + iPhone integration. This would increase monthly costs from £7.21 to £14.20.

---

## Network & Communication Flow

### Port Map

| Port | Service | Access |
|------|---------|--------|
| 3000 | Butler PWA | LAN + Cloudflare Tunnel |
| 8000 | Butler API | LAN + Cloudflare Tunnel |
| 8096 | Jellyfin | LAN + Cloudflare Tunnel |
| 8123 | Home Assistant | LAN + Cloudflare Tunnel |
| 2283 | Immich | LAN + Cloudflare Tunnel |
| 8080 | Nextcloud | LAN + Cloudflare Tunnel |
| 13378 | Audiobookshelf | LAN + Cloudflare Tunnel |
| 5299 | LazyLibrarian | LAN + Cloudflare Tunnel |
| 7880 | LiveKit | LAN + Cloudflare Tunnel |
| 7878 | Radarr | LAN only |
| 8989 | Sonarr | LAN only |
| 5055 | Seerr | LAN + Cloudflare Tunnel |
| 6767 | Bazarr | LAN only |
| 9696 | Prowlarr | LAN only |
| 8081 | qBittorrent | LAN only |
| 8100 | Butler Agent | LAN only |
| 8880 | Kokoro TTS | LAN only |

### Service Communication

```
┌─────────────────────────────────────────────────────────────────────┐
│                     INTERNAL SERVICE MESH                           │
└─────────────────────────────────────────────────────────────────────┘

  Prowlarr ──────┬──────┬──────┬────── (Indexer sync)
                 │      │      │
                 ▼      ▼      ▼
              Radarr  Sonarr  LazyLibrarian
                 │      │      │
                 └──────┴──────┘
                        │
                        ▼
                  qBittorrent ──────► /Downloads/Complete/
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
      Jellyfin    Audiobookshelf   LazyLibrarian
      (Movies/TV) (Books+Audio)   (organizes→ABS)

  Home Assistant ◄────► Butler Agent ◄────► All Services
                              │
                              ▼
                         Claude API
```

---

## Implementation Phases

### Phase 1: Foundation (Day 1)
- [ ] Install OrbStack
- [ ] Install Homebrew
- [ ] Configure Cloudflare Tunnel (see [setup guide](docs/cloudflare-tunnel.md))
- [ ] Configure external drive mount
- [ ] Create directory structure

### Phase 2: Download Infrastructure (Day 1-2)
- [ ] Deploy qBittorrent
- [ ] Deploy Prowlarr
- [ ] Configure indexers (public & private trackers) — see [Prowlarr Indexer Setup Guide](docs/prowlarr-indexers.md) (#109)

### Phase 3: Media Stack (Day 2-3)
- [ ] Deploy Jellyfin
- [ ] Deploy Radarr + Sonarr + Bazarr
- [ ] Connect to Prowlarr and qBittorrent
- [ ] Test full download → playback workflow

### Phase 4: Books & Audio (Day 3-4)
- [ ] Deploy Audiobookshelf
- [ ] Deploy LazyLibrarian
- [ ] Configure LazyLibrarian connections (Prowlarr, qBittorrent)
- [ ] Write ebook reading setup guide (#110)

### Phase 5: Photos & Files (Day 4-5)
- [ ] Deploy Immich
- [ ] Deploy Nextcloud
- [ ] Configure mobile photo backup
- [ ] Set up file sync

### Phase 6: Smart Home & Alexa (Day 5-6)
- [ ] Deploy Home Assistant
- [ ] Integrate existing smart devices
- [ ] Create basic automations
- [ ] Create free Cloudflare account
- [ ] Deploy Cloudflare Tunnel (cloudflared container)
- [ ] Create free AWS account
- [ ] Deploy haaska to AWS Lambda (ZIP upload)
- [ ] Create Alexa Smart Home skill in Amazon Developer Console
- [ ] Generate HA Long-Lived Access Token
- [ ] Link Alexa skill → Lambda → Tunnel → HA
- [ ] Test Alexa → Home Assistant commands

### Phase 7: AI Butler (Day 6-7)
- [ ] Deploy Kokoro TTS
- [ ] Build Butler Agent with Claude API
- [ ] Define function schemas for all services
- [ ] Test voice command workflow

### Phase 8: Hardening (Day 7+)
- [ ] Configure automatic backups
- [ ] Set up monitoring/alerts
- [ ] Document credentials securely
- [ ] Test Cloudflare Tunnel remote access

---

## Cost Summary

### Hardware (One-Time)

| Item | Estimated Cost | Notes |
|------|---------------|-------|
| Mac Mini M4 (24GB/512GB) | £899 / $799 | Check Apple's website or authorized resellers for current pricing |
| External USB HDD (8TB) | £100-150 / $100-150 | See [Choosing an External Drive](#choosing-an-external-drive) |
| **Total Hardware** | **~£1,000-1,050** | |

> **Tip:** Look for deals during sales events (Black Friday, Amazon Prime Day). Refurbished Mac Minis from Apple are also a good option — same warranty, lower price.

### Monthly Running Costs (UK)

| Item | Cost (£) | Notes |
|------|----------|-------|
| [Claude API](https://www.anthropic.com/api) | ~£7.00 | Butler brain (~500 requests/month with multi-turn history) |
| Electricity | ~£3.70 | Mac Mini 24/7 (~15W avg × 730hrs × 34p/kWh) |
| [AWS Lambda](https://aws.amazon.com/lambda/) (haaska) | £0 | Free tier (1M requests/month) |
| [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/) | £0 | Free tier — primary remote access |
| Voice (Groq Whisper + Kokoro TTS) | £0 | STT via Groq free tier, TTS runs locally |
| All software | £0 | Open source |
| **Total Monthly (no backup)** | **~£10.70** | |
| | | |
| **Optional Add-ons:** | | |
| [iCloud 2TB](https://www.apple.com/uk/icloud/) | +£6.99 | Photo & document backup (user choice) |
| **Total Monthly (with iCloud)** | **~£17.69** | If user enables cloud backup |

### Subscription Savings (Estimated UK Prices)

| Replaced Service | Monthly Cost (£) | Notes |
|------------------|------------------|-------|
| Netflix Standard | £10.99 | Replaced by Jellyfin |
| Disney+ | £7.99 | Replaced by Jellyfin |
| iCloud 2TB | £6.99 | No longer required (optional user choice) |
| Google One 200GB | £2.49 | Replaced by Nextcloud |
| Kindle Unlimited | £9.99 | Replaced by Audiobookshelf + LazyLibrarian |
| Audible | £7.99 | Replaced by Audiobookshelf |
| Smart Home (various) | ~£5.00 | Replaced by haaska (free) |
| **Gross Savings** | **~£51.44/month** | All services replaced |
| Minus server costs | -£10.70 | |
| **Net Savings** | **~£40.74/month** | |

### Break-Even Analysis

| Item | Value |
|------|-------|
| Hardware cost (estimated) | ~£1,000 |
| Monthly net savings | £40.74 |
| **Break-even point** | **~25 months (~2.0 years)** |

> **Note:** Actual savings depend on which subscriptions you currently have. If you only had Netflix + Audible, savings would be lower. The non-financial benefits (privacy, ownership, no ads, no content removal, Alexa voice control) are immediate.
>
> **If you add iCloud backup (£6.99/mo):** Net savings = £33.75/month, break-even = ~30 months

### Total Cost of Ownership (5 Years)

| Scenario | Calculation | Total |
|----------|-------------|-------|
| **Self-hosted (no backup)** | £1,000 + (£10.70 × 60 months) | **£1,642** |
| **Self-hosted (with iCloud)** | £1,000 + (£17.69 × 60 months) | **£2,061** |
| **Subscriptions only** | £51.44 × 60 months | **£3,086** |
| **Savings (no backup)** | | **£1,444 saved** |
| **Savings (with iCloud)** | | **£1,025 saved** |

---

## Complete Software Reference

All software used in this project with links to official sources.

### Core Infrastructure

| Software | Homepage | Purpose | License |
|----------|----------|---------|---------|
| [OrbStack](https://orbstack.dev/) | [orbstack.dev](https://orbstack.dev/) | Fast Docker & Linux on macOS (Apple Silicon optimized) | Freemium |
| [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) | [cloudflare.com](https://developers.cloudflare.com/cloudflare-one/) | Primary remote access for all user-facing services (no public IP) | Free tier |
| [Homebrew](https://brew.sh/) | [brew.sh](https://brew.sh/) | Package manager for macOS CLI tools | Open Source |

### Voice & AI

| Software | Homepage | Purpose | License |
|----------|----------|---------|---------|
| [LiveKit](https://livekit.io/) | [livekit.io](https://livekit.io/) | Open-source WebRTC server for real-time audio/video | Apache 2.0 |
| [LiveKit Agents](https://github.com/livekit/agents) | [GitHub](https://github.com/livekit/agents) | Python framework for building voice AI agents | Apache 2.0 |
| [Groq Whisper](https://console.groq.com/) | [groq.com](https://console.groq.com/) | Cloud speech-to-text (Whisper large-v3-turbo, free tier) | Commercial |
| [Kokoro TTS](https://github.com/remsky/Kokoro-FastAPI) | [GitHub](https://github.com/remsky/Kokoro-FastAPI) | High-quality local text-to-speech | Apache 2.0 |
| [Claude API](https://www.anthropic.com/api) | [anthropic.com](https://www.anthropic.com/api) | LLM for understanding, reasoning, function calling | Commercial |
| Butler API | Self-built | FastAPI backend with custom Python tools (~4k lines) | - |

### Media & Entertainment

| Software | Homepage | Purpose | License |
|----------|----------|---------|---------|
| [Jellyfin](https://jellyfin.org/) | [jellyfin.org](https://jellyfin.org/) | Free media server (4K HDR, Dolby Atmos support) | GPL-2.0 |
| [Radarr](https://radarr.video/) | [radarr.video](https://radarr.video/) | Movie collection manager & automation | GPL-3.0 |
| [Sonarr](https://sonarr.tv/) | [sonarr.tv](https://sonarr.tv/) | TV series collection manager & automation | GPL-3.0 |
| [Bazarr](https://www.bazarr.media/) | [bazarr.media](https://www.bazarr.media/) | Automatic subtitle download & management | GPL-3.0 |
| [Prowlarr](https://prowlarr.com/) | [prowlarr.com](https://prowlarr.com/) | Indexer manager for *arr stack | GPL-3.0 |
| [qBittorrent](https://www.qbittorrent.org/) | [qbittorrent.org](https://www.qbittorrent.org/) | Lightweight torrent client | GPL-2.0 |

### Books & Audio

| Software | Homepage | Purpose | License |
|----------|----------|---------|---------|
| [Audiobookshelf](https://www.audiobookshelf.org/) | [audiobookshelf.org](https://www.audiobookshelf.org/) | Ebook + audiobook library, reading, streaming | GPL-3.0 |
| [LazyLibrarian](https://lazylibrarian.gitlab.io/) | [GitLab](https://gitlab.com/LazyLibrarian/LazyLibrarian) | Book search, download management, library organization | GPL-3.0 |

### Photos & Files

| Software | Homepage | Purpose | License |
|----------|----------|---------|---------|
| [Immich](https://immich.app/) | [immich.app](https://immich.app/) | Self-hosted photo/video backup with AI recognition | AGPL-3.0 |
| [Nextcloud](https://nextcloud.com/) | [nextcloud.com](https://nextcloud.com/) | Self-hosted file sync, calendar, contacts | AGPL-3.0 |

### Smart Home

| Software | Homepage | Purpose | License |
|----------|----------|---------|---------|
| [Home Assistant](https://www.home-assistant.io/) | [home-assistant.io](https://www.home-assistant.io/) | Open-source home automation hub | Apache 2.0 |
| [haaska](https://github.com/mike-grant/haaska) | [GitHub](https://github.com/mike-grant/haaska) | Alexa Smart Home skill for Home Assistant | MIT |
| [AWS Lambda](https://aws.amazon.com/lambda/) | [aws.amazon.com](https://aws.amazon.com/lambda/) | Serverless hosting for haaska | Free tier |

### Client App (Web PWA)

| Software | Homepage | Purpose | License |
|----------|----------|---------|---------|
| [React](https://react.dev/) | [react.dev](https://react.dev/) | UI framework for web app | MIT |
| [Vite](https://vitejs.dev/) | [vitejs.dev](https://vitejs.dev/) | Fast build tool & dev server | MIT |
| [LiveKit React SDK](https://docs.livekit.io/realtime/client-sdks/react/) | [Docs](https://docs.livekit.io/realtime/client-sdks/react/) | Pre-built voice UI components | Apache 2.0 |
| [Tailwind CSS](https://tailwindcss.com/) | [tailwindcss.com](https://tailwindcss.com/) | Utility-first CSS framework | MIT |
| [Vite PWA Plugin](https://vite-pwa-org.netlify.app/) | [Docs](https://vite-pwa-org.netlify.app/) | PWA support (installable, offline) | MIT |

> **Why PWA:** Single codebase works on iOS, Android, Windows, Mac, Linux. No app store approval needed. Instant updates.

### Notifications & Communication

| Software | Homepage | Purpose | License |
|----------|----------|---------|---------|
| [whatsapp-web.js](https://github.com/pedroslopez/whatsapp-web.js) | [GitHub](https://github.com/pedroslopez/whatsapp-web.js) | WhatsApp Web API for outbound notifications | Apache 2.0 |

### Cloud Services (Paid)

| Service | Homepage | Purpose | Monthly Cost |
|---------|----------|---------|--------------|
| [Claude API](https://www.anthropic.com/api) | [anthropic.com](https://www.anthropic.com/api) | LLM for voice assistant brain | ~£3.50 |

### Cloud Services (Optional)

| Service | Homepage | Purpose | Monthly Cost |
|---------|----------|---------|--------------|
| [iCloud 2TB](https://www.apple.com/uk/icloud/) | [apple.com](https://www.apple.com/uk/icloud/) | Photo & document backup (user choice) | £6.99 |
| [Google One 2TB](https://one.google.com/) | [one.google.com](https://one.google.com/) | Photo & document backup (user choice) | £7.99 |

---

## Notes & Considerations

### Performance Tips
1. **Direct Play > Transcoding** - Configure clients to direct play when possible
2. **Schedule ML tasks** - Run Immich face recognition during off-hours
3. **SSD for databases** - Keep all databases on internal SSD, not external drive
4. **Swap disabled** - macOS handles memory pressure well on Apple Silicon

### Security Considerations
1. **Cloudflare Tunnel** - No ports exposed to public internet; user-facing services accessible via Cloudflare-managed HTTPS
2. **Admin services LAN-only** - *arr stack, qBittorrent, Prowlarr not exposed remotely
3. **Strong passwords** - Use unique passwords for each service
4. **Regular backups** - Automate database and config backups
5. **Update schedule** - Keep containers updated for security patches

---

*Last Updated: 2026-02-07*
