"""Custom LiveKit Agents LLM plugin that streams from Butler API.

Butler API handles the Claude conversation (tool use, memory, personality)
and exposes a streaming SSE endpoint. This plugin consumes that stream and
emits ChatChunk objects that the AgentSession feeds to TTS.

SSE protocol from Butler API:
    data: {"delta": "Hello"}
    data: {"delta": " there!"}
    data: [DONE]
"""

from __future__ import annotations

import json
import logging

import aiohttp
from livekit.agents import llm
from livekit.agents.llm import ChatChunk, ChoiceDelta
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

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

    async def _run(self) -> None:
        """Stream text from Butler API and emit as ChatChunks."""
        # Extract the last user message text from the chat context
        transcript = ""
        for item in reversed(self.chat_ctx.items):
            if hasattr(item, "role") and item.role == "user":
                if hasattr(item, "text_content"):
                    transcript = item.text_content
                elif isinstance(item.content, str):
                    transcript = item.content
                elif isinstance(item.content, list):
                    transcript = " ".join(
                        p.text for p in item.content if hasattr(p, "text")
                    )
                else:
                    logger.warning("Unexpected content type: %s", type(item.content))
                    transcript = str(item.content)
                break

        if not transcript:
            logger.warning("No user message found in chat context")
            return

        payload = {
            "transcript": transcript,
            "user_id": self._user_id,
            "session_id": self._session_id,
        }
        headers = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        headers["Content-Type"] = "application/json"

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
                            delta_text = data.get("delta", "")
                            if delta_text:
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


class ButlerLLM(llm.LLM):
    """LiveKit LLM plugin that delegates to Butler API for conversation."""

    def __init__(
        self,
        *,
        butler_url: str,
        api_key: str,
        user_id: str,
        session_id: str,
    ):
        super().__init__()
        self._butler_url = butler_url
        self._api_key = api_key
        self._user_id = user_id
        self._session_id = session_id

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
            llm_instance=self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
        )
