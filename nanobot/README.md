# Nanobot - Butler AI Agent

Custom [HKUDS/nanobot](https://github.com/HKUDS/nanobot) deployment with home server integrations.

## Quick Start

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Edit with your API keys
nano .env

# 3. Start the service
docker compose up -d

# 4. Run database migration (first time only)
docker exec immich-postgres psql -U postgres -d immich -f /app/migrations/001_butler_schema.sql

# 5. Check logs
docker logs -f nanobot
```

## Architecture

Nanobot connects to multiple services:

| Service | Network | Purpose |
|---------|---------|---------|
| PostgreSQL | photos-files-stack | Memory storage (butler schema) |
| LiveKit | voice-stack | Real-time voice |
| Whisper | voice-stack | Speech-to-text |
| Kokoro | voice-stack | Text-to-speech |
| Home Assistant | smart-home-stack | Smart home control |

## Custom Tools

Located in `tools/`:

| Tool | Description |
|------|-------------|
| `remember_fact` | Store facts about users |
| `recall_facts` | Retrieve stored facts |
| `get_user` | Get user profile and preferences |

### Adding a New Tool

```python
# tools/my_tool.py
from .memory import Tool  # Base class

class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "What the tool does"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "..."}
            },
            "required": ["param1"]
        }

    async def execute(self, **kwargs) -> str:
        # Implementation
        return "Result"
```

## Custom Skills

Located in `skills/`. Each skill is a directory with a `SKILL.md`:

```markdown
---
name: my_skill
description: "What it does"
metadata: {"nanobot": {"emoji": "...", "requires": {"bins": ["curl"]}}}
---

# My Skill

Instructions for the agent...
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `HA_TOKEN` | No | Home Assistant token |
| `TELEGRAM_ENABLED` | No | Enable Telegram |
| `TELEGRAM_TOKEN` | No | Telegram bot token |
| `WHATSAPP_ENABLED` | No | Enable WhatsApp |

## Development

Mount tools/skills as volumes for hot reload:

```bash
docker compose up -d
# Edit tools/memory.py
# Changes are reflected immediately (on next request)
```

## Database Schema

The butler schema lives in Immich's PostgreSQL:

- `butler.users` - User profiles and preferences
- `butler.user_facts` - Learned facts about users
- `butler.conversation_history` - Message history
- `butler.scheduled_tasks` - Reminders and automations

See `migrations/001_butler_schema.sql` for details.
