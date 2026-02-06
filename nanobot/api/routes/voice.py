"""Voice processing routes.

POST /api/voice/process — Batch: returns full response JSON (text chat fallback)
POST /api/voice/stream  — Streaming: returns SSE text chunks (primary voice path)

Both are called by LiveKit Agents with a transcript. The stream endpoint enables
TTS to start speaking on the first sentence while Claude is still generating.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from tools import DatabasePool, Tool

from ..context import load_user_context
from ..deps import get_db_pool, get_internal_or_user, get_tools, get_user_tools
from ..llm import chat_with_tools, stream_chat_with_tools
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


@router.post("/stream")
async def stream_voice(
    req: VoiceProcessRequest,
    caller_user_id: str | None = Depends(get_internal_or_user),
    pool: DatabasePool = Depends(get_db_pool),
    tools: dict[str, Tool] = Depends(get_tools),
):
    """Stream a voice response as Server-Sent Events.

    Primary voice endpoint for the LiveKit Agent. Text chunks arrive as
    SSE events so the agent can feed them to TTS sentence-by-sentence,
    producing audio while Claude is still generating.

    SSE format:
        data: {"delta": "Hello"}
        data: {"delta": " there!"}
        data: [DONE]
    """
    user_id = caller_user_id or req.user_id
    ctx = await load_user_context(pool, user_id)
    all_tools = get_user_tools(user_id, tools, pool)
    full_response_parts: list[str] = []

    async def generate():
        try:
            async for chunk in stream_chat_with_tools(
                system_prompt=ctx.system_prompt,
                user_message=req.transcript,
                tools=all_tools,
            ):
                full_response_parts.append(chunk)
                yield f"data: {json.dumps({'delta': chunk})}\n\n"

            yield "data: [DONE]\n\n"
        finally:
            # Save conversation history even if the client disconnects mid-stream.
            # The finally block runs on both normal completion and generator aclose().
            full_text = "".join(full_response_parts)
            if full_text:
                try:
                    metadata = {"session_id": req.session_id}
                    db = pool.pool
                    await db.execute(
                        """
                        INSERT INTO butler.conversation_history
                            (user_id, channel, role, content, metadata)
                        VALUES ($1, 'voice', 'user', $2, $3::jsonb)
                        """,
                        user_id,
                        req.transcript,
                        _json_str(metadata),
                    )
                    await db.execute(
                        """
                        INSERT INTO butler.conversation_history
                            (user_id, channel, role, content, metadata)
                        VALUES ($1, 'voice', 'assistant', $2, $3::jsonb)
                        """,
                        user_id,
                        full_text,
                        _json_str(metadata),
                    )
                except Exception:
                    logger.exception(
                        "Failed to save voice conversation history for user=%s",
                        user_id,
                    )

    return StreamingResponse(generate(), media_type="text/event-stream")


def _should_end_turn(response: str) -> bool:
    """Simple heuristic for whether the conversation turn is complete."""
    lower = response.lower()
    return any(phrase in lower for phrase in _FAREWELL_PHRASES)


def _json_str(data: dict) -> str:
    """Convert dict to JSON string for asyncpg JSONB parameter."""
    return json.dumps(data)
