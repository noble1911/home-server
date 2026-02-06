"""Claude API integration with multi-turn tool orchestration.

This module calls the Anthropic API directly using the existing Tool classes
from nanobot/tools/. The key adapter is tool_to_anthropic_schema() which
converts our OpenAI-format tool schemas to Anthropic's format.

Two main functions:
- chat_with_tools(): Batch mode — waits for full response (used by text chat)
- stream_chat_with_tools(): Streaming mode — yields text chunks via SSE (used by voice)
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


async def chat_with_tools(
    system_prompt: str,
    user_message: str,
    tools: dict[str, Tool],
    max_tool_rounds: int = 5,
    *,
    db_pool: DatabasePool | None = None,
    user_id: str | None = None,
    channel: str | None = None,
) -> str:
    """Send a message to Claude, execute any tool calls, and return the response.

    Implements the multi-turn tool use loop:
    1. Send user message + tool definitions to Claude
    2. If response has tool_use blocks, execute each tool
    3. Send tool results back and repeat
    4. Return final text when Claude responds without tool use

    Args:
        system_prompt: Personalized system prompt from context.py
        user_message: User's text message or voice transcript
        tools: Dict of tool_name -> Tool instance
        max_tool_rounds: Safety limit on tool use iterations

    Returns:
        Claude's final text response
    """
    client = _get_client()
    tool_definitions = [tool_to_anthropic_schema(t) for t in tools.values()]
    messages: list[dict] = [{"role": "user", "content": user_message}]

    for round_num in range(max_tool_rounds):
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
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

    Yields:
        Text chunks as they arrive from Claude's streaming API
    """
    client = _get_client()
    tool_definitions = [tool_to_anthropic_schema(t) for t in tools.values()]
    messages: list[dict] = [{"role": "user", "content": user_message}]

    for round_num in range(max_tool_rounds):
        async with client.messages.stream(
            model=settings.anthropic_model,
            max_tokens=1024,
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
    messages: list[dict] = [{"role": "user", "content": user_message}]

    for round_num in range(max_tool_rounds):
        async with client.messages.stream(
            model=settings.anthropic_model,
            max_tokens=1024,
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
