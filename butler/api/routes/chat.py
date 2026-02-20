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

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from starlette.responses import StreamingResponse

from tools import DatabasePool, Tool

from ..auto_learn import extract_and_store_facts
from ..config import settings
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

    # Save user message first so it's visible to subsequent requests
    await pool.pool.execute(
        """
        INSERT INTO butler.conversation_history (user_id, channel, role, content, metadata)
        VALUES ($1, 'pwa', 'user', $2, $3::jsonb)
        """,
        user_id,
        user_content,
        user_metadata,
    )

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

    await pool.pool.execute(
        """
        INSERT INTO butler.conversation_history (user_id, channel, role, content, metadata)
        VALUES ($1, 'pwa', 'assistant', $2, $3::jsonb)
        """,
        user_id,
        response_text,
        {"message_id": message_id},
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
        SELECT id, channel, role, content, metadata, source, created_at
        FROM butler.conversation_history
        WHERE user_id = $1 AND created_at < $2
        ORDER BY created_at DESC, id DESC
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
            source=row["source"],
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

    # Save user message immediately so it's visible to subsequent requests
    # even if the stream is interrupted or the client disconnects.
    await pool.pool.execute(
        """
        INSERT INTO butler.conversation_history (user_id, channel, role, content, metadata)
        VALUES ($1, 'pwa', 'user', $2, $3::jsonb)
        """,
        user_id,
        user_content,
        user_metadata,
    )

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
                    await pool.pool.execute(
                        """
                        INSERT INTO butler.conversation_history
                            (user_id, channel, role, content, metadata)
                        VALUES ($1, 'pwa', 'assistant', $2, $3::jsonb)
                        """,
                        user_id,
                        full_text,
                        {"message_id": message_id},
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
                        "Failed to save assistant response for user=%s",
                        user_id,
                    )

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/chat/claude-code/stream")
async def claude_code_stream(
    req: ChatRequest,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Proxy a message to Claude Code CLI running on the host via the shim service.

    Requires the ``claude_code`` permission or admin role.

    The shim (docker/claude-code-shim/app.py) must be running on the host at
    ``settings.claude_code_shim_url``. It executes ``claude --print <message>``
    inside ~/home-server and streams stdout as SSE.

    SSE format (identical to /chat/stream)::

        data: {"type":"text_delta","delta":"some text"}
        data: {"type":"done","message_id":"<uuid>"}
        data: [DONE]
    """
    import json as _json

    db = pool.pool

    # Permission check
    row = await db.fetchrow(
        "SELECT role, permissions FROM butler.users WHERE id = $1", user_id
    )
    if row is None:
        raise HTTPException(403, "User not found")

    user_role: str | None = row["role"]
    raw_perms = row["permissions"]
    user_perms: list[str] = (
        _json.loads(raw_perms) if isinstance(raw_perms, str) else (raw_perms or [])
    )

    if user_role != "admin" and "claude_code" not in user_perms:
        raise HTTPException(403, "claude_code permission required")

    # Save user message immediately
    await db.execute(
        """
        INSERT INTO butler.conversation_history (user_id, channel, role, content, source)
        VALUES ($1, 'pwa', 'user', $2, 'claude_code')
        """,
        user_id,
        req.message,
    )

    message_id = str(uuid.uuid4())
    full_response_parts: list[str] = []

    async def generate():
        try:
            timeout = aiohttp.ClientTimeout(total=300, connect=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    async with session.post(
                        f"{settings.claude_code_shim_url}/run",
                        json={"message": req.message},
                    ) as resp:
                        if resp.status != 200:
                            err_msg = "Claude Code shim returned an error. Check that it is running on the host."
                            yield f"data: {json.dumps({'type': 'text_delta', 'delta': err_msg})}\n\n"
                        else:
                            # Forward SSE events from shim to client, accumulating text
                            async for raw_line in resp.content:
                                line = raw_line.decode(errors="replace").rstrip("\r\n")
                                if not line:
                                    continue  # Skip SSE blank-line delimiters
                                if line == "data: [DONE]":
                                    break
                                if line.startswith("data: "):
                                    data_str = line[6:]
                                    try:
                                        event = json.loads(data_str)
                                        if event.get("type") == "text_delta":
                                            full_response_parts.append(event.get("delta", ""))
                                    except json.JSONDecodeError:
                                        pass
                                    yield f"{line}\n\n"
                except aiohttp.ClientConnectorError:
                    err_msg = (
                        "Cannot reach Claude Code shim. "
                        "Start it on the Mac Mini: "
                        "python3 ~/home-server/docker/claude-code-shim/app.py"
                    )
                    yield f"data: {json.dumps({'type': 'text_delta', 'delta': err_msg})}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'message_id': message_id})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            logger.exception("Claude Code stream failed for user=%s", user_id)
            yield f"data: {json.dumps({'type': 'text_delta', 'delta': 'Unexpected error in Claude Code stream.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'message_id': message_id})}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            full_text = "".join(full_response_parts)
            if full_text:
                try:
                    await db.execute(
                        """
                        INSERT INTO butler.conversation_history
                            (user_id, channel, role, content, metadata, source)
                        VALUES ($1, 'pwa', 'assistant', $2, $3::jsonb, 'claude_code')
                        """,
                        user_id,
                        full_text,
                        {"message_id": message_id},
                    )
                except Exception:
                    logger.exception(
                        "Failed to save Claude Code response for user=%s", user_id
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
