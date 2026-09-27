<!-- Installed to the SERVER's ~/.claude/CLAUDE.md so every Claude Code session on
     the Mac Mini auto-loads shared context. Edit here (versioned), then redeploy. -->
# This machine: home server (Mac Mini, 192.168.1.117)

This box runs **many projects on one shared stack** (home-server/butler, vector-llm,
claude-esp, the games site, …). Before adding a service, opening a port, or wiring to the
brain/TTS/DB, read the shared registry:

- **`~/home-server/registry/REGISTRY.md`** — projects, shared services, ports, tunnel routes
- **`~/home-server/registry/CONVENTIONS.md`** — how to add a project (network, ports, auth)
- **`~/home-server/registry/services.yaml`** — port map (source of truth for free ports)
- Run **`~/home-server/registry/doctor.sh`** to check live containers vs the registry.

Shared services — reuse, don't duplicate:
- **butler-api:8000** — brain + per-user memory + tools (`X-API-Key: $INTERNAL_API_KEY` + `user_id` in body)
- **kokoro-tts:8880** — TTS · **immich-postgres:5432** — db `immich`, schema `butler` (+pgvector) · **Ollama host:11434**

**Games** are all at **games.noblehaus.uk**: one Caddy gateway (`games-gateway`, `~/home-server/games`)
serves a hub page and every game under its own path. A new game needs a route there, not its own
subdomain or Cloudflare route. Quick reference: `~/home-server/games/README.md`; full guide:
`docs/17-games.md` in the home-server repo.

Join the `homeserver` Docker network to reach them by name. Public ingress is `cloudflared`
(routes in the Cloudflare dashboard; WebRTC/UDP won't traverse it — use WSS). Update the
registry whenever you change services.
