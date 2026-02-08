"""User context loading for LLM calls.

Before each Claude API call, we load the user's personality config, learned
facts, and recent conversation history from PostgreSQL, then compose a system
prompt that personalizes Butler's responses.

Conversation history is now passed as actual message objects in the Claude API
messages array (multi-turn), rather than truncated summaries in the system prompt.

Facts use a hybrid approach: semantic search via pgvector (for relevance to the
current message) combined with top-confidence facts (for general context).

Database tables used:
- butler.users (soul JSONB column)
- butler.user_facts (learned facts with confidence scores + embeddings)
- butler.conversation_history (recent messages across channels)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from tools import DatabasePool
from tools.embeddings import EmbeddingService

from .config import settings

logger = logging.getLogger(__name__)


@dataclass
class UserContext:
    system_prompt: str
    user_name: str
    butler_name: str
    history: list[dict] = field(default_factory=list)


async def load_user_context(
    pool: DatabasePool,
    user_id: str,
    *,
    current_message: str | None = None,
    embedding_service: EmbeddingService | None = None,
    channel: str | None = None,
    history_limit: int | None = None,
) -> UserContext:
    """Load all context needed for a personalized LLM call.

    Args:
        pool: Database connection pool.
        user_id: The user making the request.
        current_message: The user's current message, used for semantic fact
            search. If provided with an embedding_service, facts are loaded
            by relevance to this message instead of just by confidence.
        embedding_service: Optional embedding service for semantic search.
        channel: If provided, only load history from this channel ('pwa',
            'voice'). Prevents cross-channel contamination.
        history_limit: Override the default max_history_messages setting.
    """
    db = pool.pool

    user = await db.fetchrow(
        "SELECT id, name, soul FROM butler.users WHERE id = $1", user_id
    )
    if not user:
        return UserContext(
            system_prompt=_build_system_prompt("User", {}, []),
            user_name="User",
            butler_name="Butler",
        )

    soul = user["soul"] or {}
    user_name = user["name"] or "User"
    butler_name = soul.get("butler_name", "Butler")

    facts = await _load_facts(
        db, user_id,
        current_message=current_message,
        embedding_service=embedding_service,
    )

    history = await load_conversation_messages(
        pool, user_id, limit=history_limit, channel=channel,
    )

    return UserContext(
        system_prompt=_build_system_prompt(user_name, soul, facts),
        user_name=user_name,
        butler_name=butler_name,
        history=history,
    )


async def _load_facts(
    db,
    user_id: str,
    *,
    current_message: str | None = None,
    embedding_service: EmbeddingService | None = None,
) -> list:
    """Load user facts using hybrid semantic + confidence approach.

    When embedding_service and current_message are available:
    - 10 facts by semantic similarity to the current message (pgvector)
    - 10 facts by highest confidence (for general context)
    - Deduplicated by fact ID

    Falls back to top-20 by confidence when semantic search is unavailable.
    """
    # Try semantic search if we have both an embedding service and a message
    if current_message and embedding_service:
        query_vector = await embedding_service.embed(current_message)
        if query_vector:
            return await _hybrid_fact_search(db, user_id, query_vector)

    # Fallback: top 20 by confidence (original behaviour)
    return await db.fetch(
        """
        SELECT fact, category FROM butler.user_facts
        WHERE user_id = $1
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY confidence DESC, created_at DESC
        LIMIT 20
        """,
        user_id,
    )


async def _hybrid_fact_search(db, user_id: str, query_vector: list[float]) -> list:
    """Combine semantic similarity + confidence for fact loading.

    Runs two queries:
    1. Top 10 by vector similarity to the current message
    2. Top 10 by confidence score

    Results are deduplicated by fact ID, preserving semantic results first.
    """
    # Semantic search: find facts most relevant to current conversation
    semantic_rows = await db.fetch(
        """
        SELECT id, fact, category
        FROM butler.user_facts
        WHERE user_id = $1
          AND embedding IS NOT NULL
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY embedding <=> $2::vector
        LIMIT 10
        """,
        user_id,
        "[" + ",".join(str(x) for x in query_vector) + "]",
    )

    # Confidence search: top general-purpose facts
    confidence_rows = await db.fetch(
        """
        SELECT id, fact, category
        FROM butler.user_facts
        WHERE user_id = $1
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY confidence DESC, created_at DESC
        LIMIT 10
        """,
        user_id,
    )

    # Deduplicate: semantic results take priority
    seen_ids = set()
    combined = []
    for row in list(semantic_rows) + list(confidence_rows):
        fact_id = row["id"]
        if fact_id not in seen_ids:
            seen_ids.add(fact_id)
            combined.append(row)

    logger.debug(
        "Loaded %d facts for user %s (%d semantic, %d confidence, %d after dedup)",
        len(combined), user_id, len(semantic_rows), len(confidence_rows), len(combined),
    )

    return combined


async def load_conversation_messages(
    pool: DatabasePool,
    user_id: str,
    limit: int | None = None,
    channel: str | None = None,
) -> list[dict]:
    """Load recent conversation history as message objects for the Claude API.

    Returns a list of {"role": "user"|"assistant", "content": "..."} dicts
    in chronological order, ready to prepend to the messages array.

    Args:
        channel: If provided, only load messages from this channel.
            Prevents voice sessions from seeing text chat and vice versa.
    """
    max_msgs = limit if limit is not None else settings.max_history_messages
    db = pool.pool

    if channel:
        rows = await db.fetch(
            """
            SELECT role, content
            FROM butler.conversation_history
            WHERE user_id = $1
              AND channel = $2
              AND created_at > NOW() - INTERVAL '7 days'
            ORDER BY created_at DESC
            LIMIT $3
            """,
            user_id,
            channel,
            max_msgs,
        )
    else:
        rows = await db.fetch(
            """
            SELECT role, content
            FROM butler.conversation_history
            WHERE user_id = $1 AND created_at > NOW() - INTERVAL '7 days'
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id,
            max_msgs,
        )

    # Reverse to chronological order and build message dicts.
    # Ensure messages alternate user/assistant — Claude requires this.
    # Consecutive same-role messages are merged.
    messages: list[dict] = []
    for row in reversed(rows):
        role = row["role"]
        content = row["content"]
        if messages and messages[-1]["role"] == role:
            # Merge consecutive same-role messages
            messages[-1]["content"] += "\n" + content
        else:
            messages.append({"role": role, "content": content})
    return messages


def _build_system_prompt(
    user_name: str,
    soul: dict,
    facts: list,
) -> str:
    """Compose system prompt from personality and known facts.

    Conversation history is no longer included here — it's passed as actual
    messages in the Claude API messages array for proper multi-turn context.
    """
    butler_name = soul.get("butler_name", "Butler")
    parts = [
        f"You are {butler_name}, a helpful AI assistant. "
        f"You are speaking with {user_name}."
    ]

    # Personality
    if soul:
        personality_items = []
        if p := soul.get("personality"):
            personality_items.append(f"- Style: {p}")
        if v := soul.get("verbosity"):
            personality_items.append(f"- Verbosity: {v}")
        if h := soul.get("humor"):
            personality_items.append(f"- Humor: {h}")
        if ci := soul.get("customInstructions"):
            personality_items.append(f"- Custom instructions: {ci}")
        if personality_items:
            parts.append("\nPERSONALITY:")
            parts.extend(personality_items)

    # Known facts
    if facts:
        parts.append(f"\nWHAT YOU KNOW ABOUT {user_name.upper()}:")
        for row in facts:
            category = row["category"] or "general"
            parts.append(f"- [{category}] {row['fact']}")

    # Behavioral rules
    parts.append("\nRULES:")
    parts.append("- Be concise in voice responses (1-2 sentences unless asked for detail)")
    parts.append("- Use remember_fact to store important information about the user")
    parts.append("- For home automation, confirm before executing destructive actions")

    return "\n".join(parts)
