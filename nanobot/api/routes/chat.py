"""Text chat route.

POST /api/chat — PWA sends a text message, gets an AI response.
Same pipeline as voice but with 'pwa' channel tag.
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from tools import DatabasePool, Tool

from ..context import load_user_context
from ..deps import get_current_user, get_db_pool, get_tools, get_user_tools
from ..llm import chat_with_tools, stream_chat_with_events
from ..models import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def text_chat(
    req: ChatRequest,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
    tools: dict[str, Tool] = Depends(get_tools),
):
    """Process a text chat message from the PWA.

    Flow mirrors voice/process but uses 'pwa' channel tag in
    conversation history, and returns a message_id for the PWA to
    track the response.
    """
    ctx = await load_user_context(pool, user_id)
    all_tools = get_user_tools(user_id, tools, pool)

    response_text = await chat_with_tools(
        system_prompt=ctx.system_prompt,
        user_message=req.message,
        tools=all_tools,
    )

    message_id = str(uuid.uuid4())

    # Save both sides of the conversation
    db = pool.pool
    await db.execute(
        """
        INSERT INTO butler.conversation_history (user_id, channel, role, content)
        VALUES ($1, 'pwa', 'user', $2)
        """,
        user_id,
        req.message,
    )
    await db.execute(
        """
        INSERT INTO butler.conversation_history (user_id, channel, role, content, metadata)
        VALUES ($1, 'pwa', 'assistant', $2, $3::jsonb)
        """,
        user_id,
        response_text,
        json.dumps({"message_id": message_id}),
    )

    return ChatResponse(response=response_text, message_id=message_id)


@router.post("/chat/stream")
async def stream_text_chat(
    req: ChatRequest,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
    tools: dict[str, Tool] = Depends(get_tools),
):
    """Stream a text chat response as Server-Sent Events.

    Same pipeline as ``text_chat`` but returns SSE so the PWA can render
    text as it arrives and show tool-use activity.

    SSE format::

        data: {"type":"text_delta","delta":"Hello"}
        data: {"type":"tool_start","tool":"weather"}
        data: {"type":"tool_end","tool":"weather"}
        data: {"type":"text_delta","delta":"It's sunny."}
        data: {"type":"done","message_id":"<uuid>"}
        data: [DONE]
    """
    ctx = await load_user_context(pool, user_id)
    all_tools = get_user_tools(user_id, tools, pool)
    message_id = str(uuid.uuid4())
    full_response_parts: list[str] = []

    async def generate():
        try:
            async for event in stream_chat_with_events(
                system_prompt=ctx.system_prompt,
                user_message=req.message,
                tools=all_tools,
            ):
                if event.get("type") == "text_delta":
                    full_response_parts.append(event["delta"])
                yield f"data: {json.dumps(event)}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'message_id': message_id})}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            full_text = "".join(full_response_parts)
            if full_text:
                try:
                    db = pool.pool
                    await db.execute(
                        """
                        INSERT INTO butler.conversation_history
                            (user_id, channel, role, content)
                        VALUES ($1, 'pwa', 'user', $2)
                        """,
                        user_id,
                        req.message,
                    )
                    await db.execute(
                        """
                        INSERT INTO butler.conversation_history
                            (user_id, channel, role, content, metadata)
                        VALUES ($1, 'pwa', 'assistant', $2, $3::jsonb)
                        """,
                        user_id,
                        full_text,
                        json.dumps({"message_id": message_id}),
                    )
                except Exception:
                    logger.exception(
                        "Failed to save chat conversation history for user=%s",
                        user_id,
                    )

    return StreamingResponse(generate(), media_type="text/event-stream")
