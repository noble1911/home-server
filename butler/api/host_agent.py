"""Client for the host agent (docker/host-agent) running on the Mac itself.

butler-api lives in the OrbStack VM, so anything about the bare-metal host —
real CPU/RAM, native apps, drives that aren't bind-mounted — comes from here.
Every call degrades to ``None`` when the agent is unreachable or unconfigured,
so callers can fall back to in-container data.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=8)


def configured() -> bool:
    return bool(settings.host_agent_url and settings.host_agent_token)


def _headers() -> dict[str, str]:
    return {"X-Agent-Token": settings.host_agent_token}


async def _get(path: str, **params: Any) -> dict[str, Any] | None:
    if not configured():
        return None
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(f"{settings.host_agent_url}{path}", headers=_headers(), params=params) as resp:
                if resp.status != 200:
                    logger.warning("host-agent %s -> HTTP %s", path, resp.status)
                    return None
                return await resp.json()
    except Exception as e:
        logger.warning("host-agent %s unreachable: %s", path, e)
        return None


async def get_metrics() -> dict[str, Any] | None:
    return await _get("/metrics")


async def get_storage(refresh_categories: bool = False) -> dict[str, Any] | None:
    params = {"refresh": "categories"} if refresh_categories else {}
    return await _get("/storage", **params)


async def get_jobs() -> list[dict[str, Any]]:
    data = await _get("/jobs")
    return (data or {}).get("jobs", [])


async def start_move(source: str, destination: str) -> dict[str, Any]:
    """Ask the host to move a file/folder. Raises RuntimeError with the agent's reason."""
    if not configured():
        raise RuntimeError("host agent not configured")
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        async with session.post(
            f"{settings.host_agent_url}/move",
            headers=_headers(),
            json={"source": source, "destination": destination},
        ) as resp:
            if resp.status not in (200, 202):
                raise RuntimeError(f"host agent refused move: {resp.reason} ({resp.status})")
            return await resp.json()


async def get_history(minutes: int = 60) -> dict[str, Any] | None:
    return await _get("/history", minutes=str(minutes))


async def get_trash() -> dict[str, Any] | None:
    return await _get("/trash")


async def empty_trash() -> dict[str, Any]:
    if not configured():
        raise RuntimeError("host agent not configured")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600)) as session:
        async with session.post(f"{settings.host_agent_url}/trash/empty", headers=_headers()) as resp:
            if resp.status != 200:
                raise RuntimeError(f"host agent refused: {resp.reason} ({resp.status})")
            return await resp.json()
