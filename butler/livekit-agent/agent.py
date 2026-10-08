"""LiveKit Agents voice worker for Butler.

Orchestrates the voice pipeline:
  User speaks → [Silero VAD] → [Groq Whisper STT] → [Butler API SSE] → [Kokoro TTS] → User hears

Talks to the Butler app over the room (#217, #219):
  → app   {"type": "agent_state", "state": "thinking" | "speaking" | "idle"}
  ← app   {"type": "interrupt"} on the "butler-control" topic: stop speaking now
  ← app   participant attribute speak_replies="false": answer in text only (TTS is
          skipped entirely, not just muted); can change mid-conversation
  ← app   the mic's mute state is push-to-talk: unmuted = holding the button (one
          turn, however long you pause), muted = let go (Butler answers now)
  ← app   pre-connect audio: what you said while Butler was joining is handed over
          when it arrives, so the first words of a conversation aren't lost

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
from livekit.agents.voice import room_io
from livekit.plugins import groq, openai, silero

from butler_llm import ButlerLLM
from config import settings

DEFAULT_VOICE = "bf_emma"
CONTROL_TOPIC = "butler-control"
MIC = rtc.TrackSource.SOURCE_MICROPHONE
# How long to wait for the app's pre-connect audio. LiveKit's default (3s) is
# too short over the internet: the buffer only finishes once the phone's
# connection is fully up. 10s matches how long the app keeps recording it.
PRE_CONNECT_AUDIO_TIMEOUT = 10.0

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


def prewarm(proc: agents.JobProcess) -> None:
    """Load the VAD model once per worker process, not on every call."""
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: agents.JobContext) -> None:
    """Called when the app opens a voice room.

    Room name format: 'butler_{user_id}_{session_hex}', set by Butler
    API's /api/auth/token endpoint. The app opens a fresh room on its first
    mic press (and after a disconnect), so a fresh agent is always dispatched.
    """
    # Room name: "butler_{user_id}_{hex}" — strip prefix and session suffix
    parts = ctx.job.room.name.removeprefix("butler_")
    user_id = parts.rsplit("_", 1)[0] if "_" in parts else parts
    session_id = str(uuid.uuid4())

    voice = await _fetch_user_voice(user_id)
    logger.info("Voice session started for user=%s room=%s voice=%s", user_id, ctx.job.room.name, voice)

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
        # VAD: Silero (runs locally on CPU), loaded once in prewarm
        vad=ctx.proc.userdata["vad"],
        # Until the first press; VoiceControls switches to push-to-talk turns
        turn_detection="vad",
    )
    controls = VoiceControls(session, ctx.room)
    controls.attach()

    # Start before joining: LiveKit only accepts the app's pre-connect audio
    # (what you said while Butler was joining) if the session is listening first
    await session.start(
        room=ctx.room,
        agent=ButlerAgent(user_id),
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(pre_connect_audio_timeout=PRE_CONNECT_AUDIO_TIMEOUT),
        ),
    )
    await ctx.connect()

    # No spoken greeting: you're usually already talking by the time Butler joins
    controls.start(await ctx.wait_for_participant())


class VoiceControls:
    """Wires the app's controls to the session: push-to-talk turns, stop, read
    aloud on/off, and Butler's state for the app to show.

    Push-to-talk follows the app's mic: unmuted means the button is held, so
    Butler stops talking and listens, however long you pause; muted means you
    let go, so everything said is one turn and Butler answers straight away.
    """

    def __init__(self, session: AgentSession, room: rtc.Room) -> None:
        self._session = session
        self._room = room
        self.speaking_enabled = True
        self._user: str | None = None
        self._turn_open = False
        self._heard_user = False  # the VAD has heard you during this turn
        self._tasks: set[asyncio.Task] = set()

    def attach(self) -> None:
        self._session.on("agent_state_changed", self._on_state)
        self._session.on("user_state_changed", self._on_user_state)
        self._room.on("data_received", self._on_data)
        self._room.on("participant_attributes_changed", self._on_attributes)
        self._room.on("track_published", self._on_track_published)
        self._room.on("track_unmuted", self._on_unmuted)
        self._room.on("track_muted", self._on_muted)

    def start(self, user: rtc.RemoteParticipant) -> None:
        """Pick up the app's settings, and whether the button is already held."""
        self._user = user.identity
        self.set_speaking_enabled(speak_replies(user.attributes))
        mic = next((p for p in user.track_publications.values() if p.source == MIC), None)
        if mic is not None and not mic.muted:
            # Pressed before Butler joined: keep what's been said (the pre-connect audio)
            self._begin_turn(fresh=False)
        # Otherwise, if you already let go, the default VAD turn detection
        # ends the turn once the pre-connect audio has been heard

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

    def _begin_turn(self, *, fresh: bool) -> None:
        """You pressed the mic: Butler stops talking and listens until you let go."""
        if fresh:
            self.interrupt()
            self._session.clear_user_turn()  # drop anything left from before the press
        self._session.update_options(turn_detection="manual")
        self._session.input.set_audio_enabled(True)
        self._turn_open = True
        self._heard_user = False

    def _end_turn(self) -> None:
        """You let go: what you said is one turn, answered now."""
        if not self._turn_open:
            return
        self._turn_open = False
        if not self._heard_user:
            # Nothing heard yet: you let go before Butler had joined, and what you
            # said (the pre-connect audio) is still on its way. Committing now would
            # drop it, so let the VAD end this turn once it's been heard.
            logger.info("Released before Butler heard anything; the turn ends on silence")
            self._session.update_options(turn_detection="vad")
            return
        logger.info("Released; answering")
        # Detaching the input makes commit flush the STT with silence, so the
        # last words are transcribed without waiting for the VAD to time out
        self._session.input.set_audio_enabled(False)
        self._session.commit_user_turn(transcript_timeout=5.0)

    def _is_user_mic(self, participant: rtc.Participant, publication: rtc.TrackPublication) -> bool:
        return publication.source == MIC and participant.identity == self._user

    def _on_track_published(self, publication: rtc.RemoteTrackPublication, participant) -> None:
        if self._is_user_mic(participant, publication) and not publication.muted:
            self._begin_turn(fresh=False)  # the press that opened this room

    def _on_unmuted(self, participant, publication) -> None:
        if self._is_user_mic(participant, publication):
            self._begin_turn(fresh=True)

    def _on_muted(self, participant, publication) -> None:
        if self._is_user_mic(participant, publication):
            self._end_turn()

    def _on_user_state(self, ev) -> None:
        if ev.new_state == "speaking":
            self._heard_user = True

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
        prewarm_fnc=prewarm,
        num_idle_processes=1,  # Reduce idle workers — 4+ idle processes cause unresponsive warnings
    ))
