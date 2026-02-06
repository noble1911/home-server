"""User context loading for LLM calls.

Before each Claude API call, we load the user's personality config, learned
facts, and recent conversation history from PostgreSQL, then compose a system
prompt that personalizes Butler's responses.

Database tables used:
- butler.users (soul JSONB column)
- butler.user_facts (learned facts with confidence scores)
- butler.conversation_history (recent messages across channels)
"""

from __future__ import annotations

from dataclasses import dataclass

from tools import DatabasePool


@dataclass
class UserContext:
    system_prompt: str
    user_name: str
    butler_name: str


async def load_user_context(pool: DatabasePool, user_id: str) -> UserContext:
    """Load all context needed for a personalized LLM call."""
    db = pool.pool

    user = await db.fetchrow(
        "SELECT id, name, soul FROM butler.users WHERE id = $1", user_id
    )
    if not user:
        return UserContext(
            system_prompt=_build_system_prompt("User", {}, [], []),
            user_name="User",
            butler_name="Butler",
        )

    soul = user["soul"] or {}
    user_name = user["name"] or "User"
    butler_name = soul.get("butler_name", "Butler")

    facts = await db.fetch(
        """
        SELECT fact, category FROM butler.user_facts
        WHERE user_id = $1
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY confidence DESC, created_at DESC
        LIMIT 20
        """,
        user_id,
    )

    history = await db.fetch(
        """
        SELECT role, content, channel, created_at
        FROM butler.conversation_history
        WHERE user_id = $1 AND created_at > NOW() - INTERVAL '7 days'
        ORDER BY created_at DESC
        LIMIT 20
        """,
        user_id,
    )

    return UserContext(
        system_prompt=_build_system_prompt(user_name, soul, facts, history),
        user_name=user_name,
        butler_name=butler_name,
    )


_CHANNEL_LABELS = {
    "voice": "[via voice]",
    "pwa": "[via text]",
    "whatsapp": "[via whatsapp]",
    "telegram": "[via telegram]",
}


def _channel_label(channel: str) -> str:
    """Return a human-readable label for a conversation channel."""
    return _CHANNEL_LABELS.get(channel, f"[via {channel}]")


def _build_system_prompt(
    user_name: str,
    soul: dict,
    facts: list,
    history: list,
) -> str:
    """Compose system prompt from context layers."""
    butler_name = soul.get("butler_name", "Butler")
    parts = [
        f"You are {butler_name}, a helpful AI home assistant. "
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

    # Recent conversation context (shown chronologically, across all channels)
    if history:
        parts.append("\nRECENT CONTEXT (last 7 days, across all channels):")
        for row in reversed(history):
            role = "You" if row["role"] == "assistant" else user_name
            day = row["created_at"].strftime("%b %d")
            channel_label = _channel_label(row.get("channel", "pwa"))
            content = row["content"][:100]
            parts.append(f"- {day} {channel_label} ({role}): {content}")

    # Behavioral rules
    parts.append("\nRULES:")
    parts.append("- Be concise in voice responses (1-2 sentences unless asked for detail)")
    parts.append("- Use remember_fact to store important information about the user")
    parts.append("- For home automation, confirm before executing destructive actions")

    return "\n".join(parts)
