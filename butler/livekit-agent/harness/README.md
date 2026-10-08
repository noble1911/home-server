# Voice harness

End-to-end test of push-to-talk voice on your Mac. It answers "did Butler hear
everything I said, as one request?" for a fresh press and for later presses.

- **The app**: the real `app/`, served by vite, in headless Chrome. A fake microphone
  starts "talking" at the exact moment the mic button is pressed.
- **LiveKit and the agent**: LiveKit 1.9.11 and the real `agent.py` in Docker,
  side by side as on the Mini.
- **Stand-ins**: local Whisper (`whisper_stt.py`) for Groq. `fake_butler.py` for
  Butler API and Kokoro. It mints tokens with the real `butler/api/auth.py` and
  records what the agent heard.

```bash
cd butler/livekit-agent/harness
./run.sh                 # 3 sentences × 3 presses, at 0 and 50 ms latency
LATENCIES=300 ./run.sh   # a slow connection
```

The first run builds an image (a few minutes) and downloads Whisper base.en (~140 MB).

## Output

Each line is one press:

```
ok   press 1 (cold): heard "1, 2, 3, 4. 5, 6, 7, 8" | 0.9s after you stopped
```

- **Cold** means the press opens the room, so the agent joins while you talk.
- **Warm** means the room is already up.
- **Lost words** show up as `missing`.
- **A pause that ended the turn early** shows up as `split into 2 requests`.
- The **time** is when the request reached Butler API. Real replies add Groq STT,
  Claude and Kokoro on top.

## Needs

- macOS (`say`)
- Docker with container IPs reachable from the Mac (OrbStack or Docker Desktop)
- Google Chrome
- Node
- ffmpeg

Ports 15173, 17880 and 18000 must be free. Set `CHROME=` for another Chrome path.

## Debugging a run

```bash
DEBUG_LK=1 COLD_ONLY=1 SPEECH=short.wav EXPECT=turn,off,kitchen,lights node voice_test.mjs
docker logs harness-agent          # look for "Released; answering" / "pre-connect audio"
```

Run these with `run.sh`'s services still up (comment out its `trap`). Set
`HARNESS_LOG_LEVEL=debug` on the agent container for LiveKit's pre-connect logs.
