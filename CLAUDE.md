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

> **Example:** We discovered Nanobot uses "skills" not MCP — we updated the plan.
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
- AI voice assistant (Nanobot + Claude API)
- Smart home (Home Assistant + Alexa via haaska)

**Owner:** Ron (GitHub: noble1911)
**Hardware:** Mac Mini M4 (24GB RAM, 512GB SSD) + external USB drive
**Status:** Pre-hardware - Mac Mini not yet purchased/arrived

## Current Progress

> **Tasks are tracked in [GitHub Issues](https://github.com/noble1911/home-server/issues)**

### Development Approach
We're building the software FIRST, then deploying to Mac Mini later:
1. Build PWA (React app) - can develop/test locally
2. Build Nanobot skills & tools (Python) - can develop/test locally
3. Create Docker Compose files - define the infrastructure
4. Build custom Docker images - package our code
5. Create setup scripts - automate deployment

### Blockers
- Mac Mini hardware not yet arrived (but we can build software now!)

---

## Critical: Nanobot Architecture

> ⚠️ **The plan originally said "MCP-native" - this is incorrect.**

**HKUDS/nanobot** (the one we're using) uses a **skills system**, not MCP:

```
Skills (SKILL.md)     →  Markdown files that TEACH the agent how to do things
Tools (Python class)  →  Code that EXECUTES actions (shell, filesystem, web, etc.)
```

### Two Nanobot Projects Exist - We Use HKUDS

| Project | What It Is | Our Choice |
|---------|------------|------------|
| **[HKUDS/nanobot](https://github.com/HKUDS/nanobot)** | Python, ~4k lines, WhatsApp/Telegram built-in | ✅ **Using this** |
| [nanobot-ai/nanobot](https://github.com/nanobot-ai/nanobot) | Go-based MCP host, different project | ❌ Not using |

### What's Built Into HKUDS/nanobot
- ✅ WhatsApp integration (just configure, don't rebuild)
- ✅ Telegram with voice transcription (Groq Whisper)
- ✅ Cron scheduling
- ✅ Basic memory system (`memory.py`)
- ✅ Weather skill (already exists)
- ❌ LiveKit/real-time voice (we need to add this)
- ✅ Groq Whisper STT (cloud API, free tier)

### How to Extend Nanobot

**For simple integrations** → Write a Skill (SKILL.md):
```markdown
---
name: my_skill
description: "What it does"
metadata: {"nanobot":{"requires":{"bins":["curl"]}}}
---
# Instructions for the agent
Use `curl` to call the API...
```

**For critical integrations** → Write a Tool (Python):
```python
class MyTool(Tool):
    name = "my_tool"
    description = "What it does"
    parameters = { ... }  # JSON Schema

    async def execute(self, **kwargs) -> str:
        # Actual implementation
```

---

## Project Structure

```
home-server/
├── CLAUDE.md              # This file - context for Claude
├── README.md              # User-facing quick start
├── HOMESERVER_PLAN.md     # Complete architecture & plan
├── setup.sh               # All-in-one setup (calls scripts/)
├── app/                   # Butler PWA (React + Vite + LiveKit)
├── butler/                # LiveKit agent (voice bridge to Butler API)
│   └── livekit-agent/     # Custom LLM plugin for LiveKit
├── nanobot/               # Nanobot gateway + Butler API (FastAPI)
│   ├── api/               # Butler API (auth, chat, voice, tools)
│   ├── tools/             # Custom Python tools (15+)
│   ├── migrations/        # PostgreSQL schema migrations
│   └── docker-compose.yml # Nanobot + Butler API containers
├── docker/                # Docker Compose stacks
│   ├── books-stack/       # Calibre-Web, Audiobookshelf, Readarr
│   ├── download-stack/    # qBittorrent, Prowlarr
│   ├── media-stack/       # Jellyfin, Radarr, Sonarr, Bazarr
│   ├── messaging-stack/   # WhatsApp gateway
│   ├── photos-files-stack/# Immich, Nextcloud, PostgreSQL
│   ├── smart-home-stack/  # Home Assistant, Cloudflare Tunnel
│   └── voice-stack/       # LiveKit, Kokoro TTS
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
    ├── kindle-email-setup.md
    ├── opds-setup.md
    ├── ebook-reading-guide.md
    └── prowlarr-indexers.md
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
| AI agent | HKUDS/nanobot | Minimal codebase (~4k lines), WhatsApp built-in |
| Agent extensions | Skills + Python Tools | Skills for simple, Tools for critical |
| Memory storage | PostgreSQL (Immich's DB) | Already in stack, has vector extensions |
| Task tracking | GitHub Issues | Avoids merge conflicts with parallel agents |
| Remote access | Cloudflare Tunnel | No port forwarding, works on any device with a browser |
| SSH | Optional | Not everyone runs headless |

## Monthly Costs

| Config | Cost |
|--------|------|
| No backup | ~£7.21 (Claude API + electricity) |
| With iCloud 2TB | ~£14.20 |

## Design Decisions Made (2026-02-05)

### Memory & Personalization - RESOLVED

| Question | Answer |
|----------|--------|
| Does Nanobot have built-in memory? | Yes, basic `memory.py` - we extend it |
| Memory storage? | PostgreSQL (Immich's DB, `butler` schema) |
| How to inject user context? | Load soul config + facts into system prompt |
| Where does soul config live? | PostgreSQL `butler.users` table |

### Remaining Questions

- [ ] How does Nanobot handle multi-user conversations?
- [ ] Can we run multiple Nanobot instances (one per channel)?
- [ ] Best way to share tools between voice agent and text agent?
- [ ] Voice identification vs app-based user identification?

## Notes for Future Sessions

- Ron prefers modular, DRY code - scripts should be reusable
- Keep README minimal - detailed docs go in docs/
- Always commit and push after making changes
- SSH setup is OPTIONAL - some users manage Mac Mini directly
- The Mac Mini hasn't arrived yet - we're in planning/prep phase
- **Memory/personalization is important** - Butler should know users
- **Always check `gh issue list` first** before starting work
- **Claim issues with `gh issue edit --add-assignee @me`** to avoid conflicts
- **Use `Closes #N` in PR body** to auto-close issues on merge
- **Review HOMESERVER_PLAN.md before PR** — update if you learned something new
- **Create issues for discovered work** — don't let insights get lost between sessions
