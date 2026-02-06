# Home Server Master Plan

> **Hardware:** Mac Mini M4 (24GB Unified Memory, 512GB SSD) + 8TB External USB Drive
> **Location:** United Kingdom (hardware purchased tax-free in Japan)
> **Goal:** Self-hosted, privacy-focused media server with AI voice assistant + Alexa
> **Hardware Cost:** ~£760 (Japan tax-free) vs ~£1,049 (UK) - **saving £289**
> **Monthly Cost:** ~£7.21 (API + electricity) — backup optional, Alexa via free haaska
> **Butler Engine:** [Nanobot](https://github.com/HKUDS/nanobot) (~4k lines, skill-based)
>
> ⚠️ **Note (2026-02-05):** Nanobot uses a "skills" system (markdown instruction files), not MCP. Skills teach the agent how to use tools; the agent then calls built-in executors (shell, filesystem, web). Custom Python tools can also be registered. See TODO.md for details.

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
│  │  │ Readarr  │ │qBittorrent│ │  Immich  │ │Nextcloud │ │   Home   │  │   │
│  │  │          │ │          │ │          │ │          │ │Assistant │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │   │
│  │  ┌──────────┐ ┌──────────┐ ┌───────────────────────────────────┐   │   │
│  │  │ Calibre  │ │Audiobook │ │         AI BUTLER                 │   │   │
│  │  │   Web    │ │  shelf   │ │  Whisper + Agent + Kokoro         │   │   │
│  │  └──────────┘ └──────────┘ └───────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    8TB EXTERNAL DRIVE                               │   │
│  │   /Media  /Photos  /Documents  /Books  /Downloads  /Backups         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ (Tailscale VPN)
                        ┌───────────────────────┐
                        │   Remote Access       │
                        │   Phone / Laptop      │
                        └───────────────────────┘
```

---

## Hardware Specifications

| Component | Specification | Notes |
|-----------|---------------|-------|
| **Device** | Mac Mini M4 | Apple Silicon, excellent power efficiency |
| **RAM** | 24GB Unified Memory | Shared between CPU, GPU, Neural Engine |
| **Storage (Internal)** | 512GB SSD | OS, Docker images, databases |
| **Storage (External)** | 8TB USB External HDD | Media, photos, documents (see below) |
| **Connectivity** | Gigabit Ethernet | Hardwired recommended for streaming |
| **Power Draw** | ~10-30W typical | Very efficient for 24/7 operation |

### Recommended External Drive

**Use Case:** On-demand media streaming, photo storage, document sync. Not 24/7 continuous operation.

**Purchase in Japan (Tax-Free)** - Exchange rate: £1 = ¥213

| Recommendation | Model | Japan (税込) | Tax-Free | GBP | Source |
|----------------|-------|-------------|----------|-----|--------|
| 🥇 **Best Value** | Buffalo HD-CD8U3-BA 8TB | ¥25,000 | ¥22,500 | **£106** | [Bic Camera](https://www.biccamera.com/bc/item/7832511/) |
| 🥈 **Alternative** | WD Elements Desktop 8TB | ¥31,580 | ¥28,422 | £133 | [Kakaku](https://kakaku.com/item/K0001236095/) |

**Chosen: Buffalo HD-CD8U3-BA** ([Official specs](https://www.buffalo.jp/product/detail/hd-cd8u3-ba.html))
- USB 3.2 Gen 1 (backwards compatible)
- Mac compatible (officially supported)
- Fanless, shock-absorbing, quiet operation
- Vertical or horizontal placement
- £27 cheaper than WD equivalent

> **Why consumer-grade is fine:** Your server workload is read-heavy and on-demand (stream movie → drive wakes → watch → drive sleeps). NAS-grade drives are overkill for this pattern.

**Connection Note:** Drive uses USB-A cable. Use with Mac Mini's USB-C ports via included cable or adapter. Speed is not a bottleneck (HDD maxes at ~150 MB/s, USB 3.0 supports 625 MB/s).

**Format:** Use APFS or Mac OS Extended (Journaled) - no need for NTFS drivers.

**⚠️ CRITICAL: Check Power Supply at Store**

Before purchasing, verify the AC adapter supports UK voltage:

| On Adapter | Meaning | UK Compatible? |
|------------|---------|----------------|
| **100-240V** | Universal | ✅ Yes |
| **100V** only | Japan only | ❌ Needs transformer |

Ask at store: "このACアダプターは100-240V対応ですか？" (Does this AC adapter support 100-240V?)

---

## Services by Category

### Infrastructure Layer

| Service | Homepage | Purpose | Run Method | RAM (Idle) | RAM (Peak) | Port |
|---------|----------|---------|------------|------------|------------|------|
| [**OrbStack**](https://orbstack.dev/) | [orbstack.dev](https://orbstack.dev/) | Docker engine optimized for Apple Silicon | Native macOS app | 500MB | 1GB | - |
| [**Tailscale**](https://tailscale.com/) | [tailscale.com](https://tailscale.com/) | Mesh VPN for secure remote access | Native macOS app | 50MB | 100MB | - |
| [**Cloudflare Tunnel**](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) | [cloudflare.com](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) | Secure tunnel for Alexa→HA (no public IP) | Docker (cloudflared) | 50MB | 100MB | - |
| [**Homebrew**](https://brew.sh/) | [brew.sh](https://brew.sh/) | Package manager for CLI tools | Native macOS | - | - | - |

### Voice Assistant (Real-Time)

| Service | Homepage | Purpose | Run Method | RAM (Idle) | RAM (Peak) | Port |
|---------|----------|---------|------------|------------|------------|------|
| [**LiveKit Server**](https://livekit.io/) | [livekit.io](https://livekit.io/) | WebRTC server for real-time audio streaming | Docker container | 200MB | 500MB | 7880 |
| [**LiveKit Agents**](https://github.com/livekit/agents) | [GitHub](https://github.com/livekit/agents) | Python framework orchestrating STT→LLM→TTS | Docker container | 300MB | 500MB | - |
| [**Whisper**](https://github.com/openai/whisper) | [GitHub](https://github.com/openai/whisper) | Local speech-to-text (OpenAI model) | Docker container | 500MB | 1.5GB | - |
| [**Kokoro TTS**](https://github.com/remsky/Kokoro-FastAPI) | [GitHub](https://github.com/remsky/Kokoro-FastAPI) | Local text-to-speech (natural voices) | Docker container | 400MB | 800MB | 8880 |
| [**Claude API**](https://www.anthropic.com/api) | [anthropic.com](https://www.anthropic.com/api) | LLM brain for understanding & reasoning | External API | 0MB | 0MB | - |

### Agent Orchestration

| Service | Homepage | Purpose | Run Method | RAM (Idle) | RAM (Peak) | Port |
|---------|----------|---------|------------|------------|------------|------|
| [**Nanobot**](https://github.com/HKUDS/nanobot) | [GitHub](https://github.com/HKUDS/nanobot) | Ultra-lightweight AI agent (~4k lines) | Docker container | 100MB | 300MB | 8100 |
| **Butler API** | Self-built | FastAPI gateway for PWA, voice, and chat (uses Claude API + tools) | Docker container | 50MB | 200MB | 8000 |
| Custom Skills/Tools | Self-built | Skills (markdown) + Tools (Python) for service integrations | Part of Nanobot | Included | Included | - |
| [**APScheduler**](https://apscheduler.readthedocs.io/) | [Docs](https://apscheduler.readthedocs.io/) | Cron-style task scheduling | Part of Agent | Included | Included | - |

> **Note:** The LLM (Claude) runs in the cloud to preserve local RAM. Voice processing (Whisper, Kokoro) runs locally for low latency.

### Media & Entertainment

| Service | Homepage | Purpose | Run Method | RAM (Idle) | RAM (Peak) | Port |
|---------|----------|---------|------------|------------|------------|------|
| [**Jellyfin**](https://jellyfin.org/) | [jellyfin.org](https://jellyfin.org/) | Media streaming (4K HDR, Dolby Atmos) | Docker container | 500MB | 4GB* | 8096 |
| [**Radarr**](https://radarr.video/) | [radarr.video](https://radarr.video/) | Movie automation & management | Docker container | 300MB | 500MB | 7878 |
| [**Sonarr**](https://sonarr.tv/) | [sonarr.tv](https://sonarr.tv/) | TV series automation & management | Docker container | 300MB | 500MB | 8989 |
| [**Bazarr**](https://www.bazarr.media/) | [bazarr.media](https://www.bazarr.media/) | Subtitle automation | Docker container | 200MB | 400MB | 6767 |

> *Jellyfin peaks during 4K transcoding. Direct play uses minimal resources.

### Books & Audio

| Service | Homepage | Purpose | Run Method | RAM (Idle) | RAM (Peak) | Port |
|---------|----------|---------|------------|------------|------------|------|
| [**Calibre-Web**](https://github.com/janeczku/calibre-web) | [GitHub](https://github.com/janeczku/calibre-web) | E-book library & Kindle sync | Docker container | 150MB | 300MB | 8083 |
| [**Audiobookshelf**](https://www.audiobookshelf.org/) | [audiobookshelf.org](https://www.audiobookshelf.org/) | Audiobook streaming & progress sync | Docker container | 200MB | 400MB | 13378 |
| [**Readarr**](https://readarr.com/) | [readarr.com](https://readarr.com/) | Book & audiobook automation | Docker container | 300MB | 500MB | 8787 |

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
| **Voice Assistant** | LiveKit, Whisper, Nanobot, Kokoro | 1.5GB | 3.6GB |
| **Media** | Jellyfin, *arrs, qBit | 1.5GB | 5.9GB |
| **Photos/Files** | Immich, Nextcloud | 1.4GB | 5GB |
| **Books** | Calibre, Audiobookshelf, Readarr | 0.7GB | 1.2GB |
| **Smart Home** | Home Assistant | 0.4GB | 1GB |
| **Notifications** | WhatsApp | 0.1GB | 0.2GB |
| | | | |
| **TOTAL** | | **9.1GB** | **21.9GB** |
| **Available** | 24GB | **14.9GB free** | **2.1GB free** |

### Voice Assistant RAM Breakdown

| Component | Idle | Active | Notes |
|-----------|------|--------|-------|
| LiveKit Server | 200MB | 500MB | WebRTC signaling |
| LiveKit Agent | 300MB | 500MB | Python orchestrator |
| Whisper (small) | 500MB | 1.5GB | Local STT model |
| Kokoro TTS | 400MB | 800MB | Local TTS model |
| Nanobot | 100MB | 300MB | Agent + MCPs |
| **Total Voice** | **1.5GB** | **3.6GB** | |

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

### Technology Choice: Nanobot

After evaluating options, **[Nanobot](https://github.com/HKUDS/nanobot)** is the chosen foundation:

| Factor | Nanobot | OpenClaw | Winner |
|--------|---------|----------|--------|
| Codebase | ~4,000 lines | 430,000+ lines | ✅ Nanobot |
| Auditability | Easy to read entire codebase | Requires significant time | ✅ Nanobot |
| MCP Support | Native | Native | Tie |
| WhatsApp | WebSocket (no public IP) | Yes | ✅ Nanobot |
| Voice | Groq Whisper (free tier) | Various | ✅ Nanobot |
| Scheduling | Cron + intervals | Yes | Tie |
| Customization | Research-friendly, designed for forking | Feature-complete but complex | ✅ Nanobot |
| Security surface | Minimal | Large | ✅ Nanobot |

> *"Nanobot does not aim to replace full-featured frameworks for production, but it is perfect for prototyping, learning, and quickly starting your own experiments with autonomous AI agents."* - [HKUDS](https://github.com/HKUDS/nanobot)

### Design Philosophy

The Butler is built on **Nanobot with custom MCPs**, keeping the codebase minimal and auditable:

| Principle | Implementation |
|-----------|----------------|
| **No external skills** | Skill download capability removed from codebase |
| **Custom MCPs only** | All integrations built and audited by us |
| **Network isolation** | Tailscale only - no public internet exposure |
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
│           │  (Tailscale)       │                   │ + Cloudflare Tunnel    │
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
│  │  │  │  Whisper  │ │  Claude   │ │  Kokoro   │ │ Scheduler │       │ │ │
│  │  │  │  (LOCAL)  │ │   API     │ │   TTS     │ │  (Cron)   │       │ │ │
│  │  │  │   STT     │ │ (Sonnet)  │ │  (LOCAL)  │ │           │       │ │ │
│  │  │  └───────────┘ └───────────┘ └───────────┘ └───────────┘       │ │ │
│  │  │                                                                 │ │ │
│  │  │  ┌───────────────────────────────────────────────────────────┐ │ │ │
│  │  │  │           NANOBOT + CUSTOM MCP SERVERS                    │ │ │ │
│  │  │  │                                                           │ │ │ │
│  │  │  │  ╔═══════════════════════════════════════════════════╗   │ │ │ │
│  │  │  │  ║  READ-ONLY MCPs                                   ║   │ │ │ │
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
│  │  │  │  ║  READ-WRITE MCPs                                  ║   │ │ │ │
│  │  │  │  ║  ┌──────────┐ ┌──────────┐ ┌──────────┐          ║   │ │ │ │
│  │  │  │  ║  │  Home    │ │  Radarr  │ │  Sonarr  │          ║   │ │ │ │
│  │  │  │  ║  │Assistant │ │          │ │          │          ║   │ │ │ │
│  │  │  │  ║  └──────────┘ └──────────┘ └──────────┘          ║   │ │ │ │
│  │  │  │  ║  ┌──────────┐ ┌──────────┐ ┌──────────┐          ║   │ │ │ │
│  │  │  │  ║  │ Readarr  │ │ Jellyfin │ │ WhatsApp │          ║   │ │ │ │
│  │  │  │  ║  │          │ │          │ │(outbound)│          ║   │ │ │ │
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
    summary TEXT,        -- AI-generated summary for context injection
    created_at TIMESTAMPTZ DEFAULT NOW()
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
   - Retrieve recent conversation summaries (last 7 days)
   - Fetch relevant long-term facts based on conversation context

2. **During conversation:**
   - Store each exchange in conversation_history
   - Extract and store new facts ("I love sci-fi" → user_facts)

3. **After conversation:**
   - Generate summary of conversation
   - Update fact confidence scores based on usage

#### Example System Prompt Injection

```
You are a helpful home assistant. You're speaking with Ron.

PERSONALITY:
- Style: friendly and efficient
- Formality: casual
- Verbosity: concise
- Humor: yes

WHAT YOU KNOW ABOUT RON:
- Prefers audiobooks at 1.2x speed
- Favorite author: Brandon Sanderson
- Listens to audiobooks during commute (8am, 6pm)
- Recently asked about the Dune series

RECENT CONTEXT (last 7 days, across all channels):
- Feb 04 [via voice] (Ron): What's the weather tomorrow?
- Feb 04 [via voice] (You): Tomorrow looks sunny, around 18°C.
- Feb 05 [via text] (Ron): Download "The Way of Kings" audiobook
- Feb 05 [via text] (You): Done! Added to your library.
```

#### Memory Tools

Custom Python tools interface directly with PostgreSQL (not Nanobot's built-in `memory.py`):

| Tool | Purpose |
|------|---------|
| `remember_fact` | Store a new fact about the user |
| `recall_facts` | Retrieve relevant facts for context |
| `get_recent_conversations` | Get conversation summaries |
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
│         │ WebRTC (via Tailscale)                            │              │
│         ▼                                                    │              │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                     MAC MINI SERVER                                 │  │
│   │                                                                     │  │
│   │   Audio In ──► Whisper ──► Claude API ──► Nanobot ──► Kokoro ──►   │  │
│   │                (LOCAL)      (CLOUD)        MCPs      (LOCAL)        │  │
│   │                 STT          Brain      Orchestrate    TTS          │  │
│   │                                                                     │  │
│   │   Latency: ~500-800ms round-trip (conversational)                  │  │
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

**Features:**
- Push-to-talk (hold button to speak)
- Tap-to-talk (toggle on/off)
- Voice activity visualization
- Conversation history
- User settings & preferences
- PWA install prompt

### Integrations (Custom Skills & Tools)

> **Note:** These are implemented as Nanobot skills (markdown instructions) or custom Python tools, not MCP servers. See TODO.md for implementation approach decisions.

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
| **Radarr/Sonarr/Readarr** | Add media to library | Read-write |
| **Jellyfin** | Playback control | Read-write |
| **Immich** | Photo search | Read-only |
| **WhatsApp** | Send notifications to users | Write-only (outbound) |

### Example Use Cases

| Command | What Happens |
|---------|--------------|
| *"Turn the heating on 2 days before I get back from Japan"* | Reads calendar → finds return date → schedules HA automation |
| *"Find the new Dune audiobook"* | Readarr search → Prowlarr → qBittorrent → WhatsApp notification when done |
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
                                                                  │   Nanobot     │
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
- Simple commands go direct to HA; complex ones routed to Nanobot

### Security Approach (Nanobot)

Nanobot is already minimal (~4k lines), but we further harden it:

| Nanobot Feature | Our Configuration |
|-----------------|-------------------|
| External skill loading | ❌ Disabled in config |
| Tool directory | ⚠️ Locked to our custom MCPs only |
| Shell execution | ⚠️ Removed or restricted to allowlist |
| File system access | ⚠️ Restricted to specific paths |
| Network access | ⚠️ Tailscale only (no public ports) |
| LLM providers | ✅ Claude API only |
| WhatsApp | ✅ WebSocket mode (no public IP) |
| Telegram | ✅ Voice + text enabled |
| Scheduler | ✅ Cron for automations |
| User allowlist | ✅ Only specified phone numbers |

**Why Nanobot is more secure than OpenClaw:**
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

#### External Drive (8TB) - Buffalo HD-CD8U3-BA

| Property | Value | Notes |
|----------|-------|-------|
| **Type** | Spinning HDD (5400 RPM typical) | Slower random access |
| **Interface** | USB 3.2 Gen 1 (USB 3.0) | Max ~400-500 MB/s real-world |
| **Format** | APFS or Mac OS Extended | Native Mac format |
| **Best For** | Media, photos, backups | Large sequential files |
| **Avoid** | Databases, app data | Poor random I/O performance |
| **Features** | Fanless, quiet, shock-absorbing | Good for home server |

##### ⚠️ Buffalo Drive Considerations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| **Spin-down** | Drive sleeps after inactivity, causes 2-5s delay on wake | Accept delay or schedule periodic activity |
| **Single drive** | No redundancy - if drive fails, data is lost | Cloud backup for irreplaceable data (photos/docs) |
| **USB disconnect** | macOS can unmount on sleep/wake | Enable "Prevent sleep" or use Amphetamine app |
| **Seek times** | Slow for random file access (~10ms vs 0.1ms SSD) | Keep databases on SSD |
| **Power supply** | Verify 100-240V before purchase | Check at store - may need UK plug adapter only |

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
| ├─ Whisper Turbo model | 3GB | 120GB | Speech-to-text |
| └─ Kokoro TTS model | 1GB | 121GB | Text-to-speech |
| **Docker Volumes (configs)** | 5GB | 126GB | Service configurations |
| **Homebrew packages** | 4GB | 130GB | CLI tools |
| **User Applications** | 20GB | 150GB | OrbStack GUI, etc. |
| | | | |
| **Total Used** | **~150GB** | | |
| **Reserved (30%)** | **~150GB** | | macOS health + future growth |
| **Available** | **~200GB** | | Buffer for unexpected needs |

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

### External HDD Budget (8TB)

#### Usable Space Calculation

| Factor | Impact |
|--------|--------|
| Advertised capacity | 8TB (8,000,000,000,000 bytes) |
| Actual formatted (base-2) | **7.27 TB** (7,450 GB) |
| NTFS filesystem overhead | ~1% |
| **Real usable space** | **~7.2 TB** |

#### Space Allocation Plan

| Category | Allocated | % of Total | Contents |
|----------|-----------|------------|----------|
| **Movies** | 3,000 GB | 41% | ~75 4K movies OR ~300 1080p movies |
| **TV Shows** | 2,000 GB | 28% | ~40 4K seasons OR ~200 1080p seasons |
| **Photos** | 1,000 GB | 14% | ~50,000 RAW or ~250,000 JPEG |
| **Audiobooks** | 300 GB | 4% | ~600 audiobooks |
| **eBooks** | 50 GB | <1% | ~10,000 eBooks |
| **Documents** | 200 GB | 3% | Nextcloud files |
| **Downloads Buffer** | 400 GB | 5% | In-progress downloads |
| **Backups** | 200 GB | 3% | Database & config backups |
| **Reserved** | ~50 GB | <1% | Breathing room |
| | | | |
| **Total** | **7,200 GB** | **100%** | |

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

```
/Volumes/HomeServer/                    # 8TB External Drive
│
├── Media/                              # 5TB allocated
│   ├── Movies/                         # Radarr root folder
│   │   ├── 4K/                         # 4K movies (Radarr quality profile)
│   │   └── HD/                         # 1080p movies
│   ├── TV/                             # Sonarr root folder
│   │   ├── 4K/                         # 4K shows
│   │   └── HD/                         # 1080p shows
│   └── Music/                          # Future: Lidarr
│
├── Books/                              # 350GB allocated
│   ├── eBooks/                         # Calibre-Web library
│   │   └── Calibre Library/            # Calibre database + files
│   └── Audiobooks/                     # Audiobookshelf library
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
│   │   └── Books/                      # Readarr picks up from here
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
| **Audiobooks** | Re-download via Readarr (automated) | ❌ No |
| **eBooks** | Re-download via Readarr (automated) | ❌ No |
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
| Audiobooks | Readarr auto-re-downloads | Hours (background) |

**Total downtime:** A few hours to get services running. Library rebuilds in background over days.

#### Local Backup Setup (For Databases & Configs)

Keep a rolling backup ON THE MAC'S INTERNAL SSD (not the external drive).

**Implemented:** `scripts/backup.sh` (daily via launchd), `scripts/restore.sh`, `scripts/14-backup-setup.sh`

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
| 8096 | Jellyfin | LAN + Tailscale |
| 8123 | Home Assistant | LAN + Tailscale |
| 2283 | Immich | LAN + Tailscale |
| 8080 | Nextcloud | LAN + Tailscale |
| 7878 | Radarr | LAN only |
| 8989 | Sonarr | LAN only |
| 8787 | Readarr | LAN only |
| 6767 | Bazarr | LAN only |
| 9696 | Prowlarr | LAN only |
| 8081 | qBittorrent | LAN only |
| 8083 | Calibre-Web | LAN + Tailscale |
| 13378 | Audiobookshelf | LAN + Tailscale |
| 8100 | Butler Agent | LAN only |
| 8200 | Kokoro TTS | LAN only |
| 9000 | Whisper | LAN only |

### Service Communication

```
┌─────────────────────────────────────────────────────────────────────┐
│                     INTERNAL SERVICE MESH                           │
└─────────────────────────────────────────────────────────────────────┘

  Prowlarr ──────┬──────┬──────┬────── (Indexer sync)
                 │      │      │
                 ▼      ▼      ▼
              Radarr  Sonarr  Readarr
                 │      │      │
                 └──────┴──────┘
                        │
                        ▼
                  qBittorrent ──────► /Downloads/Complete/
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
      Jellyfin    Audiobookshelf  Calibre-Web
      (Movies/TV)  (Audiobooks)    (eBooks)

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
- [ ] Install Tailscale
- [ ] Configure external drive mount
- [ ] Create directory structure

### Phase 2: Download Infrastructure (Day 1-2)
- [ ] Deploy qBittorrent
- [ ] Deploy Prowlarr
- [ ] Configure indexers

### Phase 3: Media Stack (Day 2-3)
- [ ] Deploy Jellyfin
- [ ] Deploy Radarr + Sonarr + Bazarr
- [ ] Connect to Prowlarr and qBittorrent
- [ ] Test full download → playback workflow

### Phase 4: Books & Audio (Day 3-4)
- [ ] Deploy Calibre-Web
- [ ] Deploy Audiobookshelf
- [ ] Deploy Readarr
- [ ] Configure Kindle sync

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
- [ ] Deploy Whisper Turbo
- [ ] Deploy Kokoro TTS
- [ ] Build Butler Agent with Claude API
- [ ] Define function schemas for all services
- [ ] Test voice command workflow

### Phase 8: Hardening (Day 7+)
- [ ] Configure automatic backups
- [ ] Set up monitoring/alerts
- [ ] Document credentials securely
- [ ] Test Tailscale remote access

---

## Cost Summary

### Hardware (One-Time) - Japan Shopping List (Tax-Free)

Purchased in Japan with tourist tax-free discount (10% off). Exchange rate: £1 = ¥213

| Item | Store | Japan (税込) | Tax-Free (-10%) | GBP | UK Price |
|------|-------|-------------|-----------------|-----|----------|
| Mac Mini M4 (24GB/512GB) | Yamada Denki | ¥154,800 | ¥139,320 | **£654** | £899 |
| Buffalo HD-CD8U3-BA 8TB | Bic Camera | ¥25,000 | ¥22,500 | **£106** | ~£150* |
| USB cable | Included | - | - | £0 | - |
| **Total Hardware** | | ¥179,800 | ¥161,820 | **£760** | £1,049 |

> **Savings vs UK purchase: ~£289 (28% off!)** 🎉
>
> *Buffalo not commonly sold in UK; WD equivalent price used for comparison
>
> **Remember:**
> - Bring passport for tax-free (免税) purchase
> - Check Buffalo AC adapter is 100-240V (not 100V only)
> - [Bic Camera product page](https://www.biccamera.com/bc/item/7832511/)

### Monthly Running Costs (UK)

| Item | Cost (£) | Notes |
|------|----------|-------|
| [Claude API](https://www.anthropic.com/api) | ~£3.50 | Butler brain (~500 requests/month) |
| Electricity | ~£3.70 | Mac Mini 24/7 (~15W avg × 730hrs × 34p/kWh) |
| [Tailscale](https://tailscale.com/) | £0 | Free tier (up to 100 devices) |
| [AWS Lambda](https://aws.amazon.com/lambda/) (haaska) | £0 | Free tier (1M requests/month) |
| [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/) | £0 | Free tier |
| Voice (Whisper + Kokoro) | £0 | Runs locally on Mac Mini |
| All software | £0 | Open source |
| **Total Monthly (no backup)** | **~£7.21** | |
| | | |
| **Optional Add-ons:** | | |
| [iCloud 2TB](https://www.apple.com/uk/icloud/) | +£6.99 | Photo & document backup (user choice) |
| **Total Monthly (with iCloud)** | **~£14.20** | If user enables cloud backup |

### Subscription Savings (Estimated UK Prices)

| Replaced Service | Monthly Cost (£) | Notes |
|------------------|------------------|-------|
| Netflix Standard | £10.99 | Replaced by Jellyfin |
| Disney+ | £7.99 | Replaced by Jellyfin |
| iCloud 2TB | £6.99 | No longer required (optional user choice) |
| Google One 200GB | £2.49 | Replaced by Nextcloud |
| Kindle Unlimited | £9.99 | Replaced by Calibre-Web |
| Audible | £7.99 | Replaced by Audiobookshelf |
| Smart Home (various) | ~£5.00 | Replaced by haaska (free) |
| **Gross Savings** | **~£51.44/month** | All services replaced |
| Minus server costs | -£7.21 | |
| **Net Savings** | **~£44.23/month** | |

### Break-Even Analysis

| Item | Value |
|------|-------|
| Hardware cost (Japan tax-free) | £760 |
| Monthly net savings | £44.23 |
| **Break-even point** | **~17 months (~1.4 years)** |

> **Note:** Actual savings depend on which subscriptions you currently have. If you only had Netflix + Audible, savings would be lower. The non-financial benefits (privacy, ownership, no ads, no content removal, Alexa voice control) are immediate.
>
> **If you add iCloud backup (£6.99/mo):** Net savings = £37.24/month, break-even = ~20 months

### Total Cost of Ownership (5 Years)

| Scenario | Calculation | Total |
|----------|-------------|-------|
| **Self-hosted (no backup)** | £760 + (£7.21 × 60 months) | **£1,193** |
| **Self-hosted (with iCloud)** | £760 + (£14.20 × 60 months) | **£1,612** |
| **Subscriptions only** | £51.44 × 60 months | **£3,086** |
| **Savings (no backup)** | | **£1,893 saved** |
| **Savings (with iCloud)** | | **£1,474 saved** |

---

## Complete Software Reference

All software used in this project with links to official sources.

### Core Infrastructure

| Software | Homepage | Purpose | License |
|----------|----------|---------|---------|
| [OrbStack](https://orbstack.dev/) | [orbstack.dev](https://orbstack.dev/) | Fast Docker & Linux on macOS (Apple Silicon optimized) | Freemium |
| [Tailscale](https://tailscale.com/) | [tailscale.com](https://tailscale.com/) | Zero-config mesh VPN for secure remote access | Free tier |
| [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) | [cloudflare.com](https://developers.cloudflare.com/cloudflare-one/) | Secure tunnel for Alexa→HA integration (no public IP) | Free tier |
| [Homebrew](https://brew.sh/) | [brew.sh](https://brew.sh/) | Package manager for macOS CLI tools | Open Source |

### Voice & AI

| Software | Homepage | Purpose | License |
|----------|----------|---------|---------|
| [LiveKit](https://livekit.io/) | [livekit.io](https://livekit.io/) | Open-source WebRTC server for real-time audio/video | Apache 2.0 |
| [LiveKit Agents](https://github.com/livekit/agents) | [GitHub](https://github.com/livekit/agents) | Python framework for building voice AI agents | Apache 2.0 |
| [OpenAI Whisper](https://github.com/openai/whisper) | [GitHub](https://github.com/openai/whisper) | Local speech-to-text model | MIT |
| [Kokoro TTS](https://github.com/remsky/Kokoro-FastAPI) | [GitHub](https://github.com/remsky/Kokoro-FastAPI) | High-quality local text-to-speech | Apache 2.0 |
| [Claude API](https://www.anthropic.com/api) | [anthropic.com](https://www.anthropic.com/api) | LLM for understanding, reasoning, function calling | Commercial |
| [Nanobot](https://github.com/HKUDS/nanobot) | [GitHub](https://github.com/HKUDS/nanobot) | Ultra-lightweight AI agent framework (~4k lines) | MIT |

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
| [Calibre-Web](https://github.com/janeczku/calibre-web) | [GitHub](https://github.com/janeczku/calibre-web) | E-book library web interface with Kindle sync | GPL-3.0 |
| [Audiobookshelf](https://www.audiobookshelf.org/) | [audiobookshelf.org](https://www.audiobookshelf.org/) | Self-hosted audiobook streaming with progress sync | GPL-3.0 |
| [Readarr](https://readarr.com/) | [readarr.com](https://readarr.com/) | Book & audiobook collection automation | GPL-3.0 |

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
1. **Tailscale only** - No ports exposed to public internet
2. **Strong passwords** - Use unique passwords for each service
3. **Regular backups** - Automate database and config backups
4. **Update schedule** - Keep containers updated for security patches

---

*Last Updated: 2026-02-05*
