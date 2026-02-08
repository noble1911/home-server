"""Auto-extract facts from conversations using a fast model.

After each conversation, a background task calls Claude Haiku to identify
personal facts about the user (preferences, schedules, relationships, etc.)
and stores them with source='auto_extraction'.

This runs as a fire-and-forget asyncio task so it never blocks the response.
"""

from __future__ import annotations

import json
import logging

import anthropic

from tools import DatabasePool
from tools.embeddings import EmbeddingService
from tools.memory import RememberFactTool

from .config import settings

logger = logging.getLogger(__name__)

_EXTRACTION_MODEL = "claude-haiku-4-5-20251001"

_EXTRACTION_PROMPT = """\
Analyze this conversation and extract any personal facts about the user.

Only extract facts about the USER (their preferences, habits, relationships, \
schedule, health, work, etc.). Do NOT extract general knowledge or facts about \
the assistant.

Conversation:
User: {user_message}
Assistant: {assistant_response}

Return a JSON array of extracted facts. Each fact should have:
- "fact": A concise statement about the user (e.g., "Prefers Italian food")
- "category": One of: preference, schedule, relationship, work, health, other
- "confidence": A number between 0.5 and 0.9 (how confident this is a real fact)

Return an empty array [] if there is nothing personal to learn.

Respond with ONLY the JSON array, no other text."""

# Minimum message length to bother analyzing — very short messages
# like "hi" or "thanks" rarely contain learnable facts.
_MIN_MESSAGE_LENGTH = 20


async def extract_and_store_facts(
    db_pool: DatabasePool,
    user_id: str,
    user_message: str,
    assistant_response: str,
    embedding_service: EmbeddingService | None = None,
) -> None:
    """Extract personal facts from a conversation and store them.

    This function is designed to be called via ``asyncio.create_task()``
    so it runs in the background without blocking the chat response.
    """
    if not settings.anthropic_api_key:
        return

    # Skip very short or trivial messages
    if len(user_message) < _MIN_MESSAGE_LENGTH:
        return

    try:
        facts = await _call_extraction_model(user_message, assistant_response)
        if not facts:
            return

        remember = RememberFactTool(db_pool, embedding_service)
        for fact_data in facts:
            try:
                await remember.execute(
                    user_id=user_id,
                    fact=fact_data["fact"],
                    category=fact_data.get("category", "other"),
                    confidence=fact_data.get("confidence", 0.7),
                    source="auto_extraction",
                )
                logger.debug(
                    "Auto-learned fact for user=%s: %s",
                    user_id,
                    fact_data["fact"],
                )
            except Exception:
                logger.exception("Failed to store auto-extracted fact")

        if facts:
            logger.info(
                "Auto-extracted %d fact(s) for user=%s", len(facts), user_id
            )

    except Exception:
        logger.exception("Auto-learning failed for user=%s", user_id)


async def _call_extraction_model(
    user_message: str,
    assistant_response: str,
) -> list[dict]:
    """Call Haiku to extract facts from a conversation turn."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    prompt = _EXTRACTION_PROMPT.format(
        user_message=user_message,
        assistant_response=assistant_response[:2000],  # Truncate long responses
    )

    response = await client.messages.create(
        model=_EXTRACTION_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()

    # Parse JSON response
    try:
        facts = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Auto-learn: failed to parse Haiku response: %s", text[:200])
        return []

    if not isinstance(facts, list):
        return []

    # Validate and sanitize each fact
    valid_categories = {"preference", "schedule", "relationship", "work", "health", "other"}
    validated = []
    for item in facts:
        if not isinstance(item, dict) or "fact" not in item:
            continue
        category = item.get("category", "other")
        if category not in valid_categories:
            category = "other"
        confidence = item.get("confidence", 0.7)
        if not isinstance(confidence, (int, float)):
            confidence = 0.7
        confidence = max(0.5, min(0.9, confidence))

        validated.append({
            "fact": str(item["fact"])[:500],  # Cap fact length
            "category": category,
            "confidence": confidence,
        })

    return validated
