"""Claude Code delegation tool for Butler.

Butler's other server tools are mostly *observational* — `server_health` probes
HTTP endpoints, `storage_monitor` reads `df`, `media_files` browses the
filesystem. None of them can actually *fix* anything: restart a container, read
a service's logs, edit a config, or run an arbitrary diagnostic command. This
tool is the escalation path. It hands a natural-language task to Claude Code
running on the Mac Mini host (via the claude-code-shim), which has a real shell
and full filesystem access to the home server.

The shim (``docker/claude-code-shim/app.py``) runs ``claude --print`` under a
hardened permission policy (deny-list of catastrophic operations + a macOS
Seatbelt sandbox). Butler authenticates to it with a shared secret sent in the
``X-Shim-Token`` header. The shim streams Claude Code's output back as SSE; this
tool accumulates the text and returns it to the LLM.

Because it grants real shell power, the tool is gated by the ``claude_code``
permission (see ``PERMISSION_TOOL_MAP`` in ``butler/api/deps.py``) and is only
injected into the tool set for admins or explicitly-granted users.

Usage:
    tool = ClaudeCodeTool(
        shim_url="http://host.docker.internal:7100",
        shim_token="...",
    )
    result = await tool.execute(task="Sonarr is unreachable — investigate and restart it")
    await tool.close()
"""

from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp

from .base import Tool

logger = logging.getLogger(__name__)

# Claude Code agent loops can run for a while (read logs, restart services,
# re-check). Give it a generous budget but keep it bounded so a hung run
# doesn't pin a Butler tool round open forever.
DEFAULT_TIMEOUT = 300

# Cap the text returned to the LLM so a chatty Claude Code session can't blow
# out Butler's context window. The shim already streams plain text.
MAX_RESULT_CHARS = 16000


class ClaudeCodeTool(Tool):
    """Delegate a server-administration / debugging / code task to Claude Code.

    Calls the host-side shim, which executes ``claude --print`` inside the
    home-server repo with shell access, and returns Claude Code's answer.
    """

    def __init__(
        self,
        shim_url: str,
        shim_token: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Initialize the Claude Code delegation tool.

        Args:
            shim_url: Base URL of the claude-code-shim (e.g.
                ``http://host.docker.internal:7100``).
            shim_token: Shared secret sent as the ``X-Shim-Token`` header. When
                None, no header is sent (the shim may run in warn-only mode).
            timeout: Total HTTP timeout in seconds for the delegated task.
        """
        self._shim_url = shim_url.rstrip("/")
        self._shim_token = shim_token or None
        self._timeout = aiohttp.ClientTimeout(total=timeout, connect=5)
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # -- Tool interface -------------------------------------------------------

    @property
    def name(self) -> str:
        return "run_claude_code"

    @property
    def description(self) -> str:
        return (
            "Delegate a hands-on home-server task to Claude Code, which has full "
            "shell and filesystem access on the server. Use this when the user "
            "wants you to actually FIX, debug, restart, reconfigure, or "
            "investigate something on the server that your other tools cannot do "
            "directly — for example restarting a crashed Docker container, "
            "reading a service's logs, freeing disk space, editing a config "
            "file, or diagnosing why a stack is unhealthy. Provide a complete, "
            "self-contained description of the task and any relevant context "
            "(service names, error symptoms, what the user reported); Claude "
            "Code starts fresh and does not see this conversation. Prefer your "
            "lighter read-only tools (server_health, storage_monitor) for simple "
            "status questions; reach for this only when real action is needed."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "A complete, self-contained instruction describing what "
                        "to do on the server, including any context Claude Code "
                        "needs (it cannot see this conversation). E.g. 'The "
                        "Sonarr container is unreachable on the media stack. "
                        "Check its logs, and if it has crashed, restart it and "
                        "confirm it comes back healthy.'"
                    ),
                },
            },
            "required": ["task"],
        }

    async def execute(self, **kwargs: Any) -> str:
        task = (kwargs.get("task") or "").strip()
        if not task:
            return "Error: 'task' is required — describe what Claude Code should do on the server."

        headers = {"Content-Type": "application/json"}
        if self._shim_token:
            headers["X-Shim-Token"] = self._shim_token

        try:
            session = await self._get_session()
            async with session.post(
                f"{self._shim_url}/run",
                json={"message": task},
                headers=headers,
            ) as resp:
                if resp.status == 401 or resp.status == 403:
                    return (
                        "Error: Claude Code shim rejected the request "
                        "(authentication failed). The shared secret is missing or "
                        "incorrect — check CLAUDE_CODE_SHIM_TOKEN."
                    )
                if resp.status != 200:
                    body = (await resp.text())[:500]
                    return f"Error: Claude Code shim returned HTTP {resp.status}. {body}".strip()

                text = await self._read_sse_text(resp)
        except aiohttp.ClientConnectorError:
            return (
                "Error: Cannot reach the Claude Code shim. Make sure it is running "
                "on the Mac Mini host (launchd job 'uk.noblehaus.claude-code-shim', "
                "or: python3 ~/home-server/docker/claude-code-shim/app.py)."
            )
        except TimeoutError:
            return (
                f"Error: Claude Code timed out after {self._timeout.total:.0f}s. "
                "The task may be too large; try breaking it into smaller steps."
            )
        except Exception as e:
            logger.exception("Claude Code delegation failed")
            return f"Error delegating to Claude Code: {type(e).__name__}: {e}"

        text = text.strip()
        if not text:
            return "Claude Code finished but produced no output."
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + "\n…(output truncated)"
        return text

    async def _read_sse_text(self, resp: aiohttp.ClientResponse) -> str:
        """Accumulate ``text_delta`` deltas from the shim's SSE stream.

        The shim emits ``data: {"type":"text_delta","delta":"..."}`` lines,
        keepalive comment lines (``: keepalive``), and a terminal
        ``data: [DONE]``. We ignore everything but the text deltas.
        """
        parts: list[str] = []
        async for raw_line in resp.content:
            line = raw_line.decode(errors="replace").rstrip("\r\n")
            if not line or line.startswith(":"):
                continue  # blank delimiter or keepalive comment
            if line == "data: [DONE]":
                break
            if line.startswith("data: "):
                try:
                    event = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "text_delta":
                    parts.append(event.get("delta", ""))
        return "".join(parts)
