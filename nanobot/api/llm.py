"""Claude API integration with multi-turn tool orchestration.

This module calls the Anthropic API directly using the existing Tool classes
from nanobot/tools/. The key adapter is tool_to_anthropic_schema() which
converts our OpenAI-format tool schemas to Anthropic's format.

The chat_with_tools() function implements the standard tool-use loop:
send message -> if Claude wants tools -> execute them -> send results -> repeat.
"""

from __future__ import annotations

import logging

import anthropic

from tools import Tool

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
            tool_name = block.name
            tool_input = block.input

            if tool_name in tools:
                try:
                    result = await tools[tool_name].execute(**tool_input)
                except Exception as e:
                    logger.exception("Tool %s execution failed", tool_name)
                    result = f"Error executing {tool_name}: {e}"
            else:
                result = f"Unknown tool: {tool_name}"

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
