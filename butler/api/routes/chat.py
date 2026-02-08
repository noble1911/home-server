"""Text chat route.

POST /api/chat — PWA sends a text message, gets an AI response.
GET  /api/chat/history — Paginated conversation history for the PWA.
Same pipeline as voice but with 'pwa' channel tag.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response
from starlette.responses import StreamingResponse

from tools import DatabasePool, Tool

from ..auto_learn import extract_and_store_facts
from ..context import load_user_context
from ..deps import get_current_user, get_db_pool, get_embedding_service, get_tools, get_user_tools
from ..llm import chat_with_tools, stream_chat_with_events
from ..models import ChatHistoryResponse, ChatRequest, ChatResponse, HistoryMessage


def _prepare_image_context(req: ChatRequest) -> tuple[dict | None, str, dict]:
    """Extract image payload and DB-ready content/metadata from a chat request."""
    image_payload = None
    user_content = req.message
    user_metadata: dict = {}
    if req.image:
        image_payload = {"data": req.image.data, "media_type": req.image.mediaType}
        user_content = f"[Image attached: {req.image.mediaType}]\n{req.message}"
        user_metadata = {"has_image": True, "image_media_type": req.image.mediaType}
    return image_payload, user_content, user_metadata

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
    ctx = await load_user_context(
        pool, user_id,
        current_message=req.message,
        embedding_service=get_embedding_service(),
    )
    all_tools = await get_user_tools(user_id, tools, pool)
    image_payload, user_content, user_metadata = _prepare_image_context(req)

    response_text = await chat_with_tools(
        system_prompt=ctx.system_prompt,
        user_message=req.message,
        tools=all_tools,
        history=ctx.history,
        image=image_payload,
        db_pool=pool,
        user_id=user_id,
        channel="pwa",
    )

    message_id = str(uuid.uuid4())

    db = pool.pool
    async with db.transaction():
        await db.execute(
            """
            INSERT INTO butler.conversation_history (user_id, channel, role, content, metadata)
            VALUES ($1, 'pwa', 'user', $2, $3::jsonb)
            """,
            user_id,
            user_content,
            json.dumps(user_metadata),
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

    # Auto-learn: extract facts in the background (fire-and-forget)
    asyncio.create_task(
        extract_and_store_facts(
            pool, user_id, req.message, response_text, get_embedding_service()
        )
    )

    return ChatResponse(response=response_text, message_id=message_id)


@router.get("/chat/history", response_model=ChatHistoryResponse)
async def chat_history(
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
    before: str | None = Query(None, description="ISO timestamp cursor"),
    limit: int = Query(50, ge=1, le=100),
):
    """Return paginated conversation history for the authenticated user."""
    cursor = (
        datetime.fromisoformat(before)
        if before
        else datetime.now(timezone.utc)
    )

    db = pool.pool
    rows = await db.fetch(
        """
        SELECT id, channel, role, content, metadata, created_at
        FROM butler.conversation_history
        WHERE user_id = $1 AND created_at < $2
        ORDER BY created_at DESC
        LIMIT $3
        """,
        user_id,
        cursor,
        limit + 1,
    )

    has_more = len(rows) > limit
    rows = rows[:limit]

    messages = [
        HistoryMessage(
            id=str(row["id"]),
            role=row["role"],
            content=row["content"],
            type="voice" if row["channel"] == "voice" else "text",
            timestamp=row["created_at"].isoformat(),
        )
        for row in rows
    ]

    return ChatHistoryResponse(messages=messages, hasMore=has_more)


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
    ctx = await load_user_context(
        pool, user_id,
        current_message=req.message,
        embedding_service=get_embedding_service(),
    )
    all_tools = await get_user_tools(user_id, tools, pool)
    image_payload, user_content, user_metadata = _prepare_image_context(req)

    message_id = str(uuid.uuid4())
    full_response_parts: list[str] = []

    async def generate():
        try:
            async for event in stream_chat_with_events(
                system_prompt=ctx.system_prompt,
                user_message=req.message,
                tools=all_tools,
                history=ctx.history,
                image=image_payload,
                db_pool=pool,
                user_id=user_id,
                channel="pwa",
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
                    async with db.transaction():
                        await db.execute(
                            """
                            INSERT INTO butler.conversation_history
                                (user_id, channel, role, content, metadata)
                            VALUES ($1, 'pwa', 'user', $2, $3::jsonb)
                            """,
                            user_id,
                            user_content,
                            json.dumps(user_metadata),
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
                    # Auto-learn: extract facts in the background
                    asyncio.create_task(
                        extract_and_store_facts(
                            pool, user_id, req.message, full_text,
                            get_embedding_service(),
                        )
                    )
                except Exception:
                    logger.exception(
                        "Failed to save chat conversation history for user=%s",
                        user_id,
                    )

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.delete("/chat/history", status_code=204)
async def clear_chat_history(
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Delete all conversation history for the authenticated user."""
    db = pool.pool
    await db.execute(
        "DELETE FROM butler.conversation_history WHERE user_id = $1",
        user_id,
    )
    return Response(status_code=204)
