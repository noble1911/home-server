"""Run the repo's agent.py (mounted at /agent) with local Whisper instead of Groq.

Job processes import this module (the entrypoint is pickled from it), so the
STT swap applies there too. Everything else is the real agent.
"""
import os, sys

sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), os.environ.get("HARNESS_AGENT_DIR", "/agent")]
for _k, _v in dict(LIVEKIT_API_KEY="devkey", LIVEKIT_API_SECRET="secret", GROQ_API_KEY="unused").items():
    os.environ.setdefault(_k, _v)

from livekit.plugins import groq  # noqa: E402
import whisper_stt  # noqa: E402

groq.STT = whisper_stt.WhisperSTT

import agent  # noqa: E402
from livekit.agents import WorkerOptions, cli  # noqa: E402


def prewarm(proc):
    agent.prewarm(proc)
    whisper_stt.model()


async def entrypoint(ctx):
    await agent.entrypoint(ctx)


if __name__ == "__main__":
    sys.argv = [sys.argv[0], "start", "--log-level", os.environ.get("HARNESS_LOG_LEVEL", "info")]
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm, num_idle_processes=1))
