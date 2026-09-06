"""Media inbox — file completed downloads into the library.

Completed torrents land in ``Downloads/Complete`` on the HomeServer drive.
Radarr/Sonarr import what they were tracking; anything grabbed outside them
(or that failed to import) sits there until someone moves it into the library
on HomeServer2 by hand. This module automates that:

1. ``scan()`` lists every top-level item in Complete, its size, whether
   qBittorrent is still seeding it, and what Sonarr/Radarr's *manual import*
   endpoints make of its files (series/episodes or movie, plus rejections).
2. ``import_items()`` hands matched items to Sonarr/Radarr's ``ManualImport``
   command with ``importMode=move`` (``copy`` while still seeding). They rename,
   place the files under the right root folder and update their own DB.
3. ``move_item()`` is the fallback for things the *arr apps don't recognise:
   the host agent moves the folder into a chosen library root and Jellyfin is
   asked to rescan.

Paths: butler-api sees the HomeServer drive at /mnt/external; qBittorrent,
Sonarr and Radarr see the same folder as /downloads/Complete; the host agent
needs real host paths (/Volumes/HomeServer/...). Keep the three in sync here.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import aiohttp

from . import host_agent
from .config import settings

logger = logging.getLogger(__name__)

# Where Complete lives from each vantage point
INBOX_CONTAINER = os.path.join(settings.external_drive_path, "Downloads", "Complete")
INBOX_ARR = "/downloads/Complete"
INBOX_HOST = "/Volumes/HomeServer/Downloads/Complete"

# Fallback destinations (host paths) for the plain move. Movies/TV are on
# HomeServer2; anime lives on HomeServer. Radarr/Sonarr root folders map to
# the same places via the media-stack bind mounts.
MOVE_DESTINATIONS: dict[str, dict[str, str]] = {
    "movies": {"label": "Movies (HomeServer2)", "path": "/Volumes/HomeServer2/Media/Movies"},
    "tv": {"label": "TV Shows (HomeServer2)", "path": "/Volumes/HomeServer2/Media/TV"},
    "anime-series": {"label": "Anime Series (HomeServer)", "path": "/Volumes/HomeServer/Media/Anime/Series"},
    "anime-movies": {"label": "Anime Movies (HomeServer)", "path": "/Volumes/HomeServer/Media/Anime/Movies"},
    # Not a library: a holding pen for duplicates and leftover junk folders.
    # Nothing here is ever deleted automatically — empty it by hand.
    "trash": {"label": "Trash (Downloads/Trash)", "path": "/Volumes/HomeServer/Downloads/Trash"},
}

MEDIA_EXTENSIONS = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".ts", ".wmv", ".flv", ".webm", ".mpg", ".mpeg", ".iso"}

_ARR_TIMEOUT = aiohttp.ClientTimeout(total=180)   # manualimport over 45 files takes a while


# ── qBittorrent: what is still seeding? ──────────────────────────────


async def _seeding_paths() -> set[str]:
    """content_path of every torrent qBittorrent still knows about."""
    if not settings.qbittorrent_url:
        return set()
    try:
        from .routes.downloads import _qbt_request  # reuse its login/session cache
        resp = await _qbt_request("GET", "/api/v2/torrents/info")
        if resp.status_code != 200:
            return set()
        return {t.get("content_path", "") for t in resp.json()}
    except Exception as e:
        logger.warning("qBittorrent seeding check failed: %s", e)
        return set()


# ── Sonarr / Radarr manual import ────────────────────────────────────


def _arr(app: str) -> tuple[str, str]:
    if app == "sonarr":
        return settings.sonarr_url, settings.sonarr_api_key
    return settings.radarr_url, settings.radarr_api_key


async def _arr_get(app: str, path: str, **params: Any) -> Any:
    url, key = _arr(app)
    if not url or not key:
        return None
    async with aiohttp.ClientSession(timeout=_ARR_TIMEOUT) as s:
        async with s.get(f"{url}/api/v3{path}", headers={"X-Api-Key": key}, params=params) as r:
            if r.status != 200:
                logger.warning("%s GET %s -> %s", app, path, r.status)
                return None
            return await r.json()


async def _arr_post(app: str, path: str, body: dict[str, Any]) -> Any:
    url, key = _arr(app)
    async with aiohttp.ClientSession(timeout=_ARR_TIMEOUT) as s:
        async with s.post(f"{url}/api/v3{path}", headers={"X-Api-Key": key}, json=body) as r:
            data = await r.json(content_type=None)
            if r.status >= 300:
                raise RuntimeError(f"{app} {path} -> HTTP {r.status}: {str(data)[:200]}")
            return data


async def _manual_import_candidates(app: str) -> dict[str, list[dict[str, Any]]]:
    """Candidates from one *arr, grouped by the inbox item they belong to."""
    items = await _arr_get(app, "/manualimport", folder=INBOX_ARR, filterExistingFiles="true")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for it in items or []:
        rel = it.get("relativePath") or ""
        top = rel.split("/", 1)[0] if rel else os.path.basename(it.get("path", ""))
        grouped.setdefault(top, []).append(it)
    return grouped


def _summarise(app: str, files: list[dict[str, Any]]) -> dict[str, Any]:
    """Collapse per-file candidates into one verdict for the item."""
    matched = []
    in_library = 0
    rejections: set[str] = set()
    titles: set[str] = set()
    episodes = 0
    for f in files:
        rej = [r.get("reason", "") for r in f.get("rejections") or []]
        if app == "sonarr":
            eps = f.get("episodes") or []
            ok = bool(f.get("series")) and bool(eps) and not rej
            if f.get("series"):
                titles.add(f["series"].get("title", ""))
            episodes += len(eps)
            have = bool(eps) and all(e.get("hasFile") for e in eps)
        else:
            mv = f.get("movie") or {}
            ok = bool(mv) and not rej
            if mv:
                titles.add(mv.get("title", ""))
            have = bool(mv) and bool(mv.get("hasFile"))
        rejections.update(rej)
        if ok:
            matched.append(f)
            if have:
                in_library += 1
    return {
        "app": app,
        "files": len(files),
        "matched": len(matched),
        # Matched files whose episode/movie already has a file in the library.
        # Importing these makes Sonarr/Radarr *replace* the existing file (an
        # "upgrade"), which is rarely what a stale seeding copy deserves.
        "inLibrary": in_library,
        "titles": sorted(t for t in titles if t),
        "episodes": episodes if app == "sonarr" else None,
        "rejections": sorted(rejections)[:4],
        "_files": matched,
    }


def _has_media(path: str) -> bool:
    if os.path.isfile(path):
        return os.path.splitext(path)[1].lower() in MEDIA_EXTENSIONS
    for _root, _d, files in os.walk(path):
        if any(os.path.splitext(f)[1].lower() in MEDIA_EXTENSIONS for f in files):
            return True
    return False


# ── Public API ───────────────────────────────────────────────────────


def _dir_size(path: str) -> int:
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for root, _d, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


async def scan() -> dict[str, Any]:
    """Everything in the inbox with what we know about it."""
    if not os.path.isdir(INBOX_CONTAINER):
        return {"items": [], "error": f"{INBOX_CONTAINER} is not mounted"}

    names = sorted(n for n in os.listdir(INBOX_CONTAINER) if not n.startswith("."))
    sizes, seeding, sonarr, radarr = await asyncio.gather(
        asyncio.to_thread(lambda: {n: _dir_size(os.path.join(INBOX_CONTAINER, n)) for n in names}),
        _seeding_paths(),
        _manual_import_candidates("sonarr"),
        _manual_import_candidates("radarr"),
    )

    items = []
    for n in names:
        full = os.path.join(INBOX_CONTAINER, n)
        arr_path = f"{INBOX_ARR}/{n}"
        is_seeding = any(p == arr_path or p.startswith(arr_path + "/") for p in seeding)
        s = _summarise("sonarr", sonarr.get(n, [])) if n in sonarr else None
        r = _summarise("radarr", radarr.get(n, [])) if n in radarr else None

        # Pick the app that recognises the item. "partial" = some files were
        # rejected (samples, unknown episodes); importing moves only the
        # matched ones and leaves the rest here.
        suggestion = None
        for app, summ in (("sonarr", s), ("radarr", r)):
            if summ and summ["matched"]:
                suggestion = {
                    "app": app,
                    "titles": summ["titles"],
                    "episodes": summ["episodes"],
                    "files": summ["files"],
                    "matched": summ["matched"],
                    "partial": summ["matched"] < summ["files"],
                    "inLibrary": summ["inLibrary"],
                    "allInLibrary": summ["inLibrary"] == summ["matched"],
                }
                break
        has_media = await asyncio.to_thread(_has_media, full)

        items.append({
            "name": n,
            "isDir": os.path.isdir(full),
            "empty": os.path.isdir(full) and sizes.get(n, 0) == 0,
            # A folder with no video left in it (nfo/txt/screens after an import)
            "leftover": os.path.isdir(full) and sizes.get(n, 0) > 0 and not has_media,
            "bytes": sizes.get(n, 0),
            "modifiedAt": os.path.getmtime(full),
            "ageDays": round((time.time() - os.path.getmtime(full)) / 86400, 1),
            "seeding": is_seeding,
            "suggestion": suggestion,
            "sonarr": {k: v for k, v in (s or {}).items() if not k.startswith("_")} if s else None,
            "radarr": {k: v for k, v in (r or {}).items() if not k.startswith("_")} if r else None,
        })

    return {
        "path": INBOX_HOST,
        "items": items,
        "summary": {
            "count": len(items),
            "bytes": sum(i["bytes"] for i in items),
            "importable": sum(1 for i in items if i["suggestion"] and not i["suggestion"]["allInLibrary"]),
            "inLibrary": sum(1 for i in items if i["suggestion"] and i["suggestion"]["allInLibrary"]),
            "leftovers": sum(1 for i in items if i["empty"] or i["leftover"]),
            "seeding": sum(1 for i in items if i["seeding"]),
        },
        "destinations": [{"key": k, **v} for k, v in MOVE_DESTINATIONS.items()],
    }


def _sonarr_file(f: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": f["path"],
        "folderName": f.get("folderName") or "",
        "seriesId": f["series"]["id"],
        "episodeIds": [e["id"] for e in f.get("episodes") or []],
        "quality": f.get("quality"),
        "languages": f.get("languages") or [],
        "releaseGroup": f.get("releaseGroup") or "",
        "indexerFlags": f.get("indexerFlags") or 0,
        "releaseType": f.get("releaseType") or "unknown",
    }


def _radarr_file(f: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": f["path"],
        "folderName": f.get("folderName") or "",
        "movieId": f["movie"]["id"],
        "quality": f.get("quality"),
        "languages": f.get("languages") or [],
        "releaseGroup": f.get("releaseGroup") or "",
        "indexerFlags": f.get("indexerFlags") or 0,
    }


async def import_items(names: list[str]) -> list[dict[str, Any]]:
    """Hand matched inbox items to Sonarr/Radarr's ManualImport command."""
    seeding, sonarr, radarr = await asyncio.gather(
        _seeding_paths(), _manual_import_candidates("sonarr"), _manual_import_candidates("radarr"),
    )
    results = []
    for n in names:
        arr_path = f"{INBOX_ARR}/{n}"
        is_seeding = any(p == arr_path or p.startswith(arr_path + "/") for p in seeding)
        mode = "copy" if is_seeding else "move"
        s = _summarise("sonarr", sonarr.get(n, [])) if n in sonarr else None
        r = _summarise("radarr", radarr.get(n, [])) if n in radarr else None
        try:
            if s and s["matched"]:
                cmd = await _arr_post("sonarr", "/command", {
                    "name": "ManualImport",
                    "files": [_sonarr_file(f) for f in s["_files"]],
                    "importMode": mode,
                })
                results.append({"name": n, "app": "sonarr", "mode": mode, "commandId": cmd.get("id"),
                                "files": s["matched"], "status": "queued"})
            elif r and r["matched"]:
                cmd = await _arr_post("radarr", "/command", {
                    "name": "ManualImport",
                    "files": [_radarr_file(f) for f in r["_files"]],
                    "importMode": mode,
                })
                results.append({"name": n, "app": "radarr", "mode": mode, "commandId": cmd.get("id"),
                                "files": r["matched"], "status": "queued"})
            else:
                why = (s or {}).get("rejections") or (r or {}).get("rejections") or ["not recognised"]
                results.append({"name": n, "status": "unmatched", "error": "; ".join(why)[:200]})
        except Exception as e:
            logger.exception("Import of %s failed", n)
            results.append({"name": n, "status": "failed", "error": str(e)[:200]})
    return results


async def move_item(name: str, destination_key: str) -> dict[str, Any]:
    """Plain move via the host agent for things the *arr apps don't recognise."""
    dest = MOVE_DESTINATIONS.get(destination_key)
    if not dest:
        raise ValueError(f"unknown destination '{destination_key}'")
    if "/" in name or name in ("", ".", ".."):
        raise ValueError("invalid item name")
    if not os.path.exists(os.path.join(INBOX_CONTAINER, name)):
        raise FileNotFoundError(name)
    seeding = await _seeding_paths()
    arr_path = f"{INBOX_ARR}/{name}"
    if any(p == arr_path or p.startswith(arr_path + "/") for p in seeding):
        raise RuntimeError("still seeding in qBittorrent — remove the torrent first, or import (copy) via Sonarr/Radarr")
    job = await host_agent.start_move(f"{INBOX_HOST}/{name}", f"{dest['path']}/{name}")
    return job


async def command_status(app: str, command_id: int) -> dict[str, Any] | None:
    data = await _arr_get(app, f"/command/{command_id}")
    if not data:
        return None
    return {"app": app, "id": command_id, "status": data.get("status"), "message": data.get("message"),
            "started": data.get("started"), "ended": data.get("ended")}


async def refresh_jellyfin() -> bool:
    if not (settings.jellyfin_url and settings.jellyfin_api_key):
        return False
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.post(f"{settings.jellyfin_url}/Library/Refresh",
                              headers={"X-Emby-Token": settings.jellyfin_api_key}) as r:
                return r.status in (200, 204)
    except Exception as e:
        logger.warning("Jellyfin refresh failed: %s", e)
        return False
