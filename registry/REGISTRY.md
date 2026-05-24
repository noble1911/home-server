# Home Server Registry

Single source of truth for **every project sharing this Mac Mini** (`192.168.1.117`).
If you add, move, or remove a service, update this file and `services.yaml`, then run
`./doctor.sh` to check for drift. Cloudflare tunnel routes are maintained in the
Cloudflare dashboard (domain `noblehaus.uk`) — mirror them here so they're discoverable.

> New here? Read `CONVENTIONS.md` before adding anything.

## Projects

| Project | Path (server) | Repo (local) | What it is |
|---|---|---|---|
| **home-server** | `~/home-server` | `~/random/HomeServer` | Umbrella: butler (AI brain+PWA+voice) + media/photos/books/smart-home/download stacks. Public via `cloudflared`. |
| **vector-llm** | `~/vector-llm` | `~/random/vector-llm` | Always-on-mic LLM brain for the Anki Vector robot. Runs as a **host Python process** (`python src/main.py`): host mic → faster-whisper STT → Ollama (qwen) → Kokoro TTS; escalates to butler; shares Postgres as user `vector-robot`. Its compose **provides the `ollama` container** (:11434). |
| **claude-esp** | gateway → `~/home-server`-net | `~/random/claude-esp` | ESP32 AMOLED voice device. `esp-gateway` (:8770) bridges device ↔ Groq STT ↔ butler ↔ Kokoro; Claude draws cards via `display_on_device`. *(gateway not yet deployed)* |
| **dont-lie** | `~/dont-lie` | — | Containerised web app: nginx serving a JS app on **:3001** (`dont-lie-app`), on the `homeserver` net. **Purpose not documented in-repo (no README/description) — owner to confirm.** |
| **wire-pod-backup** | `~/wire-pod-backup` | — | Backup/escrow data for wire-pod (Anki Vector auth), supporting vector-llm. **Not a running service.** |
| **gunpey** | `~/gunpey` | — | Local project directory — **no server footprint** (no compose/container, not deployed). |

## Shared services (the contracts every project should reuse, not duplicate)

| Service | Internal address (homeserver net) | LAN address | Notes |
|---|---|---|---|
| **butler-api** | `http://butler-api:8000` | `http://192.168.1.117:8000` | Brain + per-user memory + tools. Auth: `X-API-Key: $INTERNAL_API_KEY` (internal → `user_id` in body) or user JWT. Memory is keyed by `user_id`. |
| **Kokoro TTS** | `http://kokoro-tts:8880` | `:8880` | OpenAI-compatible `/v1/audio/speech` (wav/mp3). |
| **Postgres** | `immich-postgres:5432` | `:5432` | DB `immich`, schema `butler` (+pgvector). Shared by butler & vector-llm. |
| **Ollama** | `http://ollama:11434` | `:11434` | Container defined by **vector-llm's** compose (`ollama/ollama`). Embeddings (`nomic-embed-text`) + qwen brain. **Currently stopped** — start vector-llm's stack to use it; ensure it joins the `homeserver` net so butler can reach it for embeddings. |
| **LiveKit** | `ws://livekit:7880` | `:7880-7882` | WebRTC for PWA voice. **LAN-only** — media (UDP/7882, TCP/7881) does NOT traverse the Cloudflare tunnel. |
| **Groq** (cloud) | — | — | Whisper STT. Key in `~/home-server/docker/voice-stack/.env`. |
| **homeserver** (Docker network) | — | — | `external: true`. How containers reach each other by name. |
| **cloudflared** | — | — | Public ingress; routes in the Cloudflare dashboard. |

See `services.yaml` for the full machine-readable port map (the source of truth for
"which host port is taken").

## Cloudflare tunnel routes (mirror of the dashboard — keep in sync)

| Hostname | → service |
|---|---|
| `butler.noblehaus.uk` | `butler-app:80` (PWA) |
| `butler-api.noblehaus.uk` | `butler-api:8000` |
| `esp-gateway.noblehaus.uk` | `esp-gateway:8770` *(to add when the gateway deploys)* |
| _…(add the rest from the dashboard: photos, jellyfin, ha, etc.)_ | |

> `doctor.sh` can verify host ports against live containers, but it **cannot** see
> dashboard tunnel routes — those must be mirrored here by hand.
