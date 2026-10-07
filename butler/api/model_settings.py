"""Which Claude model Butler chats with (#215).

Admins pick it in Settings; the choice lives in butler.app_settings under
'chat_model' and is cached here, so the tool router reads it without a DB
round trip. Unset means the server default, ANTHROPIC_MODEL. Requests that pin
their own model (the pet voice, auto-learn) are unaffected.
"""

from __future__ import annotations

import logging

from .config import settings

logger = logging.getLogger(__name__)

SETTING_KEY = "chat_model"

# Models an admin can choose. Prices are per million tokens (input / output).
CHAT_MODELS: dict[str, dict[str, str]] = {
    "claude-opus-5-5": {
        "label": "Claude Opus 5.5",
        "description": "Most capable; best for tricky requests and long tool chains. $4 / $20 per million tokens.",
    },
    "claude-sonnet-5-5": {
        "label": "Claude Sonnet 5.5",
        "description": "Fast and capable for everyday chat and voice, at half Opus 5.5's price. $2 / $10 per million tokens.",
    },
}

_selected: str | None = None


def current_model() -> str:
    """The model to chat with right now."""
    return _selected or settings.anthropic_model


def selected_model() -> str | None:
    """The admin's choice, or None when using the server default."""
    return _selected


async def load(pool) -> None:
    """Read the saved choice at startup."""
    global _selected
    try:
        value = await pool.pool.fetchval(
            "SELECT value FROM butler.app_settings WHERE key = $1", SETTING_KEY,
        )
    except Exception:
        logger.exception("Couldn't load the chat model setting; using the server default")
        return
    _selected = value if value in CHAT_MODELS else None
    if value and _selected is None:
        logger.warning("Ignoring unknown saved chat model %r", value)
    logger.info("Chat model: %s", current_model())


async def set_model(pool, model: str | None, user_id: str) -> str:
    """Save the admin's choice (None = server default). Returns the model now in use."""
    global _selected
    if model is not None and model not in CHAT_MODELS:
        raise ValueError(f"Unknown model: {model}")
    if model is None:
        await pool.pool.execute("DELETE FROM butler.app_settings WHERE key = $1", SETTING_KEY)
    else:
        await pool.pool.execute(
            """
            INSERT INTO butler.app_settings (key, value, updated_by, updated_at)
            VALUES ($1, $2::jsonb, $3, NOW())
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = NOW()
            """,
            SETTING_KEY, model, user_id,
        )
    _selected = model
    logger.info("Chat model set to %s by %s", current_model(), user_id)
    return current_model()
