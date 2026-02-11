"""Self-update tool for Butler.

Allows Butler to check for and apply updates from the GitHub repo.
Runs the update.sh script which pulls changes and rebuilds only
the Docker stacks that have changed files.

Usage:
    tool = SelfUpdateTool()
    result = await tool.execute(action="check")   # check for updates
    result = await tool.execute(action="update")   # pull and rebuild
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

from .base import Tool

logger = logging.getLogger(__name__)

REPO_DIR = os.environ.get("REPO_DIR", os.path.expanduser("~/home-server"))
UPDATE_SCRIPT = os.path.join(REPO_DIR, "scripts", "update.sh")


class SelfUpdateTool(Tool):
    """Check for and apply home server updates from GitHub."""

    @property
    def name(self) -> str:
        return "self_update"

    @property
    def description(self) -> str:
        return (
            "Deploy and update the home server by pulling latest changes from GitHub and rebuilding affected Docker stacks. "
            "Use 'check' to see if updates are available, 'update' to pull and deploy."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["check", "update"],
                    "description": (
                        "check: See if updates are available without applying. "
                        "update: Pull changes and rebuild affected Docker stacks."
                    ),
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")

        if action not in ("check", "update"):
            return f"Error: Unknown action '{action}'. Use 'check' or 'update'."

        if not os.path.isfile(UPDATE_SCRIPT):
            return (
                f"Error: Update script not found at {UPDATE_SCRIPT}. "
                f"Make sure the repo is cloned at {REPO_DIR}."
            )

        args = ["bash", UPDATE_SCRIPT]
        if action == "check":
            args.append("--check")

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "REPO_DIR": REPO_DIR},
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
            output = stdout.decode().strip()

            # Strip ANSI color codes for cleaner LLM output
            output = re.sub(r"\033\[[0-9;]*m", "", output)

            if proc.returncode != 0:
                return f"Update failed (exit {proc.returncode}):\n{output}"

            return output

        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return "Error: Update timed out after 5 minutes."
        except Exception as e:
            logger.exception("Self-update failed")
            return f"Error running update: {e}"
