# Claude Context File

> This file helps Claude understand the project and pick up where we left off.

## Project Overview

**Goal:** Self-hosted home server on Mac Mini M4 with:
- Media streaming (Jellyfin, *arr stack)
- Photo management (Immich)
- File sync (Nextcloud)
- AI voice assistant (Nanobot + Claude API)
- Smart home (Home Assistant + Alexa via haaska)

**Owner:** Ron (GitHub: noble1911)
**Hardware:** Mac Mini M4 (24GB RAM, 512GB SSD) + 8TB external drive
**Status:** Pre-hardware - Mac Mini not yet purchased/arrived

## Current Progress

> **IMPORTANT: See [TODO.md](TODO.md) for what to work on next**
>
> TODO.md is gitignored (local only) - it tracks our development work.

### Development Approach
We're building the software FIRST, then deploying to Mac Mini later:
1. Build PWA (React app) - can develop/test locally
2. Build MCP servers (Python) - can develop/test locally
3. Create Docker Compose files - define the infrastructure
4. Build custom Docker images - package our code
5. Create setup scripts - automate deployment

### Blockers
- Mac Mini hardware not yet arrived (but we can build software now!)

## Project Structure

```
home-server/
├── CLAUDE.md              # This file - context for Claude
├── README.md              # User-facing quick start
├── HOMESERVER_PLAN.md     # Complete architecture & plan
├── setup.sh               # All-in-one setup (calls scripts/)
├── scripts/               # Individual setup scripts
│   ├── 01-homebrew.sh
│   ├── 02-tailscale.sh
│   ├── 03-power-settings.sh
│   └── 04-ssh.sh
└── docs/                  # Manual instructions for each step
    ├── 01-homebrew.md
    ├── 02-tailscale.md
    ├── 03-power-settings.md
    └── 04-ssh.md
```

## Conventions

### Scripts
- Numbered prefix: `01-`, `02-`, etc. for ordering
- Each script is standalone (can run individually)
- `setup.sh` orchestrates by curling individual scripts
- Scripts output colored status: `==>` blue, `✓` green, `⚠` yellow

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
| AI agent | Nanobot | Minimal codebase (~4k lines), auditable |
| Remote access | Tailscale | No port forwarding, works everywhere |
| SSH | Optional | Not everyone runs headless |

## Monthly Costs

| Config | Cost |
|--------|------|
| No backup | ~£7.21 (Claude API + electricity) |
| With iCloud 2TB | ~£14.20 |

## Commands I Use Often

```bash
# Push to GitHub
git add -A && git commit -m "message" && git push

# Test a script locally
bash scripts/01-homebrew.sh

# Check what's in the repo
ls -la && git status
```

## Open Design Questions

### AI Butler Memory & Personalization
Need to design and implement:

1. **User Memory** - Remember facts about each user
   - Names, preferences, routines
   - Past requests and outcomes
   - "Ron prefers audiobooks at 1.2x speed"

2. **Multi-User Support** - Already in plan, but needs:
   - User identification (JWT token from app)
   - Per-user conversation history
   - Per-user preferences

3. **Soul/Personality per User** - Custom behavior settings
   - Formality level (casual vs professional)
   - Verbosity (brief vs detailed)
   - Humor, tone, interaction style
   - Custom instructions ("always suggest audiobooks")

4. **Memory Storage Options**
   - SQLite (simple, local)
   - PostgreSQL (if we want Immich's DB)
   - Redis (fast, but volatile)
   - JSON files (simplest, but doesn't scale)

### Questions to Resolve
- Does Nanobot have built-in memory/persistence?
- How to inject user context into Claude system prompt?
- Where does "soul" config live? (JSON file? DB?)
- Voice identification vs app-based user identification?

## Notes for Future Sessions

- Ron prefers modular, DRY code - scripts should be reusable
- Keep README minimal - detailed docs go in docs/
- Always commit and push after making changes
- SSH setup is OPTIONAL - some users manage Mac Mini directly
- The Mac Mini hasn't arrived yet - we're in planning/prep phase
- **Memory/personalization is important** - Butler should know users
