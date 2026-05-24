"""Claude Code shim — runs on the Mac Mini host (not in Docker).

Butler API (in Docker) calls: POST http://host.docker.internal:7100/run
This service runs `claude --print` and streams stdout as SSE.

Security model (see docker/claude-code-shim/claude-shim-settings.json):
    * Authentication — /run requires the X-Shim-Token header to match
      CLAUDE_SHIM_TOKEN. Without this, anything on the LAN could POST /run and
      get arbitrary code execution as this user. If the env var is unset the
      shim still runs but logs a loud warning and accepts unauthenticated calls
      (backward-compatible; set the token to close the hole).
    * Permissions — Claude Code runs with `--permission-mode dontAsk` plus a
      `--settings` policy that DENIES catastrophic operations and confines the
      filesystem with a macOS Seatbelt sandbox. We deliberately do NOT use
      `--dangerously-skip-permissions`. We also avoid `--bare`, which would
      force ANTHROPIC_API_KEY auth and break the Claude subscription login.

Setup:
    pip3 install aiohttp
    export CLAUDE_SHIM_TOKEN="$(openssl rand -hex 32)"   # match butler-api
    python3 app.py

Or via launchd (auto-start on boot):
    cp claude-code-shim.plist ~/Library/LaunchAgents/   # edit the token first
    launchctl load ~/Library/LaunchAgents/claude-code-shim.plist
"""

import asyncio
import hmac
import json
import logging
import os
from pathlib import Path

from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

HOME = Path.home()
WORK_DIR = HOME / "home-server"
PORT = int(os.environ.get("CLAUDE_SHIM_PORT", "7100"))
HOST = os.environ.get("CLAUDE_SHIM_HOST", "0.0.0.0")

# Shared secret. butler-api sends it as the X-Shim-Token header. When empty,
# the shim accepts unauthenticated requests (with a warning) for backward
# compatibility — set it to lock the shim down.
SHIM_TOKEN = os.environ.get("CLAUDE_SHIM_TOKEN", "").strip()

# Hardened permission policy passed to `claude --settings`. Lives next to this
# file so it is version-controlled and reviewable.
SETTINGS_FILE = Path(__file__).resolve().parent / "claude-shim-settings.json"

# Prefer Homebrew claude; fall back to PATH
CLAUDE_BIN = "/opt/homebrew/bin/claude"
if not Path(CLAUDE_BIN).exists():
    import shutil
    CLAUDE_BIN = shutil.which("claude") or CLAUDE_BIN

# When launched via launchd the environment has a minimal PATH that doesn't
# include Homebrew. Patch it so the `claude` Node.js script can find `node`.
_HOMEBREW_BIN = "/opt/homebrew/bin"
_HOMEBREW_SBIN = "/opt/homebrew/sbin"
_current_path = os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
if _HOMEBREW_BIN not in _current_path:
    os.environ["PATH"] = f"{_HOMEBREW_BIN}:{_HOMEBREW_SBIN}:{_current_path}"


def _authorized(request: web.Request) -> bool:
    """Constant-time check of the X-Shim-Token header against CLAUDE_SHIM_TOKEN."""
    if not SHIM_TOKEN:
        # Unauthenticated mode (warned about at startup). Allow.
        return True
    provided = request.headers.get("X-Shim-Token", "")
    return hmac.compare_digest(provided, SHIM_TOKEN)


async def run_claude(request: web.Request) -> web.StreamResponse:
    if not _authorized(request):
        logger.warning("Rejected /run from %s — missing/invalid X-Shim-Token", request.remote)
        raise web.HTTPUnauthorized(reason="missing or invalid X-Shim-Token")

    body = await request.json()
    message = body.get("message", "")

    if not message:
        raise web.HTTPBadRequest(reason="message is required")

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    response = web.StreamResponse(headers=headers)
    await response.prepare(request)

    logger.info("Running claude --print for %d-char message", len(message))

    # Build the command. `dontAsk` proceeds without interactive prompts (so the
    # headless run never hangs); the --settings policy supplies the deny-list
    # and sandbox that actually contain it. Prompt goes via stdin to avoid the
    # message being parsed as CLI flags.
    cmd = [
        CLAUDE_BIN,
        "--print",
        "--permission-mode", "dontAsk",
    ]
    if SETTINGS_FILE.is_file():
        cmd += ["--settings", str(SETTINGS_FILE)]
    else:
        logger.error(
            "Permission policy %s is MISSING — Claude Code will run without a "
            "deny-list or sandbox. Restore the file before using the shim.",
            SETTINGS_FILE,
        )

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(WORK_DIR),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    assert proc.stdin is not None
    assert proc.stdout is not None

    # Feed the prompt on stdin and close it so claude knows input is complete.
    proc.stdin.write(message.encode())
    await proc.stdin.drain()
    proc.stdin.close()

    # claude --print buffers output until completion, so the connection would
    # sit idle for the full duration. Send SSE comment pings every 15s to keep
    # the connection alive through Cloudflare and nginx proxies.
    async def _read_output() -> None:
        async for line in proc.stdout:  # type: ignore[union-attr]
            chunk = line.decode(errors="replace")
            data = json.dumps({"type": "text_delta", "delta": chunk})
            await response.write(f"data: {data}\n\n".encode())

    async def _keepalive() -> None:
        while True:
            await asyncio.sleep(15)
            await response.write(b": keepalive\n\n")

    read_task = asyncio.create_task(_read_output())
    ping_task = asyncio.create_task(_keepalive())
    try:
        await read_task
    finally:
        ping_task.cancel()

    await proc.wait()
    logger.info("claude exited with code %s", proc.returncode)

    await response.write(b"data: [DONE]\n\n")
    return response


async def health(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "claude": CLAUDE_BIN,
        "authenticated": bool(SHIM_TOKEN),
        "policy": SETTINGS_FILE.is_file(),
    })


app = web.Application()
app.router.add_post("/run", run_claude)
app.router.add_get("/health", health)

if __name__ == "__main__":
    logger.info("Claude Code shim starting on %s:%d (workdir: %s)", HOST, PORT, WORK_DIR)
    if not SHIM_TOKEN:
        logger.warning(
            "=" * 70 + "\n"
            "  CLAUDE_SHIM_TOKEN is NOT set — /run is UNAUTHENTICATED.\n"
            "  Anyone who can reach %s:%d can execute commands as this user.\n"
            "  Set CLAUDE_SHIM_TOKEN (and the matching CLAUDE_CODE_SHIM_TOKEN on\n"
            "  butler-api) to close this hole. See README 4.3.\n" + "=" * 70,
            HOST, PORT,
        )
    if not SETTINGS_FILE.is_file():
        logger.error("Permission policy missing: %s", SETTINGS_FILE)
    web.run_app(app, host=HOST, port=PORT)
