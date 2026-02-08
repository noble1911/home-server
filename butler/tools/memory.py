"""PostgreSQL-based memory tools for Butler.

These tools allow the agent to remember and recall facts about users,
enabling personalized interactions across conversations.

Usage:
    The tools are automatically used by Butler API the container starts.
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

from __future__ import annotations

from typing import Any
import json
import os
import asyncpg

from .base import Tool
from .embeddings import EMBEDDING_DIM, EmbeddingService


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


class DatabaseTool(Tool):
    """Base class for tools that need a PostgreSQL connection pool.

    Handles shared vs owned pool lifecycle. If a shared DatabasePool is
    provided, it is used directly and never closed by this tool. If no
    pool is provided, one is created lazily on first use and closed when
    close() is called.
    """

    def __init__(self, db_pool: DatabasePool | None = None):
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


class RememberFactTool(DatabaseTool):
    """Store a fact about a user for future reference."""

    def __init__(
        self,
        db_pool: DatabasePool | None = None,
        embedding_service: EmbeddingService | None = None,
    ):
        super().__init__(db_pool)
        self._embedding_service = embedding_service

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

        # Generate embedding if service available
        embedding = None
        if self._embedding_service:
            embedding = await self._embedding_service.embed(fact)
            if embedding is not None and len(embedding) != EMBEDDING_DIM:
                embedding = None  # dimension mismatch — skip vector storage

        if embedding is not None:
            # Store fact with vector embedding (cast text → vector for pgvector)
            vector_str = "[" + ",".join(str(v) for v in embedding) + "]"
            await pool.execute(
                """
                INSERT INTO butler.user_facts
                    (user_id, fact, category, confidence, source, embedding)
                VALUES ($1, $2, $3, $4, 'conversation', $5::vector)
                """,
                user_id, fact, category, confidence, vector_str
            )
        else:
            await pool.execute(
                """
                INSERT INTO butler.user_facts
                    (user_id, fact, category, confidence, source)
                VALUES ($1, $2, $3, $4, 'conversation')
                """,
                user_id, fact, category, confidence
            )

        return f"Remembered: {fact}"


class RecallFactsTool(DatabaseTool):
    """Recall stored facts about a user."""

    def __init__(
        self,
        db_pool: DatabasePool | None = None,
        embedding_service: EmbeddingService | None = None,
    ):
        super().__init__(db_pool)
        self._embedding_service = embedding_service

    @property
    def name(self) -> str:
        return "recall_facts"

    @property
    def description(self) -> str:
        return (
            "Recall stored facts about a user. "
            "Use this at the start of conversations to personalize responses, "
            "or when you need to reference something you learned before. "
            "Use the 'query' parameter to search semantically (e.g., 'food preferences')."
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
                "query": {
                    "type": "string",
                    "description": (
                        "Natural language search query for semantic recall "
                        "(e.g., 'food preferences', 'work schedule'). "
                        "When provided, finds facts by meaning similarity."
                    )
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
        query = kwargs.get("query")
        category = kwargs.get("category")
        limit = kwargs.get("limit", 20)

        pool = await self._get_pool()

        # Semantic search path: embed the query and find similar facts
        if query and self._embedding_service:
            query_embedding = await self._embedding_service.embed(query)
            if query_embedding is not None:
                return await self._semantic_search(
                    pool, user_id, query_embedding, category, limit
                )
            # Embedding failed — fall through to category-based search

        # Category-based search (original behaviour)
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

        return self._format_by_category(user_id, rows)

    async def _semantic_search(
        self,
        pool: asyncpg.Pool,
        user_id: str,
        query_embedding: list[float],
        category: str | None,
        limit: int,
    ) -> str:
        """Find facts by vector similarity using cosine distance."""
        vector_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        if category:
            rows = await pool.fetch(
                """
                SELECT fact, category, confidence,
                       embedding <=> $3::vector AS distance
                FROM butler.user_facts
                WHERE user_id = $1 AND category = $2
                  AND embedding IS NOT NULL
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY embedding <=> $3::vector
                LIMIT $4
                """,
                user_id, category, vector_str, limit
            )
        else:
            rows = await pool.fetch(
                """
                SELECT fact, category, confidence,
                       embedding <=> $2::vector AS distance
                FROM butler.user_facts
                WHERE user_id = $1
                  AND embedding IS NOT NULL
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY embedding <=> $2::vector
                LIMIT $3
                """,
                user_id, vector_str, limit
            )

        if not rows:
            return f"No matching facts found for user {user_id}."

        lines = [f"Facts matching query for {user_id}:"]
        for row in rows:
            cat = row["category"] or "other"
            similarity = 1 - row["distance"]  # cosine distance → similarity
            lines.append(f"  - [{cat}] {row['fact']} (relevance: {similarity:.0%})")

        return "\n".join(lines)

    @staticmethod
    def _format_by_category(user_id: str, rows: list) -> str:
        """Format facts grouped by category (original output format)."""
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


class GetUserTool(DatabaseTool):
    """Get user profile including soul/personality configuration."""

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


class GetConversationsTool(DatabaseTool):
    """Retrieve recent conversation history for context injection."""

    @property
    def name(self) -> str:
        return "get_conversations"

    @property
    def description(self) -> str:
        return (
            "Retrieve recent conversation history for a user. "
            "Use this at the start of conversations to recall what was discussed recently, "
            "enabling continuity like 'Yesterday you asked about the Dune audiobook.'"
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
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back (default: 7)",
                    "minimum": 1,
                    "maximum": 90
                },
                "channel": {
                    "type": "string",
                    "description": "Filter by channel",
                    "enum": ["whatsapp", "telegram", "voice", "pwa"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of messages to return (default: 20)",
                    "minimum": 1,
                    "maximum": 100
                }
            },
            "required": ["user_id"]
        }

    async def execute(self, **kwargs: Any) -> str:
        user_id = kwargs["user_id"]
        days = kwargs.get("days", 7)
        channel = kwargs.get("channel")
        limit = kwargs.get("limit", 20)

        pool = await self._get_pool()

        if channel:
            rows = await pool.fetch(
                """
                SELECT role, content, channel, created_at
                FROM butler.conversation_history
                WHERE user_id = $1
                  AND channel = $2
                  AND created_at >= NOW() - INTERVAL '1 day' * $3
                ORDER BY created_at DESC
                LIMIT $4
                """,
                user_id, channel, days, limit
            )
        else:
            rows = await pool.fetch(
                """
                SELECT role, content, channel, created_at
                FROM butler.conversation_history
                WHERE user_id = $1
                  AND created_at >= NOW() - INTERVAL '1 day' * $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                user_id, days, limit
            )

        if not rows:
            return f"No recent conversations found for user {user_id} in the last {days} days."

        # Group by date for concise output (reverse to chronological order)
        by_date: dict[str, list[dict]] = {}
        for row in reversed(rows):
            date_key = row["created_at"].strftime("%Y-%m-%d")
            if date_key not in by_date:
                by_date[date_key] = []
            by_date[date_key].append({
                "role": row["role"],
                "content": row["content"],
                "channel": row["channel"],
                "time": row["created_at"].strftime("%H:%M"),
            })

        lines = [f"Recent conversations for {user_id} (last {days} days):"]
        for date, messages in by_date.items():
            lines.append(f"\n{date}:")
            for msg in messages:
                prefix = "You" if msg["role"] == "assistant" else "User"
                content = msg["content"]
                if len(content) > 120:
                    content = content[:117] + "..."
                channel_tag = f" [{msg['channel']}]" if not channel else ""
                lines.append(f"  {msg['time']} {prefix}{channel_tag}: {content}")

        return "\n".join(lines)


# Valid soul keys — prevents LLM from injecting arbitrary keys into JSONB
VALID_SOUL_KEYS = frozenset({"personality", "formality", "verbosity", "humor", "custom_instructions"})


class UpdateSoulTool(DatabaseTool):
    """Update a user's personality/soul configuration."""

    @property
    def name(self) -> str:
        return "update_soul"

    @property
    def description(self) -> str:
        return (
            "Update a user's personality and communication preferences. "
            "This merges new settings into the existing soul config without overwriting "
            "unrelated keys. Use when a user expresses preferences like "
            "'be more casual' or 'use less humor'."
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
                "personality": {
                    "type": "string",
                    "description": "Overall personality style (e.g., 'warm and encouraging', 'dry and witty')"
                },
                "formality": {
                    "type": "string",
                    "description": "Communication formality level",
                    "enum": ["casual", "balanced", "formal"]
                },
                "verbosity": {
                    "type": "string",
                    "description": "Response length preference",
                    "enum": ["concise", "balanced", "detailed"]
                },
                "humor": {
                    "type": "string",
                    "description": "Humor level in responses",
                    "enum": ["none", "light", "moderate", "heavy"]
                },
                "custom_instructions": {
                    "type": "string",
                    "description": "Free-form instructions (e.g., 'Always greet me in Spanish')"
                }
            },
            "required": ["user_id"]
        }

    async def execute(self, **kwargs: Any) -> str:
        user_id = kwargs["user_id"]

        # Extract only valid soul keys from kwargs
        updates = {
            key: kwargs[key]
            for key in VALID_SOUL_KEYS
            if key in kwargs
        }

        if not updates:
            return (
                "No soul preferences provided. Specify at least one of: "
                "personality, formality, verbosity, humor, custom_instructions."
            )

        pool = await self._get_pool()

        # Use PostgreSQL's jsonb concatenation (||) for partial merge
        # COALESCE handles NULL soul, || merges top-level keys atomically
        row = await pool.fetchrow(
            """
            UPDATE butler.users
            SET soul = COALESCE(soul, '{}'::jsonb) || $2::jsonb
            WHERE id = $1
            RETURNING soul
            """,
            user_id, json.dumps(updates)
        )

        if not row:
            return f"User {user_id} not found. Create user profile first."

        updated_soul = row["soul"] if isinstance(row["soul"], dict) else json.loads(row["soul"])
        updated_keys = ", ".join(updates.keys())
        lines = [f"Updated soul for {user_id} ({updated_keys}):"]
        for key, value in updated_soul.items():
            lines.append(f"  - {key}: {value}")

        return "\n".join(lines)
