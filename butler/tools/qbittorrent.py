"""qBittorrent tool for Butler — see what's downloading, add, pause, resume, delete.

Radarr/Sonarr/Seerr remain the right way to *request* movies and TV (they
search, rename and import). This tool is for the download client itself:
"what's downloading?", "how fast?", "pause that", and adding a magnet or
.torrent link the user already has.

Paths are the container's: qBittorrent sees the HomeServer drive as
/downloads (Complete/Incomplete), /ebooks and /audiobooks.

Usage:
    tool = QBittorrentTool(url="http://qbittorrent:8081", username="admin", password="...")
    await tool.execute(action="list", filter="downloading")
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .base import Tool

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15
MAX_ROWS = 20

# Human states from qBittorrent's internal ones
_STATE_MAP: dict[str, str] = {
    "downloading": "downloading", "forcedDL": "downloading", "metaDL": "fetching metadata",
    "uploading": "seeding", "forcedUP": "seeding",
    "pausedDL": "paused", "pausedUP": "paused (complete)", "stoppedDL": "paused", "stoppedUP": "paused (complete)",
    "stalledDL": "stalled", "stalledUP": "seeding (idle)",
    "queuedDL": "queued", "queuedUP": "queued",
    "checkingDL": "checking", "checkingUP": "checking", "checkingResumeData": "checking",
    "error": "error", "missingFiles": "error (missing files)", "moving": "moving",
}

# qBittorrent's own filter names for /torrents/info
_FILTERS = {"all", "downloading", "seeding", "completed", "paused", "active", "inactive", "stalled", "errored"}

# Categories a direct add may use, and where qBittorrent should put them.
# Radarr/Sonarr use "movies"/"tv"; the books tool uses "ebooks"/"audiobooks".
_CATEGORY_PATHS: dict[str, str] = {
    "movies": "",           # default save path (/downloads/Complete)
    "tv": "",
    "anime": "",
    "ebooks": "/ebooks",
    "audiobooks": "/audiobooks",
    "other": "",
}


def _fmt_bytes(n: float | int | None) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _fmt_speed(bps: float | int | None) -> str:
    return f"{_fmt_bytes(bps)}/s"


def _fmt_eta(seconds: int | None) -> str:
    if seconds is None or seconds < 0 or seconds >= 8_640_000:
        return "∞"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    return f"{seconds // 86400}d {(seconds % 86400) // 3600}h"


class QBittorrentTool(Tool):
    """Query and control the qBittorrent download client."""

    def __init__(
        self,
        url: str = "",
        username: str = "admin",
        password: str = "",
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None
        self._sid: str | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # -- Tool interface -------------------------------------------------------

    @property
    def name(self) -> str:
        return "qbittorrent"

    @property
    def description(self) -> str:
        return (
            "See and control the qBittorrent download client: what is downloading or "
            "seeding, speeds and ETAs, pause/resume/delete a torrent, or add a magnet "
            "link / .torrent URL the user provides. For movies and TV series prefer "
            "radarr, sonarr or seerr (they search and file things into the library); "
            "use 'add' only for a link the user gives you or content those apps can't "
            "handle. Only delete when the user explicitly asks."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "status", "add", "pause", "resume", "delete"],
                    "description": (
                        "list: torrents (optionally filtered). status: totals and speeds. "
                        "add: add a magnet/.torrent URL. pause/resume/delete: act on one torrent "
                        "by hash or name."
                    ),
                },
                "filter": {
                    "type": "string",
                    "enum": sorted(_FILTERS),
                    "description": "For list: which torrents (default 'all').",
                },
                "category": {
                    "type": "string",
                    "description": (
                        "For list: only this category. For add: one of "
                        + ", ".join(_CATEGORY_PATHS) + " (default 'other')."
                    ),
                },
                "url": {
                    "type": "string",
                    "description": "For add: a magnet: link or an http(s) URL to a .torrent file.",
                },
                "hash": {
                    "type": "string",
                    "description": "For pause/resume/delete: the torrent hash from 'list'.",
                },
                "name": {
                    "type": "string",
                    "description": (
                        "For pause/resume/delete when you don't have the hash: part of the "
                        "torrent name (must match exactly one torrent)."
                    ),
                },
                "delete_files": {
                    "type": "boolean",
                    "description": "For delete: also remove the downloaded files (default false).",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        if not self.url:
            return "Error: QBITTORRENT_URL not configured."
        try:
            if action == "list":
                return await self._list(kwargs.get("filter") or "all", kwargs.get("category"))
            if action == "status":
                return await self._status()
            if action == "add":
                return await self._add(kwargs.get("url") or "", kwargs.get("category") or "other")
            if action in ("pause", "resume", "delete"):
                torrent = await self._find(kwargs.get("hash"), kwargs.get("name"))
                if isinstance(torrent, str):
                    return torrent  # error text
                if action == "delete":
                    return await self._delete(torrent, bool(kwargs.get("delete_files", False)))
                return await self._pause_resume(torrent, action)
            return f"Error: Unknown action '{action}'."
        except aiohttp.ClientError as e:
            return f"Error: could not reach qBittorrent — {e}"
        except TimeoutError:
            return "Error: qBittorrent request timed out."
        except Exception as e:
            logger.exception("qbittorrent tool failed")
            return f"Error: {e}"

    # -- HTTP -----------------------------------------------------------------

    async def _login(self) -> bool:
        session = await self._get_session()
        async with session.post(
            f"{self.url}/api/v2/auth/login",
            data={"username": self.username, "password": self.password},
        ) as resp:
            if resp.status != 200 or (await resp.text()).strip() != "Ok.":
                self._sid = None
                return False
            self._sid = resp.cookies.get("SID").value if resp.cookies.get("SID") else None
            return self._sid is not None

    async def _request(self, method: str, path: str, *, retry: bool = True, **kwargs: Any) -> tuple[int, Any]:
        """Authenticated request; returns (status, json-or-text). Re-logs-in on 403."""
        if self._sid is None and not await self._login():
            return 401, "Error: qBittorrent login failed (check QBITTORRENT_USERNAME/PASSWORD)."
        session = await self._get_session()
        async with session.request(
            method, f"{self.url}{path}", cookies={"SID": self._sid or ""}, **kwargs,
        ) as resp:
            if resp.status == 403 and retry:
                self._sid = None
                return await self._request(method, path, retry=False, **kwargs)
            text = await resp.text()
            try:
                import json
                return resp.status, json.loads(text)
            except ValueError:
                return resp.status, text

    # -- Actions --------------------------------------------------------------

    async def _torrents(self, filter_: str = "all", category: str | None = None) -> list[dict] | str:
        params: dict[str, str] = {"filter": filter_ if filter_ in _FILTERS else "all", "sort": "added_on", "reverse": "true"}
        if category:
            params["category"] = category
        status, data = await self._request("GET", "/api/v2/torrents/info", params=params)
        if status != 200 or not isinstance(data, list):
            return f"Error: qBittorrent returned HTTP {status}"
        return data

    @staticmethod
    def _row(t: dict) -> str:
        state = _STATE_MAP.get(t.get("state", ""), t.get("state", "?"))
        progress = round((t.get("progress") or 0) * 100)
        bits = [f"{progress}%", state, _fmt_bytes(t.get("size"))]
        if (t.get("dlspeed") or 0) > 0:
            bits.append(f"↓{_fmt_speed(t['dlspeed'])} eta {_fmt_eta(t.get('eta'))}")
        if (t.get("upspeed") or 0) > 0:
            bits.append(f"↑{_fmt_speed(t['upspeed'])}")
        if t.get("category"):
            bits.append(f"[{t['category']}]")
        return f"- {t.get('name', '?')} — {' · '.join(bits)} (hash {t.get('hash', '')})"

    async def _list(self, filter_: str, category: str | None) -> str:
        filter_ = filter_ if filter_ in _FILTERS else "all"
        torrents = await self._torrents(filter_, category)
        if isinstance(torrents, str):
            return torrents
        if not torrents:
            scope = f" matching filter '{filter_}'" if filter_ != "all" else ""
            scope += f" in category '{category}'" if category else ""
            return f"No torrents{scope}."
        lines = [f"{len(torrents)} torrent(s){' (' + filter_ + ')' if filter_ != 'all' else ''}:"]
        lines += [self._row(t) for t in torrents[:MAX_ROWS]]
        if len(torrents) > MAX_ROWS:
            lines.append(f"...and {len(torrents) - MAX_ROWS} more. Use a filter or category to narrow down.")
        return "\n".join(lines)

    async def _status(self) -> str:
        torrents = await self._torrents("all")
        if isinstance(torrents, str):
            return torrents
        st_, info = await self._request("GET", "/api/v2/transfer/info")
        counts: dict[str, int] = {}
        for t in torrents:
            counts[_STATE_MAP.get(t.get("state", ""), "other")] = counts.get(_STATE_MAP.get(t.get("state", ""), "other"), 0) + 1
        summary = ", ".join(f"{n} {s}" for s, n in sorted(counts.items(), key=lambda x: -x[1])) or "none"
        speeds = ""
        if st_ == 200 and isinstance(info, dict):
            speeds = (f"\nSpeeds: ↓{_fmt_speed(info.get('dl_info_speed'))} ↑{_fmt_speed(info.get('up_info_speed'))}"
                      f" · session ↓{_fmt_bytes(info.get('dl_info_data'))} ↑{_fmt_bytes(info.get('up_info_data'))}")
        active = [t for t in torrents if (t.get("dlspeed") or 0) > 0]
        detail = ("\nDownloading now:\n" + "\n".join(self._row(t) for t in active[:5])) if active else ""
        return f"qBittorrent: {len(torrents)} torrent(s) — {summary}.{speeds}{detail}"

    async def add(self, url: str, category: str) -> str:
        """Public entry for other tools (Prowlarr grab)."""
        if not self.url:
            return "Error: QBITTORRENT_URL not configured."
        try:
            return await self._add(url, category)
        except aiohttp.ClientError as e:
            return f"Error: could not reach qBittorrent — {e}"
        except TimeoutError:
            return "Error: qBittorrent request timed out."

    async def _add(self, url: str, category: str) -> str:
        url = url.strip()
        if not (url.startswith("magnet:") or url.startswith("http://") or url.startswith("https://")):
            return "Error: 'url' must be a magnet: link or an http(s) link to a .torrent file."
        category = category.lower().strip() or "other"
        if category not in _CATEGORY_PATHS:
            return f"Error: category must be one of {', '.join(_CATEGORY_PATHS)}."
        data: dict[str, str] = {"urls": url, "category": category}
        if _CATEGORY_PATHS[category]:
            data["savepath"] = _CATEGORY_PATHS[category]
        status, body = await self._request("POST", "/api/v2/torrents/add", data=data)
        if status != 200 or (isinstance(body, str) and body.strip() not in ("Ok.", "")):
            return f"Error: qBittorrent refused the torrent (HTTP {status}: {str(body)[:120]})."
        where = _CATEGORY_PATHS[category] or "/downloads/Complete"
        note = ""
        if category in ("movies", "tv", "anime"):
            note = (" Note: added directly, so Radarr/Sonarr will not import it — it will land in "
                    "Downloads/Complete and needs filing from the dashboard's Media inbox.")
        return f"Added to qBittorrent (category: {category}, saving under {where}).{note}"

    async def _find(self, hash_: str | None, name: str | None) -> dict | str:
        torrents = await self._torrents("all")
        if isinstance(torrents, str):
            return torrents
        if hash_:
            h = hash_.strip().lower()
            matches = [t for t in torrents if (t.get("hash") or "").lower().startswith(h)]
        elif name:
            n = name.strip().lower()
            matches = [t for t in torrents if n in (t.get("name") or "").lower()]
        else:
            return "Error: give a 'hash' (from list) or a 'name' fragment."
        if not matches:
            return f"No torrent matches {'hash ' + hash_ if hash_ else repr(name)}."
        if len(matches) > 1:
            names = "; ".join((t.get("name") or "?")[:50] for t in matches[:5])
            return f"{len(matches)} torrents match — be more specific: {names}"
        return matches[0]

    async def _pause_resume(self, torrent: dict, action: str) -> str:
        # qBittorrent 5 renamed pause/resume to stop/start; try new then old.
        for path in ((f"/api/v2/torrents/{'stop' if action == 'pause' else 'start'}"),
                     (f"/api/v2/torrents/{action}")):
            status, _ = await self._request("POST", path, data={"hashes": torrent["hash"]})
            if status == 200:
                return f"{'Paused' if action == 'pause' else 'Resumed'}: {torrent.get('name')}"
        return f"Error: qBittorrent would not {action} that torrent (HTTP {status})."

    async def _delete(self, torrent: dict, delete_files: bool) -> str:
        status, _ = await self._request(
            "POST", "/api/v2/torrents/delete",
            data={"hashes": torrent["hash"], "deleteFiles": "true" if delete_files else "false"},
        )
        if status != 200:
            return f"Error: qBittorrent would not delete that torrent (HTTP {status})."
        return f"Deleted: {torrent.get('name')}{' (files removed too)' if delete_files else ' (files kept)'}"
