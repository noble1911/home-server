"""PostgreSQL-based memory tools for Butler.

These tools allow the agent to remember and recall facts about users,
enabling personalized interactions across conversations.

Usage:
    The tools are automatically registered with Nanobot when the container starts.
    They connect to Immich's PostgreSQL database using the butler schema.

Example:
    # Create a shared pool and initialize tools
    pool = await DatabasePool.create("postgresql://...")
    remember = RememberFactTool(pool)
    recall = RecallFactsTool(pool)
    get_user = GetUserTool(pool)

    # When shutting down
    await pool.close()
"""

from typing import Any
import os
import asyncpg

from .base import Tool


class DatabasePool:
    """Shared database connection pool manager.

    This class manages a single connection pool that can be shared
    across multiple tools, avoiding the overhead of creating separate
    pools for each tool instance.

    Example:
        pool = await DatabasePool.create()
        try:
            # Use pool with tools
            tool = RememberFactTool(pool)
            await tool.execute(...)
        finally:
            await pool.close()
    """

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    @classmethod
    async def create(
        cls,
        db_url: str | None = None,
        min_size: int = 2,
        max_size: int = 10,
    ) -> "DatabasePool":
        """Create a new database pool.

        Args:
            db_url: PostgreSQL connection URL. Defaults to DATABASE_URL env var.
            min_size: Minimum number of connections to keep open.
            max_size: Maximum number of connections allowed.

        Returns:
            DatabasePool instance ready to use.
        """
        url = db_url or os.environ.get("DATABASE_URL")
        if not url:
            raise ValueError("DATABASE_URL environment variable not set")

        pool = await asyncpg.create_pool(
            url,
            min_size=min_size,
            max_size=max_size,
        )
        return cls(pool)

    @property
    def pool(self) -> asyncpg.Pool:
        """Get the underlying asyncpg pool."""
        return self._pool

    async def close(self) -> None:
        """Close the connection pool.

        Should be called when shutting down to cleanly release connections.
        """
        await self._pool.close()

    async def __aenter__(self) -> "DatabasePool":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()


class RememberFactTool(Tool):
    """Store a fact about a user for future reference."""

    def __init__(self, db_pool: DatabasePool | None = None):
        """Initialize the tool.

        Args:
            db_pool: Shared database pool. If not provided, creates one lazily.
        """
        self._db_pool = db_pool
        self._owned_pool: DatabasePool | None = None  # Pool we created ourselves

    async def _get_pool(self) -> asyncpg.Pool:
        """Get the database connection pool, creating if needed."""
        if self._db_pool:
            return self._db_pool.pool

        # Lazy initialization for backwards compatibility
        if self._owned_pool is None:
            self._owned_pool = await DatabasePool.create()
        return self._owned_pool.pool

    async def close(self) -> None:
        """Close any pool we created ourselves."""
        if self._owned_pool:
            await self._owned_pool.close()
            self._owned_pool = None

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

    def __init__(self, db_pool: DatabasePool | None = None):
        """Initialize the tool.

        Args:
            db_pool: Shared database pool. If not provided, creates one lazily.
        """
        self._db_pool = db_pool
        self._owned_pool: DatabasePool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        """Get the database connection pool, creating if needed."""
        if self._db_pool:
            return self._db_pool.pool

        if self._owned_pool is None:
            self._owned_pool = await DatabasePool.create()
        return self._owned_pool.pool

    async def close(self) -> None:
        """Close any pool we created ourselves."""
        if self._owned_pool:
            await self._owned_pool.close()
            self._owned_pool = None

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

    def __init__(self, db_pool: DatabasePool | None = None):
        """Initialize the tool.

        Args:
            db_pool: Shared database pool. If not provided, creates one lazily.
        """
        self._db_pool = db_pool
        self._owned_pool: DatabasePool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        """Get the database connection pool, creating if needed."""
        if self._db_pool:
            return self._db_pool.pool

        if self._owned_pool is None:
            self._owned_pool = await DatabasePool.create()
        return self._owned_pool.pool

    async def close(self) -> None:
        """Close any pool we created ourselves."""
        if self._owned_pool:
            await self._owned_pool.close()
            self._owned_pool = None

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

        # asyncpg automatically deserializes JSONB to dict
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
