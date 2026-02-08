"""LiveKit Agents voice worker for Butler.

Orchestrates the voice pipeline:
  User speaks → [Silero VAD] → [Groq Whisper STT] → [Butler API SSE] → [Kokoro TTS] → User hears

Run in development: python agent.py dev
Run in production:  python agent.py start
"""

from __future__ import annotations

import logging
import uuid

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, cli
from livekit.plugins import groq, openai, silero

from butler_llm import ButlerLLM
from config import settings

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

    logger.info("Voice session started for user=%s room=%s", user_id, ctx.room.name)

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
        ),
        # TTS: Kokoro via OpenAI-compatible endpoint
        tts=openai.TTS(
            base_url=f"{settings.kokoro_url}/v1",
            api_key="not-needed",
            model="kokoro",
            voice="bf_emma",
        ),
        # VAD: Silero (runs locally on CPU)
        vad=silero.VAD.load(),
    )

    await session.start(room=ctx.room, agent=ButlerAgent(user_id))

    # Greet the user directly via TTS (bypasses LLM — instant feedback)
    await session.say("Hello! How can I help you?")


if __name__ == "__main__":
    cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
