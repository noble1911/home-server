# Step 12: Deploy Voice Stack

Deploy LiveKit (WebRTC) and Kokoro (text-to-speech). Speech-to-text uses Groq's cloud API (free tier).

## Automated

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/12-voice-stack.sh | bash
```

**Note:** First run downloads ~1GB of TTS models. Be patient!

## Manual

### 1. Start Services

```bash
cd docker/voice-stack
docker compose up -d
```

### 2. Verify Running

```bash
docker compose ps
```

## Services

| Service | URL | Purpose | RAM (Peak) |
|---------|-----|---------|------------|
| LiveKit | ws://localhost:7880 | WebRTC server | 500MB |
| Groq Whisper | Cloud API | Speech-to-text (free tier) | 0MB |
| Kokoro | http://localhost:8880 | Text-to-speech | 800MB |
| LiveKit Agent | (internal) | Voice pipeline orchestrator | 500MB |

## How Voice Works

```
You speak into PWA app
        ↓
Audio streams via WebRTC to LiveKit
        ↓
LiveKit Agent sends audio to Groq Whisper API (cloud)
        ↓
Groq transcribes to text (~50ms)
        ↓
Text goes to Butler API → Claude (SSE streaming)
        ↓
Claude's response goes to Kokoro
        ↓
Kokoro generates audio
        ↓
Audio streams back via LiveKit
        ↓
You hear the response
```

Total latency: ~650ms for conversational feel.

## Testing the Services

### Test Kokoro (TTS)

```bash
# Generate speech
curl -X POST "http://localhost:8880/v1/audio/speech" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "kokoro",
    "input": "Hello! I am your home assistant.",
    "voice": "af_bella"
  }' \
  --output test_output.mp3

# Play it
afplay test_output.mp3
```

Available voices:
- `af_bella` - American female
- `af_sarah` - American female
- `am_adam` - American male
- `am_michael` - American male
- `bf_emma` - British female
- `bm_george` - British male

### Test LiveKit

```bash
# Generate API keys (for production)
docker run --rm livekit/generate

# Test connection with LiveKit CLI
brew install livekit-cli
livekit-cli join-room \
  --url ws://localhost:7880 \
  --api-key devkey \
  --api-secret secret \
  --room test-room
```

## Configuration

### LiveKit Keys & .env File

The voice stack uses a `.env` file at `docker/voice-stack/.env` for API keys. This file is **auto-generated** by `13-nanobot.sh` to stay in sync with the Nanobot `.env`:

```
LIVEKIT_API_KEY=<generated>
LIVEKIT_API_SECRET=<generated>
INTERNAL_API_KEY=<generated>
GROQ_API_KEY=<your-groq-key>
```

The `13-nanobot.sh` script also updates `docker/voice-stack/livekit.yaml` to replace the default dev keys with production keys.

**If you need to regenerate keys manually:**

```bash
docker run --rm livekit/generate
```

Then update both `nanobot/.env` and `docker/voice-stack/.env` with the new values.

### Kokoro Voices

You can set a default voice or let the application choose per-request.

## Integration with Butler API

The voice stack provides the WebRTC and TTS infrastructure. The LiveKit Agent orchestrates the pipeline:

1. Captures audio and sends to Groq Whisper for transcription
2. Sends transcript to Butler API (SSE streaming)
3. Butler processes with Claude, calls tools (Home Assistant, Radarr, etc.)
4. Response text sent to Kokoro for audio generation
5. Audio streams back through LiveKit to the PWA

## PWA Client

The client app (React PWA) will:

1. Connect to LiveKit via WebRTC
2. Stream microphone audio
3. Receive audio responses
4. Display conversation transcript

See HOMESERVER_PLAN.md for the full PWA architecture.

## Volume Mappings

| Service | Volume | Purpose |
|---------|--------|---------|
| Kokoro | `kokoro-models` | Cached TTS models |
| LiveKit | Config file | Server configuration |

Models are stored on SSD (Docker volumes) for fast loading.

## Docker Commands

```bash
# View logs
docker logs kokoro-tts
docker logs livekit
docker logs livekit-agent

# Restart
cd docker/voice-stack
docker compose restart

# Update
docker compose pull
docker compose up -d
```

## Troubleshooting

### Kokoro audio quality issues

- Ensure audio format is supported (mp3, wav)
- Try different voices
- Check for GPU acceleration (if available)

### LiveKit connection issues

```bash
# Check WebSocket is accessible
curl -v http://localhost:7880

# Verify config
cat docker/voice-stack/livekit.yaml
```

### Out of memory

Voice stack needs ~2GB RAM at peak. If running with other stacks:
1. Stop ML-intensive services temporarily
2. Stagger service startup

## Performance Tips

1. **Keep Kokoro warm:** Don't stop/start frequently — model loading is slow
2. **Schedule heavy ML tasks (Immich) for off-hours**
3. **Monitor with:** `docker stats`

## What's Next?

With voice infrastructure ready:

1. **Deploy Nanobot** (issue #11) - the AI agent
2. **Build Butler tools** (issues #2-#9) - service integrations
3. **Create PWA** - the client interface
4. **Connect to LiveKit Agents** - orchestrate the flow

See HOMESERVER_PLAN.md > AI Butler Architecture for details.
