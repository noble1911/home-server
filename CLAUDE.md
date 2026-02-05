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

### Completed
- [x] Master plan document (HOMESERVER_PLAN.md)
- [x] Cost optimization: removed iCloud (optional) and HA Cloud (replaced with free haaska)
- [x] Setup scripts for initial Mac Mini configuration
- [x] Modular docs structure (scripts/ + docs/)

### In Progress
- [ ] Waiting for Mac Mini hardware

### Next Steps (when hardware arrives)
1. Run `setup.sh` on Mac Mini
2. Create step 5: OrbStack installation
3. Create step 6+: Docker containers for each service

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

## Notes for Future Sessions

- Ron prefers modular, DRY code - scripts should be reusable
- Keep README minimal - detailed docs go in docs/
- Always commit and push after making changes
- SSH setup is OPTIONAL - some users manage Mac Mini directly
- The Mac Mini hasn't arrived yet - we're in planning/prep phase
