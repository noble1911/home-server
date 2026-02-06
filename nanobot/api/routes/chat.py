"""Text chat route.

POST /api/chat — PWA sends a text message, gets an AI response.
Same pipeline as voice but with 'pwa' channel tag.
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends

from tools import DatabasePool, Tool

from ..context import load_user_context
from ..deps import get_current_user, get_db_pool, get_tools
from ..llm import chat_with_tools
from ..models import ChatRequest, ChatResponse

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

    response_text = await chat_with_tools(
        system_prompt=ctx.system_prompt,
        user_message=req.message,
        tools=tools,
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
