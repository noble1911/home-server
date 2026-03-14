# Vector Robot Setup (wire-pod)

Wire-pod replaces the cloud backend for Anki/DDL Vector robots. This setup connects Vector to Butler's AI pipeline, giving the robot access to all of Ron's tools, memory, and home automation.

## Architecture

```
Vector Robot → wire-pod (STT + intent) → Butler API (OpenAI-compat endpoint) → Claude + Tools
```

- **wire-pod** handles: robot communication, speech-to-text, command processing
- **Butler API** handles: AI responses, tool execution, memory/facts
- Vector uses Ron's user profile — same memory, facts, and personality as voice/PWA

## Install (Native macOS)

Wire-pod runs natively on macOS (not in Docker) so the Vector SDK has full access to the robot.

1. Download `WirePod-v1.2.13.dmg` from [WirePod releases](https://github.com/kercre123/WirePod/releases)
2. Drag `WirePod.app` to `/Applications`
3. Open WirePod from Applications (approve the unsigned app in System Settings → Security)
4. Config is stored at:
   - `~/Library/Application Support/wire-pod/wire-pod-conf.json` — app settings (port, auto-start)
   - `/Applications/WirePod.app/Contents/Frameworks/chipper/` — robot data, jdocs, certs

## Configure wire-pod

1. Open the wire-pod web UI: `http://192.168.1.117:8090`

2. Go to **Bot Settings** and set up your Vector robot (follow the on-screen instructions to authenticate your robot)

3. Go to **Custom Settings > Knowledge Graph**:
   - **Provider:** Custom
   - **API URL:** `http://localhost:8000/api/openai/v1` (wire-pod's Go client appends `/chat/completions` automatically)
   - **API Key:** Your `INTERNAL_API_KEY` value (from butler `.env`)
   - **Model:** `claude-sonnet` (any value works — Butler uses its own model config)

4. Enable **Intent Graph** if available — this sends all unmatched voice commands to the LLM instead of requiring "I have a question" prefix.

## Configure Vector Robot

The Vector robot needs to be pointed to wire-pod. Follow the [wire-pod setup guide](https://github.com/kercre123/wire-pod/wiki/Installation) to:

1. Put Vector in recovery mode
2. Set the robot's server URL to `http://192.168.1.117` (or `escapepod.local` if mDNS works)
3. Authenticate the robot via the wire-pod web UI

## How It Works

- Vector's speech is transcribed by wire-pod's STT
- Knowledge graph queries are sent to Butler's OpenAI-compatible endpoint
- Butler loads Ron's context (personality, facts, conversation history)
- Butler routes through its full tool pipeline (weather, home automation, media, etc.)
- Response is sent back to wire-pod, which uses Vector's built-in TTS
- Conversations are stored with channel `vector` for history isolation

## Ports

| Port | Service |
|------|---------|
| 80   | HTTP (robot setup) |
| 443  | HTTPS/gRPC (robot communication) |
| 8084 | Additional robot services |
| 8090 | Wire-pod web UI |

## Troubleshooting

- **Robot can't connect:** Ensure ports 80/443 aren't blocked. Check the WirePod app logs (systray → View Logs).
- **No AI responses:** Verify the API URL and key in wire-pod settings. Test with:
  ```bash
  curl -X POST http://localhost:8000/api/openai/v1/chat/completions \
    -H "Content-Type: application/json" \
    -H "X-API-Key: YOUR_INTERNAL_API_KEY" \
    -d '{"messages":[{"role":"user","content":"Hello"}]}'
  ```
- **Wire-pod web UI not loading:** Check `http://192.168.1.117:8090`
- **Migrating from Docker:** Back up `/data` from the container, copy `chipper/jdocs/`, `chipper/apiConfig.json`, and `certs/server_config.json` to the native app's `Frameworks/chipper/` directory.
