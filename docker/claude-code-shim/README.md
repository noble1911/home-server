# Claude Code shim

A tiny HTTP service that runs on the **Mac Mini host** (not in Docker) and runs
`claude --print` on demand. It lets Butler — which lives in a container — reach a
real shell with full filesystem access to the home server, using your Claude
subscription rather than metered API tokens.

```
butler-api (Docker)  ──POST /run (X-Shim-Token)──▶  shim (host)  ──▶  claude --print
                     ◀────────── SSE text ──────────              ◀── stdout
```

Two things call it:

- **`run_claude_code` tool** — Butler's normal chat delegates here when a
  request needs real action ("restart Sonarr", "free up disk", "why is the photos
  stack unhealthy"). Gated by the `claude_code` permission.
- **`/chat/claude-code/stream`** — the manual "Claude Code mode" toggle in the PWA.

## Security model

Claude Code with a shell is powerful and Butler is reachable from the internet
via Cloudflare Tunnel, so the shim is locked down in three independent layers:

1. **Authentication (`X-Shim-Token`).** `/run` requires a shared secret matching
   `CLAUDE_SHIM_TOKEN`. Without it, anything that can reach port 7100 on the host
   (the whole LAN, since it binds `0.0.0.0`) could execute commands as your user.
   butler-api sends the token from `CLAUDE_CODE_SHIM_TOKEN`. `/health` stays open
   so `server_health` can probe it. *If the token is unset the shim still runs but
   logs a loud warning and accepts unauthenticated calls — set it.*

2. **Deny-list (`permissions.deny`).** Verified fact: in headless `-p` mode an
   *allow*-list does **not** contain anything (unlisted/safe commands still run),
   so containment comes from denying catastrophic operations — privilege
   escalation (`sudo`), power/disk (`shutdown`, `dd`, `diskutil`), Docker data
   loss (`docker system prune`, `docker volume rm`), git history rewrites
   (`--force`, `reset --hard`), and edits to this shim's own policy. Deny rules
   always win over any inherited allow.

3. **macOS Seatbelt sandbox.** The hard, OS-level wall. Filesystem writes are
   confined to the repo + data dirs; reads of `~/.ssh`, keychains, cloud creds,
   etc. are denied; `allowUnsandboxedCommands: false` means a blocked command
   cannot silently retry outside the sandbox. `docker` can still manage
   containers because the OrbStack daemon socket is allowed through
   (`network.allowUnixSockets`); its data-destroying subcommands stay denied.

We deliberately do **not** use `--dangerously-skip-permissions`, and we do **not**
use `--bare` (it forces `ANTHROPIC_API_KEY` auth and would break the subscription
login).

## Files

| File | Purpose |
|------|---------|
| `app.py` | The aiohttp service. Auth, runs `claude --print --permission-mode dontAsk --settings …`, streams SSE. |
| `claude-shim-settings.json` | The deny-list + sandbox policy passed to `claude --settings`. |
| `claude-code-shim.plist` | launchd job (auto-start, holds `CLAUDE_SHIM_TOKEN`). |

## Setup

See README section 4.3. In short: install the `claude` CLI + `claude login`,
create the venv, generate a token (`openssl rand -hex 32`) and set it on both
sides, then load the launchd job.

## Tuning the sandbox

The policy errs on the side of safety, so a legitimate repair command may
occasionally fail with a sandbox error. To loosen it deliberately:

- **A command needs to escape the sandbox** (e.g. talks to a socket the sandbox
  blocks): add its prefix to `sandbox.excludedCommands` (like `docker` already
  is). It then runs unsandboxed but still under the deny-list.
- **A command needs to write somewhere new:** add the path to
  `sandbox.filesystem.allowWrite`.
- **You want maximum capability over safety** (not recommended given internet
  exposure): set `sandbox.allowUnsandboxedCommands: true` so blocked commands
  retry unsandboxed.

After editing the policy, the change takes effect on the next `/run` (no restart
needed — `--settings` is read per invocation). Validate with:

```bash
curl http://localhost:7100/health   # expect authenticated:true, policy:true
```

> Behavior was verified against Claude Code v2.1.150. The permission semantics
> (`dontAsk` is fail-open; deny-list + sandbox are the real boundaries) are
> recorded in the project memory note `claude-code-headless-permissions`.
