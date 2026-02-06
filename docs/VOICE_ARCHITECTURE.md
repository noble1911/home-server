# LiveKit Voice Integration Architecture

> Architecture decision record for Butler voice integration.
> **Issue:** #10 | **Date:** 2026-02-05

## Overview

This document defines how real-time voice works in Butler, integrating LiveKit with Nanobot for AI-powered voice conversations.

**Target latency:** 500-800ms from speech end to first audio response

---

## Key Decisions

### 1. Separate Service or Extend Nanobot?

**Decision: LiveKit Agents as a separate service that delegates to Nanobot**

| Option | Verdict | Rationale |
|--------|---------|-----------|
| Extend Nanobot with LiveKit | :x: | Nanobot not designed for WebRTC; complex integration |
| **LiveKit Agents + Nanobot** | :white_check_mark: | Each does what it does best |
| Custom voice service | :x: | Reinventing the wheel; months of work |

**Responsibilities:**

| Service | Handles |
|---------|---------|
| **LiveKit Agents** | Audio capture, VAD, STT orchestration, TTS streaming |
| **Nanobot** | LLM reasoning, tool calling, memory, personality |

### 2. How to Share Tools Between Voice and Text?

**Decision: Nanobot is the single tool executor**

All channels route through Nanobot's API for tool execution. No duplication of tool logic.

```
Voice:    PWA → LiveKit → Whisper → [Nanobot API] → Kokoro → LiveKit → PWA
Text:     PWA → [Nanobot API] → PWA
WhatsApp: WhatsApp → [Nanobot built-in] → WhatsApp
```

### 3. Session Management Across Channels

**Decision: JWT-based identity + PostgreSQL session state**

| Layer | Storage | Purpose |
|-------|---------|---------|
| User Identity | JWT token | Who is this user? |
| User Profile | `butler.users` | Personality, preferences, permissions |
| Conversation | `butler.conversation_history` | Recent context (7 days) |
| Facts | `butler.user_facts` | Long-term memory with embeddings |

All channels write to the same database, enabling cross-channel continuity.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           BUTLER VOICE ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌─────────────┐              ┌────────────────────┐                           │
│   │  Butler PWA │◄────────────►│   LiveKit Server   │                           │
│   │   (React)   │   WebRTC     │      :7880         │                           │
│   └─────────────┘              └──────────┬─────────┘                           │
│                                           │                                      │
│                                           │ Audio subscription                   │
│                                           ▼                                      │
│                              ┌────────────────────────┐                         │
│                              │    LiveKit Agents      │                         │
│                              │       (Python)         │                         │
│                              │                        │                         │
│                              │  • Voice Activity Det. │                         │
│                              │  • Audio buffering     │                         │
│                              │  • Pipeline orchestr.  │                         │
│                              └───────────┬────────────┘                         │
│                                          │                                       │
│                    ┌─────────────────────┼─────────────────────┐                │
│                    │                     │                     │                │
│                    ▼                     ▼                     ▼                │
│            ┌─────────────┐      ┌─────────────────┐    ┌─────────────┐         │
│            │   Whisper   │      │     Nanobot     │    │   Kokoro    │         │
│            │    :9000    │      │      :8100      │    │    :8880    │         │
│            │    (STT)    │      │                 │    │    (TTS)    │         │
│            │             │      │  • Claude API   │    │             │         │
│            │  small model│      │  • Tool calling │    │  bf_emma    │         │
│            │  ~200ms     │      │  • Memory       │    │  ~150ms     │         │
│            └─────────────┘      │  • Personality  │    └─────────────┘         │
│                                 └────────┬────────┘                             │
│                                          │                                       │
│                                          ▼                                       │
│                                 ┌─────────────────┐                             │
│                                 │   PostgreSQL    │                             │
│                                 │     :5432       │                             │
│                                 │                 │                             │
│                                 │  butler schema  │                             │
│                                 └─────────────────┘                             │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Voice Flow

### Step-by-Step Sequence

```
1. USER PRESSES MIC
   └─► PWA requests LiveKit token from Nanobot API
   └─► PWA connects to LiveKit room with JWT
   └─► PWA publishes local audio track

2. AUDIO STREAMS
   └─► WebRTC transmits audio to LiveKit Server
   └─► LiveKit Agents joins room, subscribes to user audio

3. VOICE ACTIVITY DETECTION
   └─► LiveKit Agents detects speech start
   └─► Buffers audio while user speaks
   └─► Detects speech end (silence threshold)

4. SPEECH-TO-TEXT
   └─► Audio chunk sent to Whisper (HTTP POST /asr)
   └─► Whisper returns transcription text
   └─► ~200ms latency

5. LLM PROCESSING
   └─► Transcript sent to Nanobot API (POST /api/voice/process)
   └─► Nanobot loads user context, personality, recent facts
   └─► Claude processes with tool definitions
   └─► Tools executed if needed (Home Assistant, etc.)
   └─► Response text generated
   └─► ~300ms latency

6. TEXT-TO-SPEECH
   └─► Response sent to Kokoro (POST /v1/audio/speech)
   └─► Audio generated with selected voice
   └─► ~150ms to first chunk

7. AUDIO PLAYBACK
   └─► LiveKit Agents publishes audio to room
   └─► Transcript sent as data message (for UI)
   └─► PWA subscribes, plays through speaker
   └─► PWA displays transcript bubble

TOTAL: ~800ms from speech end to first audio
```

### Latency Budget

| Step | Target | Notes |
|------|--------|-------|
| Audio to LiveKit | 50ms | WebRTC, near-instant |
| VAD + Buffering | 100ms | Wait for speech end |
| Whisper STT | 200ms | Using "small" model |
| Nanobot + Claude | 300ms | API call + reasoning |
| Kokoro TTS | 150ms | First audio chunk |
| **Total** | **800ms** | Conversational feel |

---

## API Interfaces

### Nanobot API Endpoints

```http
POST /api/auth/token
  Request:  { user_id: string }
  Response: { livekit_token: string, room_name: string }
  Purpose:  Generate LiveKit room token for PWA

POST /api/chat
  Headers:  Authorization: Bearer <jwt>
  Request:  { message: string, type: "text" }
  Response: { response: string, message_id: string }
  Purpose:  Text chat from PWA

POST /api/voice/process
  Request:  { transcript: string, user_id: string, session_id: string }
  Response: { response: string, should_end_turn: boolean }
  Purpose:  Process voice transcript (called by LiveKit Agents)

GET /api/users/me
  Headers:  Authorization: Bearer <jwt>
  Response: { id, name, preferences, soul_config }
  Purpose:  Get user profile for PWA
```

### LiveKit Agents → Services

```python
# STT: Whisper
POST http://whisper:9000/asr
  Body: audio file (wav/mp3)
  Response: { "text": "transcribed text" }

# LLM: Nanobot
POST http://nanobot:8100/api/voice/process
  Body: { "transcript": "...", "user_id": "...", "session_id": "..." }
  Response: { "response": "..." }

# TTS: Kokoro
POST http://kokoro-tts:8880/v1/audio/speech
  Body: { "input": "text", "voice": "bf_emma" }
  Response: audio stream (mp3)
```

---

## Docker Configuration

### Addition to voice-stack/docker-compose.yml

```yaml
services:
  # ... existing livekit, whisper, kokoro-tts ...

  livekit-agents:
    build: ../../butler/livekit-agent
    container_name: livekit-agents
    environment:
      - LIVEKIT_URL=ws://livekit:7880
      - LIVEKIT_API_KEY=devkey
      - LIVEKIT_API_SECRET=secret
      - WHISPER_URL=http://whisper:9000
      - KOKORO_URL=http://kokoro-tts:8880
      - NANOBOT_URL=http://nanobot:8100
    depends_on:
      - livekit
      - whisper
      - kokoro-tts
    restart: unless-stopped
    networks:
      - butler-net
```

---

## PWA Integration

### Current State (Placeholder)

```typescript
// VoiceButton.tsx - line 31
setTimeout(() => setVoiceStatus('idle'), 1500)  // Simulated
```

### Target State (LiveKit SDK)

```typescript
import { LiveKitRoom, useVoiceAssistant } from '@livekit/components-react'

function VoiceRoom({ token, serverUrl }) {
  return (
    <LiveKitRoom token={token} serverUrl={serverUrl}>
      <VoiceAssistantUI />
    </LiveKitRoom>
  )
}

function VoiceAssistantUI() {
  const { state, audioTrack } = useVoiceAssistant()
  // state: 'idle' | 'listening' | 'thinking' | 'speaking'
  // Transcripts received via data messages
}
```

---

## Implementation Sequence

| Phase | Issue | Description |
|-------|-------|-------------|
| 1 | #11 | Deploy Nanobot with HTTP API endpoints |
| 2 | New | Build LiveKit Agents worker |
| 3 | New | Connect PWA to LiveKit (replace placeholders) |
| 4 | #4-9 | Implement tools for voice commands |

---

## Security

1. **JWT tokens** - PWA authenticates, receives scoped LiveKit token
2. **Internal network** - Whisper, Kokoro, Nanobot not exposed externally
3. **Cloudflare Tunnel** - LiveKit accessible via tunnel, not directly on public internet
4. **No stored audio** - Audio processed in-memory, not persisted

---

## Trade-offs Accepted

| Decision | Trade-off | Why Acceptable |
|----------|-----------|----------------|
| HTTP between services | Slight latency vs gRPC | Simpler debugging, standard tooling |
| Single Nanobot instance | No horizontal scaling | Home server, 1-2 users max |
| Whisper "small" model | Less accurate than "large" | Faster response, good enough for commands |
| No audio storage | Can't replay conversations | Privacy, storage savings |

---

## Future Enhancements (Not in Scope)

- **Wake word detection** - Currently push-to-talk only; Porcupine integration later
- **Voice identification** - Currently JWT-based; speaker recognition optional
- **Interruption handling** - Can user interrupt Butler mid-response?
- **Multi-turn streaming** - Currently request/response; could stream partial responses

---

## References

- [LiveKit Agents Documentation](https://docs.livekit.io/agents/)
- [Whisper ASR Web Service](https://github.com/ahmetoner/whisper-asr-webservice)
- [Kokoro TTS FastAPI](https://github.com/remsky/Kokoro-FastAPI)
- [HKUDS/nanobot](https://github.com/HKUDS/nanobot)
