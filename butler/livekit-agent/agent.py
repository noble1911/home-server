"""LiveKit Agents voice worker for Butler.

Orchestrates the voice pipeline:
  User speaks → [Silero VAD] → [Groq Whisper STT] → [Butler API SSE] → [Kokoro TTS] → User hears

Run in development: python agent.py dev
Run in production:  python agent.py start
"""

from __future__ import annotations

import logging
import uuid

import aiohttp
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, cli
from livekit.plugins import groq, openai, silero

from butler_llm import ButlerLLM
from config import settings

DEFAULT_VOICE = "bf_emma"

load_dotenv()

logger = logging.getLogger(__name__)


class ButlerAgent(Agent):
    """Agent identity passed to the session."""

    def __init__(self, user_id: str) -> None:
        super().__init__(
            instructions=(
                "You are Butler, a friendly and helpful home assistant. "
                "Keep responses concise and natural for voice conversation."
            ),
        )
        self.user_id = user_id


async def _fetch_user_voice(user_id: str) -> str:
    """Fetch the user's preferred TTS voice from Butler API.

    Returns the voice ID (e.g. 'bf_emma') or the default on any error.
    """
    url = f"{settings.butler_api_url}/api/voice/user-voice/{user_id}"
    headers = {}
    if settings.butler_api_key:
        headers["X-API-Key"] = settings.butler_api_key
    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("voice") or DEFAULT_VOICE
    except Exception:
        logger.warning("Failed to fetch voice preference for user=%s, using default", user_id)
    return DEFAULT_VOICE


async def entrypoint(ctx: agents.JobContext) -> None:
    """Called when a user joins a LiveKit room.

    Room name format: 'butler_{user_id}_{session_hex}', set by Butler
    API's /api/auth/token endpoint. Each voice button press creates a
    unique room so a fresh agent is always dispatched.
    """
    await ctx.connect()

    # Room name: "butler_{user_id}_{hex}" — strip prefix and session suffix
    parts = ctx.room.name.removeprefix("butler_")
    user_id = parts.rsplit("_", 1)[0] if "_" in parts else parts
    session_id = str(uuid.uuid4())

    voice = await _fetch_user_voice(user_id)
    logger.info("Voice session started for user=%s room=%s voice=%s", user_id, ctx.room.name, voice)

    session = AgentSession(
        # STT: Groq Whisper (cloud, ~50ms, free tier)
        stt=groq.STT(
            model="whisper-large-v3-turbo",
            language="en",
        ),
        # LLM: Butler API (streams Claude response via SSE)
        llm=ButlerLLM(
            butler_url=settings.butler_api_url,
            api_key=settings.butler_api_key,
            user_id=user_id,
            session_id=session_id,
            room=ctx.room,
        ),
        # TTS: Kokoro via OpenAI-compatible endpoint
        tts=openai.TTS(
            base_url=f"{settings.kokoro_url}/v1",
            api_key="not-needed",
            model="kokoro",
            voice=voice,
        ),
        # VAD: Silero (runs locally on CPU)
        vad=silero.VAD.load(),
    )

    await session.start(room=ctx.room, agent=ButlerAgent(user_id))

    # Greet the user directly via TTS (bypasses LLM — instant feedback)
    await session.say("Hello! How can I help you?")


if __name__ == "__main__":
    cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
