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

Two-phase tool routing:
When many tools are registered, Phase 1 sends only a lightweight catalog
(~800 tokens) instead of all tool schemas (~15,000 tokens). Claude picks
which tools it needs via a `request_tools` meta-tool, then Phase 2 loads
only those schemas. This reduces API costs by 80-95%.
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


def _web_search_tool(model: str) -> dict:
    """Server-side web search definition for the model in use.

    Opus 5 / Sonnet 5 / the 4.6+ family take the dynamic-filtering variant;
    Haiku 4.5 and older only accept the basic one.
    """
    basic = model.startswith("claude-haiku-4-5") or model.startswith("claude-3")
    return {
        "type": "web_search_20250305" if basic else "web_search_20260209",
        "name": "web_search",
        "max_uses": settings.web_search_max_uses,
    }


def _request_kwargs(model: str) -> dict:
    """Per-model request options: effort where the model supports it."""
    if model.startswith("claude-haiku-4-5") or model.startswith("claude-3"):
        return {}
    return {"output_config": {"effort": settings.chat_effort}}


def _refusal_text() -> str:
    return "I can't help with that one."


def _build_tool_definitions(tools: dict[str, Tool], model: str) -> list[dict]:
    """Full schemas for `tools` plus web search (no cache marker yet)."""
    defs = [tool_to_anthropic_schema(t) for t in tools.values()]
    if settings.web_search_enabled:
        defs.append(_web_search_tool(model))
    return defs


# ── Two-phase tool routing ──────────────────────────────────────────

# Tools always sent with full schemas (small, frequently used).
# Others go in the lightweight catalog and are loaded on demand.
ROUTING_CORE_TOOLS: set[str] = {
    "remember_fact", "recall_facts", "get_user",
    "weather", "display_in_chat", "display_on_device", "display_image",
    "radarr", "seerr", "books", "sonarr", "qbittorrent",
    # Escalation path for server fixes — keep core so Claude reliably knows it
    # can delegate to a real shell without first round-tripping request_tools.
    "run_claude_code",
}

# Only enable routing when there are this many non-core tools.
ROUTING_MIN_TOOLS = 4

# Meta-tool schema for requesting additional tools.
_REQUEST_TOOLS_SCHEMA: dict = {
    "name": "request_tools",
    "description": (
        "Activate additional tools to fulfill the user's request. "
        "Review the ADDITIONAL TOOLS list in your instructions and "
        "request the ones you need. You can request multiple at once."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tool names from the ADDITIONAL TOOLS list.",
            },
        },
        "required": ["tools"],
    },
}


def _build_tool_catalog(tools: dict[str, Tool], active_names: set[str]) -> str:
    """One line per *inactive* tool, for the system prompt.

    Active tools already have full schemas; the rest are listed by name so
    Claude can activate them with request_tools.
    """
    lines = [
        "ADDITIONAL TOOLS (call request_tools to activate any you need, then use them):",
    ]
    for name in sorted(tools):
        if name in active_names:
            continue
        # Enough of the description to tell what the tool can do (the first
        # sentence alone hid e.g. Jellyfin's "recently added" and "now playing").
        desc = " ".join(tools[name].description.split())
        if len(desc) > 220:
            desc = desc[:217].rsplit(" ", 1)[0] + "..."
        actions = (tools[name].parameters or {}).get("properties", {}).get("action", {}).get("enum")
        suffix = f" [actions: {', '.join(actions)}]" if actions else ""
        lines.append(f"- {name}: {desc}{suffix}")
    return "\n".join(lines)


class _ToolRouter:
    """Manage tool routing state across API rounds.

    Round 1 sends full schemas for the small *core* set plus a one-line
    catalog of everything else and a `request_tools` meta-tool. Tools
    activated via request_tools (or called directly by name — Claude
    sometimes skips the meta-tool) get their schemas on later rounds.

    Model choice: if `settings.routing_model` is set, it handles rounds until
    the first tool is used; the main model always writes the answer. With
    it unset (the default) the main model does everything, which keeps a
    single prompt cache.
    """

    def __init__(
        self,
        all_tools: dict[str, Tool],
        system_blocks: list[dict],
    ) -> None:
        self._all_tools = all_tools
        self._base_blocks = system_blocks
        self._tools_used = False

        core_names = ROUTING_CORE_TOOLS & set(all_tools)
        non_core_names = set(all_tools) - core_names
        self._enabled = (
            settings.tool_routing_enabled
            and len(non_core_names) >= ROUTING_MIN_TOOLS
        )
        start = {n: all_tools[n] for n in core_names} if self._enabled else dict(all_tools)
        self._active_tools: dict[str, Tool] = start

    # -- state ----------------------------------------------------------

    @property
    def model(self) -> str:
        if settings.routing_model and not self._tools_used:
            return settings.routing_model
        return settings.anthropic_model

    @property
    def request_kwargs(self) -> dict:
        return _request_kwargs(self.model)

    @property
    def active_tools(self) -> dict[str, Tool]:
        return self._active_tools

    @property
    def _inactive_names(self) -> set[str]:
        return set(self._all_tools) - set(self._active_tools)

    def note_tool_use(self) -> None:
        self._tools_used = True

    # -- request shaping -------------------------------------------------

    @property
    def tool_definitions(self) -> list[dict]:
        defs = [tool_to_anthropic_schema(t) for t in self._active_tools.values()]
        if self._inactive_names:
            defs.append(_REQUEST_TOOLS_SCHEMA)
        if settings.web_search_enabled:
            defs.append(_web_search_tool(self.model))
        # Anthropic caches all tool schemas up to the one with cache_control.
        if defs:
            defs[-1] = {**defs[-1], "cache_control": {"type": "ephemeral"}}
        return defs

    @property
    def system_blocks(self) -> list[dict]:
        if not self._inactive_names:
            return self._base_blocks
        return self._base_blocks + [{
            "type": "text",
            "text": _build_tool_catalog(self._all_tools, set(self._active_tools)),
            "cache_control": {"type": "ephemeral"},
        }]

    # -- activation ------------------------------------------------------

    def handle_request_tools(self, tool_names: list[str]) -> str:
        valid = [n for n in tool_names if n in self._all_tools]
        invalid = [n for n in tool_names if n not in self._all_tools]
        for n in valid:
            self._active_tools[n] = self._all_tools[n]
        self._tools_used = True
        parts = []
        if valid:
            parts.append(f"Tools activated: {', '.join(valid)}. You can now use them.")
        if invalid:
            parts.append(f"Unknown tools (ignored): {', '.join(invalid)}")
        logger.info("Tool routing: requested=%s valid=%s", tool_names, valid)
        return " ".join(parts) or "No valid tools requested."

    def resolve(self, name: str) -> Tool | None:
        """Tool for a tool_use block, activating it if Claude skipped request_tools."""
        tool = self._active_tools.get(name)
        if tool is None and name in self._all_tools:
            tool = self._all_tools[name]
            self._active_tools[name] = tool
            logger.info("Tool routing: auto-activated %s (called without request_tools)", name)
        return tool


async def _run_tool_block(
    block,
    router: _ToolRouter,
    *,
    db_pool: DatabasePool | None,
    user_id: str | None,
    channel: str | None,
) -> str:
    """Execute one tool_use block: routing meta-tool or a real tool (audited)."""
    if block.name == "request_tools":
        return router.handle_request_tools(block.input.get("tools", []))
    router.resolve(block.name)
    router.note_tool_use()
    return await execute_and_log_tool(
        block.name, block.input, router.active_tools,
        db_pool=db_pool, user_id=user_id, channel=channel,
    )


# ── Message building ────────────────────────────────────────────────

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


# ── Tool execution helpers ──────────────────────────────────────────

async def _execute_tool_blocks(
    tool_use_blocks: list,
    router: _ToolRouter,
    *,
    db_pool: DatabasePool | None = None,
    user_id: str | None = None,
    channel: str | None = None,
) -> list[dict]:
    """Execute tool blocks and return results, handling request_tools specially.

    If request_tools is among the blocks, it transitions the router to
    execution phase. Other tools are executed normally via active_tools.
    """
    tool_results: list[dict] = []
    for block in tool_use_blocks:
        result = await _run_tool_block(
            block, router, db_pool=db_pool, user_id=user_id, channel=channel,
        )
        tool_results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": result,
        })
    return tool_results


# ── Main API functions ──────────────────────────────────────────────

async def chat_with_tools(
    system_prompt: list[dict],
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

    When tool routing is enabled, Phase 1 sends only a lightweight catalog
    instead of all tool schemas. Claude picks tools via request_tools, then
    Phase 2 loads the selected schemas.

    Args:
        system_prompt: System prompt content blocks from context.py
        user_message: User's text message or voice transcript
        tools: Dict of tool_name -> Tool instance
        max_tool_rounds: Safety limit on tool use iterations
        history: Previous conversation messages for multi-turn context

    Returns:
        Claude's final text response
    """
    client = _get_client()
    router = _ToolRouter(tools, system_prompt)
    messages = _build_messages(user_message, history, image=image)

    for round_num in range(max_tool_rounds):
        response = await client.messages.create(
            model=router.model,
            max_tokens=settings.max_tokens,
            system=router.system_blocks,
            tools=router.tool_definitions,
            messages=messages,
            **router.request_kwargs,
        )

        if response.stop_reason == "refusal":
            return _refusal_text()

        # Extract custom tool use blocks (server-side tools like web_search
        # have type "server_tool_use" and are handled by Anthropic automatically)
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        # Server-side tool pause — Anthropic needs another round-trip to
        # finish processing (e.g. web search). Send the partial response
        # back without executing any custom tools.
        if not tool_use_blocks and response.stop_reason == "pause_turn":
            logger.info("Server-side tool pause (round %d), continuing", round_num + 1)
            messages.append({"role": "assistant", "content": response.content})
            continue

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

        # Execute tools (including request_tools routing)
        tool_results = await _execute_tool_blocks(
            tool_use_blocks, router,
            db_pool=db_pool, user_id=user_id, channel=channel,
        )

        # Send tool results back
        messages.append({"role": "user", "content": tool_results})

    # Exhausted tool rounds
    logger.warning("Exhausted %d tool rounds", max_tool_rounds)
    return "I'm sorry, I wasn't able to complete that request. Could you try again?"


async def stream_chat_with_tools(
    system_prompt: list[dict],
    user_message: str,
    tools: dict[str, Tool],
    max_tool_rounds: int = 5,
    *,
    history: list[dict] | None = None,
    image: dict | None = None,
    db_pool: DatabasePool | None = None,
    user_id: str | None = None,
    channel: str | None = None,
) -> AsyncGenerator[str | dict, None]:
    """Stream Claude's response text, executing any tool calls between rounds.

    Like chat_with_tools() but yields text chunks as they arrive from
    Claude's streaming API. This enables the voice pipeline to start TTS
    on the first sentence while Claude is still generating.

    Each round is streamed: if Claude says "Let me check the lights" before
    calling a tool, those words are yielded immediately. After tool execution,
    the next round streams the result ("The lights are now on").

    Args:
        system_prompt: System prompt content blocks from context.py
        user_message: User's text message or voice transcript
        tools: Dict of tool_name -> Tool instance
        max_tool_rounds: Safety limit on tool use iterations
        history: Previous conversation messages for multi-turn context

    Yields:
        Text chunks as they arrive from Claude's streaming API
    """
    client = _get_client()
    router = _ToolRouter(tools, system_prompt)
    messages = _build_messages(user_message, history, image=image)

    for round_num in range(max_tool_rounds):
        async with client.messages.stream(
            model=router.model,
            max_tokens=settings.max_tokens,
            system=router.system_blocks,
            tools=router.tool_definitions,
            messages=messages,
            **router.request_kwargs,
        ) as stream:
            # Iterate raw events (instead of text_stream) so we can detect
            # server-side tool activity and yield spoken feedback for TTS.
            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "server_tool_use":
                        yield "Let me look that up. "
                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield event.delta.text

            response = await stream.get_final_message()

        if response.stop_reason == "refusal":
            yield _refusal_text()
            return

        # Check if Claude requested custom tool use
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_use_blocks and response.stop_reason == "pause_turn":
            logger.info("Server-side tool pause in voice stream (round %d)", round_num + 1)
            messages.append({"role": "assistant", "content": response.content})
            continue

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
            # Intercept display_in_chat: yield visual event before executing
            if block.name == "display_in_chat":
                yield {
                    "type": "visual_content",
                    "content": block.input.get("content", ""),
                    "title": block.input.get("title", ""),
                }

            # Intercept display_on_device: yield a structured card event for the
            # esp-gateway to forward to the physical device screen.
            if block.name == "display_on_device":
                yield {"type": "device_card", "card": dict(block.input)}

            # Intercept display_image: yield an SVG event; the esp-gateway rasterizes
            # it to a PNG and sends it to the device.
            if block.name == "display_image":
                yield {"type": "device_image", "svg": block.input.get("svg", "")}

            result = await _run_tool_block(
                block, router, db_pool=db_pool, user_id=user_id, channel=channel,
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
    system_prompt: list[dict],
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
    router = _ToolRouter(tools, system_prompt)
    messages = _build_messages(user_message, history, image=image)

    for round_num in range(max_tool_rounds):
        web_search_active = False

        async with client.messages.stream(
            model=router.model,
            max_tokens=settings.max_tokens,
            system=router.system_blocks,
            tools=router.tool_definitions,
            messages=messages,
            **router.request_kwargs,
        ) as stream:
            # Iterate raw streaming events instead of text_stream so we can
            # detect server-side tool activity (web search) and emit UI events.
            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "server_tool_use":
                        web_search_active = True
                        yield {"type": "tool_start", "tool": block.name}
                    elif block.type == "web_search_tool_result" and web_search_active:
                        web_search_active = False
                        yield {"type": "tool_end", "tool": "web_search"}
                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield {"type": "text_delta", "delta": event.delta.text}

            # Safety: close indicator if stream ended mid-search
            if web_search_active:
                yield {"type": "tool_end", "tool": "web_search"}

            response = await stream.get_final_message()

        if response.stop_reason == "refusal":
            yield {"type": "text_delta", "delta": _refusal_text()}
            return

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_use_blocks and response.stop_reason == "pause_turn":
            logger.info("Server-side tool pause in event stream (round %d)", round_num + 1)
            messages.append({"role": "assistant", "content": response.content})
            continue

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
            if block.name == "request_tools":
                result = router.handle_request_tools(
                    block.input.get("tools", []),
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
                continue

            yield {"type": "tool_start", "tool": block.name}

            result = await _run_tool_block(
                block, router, db_pool=db_pool, user_id=user_id, channel=channel,
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
