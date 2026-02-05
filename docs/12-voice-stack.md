# Step 12: Deploy Voice Stack

Deploy LiveKit (WebRTC), Whisper (speech-to-text), and Kokoro (text-to-speech).

## Automated

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/12-voice-stack.sh | bash
```

**Note:** First run downloads ~2-3GB of ML models. Be patient!

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
| Whisper | http://localhost:9000 | Speech-to-text | 1.5GB |
| Kokoro | http://localhost:8880 | Text-to-speech | 800MB |

## How Voice Works

```
You speak into PWA app
        ↓
Audio streams via WebRTC to LiveKit
        ↓
LiveKit forwards to Whisper
        ↓
Whisper transcribes to text
        ↓
Text goes to Claude API (via Nanobot)
        ↓
Claude's response goes to Kokoro
        ↓
Kokoro generates audio
        ↓
Audio streams back via LiveKit
        ↓
You hear the response
```

Total latency: ~500-800ms for conversational feel.

## Testing the Services

### Test Whisper (STT)

```bash
# Record a test audio file
# Or use any .wav file

curl -X POST "http://localhost:9000/asr" \
  -H "Content-Type: multipart/form-data" \
  -F "audio_file=@test.wav"

# Response: {"text": "your transcribed text"}
```

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

### LiveKit Keys

The default development keys are:
- API Key: `devkey`
- API Secret: `secret`

**For production, generate new keys:**

```bash
docker run --rm livekit/generate
```

Update `docker/voice-stack/livekit.yaml`:

```yaml
keys:
  YOUR_API_KEY: YOUR_API_SECRET
```

### Whisper Model Selection

Edit `docker-compose.yml` to change model:

| Model | RAM | Speed | Accuracy |
|-------|-----|-------|----------|
| `tiny` | 400MB | Fastest | Lower |
| `base` | 500MB | Fast | OK |
| `small` | 1.5GB | Medium | Good ⬅️ Default |
| `medium` | 3GB | Slow | Better |
| `large` | 6GB | Slowest | Best |

For Mac Mini M4 (24GB), `small` is the sweet spot.

### Kokoro Voices

You can set a default voice or let the application choose per-request.

## Integration with Nanobot

The voice stack provides the STT/TTS infrastructure. Nanobot (issue #11) will:

1. Receive transcribed text from Whisper
2. Process with Claude API
3. Call tools (Home Assistant, Radarr, etc.)
4. Send response to Kokoro for audio
5. Stream back through LiveKit

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
docker logs whisper
docker logs kokoro-tts
docker logs livekit

# Check model loading progress
docker logs whisper -f

# Restart
cd docker/voice-stack
docker compose restart

# Update
docker compose pull
docker compose up -d
```

## Troubleshooting

### Whisper slow or not responding

Model may still be loading. Check:
```bash
docker logs whisper -f
```

If memory is an issue, try `tiny` or `base` model.

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

Voice stack needs ~3-4GB RAM at peak. If running with other stacks:
1. Stop ML-intensive services temporarily
2. Use smaller Whisper model
3. Stagger service startup

## Performance Tips

1. **Keep models warm:** Don't stop/start frequently
2. **Use smaller model for quick interactions**
3. **Schedule heavy ML tasks (Immich) for off-hours**
4. **Monitor with:** `docker stats`

## What's Next?

With voice infrastructure ready:

1. **Deploy Nanobot** (issue #11) - the AI agent
2. **Build Butler tools** (issues #2-#9) - service integrations
3. **Create PWA** - the client interface
4. **Connect to LiveKit Agents** - orchestrate the flow

See HOMESERVER_PLAN.md > AI Butler Architecture for details.
