# Conventions for adding a project/service to this server

The Mac Mini runs many projects on one shared stack. Follow these so projects stay
discoverable and don't collide. Update `REGISTRY.md` + `services.yaml` as part of the change.

## 1. Pick a free host port
Check `services.yaml` and run `./doctor.sh` to see what's live. Choose a port not listed,
add it to `services.yaml`, then re-run `doctor.sh`.

## 2. Join the shared Docker network
Containers reach shared services by name only if they're on the `homeserver` network:
```yaml
networks:
  homeserver:
    external: true
```
Then reference services as `http://butler-api:8000`, `http://kokoro-tts:8880`, `immich-postgres:5432`, etc.

## 3. Reuse shared services — don't duplicate them
- **Brain / memory:** call butler at `http://butler-api:8000`. For service-to-service use
  `X-API-Key: $INTERNAL_API_KEY` (from `~/home-server/butler/.env`) and put `user_id` in the
  body — butler's per-user memory (conversation history + semantic facts) is keyed by `user_id`.
  Pick a stable `user_id` for your project (e.g. vector-llm uses `vector-robot`).
- **TTS:** Kokoro at `http://kokoro-tts:8880/v1/audio/speech` (OpenAI-compatible).
- **STT:** Groq Whisper (cloud); key in `voice-stack/.env`. Or local faster-whisper (see vector-llm).
- **DB:** Postgres `immich-postgres:5432`, db `immich`. Use your own schema or butler's tables with your `user_id`.
- **Embeddings / local LLM:** Ollama on the host (`:11434`).

## 4. Secrets
Per-stack `.env` files (git-ignored). Never commit secrets. `INTERNAL_API_KEY` is shared
across internal callers — read it from `~/home-server/butler/.env`, don't hardcode it.

## 5. Public exposure
Add a Cloudflare Tunnel route in the dashboard (`<name>.noblehaus.uk → http://<container>:<port>`)
and mirror it in `REGISTRY.md`. Note: WebRTC/UDP media does **not** traverse the tunnel — use
WSS/HTTP for anything that must work off-LAN (this is why claude-esp uses a WS gateway, not LiveKit).

## 6. Container hygiene
`restart: unless-stopped` + a `healthcheck`. Prefer the shared Postgres over standing up a new DB.

## 7. Keep the registry honest
After any change: update `REGISTRY.md` + `services.yaml`, run `./doctor.sh`, commit.
