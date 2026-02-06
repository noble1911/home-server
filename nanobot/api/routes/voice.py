"""Voice processing route.

POST /api/voice/process — Called by LiveKit Agents with a transcript.
Loads user context, calls Claude with tools, saves conversation, returns response.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends

from tools import DatabasePool, Tool

from ..context import load_user_context
from ..deps import get_db_pool, get_internal_or_user, get_tools, get_user_tools
from ..llm import chat_with_tools
from ..models import VoiceProcessRequest, VoiceProcessResponse

logger = logging.getLogger(__name__)

router = APIRouter()

_FAREWELL_PHRASES = frozenset(
    ["goodbye", "goodnight", "good night", "talk to you later", "that's all"]
)


@router.post("/process", response_model=VoiceProcessResponse)
async def process_voice(
    req: VoiceProcessRequest,
    caller_user_id: str | None = Depends(get_internal_or_user),
    pool: DatabasePool = Depends(get_db_pool),
    tools: dict[str, Tool] = Depends(get_tools),
):
    """Process a voice transcript and return an AI response.

    This is the core voice pipeline endpoint that LiveKit Agents calls
    after Whisper transcribes the user's speech. The flow:
    1. Determine user_id (from JWT or request body for internal calls)
    2. Load user context (soul config, facts, conversation history)
    3. Call Claude with available tools
    4. Save both user and assistant messages to conversation history
    5. Return response text for Kokoro TTS
    """
    user_id = caller_user_id or req.user_id

    ctx = await load_user_context(pool, user_id)
    all_tools = get_user_tools(user_id, tools, pool)

    response_text = await chat_with_tools(
        system_prompt=ctx.system_prompt,
        user_message=req.transcript,
        tools=all_tools,
    )

    # Save conversation to history
    db = pool.pool
    metadata = {"session_id": req.session_id}
    await db.execute(
        """
        INSERT INTO butler.conversation_history (user_id, channel, role, content, metadata)
        VALUES ($1, 'voice', 'user', $2, $3::jsonb)
        """,
        user_id,
        req.transcript,
        _json_str(metadata),
    )
    await db.execute(
        """
        INSERT INTO butler.conversation_history (user_id, channel, role, content, metadata)
        VALUES ($1, 'voice', 'assistant', $2, $3::jsonb)
        """,
        user_id,
        response_text,
        _json_str(metadata),
    )

    return VoiceProcessResponse(
        response=response_text,
        should_end_turn=_should_end_turn(response_text),
    )


def _should_end_turn(response: str) -> bool:
    """Simple heuristic for whether the conversation turn is complete."""
    lower = response.lower()
    return any(phrase in lower for phrase in _FAREWELL_PHRASES)


def _json_str(data: dict) -> str:
    """Convert dict to JSON string for asyncpg JSONB parameter."""
    return json.dumps(data)
