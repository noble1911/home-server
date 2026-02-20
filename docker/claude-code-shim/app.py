"""Claude Code shim — runs on the Mac Mini host (not in Docker).

Butler API (in Docker) calls: POST http://host.docker.internal:7100/run
This service runs `claude --print <message>` and streams stdout as SSE.

Setup:
    pip3 install aiohttp
    python3 app.py

Or via launchd (auto-start on boot):
    cp claude-code-shim.plist ~/Library/LaunchAgents/
    launchctl load ~/Library/LaunchAgents/claude-code-shim.plist
"""

import asyncio
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


async def run_claude(request: web.Request) -> web.StreamResponse:
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

    proc = await asyncio.create_subprocess_exec(
        CLAUDE_BIN, "--print", "--dangerously-skip-permissions", message,
        cwd=str(WORK_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    assert proc.stdout is not None

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
    return web.json_response({"status": "ok", "claude": CLAUDE_BIN})


app = web.Application()
app.router.add_post("/run", run_claude)
app.router.add_get("/health", health)

if __name__ == "__main__":
    logger.info("Claude Code shim starting on port %d (workdir: %s)", PORT, WORK_DIR)
    web.run_app(app, host="0.0.0.0", port=PORT)
