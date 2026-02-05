# Claude Context File

> This file helps Claude understand the project and pick up where we left off.
> **Multiple Claude agents work on this project in parallel** - check TODO.md before starting work.

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
> TODO.md is gitignored (local only) - it tracks our development work and task assignments.
> **Always check TODO.md before starting work** to avoid duplicating effort.

### Development Approach
We're building the software FIRST, then deploying to Mac Mini later:
1. Build PWA (React app) - can develop/test locally
2. Build Nanobot skills & tools (Python) - can develop/test locally
3. Create Docker Compose files - define the infrastructure
4. Build custom Docker images - package our code
5. Create setup scripts - automate deployment

### Blockers
- Mac Mini hardware not yet arrived (but we can build software now!)

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
- ❌ Local Whisper STT (uses Groq API, we want local)

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

## Project Structure

```
home-server/
├── CLAUDE.md              # This file - context for Claude
├── README.md              # User-facing quick start
├── HOMESERVER_PLAN.md     # Complete architecture & plan
├── TODO.md                # Task tracking (gitignored, local only)
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
| AI agent | HKUDS/nanobot | Minimal codebase (~4k lines), WhatsApp built-in |
| Agent extensions | Skills + Python Tools | Skills for simple, Tools for critical |
| Memory storage | PostgreSQL (Immich's DB) | Already in stack, has vector extensions |
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
- **Check TODO.md first** - other agents may be working on related tasks
- **Update TODO.md** when you start/finish work to avoid conflicts
