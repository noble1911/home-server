# Butler API

FastAPI backend for the Butler AI assistant with home server integrations.

## Quick Start

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Edit with your API keys
nano .env

# 3. Start the service
docker compose up -d

# 4. Run database migrations (first time only)
docker exec immich-postgres psql -U postgres -d immich -f /app/migrations/001_butler_schema.sql
docker exec immich-postgres psql -U postgres -d immich -f /app/migrations/003_update_embedding_dimensions.sql

# 5. Check logs
docker logs -f butler-api
```

## Architecture

Butler API connects to multiple services:

| Service | Network | Purpose |
|---------|---------|---------|
| PostgreSQL | photos-files-stack | Memory storage (butler schema) |
| LiveKit | voice-stack | Real-time voice |
| Groq Whisper | Cloud API (free tier) | Speech-to-text |
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
from .base import Tool

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

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `HA_TOKEN` | No | Home Assistant token |
| `WHATSAPP_GATEWAY_URL` | No | WhatsApp gateway for outbound notifications |

## Development

Mount tools as volumes for hot reload:

```bash
docker compose up -d
# Edit tools/memory.py
# Changes are reflected immediately (on next request)
```

## Embedding Model

Butler uses **nomic-embed-text** via a local Ollama instance for semantic search over user facts. The configuration lives in `tools/embeddings.py`:

| Setting | Value | Notes |
|---------|-------|-------|
| Model | `nomic-embed-text` | 768-dim, runs locally via Ollama |
| Dimensions | 768 | Stored in `EMBEDDING_DIM` constant |
| DB column | `VECTOR(768)` | pgvector type in `butler.user_facts` |
| Index | HNSW (cosine) | Approximate nearest-neighbour search |

### Changing the embedding model

1. Update `EMBEDDING_MODEL` and `EMBEDDING_DIM` in `tools/embeddings.py`
2. Write a new migration to `ALTER COLUMN embedding TYPE VECTOR(<new_dim>)` and rebuild the HNSW index (see `003_update_embedding_dimensions.sql` for the pattern)
3. Re-embed existing facts — old vectors will be incompatible with the new dimension

## Database Schema

The butler schema lives in Immich's PostgreSQL:

- `butler.users` - User profiles and preferences
- `butler.user_facts` - Learned facts about users (with optional vector embeddings)
- `butler.conversation_history` - Message history
- `butler.scheduled_tasks` - Reminders and automations

See `migrations/001_butler_schema.sql` for the initial schema and `003_update_embedding_dimensions.sql` for the dimension migration.
