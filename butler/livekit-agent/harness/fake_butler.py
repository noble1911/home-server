"""Stand-in for Butler API and Kokoro in the voice harness.

Mints LiveKit tokens with the real butler/api/auth.py, records every transcript
the agent sends to /api/voice/stream (what Butler "heard"), and answers TTS with
a tone as long as the reply would take to say. Serves the test speech too.
"""
import io, os, sys, time, uuid

import av
import numpy as np
from aiohttp import web

BUTLER_DIR, WORK = "/butler", "/work"
os.environ.update(LIVEKIT_API_KEY="devkey", LIVEKIT_API_SECRET="secret")
sys.path.insert(0, BUTLER_DIR)
from api.auth import create_livekit_token  # noqa: E402  the real token grants

heard: list[dict] = []
PROFILE = {"id": "ron", "name": "Ron", "butlerName": "Butler", "role": "admin", "permissions": [],
           "createdAt": "2026-01-01T00:00:00Z", "facts": [],
           "soul": {"personality": "balanced", "verbosity": "concise", "humor": "subtle", "voice": "bf_emma"},
           "notificationPrefs": {"enabled": False, "categories": []}}


@web.middleware
async def cors(request, handler):
    try:
        resp = web.Response() if request.method == "OPTIONS" else await handler(request)
    except web.HTTPException as e:
        resp = e
    resp.headers.update({"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*",
                         "Access-Control-Allow-Methods": "*"})
    return resp


async def token(request):
    room = f"butler_ron_{uuid.uuid4().hex[:8]}"
    return web.json_response({"livekit_token": create_livekit_token("ron", room), "room_name": room})


async def voice_stream(request):
    body = await request.json()
    heard.append({"t": time.time(), "text": body.get("transcript", "")})
    print(f"HEARD: {body.get('transcript')!r}", flush=True)
    resp = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
    await resp.prepare(request)
    await resp.write(b'data: {"delta": "Okay, done."}\n\n')
    await resp.write(b"data: [DONE]\n\n")
    return resp


def tone_mp3(seconds: float, rate: int = 24000) -> bytes:
    t = np.arange(int(rate * seconds)) / rate
    samples = (0.1 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16).reshape(1, -1)
    frame = av.AudioFrame.from_ndarray(samples, format="s16p", layout="mono")
    frame.sample_rate = rate
    buf = io.BytesIO()
    with av.open(buf, "w", format="mp3") as out:
        stream = out.add_stream("mp3", rate=rate, layout="mono")
        for packet in [*stream.encode(frame), *stream.encode(None)]:
            out.mux(packet)
    return buf.getvalue()


async def tts(request):
    text = (await request.json()).get("input") or "Okay"
    return web.Response(body=tone_mp3(max(0.5, len(text) / 15)), content_type="audio/mpeg")


async def other(request):
    return web.json_response({})


app = web.Application(middlewares=[cors])
app.router.add_post("/api/auth/token", token)
app.router.add_post("/api/voice/stream", voice_stream)
app.router.add_get("/api/voice/user-voice/{user}", lambda r: web.json_response({"voice": "bf_emma"}))
app.router.add_get("/api/user/profile", lambda r: web.json_response(PROFILE))
app.router.add_get("/api/chat/history", lambda r: web.json_response({"messages": [], "hasMore": False}))
app.router.add_get("/api/approvals", lambda r: web.json_response({"approvals": []}))
app.router.add_post("/v1/audio/speech", tts)
app.router.add_get("/harness/heard", lambda r: web.json_response(heard))
app.router.add_get("/harness/{name}.wav", lambda r: web.FileResponse(os.path.join(WORK, r.match_info["name"] + ".wav")))
app.router.add_route("*", "/{tail:.*}", other)
web.run_app(app, port=18000, print=lambda *_: print("fake butler on :18000", flush=True))
