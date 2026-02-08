"""Custom LiveKit Agents LLM plugin that streams from Butler API.

Butler API handles the Claude conversation (tool use, memory, personality)
and exposes a streaming SSE endpoint. This plugin consumes that stream and
emits ChatChunk objects that the AgentSession feeds to TTS.

It also publishes data channel messages to the PWA for:
- User/assistant transcripts (so voice messages appear in chat)
- Visual content (rich markdown pushed by display_in_chat tool)

SSE protocol from Butler API:
    data: {"delta": "Hello"}
    data: {"delta": " there!"}
    data: {"type": "visual_content", "content": "...", "title": "..."}
    data: [DONE]
"""

from __future__ import annotations

import json
import logging

import aiohttp
from livekit.agents import llm
from livekit.agents.llm import ChatChunk, ChoiceDelta
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions
from livekit.rtc import Room

logger = logging.getLogger(__name__)


class ButlerLLMStream(llm.LLMStream):
    """Consumes SSE from Butler API's /api/voice/stream endpoint."""

    def __init__(
        self,
        *,
        butler_url: str,
        api_key: str,
        user_id: str,
        session_id: str,
        room: Room,
        llm_instance: llm.LLM,
        chat_ctx: llm.ChatContext,
        tools: list,
        conn_options: APIConnectOptions,
    ):
        super().__init__(
            llm=llm_instance,
            chat_ctx=chat_ctx,
            tools=tools,
            conn_options=conn_options,
        )
        self._butler_url = butler_url
        self._api_key = api_key
        self._user_id = user_id
        self._session_id = session_id
        self._room = room

    def _extract_transcript(self) -> str:
        """Extract the user's speech transcript from the chat context.

        LiveKit Agents populates chat_ctx.items with ChatMessage objects.
        For STT speech, the transcript is a user-role message. We also
        handle fallback cases where text may come from other roles
        (e.g. generate_reply instructions).
        """
        # Primary: find the last user message (regular STT speech)
        for item in reversed(self.chat_ctx.items):
            role = getattr(item, "role", None)
            if role == "user":
                text = getattr(item, "text_content", None)
                if text:
                    return text
                content = getattr(item, "content", None)
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts = [p.text for p in content if hasattr(p, "text")]
                    if parts:
                        return " ".join(parts)

        # Fallback: last non-empty text from any role (for generate_reply)
        for item in reversed(self.chat_ctx.items):
            role = getattr(item, "role", None)
            if role in ("system", "developer"):
                continue  # Skip system instructions
            text = getattr(item, "text_content", None)
            if text and text.strip():
                return text

        return ""

    async def _publish_data(self, message: dict) -> None:
        """Publish a JSON message to all room participants via data channel."""
        try:
            await self._room.local_participant.publish_data(
                json.dumps(message).encode(),
                reliable=True,
            )
        except Exception:
            logger.warning("Failed to publish data channel message: %s", message.get("type"))

    async def _run(self) -> None:
        """Stream text from Butler API and emit as ChatChunks."""
        transcript = self._extract_transcript()

        if not transcript:
            logger.warning("No transcript found in chat context, items: %s", [
                {"type": type(item).__name__, "role": getattr(item, "role", "?"),
                 "text": (getattr(item, "text_content", None) or str(getattr(item, "content", ""))[:80])}
                for item in self.chat_ctx.items
            ])
            return

        logger.info("Processing voice transcript: %s", transcript[:100])

        # Publish user transcript to chat
        await self._publish_data({
            "type": "user_transcript",
            "text": transcript,
            "isFinal": True,
        })

        payload = {
            "transcript": transcript,
            "user_id": self._user_id,
            "session_id": self._session_id,
        }
        headers = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        headers["Content-Type"] = "application/json"

        spoken_parts: list[str] = []

        try:
            timeout = aiohttp.ClientTimeout(total=90)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self._butler_url}/api/voice/stream",
                    json=payload,
                    headers=headers,
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error(
                            "Butler API returned %d: %s", resp.status, body
                        )
                        self._event_ch.send_nowait(
                            ChatChunk(
                                id="butler-error",
                                delta=ChoiceDelta(
                                    role="assistant",
                                    content="Sorry, I'm having trouble right now.",
                                ),
                            )
                        )
                        return

                    # Read SSE stream line-by-line (readline ensures
                    # complete lines even if TCP chunks split mid-event)
                    while True:
                        raw_line = await resp.content.readline()
                        if not raw_line:
                            break

                        line = raw_line.decode("utf-8").strip()
                        if not line:
                            continue
                        if not line.startswith("data: "):
                            continue

                        data_str = line[6:]  # Strip "data: " prefix
                        if data_str == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)

                            if data.get("type") == "visual_content":
                                # Visual content → data channel (not TTS)
                                await self._publish_data(data)
                            else:
                                # Spoken text → TTS
                                delta_text = data.get("delta", "")
                                if delta_text:
                                    spoken_parts.append(delta_text)
                                    self._event_ch.send_nowait(
                                        ChatChunk(
                                            id="butler",
                                            delta=ChoiceDelta(
                                                role="assistant",
                                                content=delta_text,
                                            ),
                                        )
                                    )
                        except json.JSONDecodeError:
                            logger.warning("Invalid SSE JSON: %s", data_str)

        except aiohttp.ClientError as e:
            logger.error("Butler API connection error: %s", e)
            self._event_ch.send_nowait(
                ChatChunk(
                    id="butler-error",
                    delta=ChoiceDelta(
                        role="assistant",
                        content="Sorry, I can't reach my brain right now.",
                    ),
                )
            )

        # Publish assistant transcript so it appears in chat
        full_spoken = "".join(spoken_parts)
        if full_spoken:
            await self._publish_data({
                "type": "assistant_transcript",
                "text": full_spoken,
                "isFinal": True,
            })


class ButlerLLM(llm.LLM):
    """LiveKit LLM plugin that delegates to Butler API for conversation."""

    def __init__(
        self,
        *,
        butler_url: str,
        api_key: str,
        user_id: str,
        session_id: str,
        room: Room,
    ):
        super().__init__()
        self._butler_url = butler_url
        self._api_key = api_key
        self._user_id = user_id
        self._session_id = session_id
        self._room = room

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        **kwargs,
    ) -> ButlerLLMStream:
        return ButlerLLMStream(
            butler_url=self._butler_url,
            api_key=self._api_key,
            user_id=self._user_id,
            session_id=self._session_id,
            room=self._room,
            llm_instance=self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
        )
