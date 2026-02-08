"""Claude API integration with multi-turn tool orchestration.

This module calls the Anthropic API directly using the existing Tool classes
from tools/. The key adapter is tool_to_anthropic_schema() which
converts our OpenAI-format tool schemas to Anthropic's format.

Three main functions:
- chat_with_tools(): Batch mode — waits for full response (used by text chat)
- stream_chat_with_tools(): Streaming mode — yields text chunks via SSE (used by voice)
- stream_chat_with_events(): Event streaming — yields structured events (used by PWA)

All three accept an optional `history` parameter for multi-turn conversation
context. History messages are prepended to the messages array so Claude sees
the full conversation.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

import anthropic

from tools import DatabasePool, Tool

from .audit import execute_and_log_tool
from .config import settings

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    """Lazy-initialize the Anthropic client."""
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def tool_to_anthropic_schema(tool: Tool) -> dict:
    """Convert a Tool's OpenAI-format schema to Anthropic's format.

    OpenAI: {"type": "function", "function": {"name", "description", "parameters"}}
    Anthropic: {"name", "description", "input_schema"}

    The JSON Schema for parameters is identical; only the wrapper differs.
    """
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.parameters,
    }


def _build_messages(
    user_message: str,
    history: list[dict] | None = None,
    *,
    image: dict | None = None,
) -> list[dict]:
    """Build the messages array with optional conversation history.

    Prepends history messages, then appends the current user message.
    Ensures the first message is always from the user role (Claude API requirement)
    by stripping any leading assistant messages from history.

    When *image* is provided (``{"data": ..., "media_type": ...}``), the
    current user message is formatted as a list of content blocks so Claude
    receives both the image and text together.
    """
    messages: list[dict] = []

    if history:
        # Skip leading assistant messages — Claude requires the first message
        # to have role "user". This can happen when the user's oldest message
        # aged out of the history window.
        started = False
        for msg in history:
            if not started:
                if msg["role"] != "user":
                    continue
                started = True
            messages.append({"role": msg["role"], "content": msg["content"]})

    # Build the content for the current user message.
    if image:
        content: str | list[dict] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image["media_type"],
                    "data": image["data"],
                },
            },
            {"type": "text", "text": user_message},
        ]
    else:
        content = user_message

    # Claude requires strict user/assistant alternation. If history ends
    # with a user message (e.g. the previous assistant reply wasn't stored),
    # merge into it to avoid consecutive user messages.
    if messages and messages[-1]["role"] == "user":
        prev = messages[-1]["content"]
        if image or isinstance(prev, list):
            # Either the new message has an image, or the previous message
            # already uses content-block format (e.g. from a prior image
            # turn). Normalise both sides into block lists and merge.
            # Note: content values are always str or list[dict] here.
            if isinstance(prev, str):
                prev_blocks = [{"type": "text", "text": prev}]
            else:
                prev_blocks = list(prev)

            if isinstance(content, str):
                new_blocks: list[dict] = [{"type": "text", "text": content}]
            else:
                new_blocks = list(content)

            messages[-1]["content"] = prev_blocks + new_blocks
        else:
            messages[-1]["content"] += "\n\n" + user_message
    else:
        messages.append({"role": "user", "content": content})

    return messages


async def chat_with_tools(
    system_prompt: str,
    user_message: str,
    tools: dict[str, Tool],
    max_tool_rounds: int = 5,
    *,
    history: list[dict] | None = None,
    image: dict | None = None,
    db_pool: DatabasePool | None = None,
    user_id: str | None = None,
    channel: str | None = None,
) -> str:
    """Send a message to Claude, execute any tool calls, and return the response.

    Implements the multi-turn tool use loop:
    1. Send conversation history + user message + tool definitions to Claude
    2. If response has tool_use blocks, execute each tool
    3. Send tool results back and repeat
    4. Return final text when Claude responds without tool use

    Args:
        system_prompt: Personalized system prompt from context.py
        user_message: User's text message or voice transcript
        tools: Dict of tool_name -> Tool instance
        max_tool_rounds: Safety limit on tool use iterations
        history: Previous conversation messages for multi-turn context

    Returns:
        Claude's final text response
    """
    client = _get_client()
    tool_definitions = [tool_to_anthropic_schema(t) for t in tools.values()]
    messages = _build_messages(user_message, history, image=image)

    for round_num in range(max_tool_rounds):
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.max_tokens,
            system=system_prompt,
            tools=tool_definitions if tools else [],
            messages=messages,
        )

        # Extract tool use blocks
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_use_blocks:
            # No tool use — extract text and return
            text_parts = [b.text for b in response.content if b.type == "text"]
            return " ".join(text_parts) if text_parts else ""

        logger.info(
            "Tool use round %d: %s",
            round_num + 1,
            [b.name for b in tool_use_blocks],
        )

        # Append the full assistant response (including tool_use blocks)
        messages.append({"role": "assistant", "content": response.content})

        # Execute tools and collect results
        tool_results = []
        for block in tool_use_blocks:
            result = await execute_and_log_tool(
                block.name, block.input, tools,
                db_pool=db_pool, user_id=user_id, channel=channel,
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                }
            )

        # Send tool results back
        messages.append({"role": "user", "content": tool_results})

    # Exhausted tool rounds
    logger.warning("Exhausted %d tool rounds", max_tool_rounds)
    return "I'm sorry, I wasn't able to complete that request. Could you try again?"


async def stream_chat_with_tools(
    system_prompt: str,
    user_message: str,
    tools: dict[str, Tool],
    max_tool_rounds: int = 5,
    *,
    history: list[dict] | None = None,
    image: dict | None = None,
    db_pool: DatabasePool | None = None,
    user_id: str | None = None,
    channel: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream Claude's response text, executing any tool calls between rounds.

    Like chat_with_tools() but yields text chunks as they arrive from
    Claude's streaming API. This enables the voice pipeline to start TTS
    on the first sentence while Claude is still generating.

    Each round is streamed: if Claude says "Let me check the lights" before
    calling a tool, those words are yielded immediately. After tool execution,
    the next round streams the result ("The lights are now on").

    Args:
        system_prompt: Personalized system prompt from context.py
        user_message: User's text message or voice transcript
        tools: Dict of tool_name -> Tool instance
        max_tool_rounds: Safety limit on tool use iterations
        history: Previous conversation messages for multi-turn context

    Yields:
        Text chunks as they arrive from Claude's streaming API
    """
    client = _get_client()
    tool_definitions = [tool_to_anthropic_schema(t) for t in tools.values()]
    messages = _build_messages(user_message, history, image=image)

    for round_num in range(max_tool_rounds):
        async with client.messages.stream(
            model=settings.anthropic_model,
            max_tokens=settings.max_tokens,
            system=system_prompt,
            tools=tool_definitions if tools else [],
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text

            response = await stream.get_final_message()

        # Check if Claude requested tool use
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_use_blocks:
            return  # Done — all text has been yielded

        logger.info(
            "Streaming tool use round %d: %s",
            round_num + 1,
            [b.name for b in tool_use_blocks],
        )

        # Append assistant response and execute tools
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in tool_use_blocks:
            result = await execute_and_log_tool(
                block.name, block.input, tools,
                db_pool=db_pool, user_id=user_id, channel=channel,
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    # Exhausted tool rounds
    logger.warning("Exhausted %d streaming tool rounds", max_tool_rounds)
    yield "I'm sorry, I wasn't able to complete that request. Could you try again?"


async def stream_chat_with_events(
    system_prompt: str,
    user_message: str,
    tools: dict[str, Tool],
    max_tool_rounds: int = 5,
    *,
    history: list[dict] | None = None,
    image: dict | None = None,
    db_pool: DatabasePool | None = None,
    user_id: str | None = None,
    channel: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream Claude's response as structured events, including tool lifecycle.

    Like stream_chat_with_tools() but yields dicts with a ``type`` field so
    callers can distinguish text chunks from tool invocations:

    - ``{"type": "text_delta", "delta": "..."}``  — text as it arrives
    - ``{"type": "tool_start", "tool": "weather"}`` — tool execution begins
    - ``{"type": "tool_end", "tool": "weather"}``   — tool execution finished

    Used by the PWA chat streaming endpoint to surface tool activity in the UI.
    """
    client = _get_client()
    tool_definitions = [tool_to_anthropic_schema(t) for t in tools.values()]
    messages = _build_messages(user_message, history, image=image)

    for round_num in range(max_tool_rounds):
        async with client.messages.stream(
            model=settings.anthropic_model,
            max_tokens=settings.max_tokens,
            system=system_prompt,
            tools=tool_definitions if tools else [],
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield {"type": "text_delta", "delta": text}

            response = await stream.get_final_message()

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_use_blocks:
            return

        logger.info(
            "Event-stream tool use round %d: %s",
            round_num + 1,
            [b.name for b in tool_use_blocks],
        )

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in tool_use_blocks:
            yield {"type": "tool_start", "tool": block.name}

            result = await execute_and_log_tool(
                block.name, block.input, tools,
                db_pool=db_pool, user_id=user_id, channel=channel,
            )

            yield {"type": "tool_end", "tool": block.name}

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    logger.warning("Exhausted %d event-stream tool rounds", max_tool_rounds)
    yield {
        "type": "text_delta",
        "delta": "I'm sorry, I wasn't able to complete that request. Could you try again?",
    }
