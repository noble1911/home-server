"""PostgreSQL-based memory tools for Butler.

These tools allow the agent to remember and recall facts about users,
enabling personalized interactions across conversations.

Usage:
    The tools are automatically registered with Nanobot when the container starts.
    They connect to Immich's PostgreSQL database using the butler schema.
"""

from typing import Any
import os
import asyncpg

# Note: In production, import from nanobot.agent.tools
# For now, we define a compatible base class
class Tool:
    """Base class for Nanobot tools (compatible interface)."""

    @property
    def name(self) -> str:
        raise NotImplementedError

    @property
    def description(self) -> str:
        raise NotImplementedError

    @property
    def parameters(self) -> dict[str, Any]:
        raise NotImplementedError

    async def execute(self, **kwargs: Any) -> str:
        raise NotImplementedError

    def to_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function schema format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }


class RememberFactTool(Tool):
    """Store a fact about a user for future reference."""

    def __init__(self, db_url: str | None = None):
        self.db_url = db_url or os.environ.get("DATABASE_URL")
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.db_url)
        return self._pool

    @property
    def name(self) -> str:
        return "remember_fact"

    @property
    def description(self) -> str:
        return (
            "Store a fact about the user for future reference. "
            "Use this to remember preferences, important dates, relationships, "
            "or any information that should persist across conversations."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "User identifier (phone number, telegram id, etc.)"
                },
                "fact": {
                    "type": "string",
                    "description": "The fact to remember (e.g., 'Prefers to be called Bob')"
                },
                "category": {
                    "type": "string",
                    "description": "Category: preference, schedule, relationship, work, health, or other",
                    "enum": ["preference", "schedule", "relationship", "work", "health", "other"]
                },
                "confidence": {
                    "type": "number",
                    "description": "How confident are we? 1.0 = explicit statement, 0.5 = inferred",
                    "minimum": 0.0,
                    "maximum": 1.0
                }
            },
            "required": ["user_id", "fact"]
        }

    async def execute(self, **kwargs: Any) -> str:
        user_id = kwargs["user_id"]
        fact = kwargs["fact"]
        category = kwargs.get("category", "other")
        confidence = kwargs.get("confidence", 1.0)

        pool = await self._get_pool()

        # Ensure user exists
        await pool.execute(
            """
            INSERT INTO butler.users (id, name)
            VALUES ($1, $1)
            ON CONFLICT (id) DO NOTHING
            """,
            user_id
        )

        # Store the fact
        await pool.execute(
            """
            INSERT INTO butler.user_facts (user_id, fact, category, confidence, source)
            VALUES ($1, $2, $3, $4, 'conversation')
            """,
            user_id, fact, category, confidence
        )

        return f"Remembered: {fact}"


class RecallFactsTool(Tool):
    """Recall stored facts about a user."""

    def __init__(self, db_url: str | None = None):
        self.db_url = db_url or os.environ.get("DATABASE_URL")
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.db_url)
        return self._pool

    @property
    def name(self) -> str:
        return "recall_facts"

    @property
    def description(self) -> str:
        return (
            "Recall stored facts about a user. "
            "Use this at the start of conversations to personalize responses, "
            "or when you need to reference something you learned before."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "User identifier"
                },
                "category": {
                    "type": "string",
                    "description": "Optional: filter by category",
                    "enum": ["preference", "schedule", "relationship", "work", "health", "other"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of facts to return (default: 20)",
                    "minimum": 1,
                    "maximum": 100
                }
            },
            "required": ["user_id"]
        }

    async def execute(self, **kwargs: Any) -> str:
        user_id = kwargs["user_id"]
        category = kwargs.get("category")
        limit = kwargs.get("limit", 20)

        pool = await self._get_pool()

        if category:
            rows = await pool.fetch(
                """
                SELECT fact, category, confidence, created_at
                FROM butler.user_facts
                WHERE user_id = $1 AND category = $2
                AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY confidence DESC, created_at DESC
                LIMIT $3
                """,
                user_id, category, limit
            )
        else:
            rows = await pool.fetch(
                """
                SELECT fact, category, confidence, created_at
                FROM butler.user_facts
                WHERE user_id = $1
                AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY confidence DESC, created_at DESC
                LIMIT $2
                """,
                user_id, limit
            )

        if not rows:
            return f"No facts stored for user {user_id}."

        facts_by_category: dict[str, list[str]] = {}
        for row in rows:
            cat = row["category"] or "other"
            if cat not in facts_by_category:
                facts_by_category[cat] = []
            facts_by_category[cat].append(row["fact"])

        lines = [f"Known facts about {user_id}:"]
        for cat, facts in facts_by_category.items():
            lines.append(f"\n{cat.title()}:")
            for fact in facts:
                lines.append(f"  - {fact}")

        return "\n".join(lines)


class GetUserTool(Tool):
    """Get user profile including soul/personality configuration."""

    def __init__(self, db_url: str | None = None):
        self.db_url = db_url or os.environ.get("DATABASE_URL")
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.db_url)
        return self._pool

    @property
    def name(self) -> str:
        return "get_user"

    @property
    def description(self) -> str:
        return (
            "Get the user's profile including their name and personality preferences. "
            "The 'soul' field contains tone, verbosity, and other customization settings."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "User identifier"
                }
            },
            "required": ["user_id"]
        }

    async def execute(self, **kwargs: Any) -> str:
        user_id = kwargs["user_id"]

        pool = await self._get_pool()

        row = await pool.fetchrow(
            """
            SELECT id, name, soul, created_at
            FROM butler.users
            WHERE id = $1
            """,
            user_id
        )

        if not row:
            return f"User {user_id} not found. They may be new."

        import json
        soul = row["soul"] or {}

        lines = [
            f"User: {row['name']}",
            f"ID: {row['id']}",
            f"Member since: {row['created_at'].strftime('%Y-%m-%d')}",
        ]

        if soul:
            lines.append("Preferences:")
            for key, value in soul.items():
                lines.append(f"  - {key}: {value}")

        return "\n".join(lines)
