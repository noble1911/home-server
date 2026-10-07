"""LiveKit Agents voice worker for Butler.

Orchestrates the voice pipeline:
  User speaks → [Silero VAD] → [Groq Whisper STT] → [Butler API SSE] → [Kokoro TTS] → User hears

Talks to the Butler app over the room (#217):
  → app   {"type": "agent_state", "state": "thinking" | "speaking" | "idle"}
  ← app   {"type": "interrupt"} on the "butler-control" topic: stop speaking now
  ← app   participant attribute speak_replies="false": answer in text only (TTS is
          skipped entirely, not just muted); can change mid-conversation

Run in development: python agent.py dev
Run in production:  python agent.py start
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

import aiohttp
from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, cli
from livekit.plugins import groq, openai, silero

from butler_llm import ButlerLLM
from config import settings

DEFAULT_VOICE = "bf_emma"
CONTROL_TOPIC = "butler-control"
GREETING = "Hello! How can I help you?"

# LiveKit's agent states, as the app understands them ("listening" = waiting for you).
APP_STATES = {"thinking": "thinking", "speaking": "speaking"}


def speak_replies(attributes: dict[str, str] | None) -> bool:
    """The app sets speak_replies="false" when "Read replies aloud" is off."""
    return (attributes or {}).get("speak_replies", "true").lower() != "false"

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
    controls = VoiceControls(session, ctx.room)
    controls.attach()

    user = await ctx.wait_for_participant()
    controls.set_speaking_enabled(speak_replies(user.attributes))

    # Greet the user directly via TTS (bypasses LLM — instant feedback)
    if controls.speaking_enabled:
        await session.say(GREETING)


class VoiceControls:
    """Wires the app's controls (stop, read aloud on/off) and state display to the session."""

    def __init__(self, session: AgentSession, room: rtc.Room) -> None:
        self._session = session
        self._room = room
        self.speaking_enabled = True
        self._tasks: set[asyncio.Task] = set()

    def attach(self) -> None:
        self._session.on("agent_state_changed", self._on_state)
        self._room.on("data_received", self._on_data)
        self._room.on("participant_attributes_changed", self._on_attributes)

    def set_speaking_enabled(self, enabled: bool) -> None:
        self.speaking_enabled = enabled
        # Takes effect from the next reply; interrupt to silence one already playing
        self._session.output.set_audio_enabled(enabled)
        if not enabled:
            self.interrupt()
        logger.info("Spoken replies %s", "on" if enabled else "off")

    def interrupt(self) -> None:
        """Stop the reply now. The user asked, so this overrides allow_interruptions."""
        try:
            self._session.interrupt(force=True)
        except RuntimeError:  # session not running (starting up or closing)
            pass

    def _on_state(self, ev) -> None:
        state = APP_STATES.get(ev.new_state, "idle")
        self._spawn(self._publish({"type": "agent_state", "state": state}))

    def _on_data(self, packet: rtc.DataPacket) -> None:
        if packet.topic != CONTROL_TOPIC:
            return
        try:
            message = json.loads(packet.data)
        except ValueError:
            return
        if message.get("type") == "interrupt":
            logger.info("Interrupted by the app")
            self.interrupt()

    def _on_attributes(self, changed: dict[str, str], participant) -> None:
        if "speak_replies" in changed:
            self.set_speaking_enabled(speak_replies(changed))

    async def _publish(self, message: dict) -> None:
        try:
            await self._room.local_participant.publish_data(json.dumps(message).encode(), reliable=True)
        except Exception:
            logger.debug("Couldn't publish %s", message.get("type"))

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


if __name__ == "__main__":
    cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        num_idle_processes=1,  # Reduce idle workers — 4+ idle processes cause unresponsive warnings
    ))
