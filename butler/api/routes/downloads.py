"""Download management routes (qBittorrent proxy).

GET    /api/downloads              — List all torrents with progress, speed, state, ETA
POST   /api/downloads/{hash}/pause — Pause a torrent
POST   /api/downloads/{hash}/resume — Resume a torrent
DELETE /api/downloads/{hash}       — Delete a torrent (optional ?deleteFiles=true)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import settings
from ..deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# ── qBittorrent session management ───────────────────────────────────

_qbt_sid: str | None = None


async def _qbt_login() -> str:
    """Authenticate with qBittorrent and return SID cookie."""
    global _qbt_sid

    url = settings.qbittorrent_url
    if not url:
        raise HTTPException(503, "qBittorrent URL not configured")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{url}/api/v2/auth/login",
            data={
                "username": settings.qbittorrent_username,
                "password": settings.qbittorrent_password,
            },
            timeout=10,
        )

    if resp.status_code != 200 or resp.text.strip() != "Ok.":
        _qbt_sid = None
        raise HTTPException(502, "Failed to authenticate with qBittorrent")

    sid = resp.cookies.get("SID")
    if not sid:
        raise HTTPException(502, "No SID cookie in qBittorrent login response")

    _qbt_sid = sid
    return sid


async def _qbt_request(
    method: str, path: str, retry: bool = True, **kwargs: Any
) -> httpx.Response:
    """Make an authenticated request to qBittorrent, re-login on 403."""
    global _qbt_sid

    url = settings.qbittorrent_url
    if not url:
        raise HTTPException(503, "qBittorrent URL not configured")

    if _qbt_sid is None:
        await _qbt_login()

    async with httpx.AsyncClient(cookies={"SID": _qbt_sid}) as client:  # type: ignore[arg-type]
        resp = await client.request(method, f"{url}{path}", timeout=10, **kwargs)

    if resp.status_code == 403 and retry:
        await _qbt_login()
        return await _qbt_request(method, path, retry=False, **kwargs)

    return resp


# ── Helpers ──────────────────────────────────────────────────────────

_STATE_MAP: dict[str, str] = {
    "downloading": "downloading",
    "forcedDL": "downloading",
    "uploading": "seeding",
    "forcedUP": "seeding",
    "pausedDL": "paused",
    "pausedUP": "paused",
    "stalledDL": "stalled",
    "stalledUP": "stalled",
    "queuedDL": "queued",
    "queuedUP": "queued",
    "checkingDL": "checking",
    "checkingUP": "checking",
    "checkingResumeData": "checking",
    "error": "error",
    "missingFiles": "error",
    "moving": "moving",
}


def _format_bytes(n: int | float) -> str:
    """Format byte count into a human-readable string."""
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(value) < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _format_speed(bps: int | float) -> str:
    """Format bytes/s into a human-readable speed string."""
    return f"{_format_bytes(bps)}/s"


def _format_eta(seconds: int) -> str:
    """Format ETA seconds into a human-readable string."""
    if seconds < 0 or seconds == 8640000:  # qBittorrent uses 8640000 for infinity
        return "∞"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours < 24:
        return f"{hours}h {minutes}m"
    days = hours // 24
    return f"{days}d {hours % 24}h"


def _format_torrent(t: dict[str, Any]) -> dict[str, Any]:
    """Format a single qBittorrent torrent into our API shape."""
    added_ts = t.get("added_on", 0)
    added_on = (
        datetime.fromtimestamp(added_ts, tz=timezone.utc).isoformat()
        if added_ts
        else None
    )

    return {
        "hash": t["hash"],
        "name": t.get("name", "Unknown"),
        "progress": round(t.get("progress", 0), 4),
        "size": t.get("size", 0),
        "sizeFormatted": _format_bytes(t.get("size", 0)),
        "downloaded": t.get("downloaded", 0),
        "downloadedFormatted": _format_bytes(t.get("downloaded", 0)),
        "dlSpeed": t.get("dlspeed", 0),
        "dlSpeedFormatted": _format_speed(t.get("dlspeed", 0)),
        "upSpeed": t.get("upspeed", 0),
        "upSpeedFormatted": _format_speed(t.get("upspeed", 0)),
        "eta": t.get("eta", 0),
        "etaFormatted": _format_eta(t.get("eta", 0)),
        "state": _STATE_MAP.get(t.get("state", ""), t.get("state", "unknown")),
        "category": t.get("category", ""),
        "addedOn": added_on,
    }


# ── Routes ───────────────────────────────────────────────────────────


@router.get("/downloads")
async def list_downloads(
    _user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """List all torrents with progress, speed, state, and ETA."""
    resp = await _qbt_request("GET", "/api/v2/torrents/info")

    if resp.status_code != 200:
        raise HTTPException(502, f"qBittorrent returned {resp.status_code}")

    raw_torrents: list[dict[str, Any]] = resp.json()

    torrents = [_format_torrent(t) for t in raw_torrents]

    # Sort: downloading first, then by progress descending
    state_order = {
        "downloading": 0,
        "stalled": 1,
        "queued": 2,
        "checking": 3,
        "moving": 4,
        "paused": 5,
        "error": 6,
        "seeding": 7,
    }
    torrents.sort(key=lambda t: (state_order.get(t["state"], 99), -t["progress"]))

    # Summary
    downloading = sum(1 for t in torrents if t["state"] == "downloading")
    seeding = sum(1 for t in torrents if t["state"] == "seeding")
    paused = sum(1 for t in torrents if t["state"] == "paused")
    total_dl_speed = sum(t["dlSpeed"] for t in torrents)

    return {
        "torrents": torrents,
        "summary": {
            "total": len(torrents),
            "downloading": downloading,
            "seeding": seeding,
            "paused": paused,
            "dlSpeed": total_dl_speed,
            "dlSpeedFormatted": _format_speed(total_dl_speed),
        },
    }


@router.post("/downloads/{torrent_hash}/pause")
async def pause_torrent(
    torrent_hash: str,
    _user_id: str = Depends(get_current_user),
) -> dict[str, str]:
    """Pause a torrent."""
    resp = await _qbt_request(
        "POST",
        "/api/v2/torrents/pause",
        data={"hashes": torrent_hash},
    )
    if resp.status_code != 200:
        raise HTTPException(502, f"qBittorrent returned {resp.status_code}")
    return {"status": "ok"}


@router.post("/downloads/{torrent_hash}/resume")
async def resume_torrent(
    torrent_hash: str,
    _user_id: str = Depends(get_current_user),
) -> dict[str, str]:
    """Resume a torrent."""
    resp = await _qbt_request(
        "POST",
        "/api/v2/torrents/resume",
        data={"hashes": torrent_hash},
    )
    if resp.status_code != 200:
        raise HTTPException(502, f"qBittorrent returned {resp.status_code}")
    return {"status": "ok"}


@router.delete("/downloads/{torrent_hash}")
async def delete_torrent(
    torrent_hash: str,
    delete_files: bool = Query(False, alias="deleteFiles"),
    _user_id: str = Depends(get_current_user),
) -> dict[str, str]:
    """Delete a torrent, optionally removing downloaded files."""
    resp = await _qbt_request(
        "POST",
        "/api/v2/torrents/delete",
        data={
            "hashes": torrent_hash,
            "deleteFiles": str(delete_files).lower(),
        },
    )
    if resp.status_code != 200:
        raise HTTPException(502, f"qBittorrent returned {resp.status_code}")
    return {"status": "ok"}
