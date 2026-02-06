"""Text chat route.

POST /api/chat — PWA sends a text message, gets an AI response.
GET  /api/chat/history — Paginated conversation history for the PWA.
Same pipeline as voice but with 'pwa' channel tag.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from tools import DatabasePool, Tool

from ..context import load_user_context
from ..deps import get_current_user, get_db_pool, get_tools, get_user_tools
from ..llm import chat_with_tools
from ..models import ChatHistoryResponse, ChatRequest, ChatResponse, HistoryMessage

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
