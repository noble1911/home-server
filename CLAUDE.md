# Claude Context File

> This file helps Claude understand the project and pick up where we left off.
> **Multiple Claude agents work on this project in parallel.**

## ⚡ START HERE: Task Workflow

### When Starting a New Session

```bash
# 1. Check for available tasks
gh issue list

# 2. Claim an issue before starting work
gh issue edit <number> --add-assignee @me

# 3. Create a branch for your work
git checkout -b ron875/issue-<number>-short-description
```

### When Completing a Task

**Before creating a PR, always:**

1. **Review HOMESERVER_PLAN.md** — Does anything need updating based on what you learned?
   - Incorrect assumptions? Fix them.
   - New decisions made? Document them.
   - Architecture changed? Update the diagrams/tables.

2. **Update if needed** — Keep the plan accurate for future agents.

3. **Create the PR:**
```bash
# Reference the issue in PR body (auto-closes on merge)
gh pr create --title "Build Home Assistant Tool" --body "Closes #4"
```

> **Example:** We decided to use PostgreSQL directly instead of memory.py — we updated the issue.

### When You Discover Undocumented Work

During code review, exploration, or implementation, you may discover:
- **Missing features** that aren't tracked (e.g., "vector search exists in schema but no tool uses it")
- **Code quality issues** worth addressing later (e.g., "connection pools should be shared")
- **Architectural decisions** that need to be made (e.g., "which embedding model to use?")
- **Documentation gaps** where the plan doesn't match reality

**Create GitHub issues to track these discoveries:**

```bash
# Create a new issue with full context
gh issue create --title "Short descriptive title" --body "## Task
Description of what needs to be done.

## Context
Why this matters, what you discovered.

## Acceptance Criteria
- [ ] Specific measurable outcomes"
```

**Why this matters:**
- Future agents can pick up the work
- Nothing gets lost between sessions
- Avoids duplicate discovery effort
- Builds a clear backlog of improvements

> **Example:** During code review, we found memory tools don't use vector search despite the schema supporting it → Created Issue #25 to track implementing semantic search.

### Quick Commands
```bash
gh issue list                              # See all open issues
gh issue list --assignee @me               # See your assigned issues
gh issue view <number>                     # Read issue details
gh issue edit <number> --add-assignee @me  # Claim an issue
```

---

## Project Overview

**Goal:** Self-hosted home server on Mac Mini M4 with:
- Media streaming (Jellyfin, *arr stack)
- Photo management (Immich)
- File sync (Nextcloud)
- AI voice assistant (Butler API + Claude API)
- Smart home (Home Assistant + Alexa via haaska)

**Owner:** Ron (GitHub: noble1911)
**Hardware:** Mac Mini M4 (24GB RAM, 512GB SSD) + external USB drive
**Status:** Live and running — all stacks deployed, actively maintained
**SSH Access:** `ssh 192.168.1.117`

## Current Progress

> **Tasks are tracked in [GitHub Issues](https://github.com/noble1911/home-server/issues)**

### Server Status
The Mac Mini is set up and all Docker stacks are deployed via OrbStack. Active work is now focused on bug fixes, new Butler tools, and UI improvements.

### Deployed Stacks
| Stack | Services | Status |
|-------|----------|--------|
| **media-stack** | Radarr, Sonarr, Bazarr, Seerr | Running |
| **download-stack** | qBittorrent, Prowlarr | Running |
| **books-stack** | Audiobookshelf, LazyLibrarian | Running |
| **photos-files-stack** | Immich, PostgreSQL, Redis, Nextcloud | Running |
| **smart-home-stack** | Home Assistant, Cloudflare Tunnel | Running |
| **voice-stack** | LiveKit, Kokoro TTS, LiveKit Agent | Running |
| **messaging-stack** | WhatsApp Gateway | Running |

### Native Services (not Docker)
| Service | Description | Status |
|---------|-------------|--------|
| **Jellyfin** | Media streaming — native `/Applications/Jellyfin.app`, 10.11.11 arm64 as of 2026-09-06 (uses VideoToolbox HW transcode; Docker container retired 2026-05-25). Upgrade = swap the app bundle from repo.jellyfin.org macOS arm64 dmg; backups in `/Volumes/HomeServer/Backups/jellyfin/`. Port 8096; Butler reaches it via `host.docker.internal:8096`. | Running |
| **wire-pod** | Vector robot server (WirePod v1.2.13 macOS app, `/Applications/WirePod.app`) | Not running (since at least 2026-09-06; vector-llm is paused too) |

### Co-hosted Projects (shared Mac Mini)

The Mac Mini runs more than just home-server. The **deployment registry** (`registry/`)
is the single source of truth for *every* project sharing the box — host-port map,
shared-service contracts (butler-api, Kokoro, Postgres, Ollama, LiveKit), and Cloudflare
routes. **Read `registry/REGISTRY.md` and `registry/services.yaml` before binding a new
port or adding a service**, and run `registry/doctor.sh` to check for drift against live
`docker ps`.

| Project | Server path | What it is | Status |
|---------|-------------|------------|--------|
| **esp-gateway** (claude-esp) | `~/esp-gateway` | ESP32 AMOLED voice device bridge (device ↔ Groq STT ↔ butler ↔ Kokoro), port 8770 | Running |
| **games site** | `~/home-server/games` | `games-gateway` (Caddy): https://games.noblehaus.uk/ — a hub page and every game below under its own path, LAN port 3010. See `docs/17-games.md` | Running |
| **dont-lie** | `~/dont-lie` | "Word Poker" ("Don't Lie") web game — Expo/React-Native app served via nginx, port 3001 (`dont-lie-app`); at games.noblehaus.uk/dont-lie/ | Running |
| **gunpey** | `~/gunpey` | Gunpey 99 — Node multiplayer server + game in a container, port 3003 (`gunpey`); at games.noblehaus.uk/gunpey/ | Running |
| **super-skidmarks** | `~/super-skidmarks` | Super Skidmarks web remake — game + WebSocket relay in one container, port 3002 (`super-skidmarks`); at games.noblehaus.uk/skidmarks/ | Running |
| **modern-combat** | `~/modern-combat` | Modern Combat — Close Combat-style tactics; Node game server + multiplayer relay in one container, port 3004 (`modern-combat`); at games.noblehaus.uk/modern-combat/ | Running |
| **tycoon-town** | `~/tycoon-town` | Tycoon Town — property-trading game; Node server + online multiplayer relay in one container, port 3005 (`tycoon-town`); at games.noblehaus.uk/tycoon-town/ | Running |
| **froths-party** | `~/froths-party` | Froths Party — Jackbox-style party games for phones (Node + Socket.IO), port 3006 (`froths-party`); at games.noblehaus.uk/froths/ | Running |
| **vector-llm** | `~/vector-llm` | Always-on-mic LLM brain for the Anki Vector robot (host Python process; its compose provides the shared `ollama` container) | Paused (2026-05-25) |
| **wire-pod-backup** | `~/wire-pod-backup` | Backup/escrow data for wire-pod (Anki Vector auth) | Not a service |

### Butler API (~4k LOC, FastAPI)
- **25+ custom Python tools** — media, smart home, memory, scheduling, email, calendar, etc.
- **10 database migrations** — PostgreSQL with pgvector (768-dim nomic-embed-text embeddings)
- **LiveKit voice agent** — STT → Claude → Kokoro TTS pipeline
- **2-phase tool routing** — reduces API costs 80-95% by routing to relevant tools only

---

## Project Structure

```
home-server/
├── CLAUDE.md              # This file - context for Claude
├── README.md              # User-facing quick start
├── HOMESERVER_PLAN.md     # Complete architecture & plan
├── setup.sh               # All-in-one setup (calls scripts/)
├── .github/workflows/     # CI/CD (build-and-push, CI)
├── app/                   # Butler PWA (React + Vite + LiveKit)
│   └── android/           # Android app: Capacitor shell + native notifications (docs/18-android-app.md)
├── butler/                # Butler API (FastAPI) + LiveKit agent
│   ├── api/               # Auth, chat, voice, tools routes
│   ├── tools/             # Custom Python tools (25+)
│   ├── migrations/        # PostgreSQL schema migrations
│   ├── livekit-agent/     # LiveKit Agents worker (STT → LLM → TTS)
│   └── docker-compose.yml # Butler API container
├── docker/                # Docker Compose stacks
│   ├── books-stack/       # Audiobookshelf, LazyLibrarian
│   ├── download-stack/    # qBittorrent, Prowlarr
│   ├── media-stack/       # Radarr, Sonarr, Bazarr, Seerr (Jellyfin = native app, see above)
│   ├── messaging-stack/   # WhatsApp gateway
│   ├── photos-files-stack/# Immich, Nextcloud, PostgreSQL
│   ├── smart-home-stack/  # Home Assistant, Cloudflare Tunnel
│   └── voice-stack/       # LiveKit, Kokoro TTS
│   # wire-pod runs natively via /Applications/WirePod.app (not Docker)
├── registry/              # Deployment registry — source of truth for ALL projects on the Mac Mini
│   ├── REGISTRY.md        #   human-readable: projects, shared services, tunnel routes
│   ├── services.yaml      #   machine-readable host-port map
│   └── doctor.sh          #   drift check: registry vs live `docker ps`
├── scripts/               # Individual setup scripts (01-15)
│   ├── 01-homebrew.sh
│   ├── 03-power-settings.sh
│   ├── ...
│   ├── 15-alexa-haaska.sh
│   ├── backup.sh          # Daily backup (via launchd)
│   ├── restore.sh         # Restore from backup
│   ├── change-drive.sh    # Migrate to a different external drive
│   └── lib/               # Shared helper functions
└── docs/                  # Manual instructions for each step
    ├── 01-homebrew.md ... 15-alexa-haaska.md
    ├── VOICE_ARCHITECTURE.md
    ├── google-oauth-setup.md
    ├── kindle-email-setup.md   # Send to Kindle via Butler (#213)
    ├── 18-android-app.md       # Android app: install, notifications, builds, signing key (#214)
    ├── ebook-reading-guide.md
    └── prowlarr-indexers.md
```

## Conventions

### Scripts
- Numbered prefix: `01-`, `02-`, etc. for ordering
- Each script is standalone (can run individually)
- `setup.sh` orchestrates: curls scripts 01-06 (self-contained), then clones repo to `~/home-server` and runs 07+ locally (they need sibling files like `docker/`, `lib/`)
- Scripts output colored status: `==>` blue, `✓` green, `⚠` yellow
- Data directory: `/Volumes/HomeServer` (external drive) or `~/HomeServer` (`--skip-drive`)

### Documentation
- Each script has matching doc: `scripts/01-foo.sh` ↔ `docs/01-foo.md`
- Docs have "Automated" section (curl command) + "Manual" section
- Docs link to next step at bottom

### Git
- Repo: github.com/noble1911/home-server
- SSH alias: `github.com-noble1911` (uses ~/.ssh/id_ed25519_noble1911)
- Commit style: imperative mood, brief description

## Key Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Alexa integration | haaska + AWS Lambda | Free vs £5/mo HA Cloud |
| Cloud backup | Optional (user choice) | Cost reduction, user accepts risk |
| Docker runtime | OrbStack | Optimized for Apple Silicon |
| AI backend | Butler API (FastAPI) | Custom Python tools, Claude API direct |
| Memory storage | PostgreSQL (Immich's DB) | Already in stack, has pgvector |
| Embeddings | nomic-embed-text (768-dim) | Local, fast, good quality |
| Task tracking | GitHub Issues | Avoids merge conflicts with parallel agents |
| Remote access | Cloudflare Tunnel | No port forwarding, works on any device |
| SSH | Available at 192.168.1.117 | Local network access for management |
| Book management | BookTool (Open Library + Prowlarr) | Replaced Readarr — simpler, more reliable |
| Tool routing | 2-phase (categorise → route) | 80-95% API cost reduction |
| Chat model | Admin picks in Settings (Opus 5.5 / Sonnet 5.5), stored in `butler.app_settings`; else `ANTHROPIC_MODEL`. 5.x models opt in to server-side refusal fallback | Cost/quality dial without redeploys; chosen over running Butler on headless Claude Code (latency, shared subscription limits, account terms) (#215) |
| Android app | Capacitor shell loading the live site; notifications over Butler's own WebSocket (no Firebase) | One UI codebase, web deploys update the app; no Google account needed. APK built on demand (Actions → Build Android app) (#214) |
| Side-effecting actions (email send, calendar edits) | Tap-to-approve drafts (`butler/api/approvals.py`) | The model can draft but never execute; the app's Approve button calls the API directly (#212) |

## Monthly Costs

| Config | Cost |
|--------|------|
| No backup | ~£7.21 (Claude API + electricity) |
| With iCloud 2TB | ~£14.20 |

## Design Decisions Made

### Memory & Personalization - IMPLEMENTED

| Question | Answer |
|----------|--------|
| Does Butler have built-in memory? | Yes, `memory.py` with pgvector semantic search |
| Memory storage? | PostgreSQL (Immich's DB, `butler` schema) |
| Embedding model? | nomic-embed-text, 768-dim, runs locally |
| How to inject user context? | Load soul config + facts into system prompt |
| Where does soul config live? | PostgreSQL `butler.users` table |

### Remaining Questions

- [ ] Voice identification vs app-based user identification?

## Notes for Future Sessions

- Ron prefers modular, DRY code - scripts should be reusable
- Keep README minimal - detailed docs go in docs/
- Always commit and push after making changes
- **Server is live** at `192.168.1.117` — SSH available for remote management
- **Memory/personalization is important** - Butler should know users
- **Always check `gh issue list` first** before starting work
- **Claim issues with `gh issue edit --add-assignee @me`** to avoid conflicts
- **Use `Closes #N` in PR body** to auto-close issues on merge
- **Review HOMESERVER_PLAN.md before PR** — update if you learned something new
- **Create issues for discovered work** — don't let insights get lost between sessions
- **BookTool replaced Readarr** — uses Open Library for search, Prowlarr + qBit for downloads
- **CI/CD exists** — `.github/workflows/` has build-and-push and CI pipelines
- **`registry/` is the source of truth for the shared box** — every project on the Mac Mini, its host ports, shared-service contracts, and Cloudflare routes. Update `REGISTRY.md` + `services.yaml` and run `registry/doctor.sh` when you add/move/remove a service. Co-hosted projects: esp-gateway (:8770), the games site (games-gateway :3010 → dont-lie :3001, super-skidmarks :3002, gunpey :3003, modern-combat :3004, tycoon-town :3005, froths-party :3006; `docs/17-games.md`), vector-llm (paused)
