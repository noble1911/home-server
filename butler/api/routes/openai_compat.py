"""OpenAI-compatible chat completions endpoint for wire-pod (Vector robot).

POST /api/openai/v1/chat/completions

Wire-pod sends requests in OpenAI format. This endpoint translates them
into Butler's pipeline (context loading, tool routing, memory) and returns
an OpenAI-format response. All requests use Ron's user profile for memory
and personalization.

Authentication: Bearer token or X-API-Key header (internal API key).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, Header, HTTPException
from fastapi import Depends
from pydantic import BaseModel

from tools import DatabasePool, Tool

from ..auto_learn import extract_and_store_facts
from ..config import settings
from ..context import load_user_context
from ..deps import get_db_pool, get_embedding_service, get_tools, get_user_tools

from ..llm import chat_with_tools

logger = logging.getLogger(__name__)

router = APIRouter()

# The Butler user ID that Vector will use for all interactions.
# This is Ron's user — Vector shares his memory, facts, and context.
VECTOR_USER_ID = "ron"
VECTOR_CHANNEL = "vector"


# ── Request / response models (OpenAI format) ──────────────────────

class _Message(BaseModel):
    role: str
    content: str


class OpenAIChatRequest(BaseModel):
    model: str = ""
    messages: list[_Message] = []
    max_tokens: int | None = None
    temperature: float | None = None
    stream: bool = False


class OpenAIChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[dict]
    usage: dict


# ── Endpoint ────────────────────────────────────────────────────────

@router.post("/v1/chat/completions", response_model=OpenAIChatResponse)
async def openai_chat_completions(
    req: OpenAIChatRequest,
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None),
    pool: DatabasePool = Depends(get_db_pool),
    tools: dict[str, Tool] = Depends(get_tools),
):
    """OpenAI-compatible completions endpoint for wire-pod.

    Extracts the last user message from the OpenAI messages array,
    routes it through Butler's full pipeline (context, tools, memory),
    and returns the response in OpenAI format.

    Accepts the internal API key via either:
    - Authorization: Bearer <key> (OpenAI client standard — used by wire-pod)
    - X-API-Key: <key> (Butler internal convention)
    """
    # Extract key from Bearer token or X-API-Key header
    api_key = x_api_key
    if not api_key and authorization and authorization.startswith("Bearer "):
        api_key = authorization.removeprefix("Bearer ")

    if not api_key or not settings.internal_api_key or api_key != settings.internal_api_key:
        raise HTTPException(401, "Invalid or missing API key")

    # Extract the last user message from the OpenAI messages array
    user_message = ""
    for msg in reversed(req.messages):
        if msg.role == "user":
            user_message = msg.content
            break

    if not user_message:
        raise HTTPException(400, "No user message found in messages array")

    # Load Butler context for Ron's user (memory, facts, soul config)
    ctx = await load_user_context(
        pool,
        VECTOR_USER_ID,
        current_message=user_message,
        embedding_service=get_embedding_service(),
        channel=VECTOR_CHANNEL,
    )

    # Get tools filtered by Ron's permissions
    all_tools = await get_user_tools(VECTOR_USER_ID, tools, pool)

    # Run through Butler's full tool-routing pipeline
    response_text = await chat_with_tools(
        system_prompt=ctx.system_prompt,
        user_message=user_message,
        tools=all_tools,
        history=ctx.history,
        db_pool=pool,
        user_id=VECTOR_USER_ID,
        channel=VECTOR_CHANNEL,
    )

    # Save conversation history
    db = pool.pool
    metadata = json.dumps({"source": "vector_robot"})
    await db.execute(
        """
        INSERT INTO butler.conversation_history (user_id, channel, role, content, metadata)
        VALUES ($1, $2, 'user', $3, $4::jsonb)
        """,
        VECTOR_USER_ID, VECTOR_CHANNEL, user_message, metadata,
    )
    await db.execute(
        """
        INSERT INTO butler.conversation_history (user_id, channel, role, content, metadata)
        VALUES ($1, $2, 'assistant', $3, $4::jsonb)
        """,
        VECTOR_USER_ID, VECTOR_CHANNEL, response_text, metadata,
    )

    # Auto-learn facts in background
    asyncio.create_task(
        extract_and_store_facts(
            pool, VECTOR_USER_ID, user_message, response_text,
            get_embedding_service(),
        )
    )

    # Return OpenAI-format response
    return OpenAIChatResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=req.model or settings.anthropic_model,
        choices=[{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": response_text,
            },
            "finish_reason": "stop",
        }],
        usage={
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    )
