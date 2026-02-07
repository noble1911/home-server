# Step 13: Deploy Nanobot AI Agent

Deploy Nanobot, the AI agent that powers Butler's intelligence.

## Automated

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/13-nanobot.sh | bash
```

**Note:** The script will prompt you for several API keys and configuration values. You can skip optional ones by pressing Enter:

| Prompt | Required? | Where to get it |
|--------|-----------|-----------------|
| **Anthropic API key** | Yes | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) |
| **Groq API key** | Optional (for voice STT) | [console.groq.com/keys](https://console.groq.com/keys) (free tier) |
| **OpenWeatherMap API key** | Optional (for weather) | [openweathermap.org/api](https://openweathermap.org/api) (free tier) |
| **Google OAuth credentials** | Optional (for Calendar/Gmail) | See [Google OAuth Setup](./google-oauth-setup.md) |
| **Cloudflare Tunnel token** | Optional (for Alexa) | Cloudflare Zero Trust > Networks > Tunnels |
| **Admin invite code** | Optional (default: BUTLER-001) | You choose — first user becomes admin |

Security secrets (JWT_SECRET, INTERNAL_API_KEY, LIVEKIT keys) are auto-generated.

## Manual

### 1. Prerequisites

Ensure these are running first:
- **Photos/Files stack** (10-photos-files.sh) - Provides PostgreSQL
- **Smart Home stack** (11-smart-home.sh) - Optional, for Home Assistant
- **Voice stack** (12-voice-stack.sh) - Optional, for voice features

### 2. Configure Environment

```bash
cd nanobot
cp .env.example .env
```

Edit `.env` and add your API keys:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Optional: Home Assistant
HA_TOKEN=your-long-lived-access-token
```

### 3. Run Database Migration

From the `nanobot/` directory, copy the migration file into the container and execute it:

```bash
docker cp migrations/001_butler_schema.sql immich-postgres:/tmp/
docker exec immich-postgres psql -U postgres -d immich -f /tmp/001_butler_schema.sql
```

### 4. Deploy

```bash
cd nanobot
docker compose up -d
```

### 5. Verify

```bash
curl http://localhost:8100/health
```

## Architecture

```
┌──────────────────────┐    ┌──────────────────────────────┐
│      NANOBOT          │    │        BUTLER API             │
│     (Gateway)         │    │        (FastAPI)              │
│      :8100            │    │         :8000                 │
│                       │    │                               │
│  WhatsApp/Telegram    │    │  PWA chat, voice, auth,      │
│  channel interface    │    │  OAuth, tools, scheduling    │
└───────────┬───────────┘    └──────────────┬───────────────┘
            │                               │
            └───────────┬───────────────────┘
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
  ┌────────────┐ ┌────────────┐ ┌────────────┐
  │ PostgreSQL │ │    Home    │ │   Voice    │
  │  (Immich)  │ │ Assistant  │ │   Stack    │
  └────────────┘ └────────────┘ └────────────┘
```

## Service Details

| Component | URL | Purpose |
|-----------|-----|---------|
| Nanobot Gateway | http://localhost:8100 | WhatsApp/Telegram interface |
| Butler API | http://localhost:8000 | PWA, voice, auth, tools |
| Model | claude-sonnet-4 | LLM reasoning |

## Database Schema

Nanobot uses a `butler` schema in Immich's PostgreSQL:

| Table | Purpose |
|-------|---------|
| `butler.users` | User profiles and personality config |
| `butler.user_facts` | Learned facts with semantic embeddings |
| `butler.conversation_history` | Message history per channel |
| `butler.scheduled_tasks` | Reminders and automations |

### Query Examples

```bash
# List users
docker exec immich-postgres psql -U postgres -d immich \
  -c "SELECT * FROM butler.users;"

# View conversation history
docker exec immich-postgres psql -U postgres -d immich \
  -c "SELECT * FROM butler.conversation_history ORDER BY created_at DESC LIMIT 10;"

# Check stored facts
docker exec immich-postgres psql -U postgres -d immich \
  -c "SELECT * FROM butler.user_facts;"
```

## Custom Tools

Nanobot loads custom tools from `/nanobot/tools/`:

### Memory Tools

| Tool | Description |
|------|-------------|
| `RememberFactTool` | Store facts about users with categories and confidence |
| `RecallFactsTool` | Retrieve facts with optional filtering |
| `GetUserTool` | Fetch user profile and personality config |

### Home Assistant Tools

| Tool | Description |
|------|-------------|
| `HomeAssistantTool` | Control devices (turn_on, turn_off, toggle, get_state, call_service) |
| `ListEntitiesByDomainTool` | List entities filtered by domain (light, switch, etc.) |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `JWT_SECRET` | Auto | JWT signing secret (auto-generated) |
| `INTERNAL_API_KEY` | Auto | Internal API key for service-to-service auth (auto-generated) |
| `LIVEKIT_API_KEY` | Auto | LiveKit API key (auto-generated, synced to voice-stack) |
| `LIVEKIT_API_SECRET` | Auto | LiveKit API secret (auto-generated, synced to voice-stack) |
| `GROQ_API_KEY` | No | Groq API key for voice STT |
| `OPENWEATHERMAP_API_KEY` | No | Weather queries |
| `GOOGLE_CLIENT_ID` | No | Google OAuth (Calendar/Gmail) |
| `GOOGLE_CLIENT_SECRET` | No | Google OAuth secret |
| `CLOUDFLARE_TUNNEL_TOKEN` | No | Cloudflare Tunnel for Alexa integration |
| `INVITE_CODES` | No | Admin invite code (default: BUTLER-001) |
| `HA_TOKEN` | No | Home Assistant long-lived access token |
| `DB_USER` | No | PostgreSQL user (default: postgres) |
| `DB_PASSWORD` | No | PostgreSQL password (default: postgres) |
| `RADARR_API_KEY` | No | Auto-synced from `~/.homeserver-credentials` |
| `SONARR_API_KEY` | No | Auto-synced from `~/.homeserver-credentials` |

## Docker Commands

```bash
# View logs
docker logs nanobot -f

# Restart
docker restart nanobot

# Rebuild after code changes
cd nanobot
docker compose build
docker compose up -d

# Enter container
docker exec -it nanobot bash

# Check resource usage
docker stats nanobot
```

## Adding Custom Tools

Create a new file in `nanobot/tools/`:

```python
# nanobot/tools/my_tool.py
from typing import Any

class MyTool:
    name = "my_tool"
    description = "What this tool does"
    parameters = {
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "Parameter description"
            }
        },
        "required": ["param1"]
    }

    async def execute(self, **kwargs) -> str:
        param1 = kwargs.get("param1")
        # Your implementation here
        return f"Result: {param1}"
```

Export in `__init__.py`:

```python
from .my_tool import MyTool
```

Rebuild to load new tools:

```bash
docker compose build && docker compose up -d
```

## Adding Skills

Skills are markdown files that teach Nanobot how to do things.

Create `nanobot/skills/my_skill/SKILL.md`:

```markdown
---
name: my_skill
description: "What this skill does"
metadata: {"nanobot":{"requires":{"bins":["curl"]}}}
---

# Instructions

When the user asks about X, do Y by...
```

## Troubleshooting

### Nanobot not starting

```bash
# Check logs
docker logs nanobot

# Common issues:
# - Missing ANTHROPIC_API_KEY
# - PostgreSQL not accessible
# - Network not found
```

### Database connection failed

```bash
# Verify PostgreSQL is running
docker exec immich-postgres pg_isready -U postgres

# Check network connectivity
docker network inspect photos-files-stack_default
```

### Home Assistant not working

```bash
# Test HA connection
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://homeassistant:8123/api/

# Verify token in .env
grep HA_TOKEN nanobot/.env
```

### Tools not loading

```bash
# Check tool syntax
docker exec nanobot python -c "from tools import *; print('OK')"

# View tool registration
docker logs nanobot | grep -i tool
```

## Network Connections

Nanobot connects to multiple Docker networks:

| Network | Service | Purpose |
|---------|---------|---------|
| `photos-files-stack_default` | immich-postgres | Database storage |
| `smart-home-stack_default` | homeassistant | Smart home control |
| `voice-stack_default` | livekit, kokoro | Voice features |

## Resource Usage

| State | RAM | CPU |
|-------|-----|-----|
| Idle | ~200MB | ~1% |
| Processing | ~500MB | ~20% |

## Security Notes

1. **API keys** - Keep `.env` file secure, never commit to git
2. **Network isolation** - Nanobot only accessible locally (no port forwarding)
3. **Tool permissions** - Tools run with Nanobot's container privileges
4. **Audit logging** - Consider enabling verbose mode for debugging

## What's Next?

With Nanobot running:

1. **Build more tools** (issues #5-#9):
   - Radarr, Sonarr, Readarr, Jellyfin

2. **Add voice API** (issue #30):
   - Endpoints for voice processing

3. **Build LiveKit Agents** (issue #29):
   - Voice orchestration layer

4. **Connect PWA** (issue #31):
   - Enable voice in the app

See [docs/VOICE_ARCHITECTURE.md](VOICE_ARCHITECTURE.md) for the full plan.
