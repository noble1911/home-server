"""Prowlarr tool for Butler — search the indexers and grab a chosen result.

Radarr/Sonarr/Seerr are still the right way to *request* a film or series
(they search, rename and import). This tool is for when the user wants to
see what's actually out there and pick: "search the indexers for X",
"grab the 1080p one with the most seeders". A grab hands the torrent to
qBittorrent; movies/TV then land in Downloads/Complete for the dashboard's
Media inbox to file, books go straight to /ebooks or /audiobooks.

Usage:
    tool = ProwlarrTool(url="http://prowlarr:9696", api_key="...", qbit=qbittorrent_tool)
    await tool.execute(action="search", query="Project Hail Mary", category="books")
    await tool.execute(action="grab", result_id="a1b2c3", category="ebooks")
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import OrderedDict
from typing import Any

import aiohttp

from .base import Tool

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 45          # Prowlarr fans out to every indexer
DEFAULT_LIMIT = 10
MAX_LIMIT = 25
RESULT_CACHE_SIZE = 300       # search results kept for later grabs

# Newznab category ids Prowlarr understands. Public trackers often ignore
# them, so a categorised search that returns nothing is retried uncategorised.
_CATEGORY_IDS: dict[str, list[int]] = {
    "movies": [2000],
    "tv": [5000],
    "anime": [5070],
    "books": [7000, 7020],
    "audiobooks": [3030],
    "other": [],
}

# Which qBittorrent category a grab defaults to, per search category
_QBIT_CATEGORY: dict[str, str] = {
    "movies": "movies", "tv": "tv", "anime": "anime",
    "books": "ebooks", "audiobooks": "audiobooks", "other": "other",
}

_QUALITY_RE = re.compile(
    r"\b(2160p|4k|1080p|720p|480p|remux|bluray|blu-ray|web-?dl|webrip|hdtv|hevc|x265|x264|h\.?264|h\.?265|"
    r"dv|hdr(?:10\+?)?|atmos|dts(?:-hd)?|epub|mobi|azw3|pdf|m4b|mp3|flac)\b",
    re.IGNORECASE,
)


def _fmt_bytes(n: float | int | None) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _quality_tags(title: str) -> str:
    seen: list[str] = []
    for m in _QUALITY_RE.findall(title):
        t = m.upper().replace("BLU-RAY", "BLURAY")
        if t not in seen:
            seen.append(t)
    return " ".join(seen[:5])


def _result_id(r: dict) -> str:
    key = r.get("guid") or r.get("downloadUrl") or r.get("magnetUrl") or r.get("title") or ""
    return hashlib.sha1(key.encode()).hexdigest()[:6]


class ProwlarrTool(Tool):
    """Search Prowlarr's indexers; grab a result into qBittorrent."""

    def __init__(
        self,
        url: str = "",
        api_key: str = "",
        qbit: Any | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self._qbit = qbit  # QBittorrentTool (has .add(url, category))
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None
        self._results: OrderedDict[str, dict] = OrderedDict()

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
        return "prowlarr"

    @property
    def description(self) -> str:
        return (
            "Search the torrent indexers (via Prowlarr) and download a chosen result. "
            "Use 'search' to list candidates with size, seeders, quality and indexer, "
            "then 'grab' with the result_id the user picks to send it to qBittorrent. "
            "Use this when the user wants to see or choose the actual release, or for "
            "content Radarr/Sonarr can't handle; for an ordinary 'add this film/show' "
            "request prefer radarr, sonarr or seerr, which also file it into the library. "
            "'indexers' lists the configured indexers and whether they're enabled."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "grab", "indexers"],
                    "description": "search: find releases. grab: download one result. indexers: list indexers.",
                },
                "query": {
                    "type": "string",
                    "description": "For search: title, optionally with year, season/episode or format (e.g. 'Dune 2021 1080p').",
                },
                "category": {
                    "type": "string",
                    "enum": list(_CATEGORY_IDS),
                    "description": (
                        "For search: narrows the indexer categories and sets the default download "
                        "category. For grab: qBittorrent category override "
                        "(movies, tv, anime, ebooks, audiobooks, other)."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": f"For search: how many results to show (default {DEFAULT_LIMIT}, max {MAX_LIMIT}).",
                },
                "result_id": {
                    "type": "string",
                    "description": "For grab: the id shown in a previous search result.",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        if not self.url or not self.api_key:
            return "Error: PROWLARR_URL / PROWLARR_API_KEY not configured."
        try:
            if action == "search":
                return await self._search(
                    (kwargs.get("query") or "").strip(),
                    (kwargs.get("category") or "other").lower(),
                    int(kwargs.get("limit") or DEFAULT_LIMIT),
                )
            if action == "grab":
                return await self._grab((kwargs.get("result_id") or "").strip().lower(), kwargs.get("category"))
            if action == "indexers":
                return await self._indexers()
            return f"Error: Unknown action '{action}'."
        except aiohttp.ClientError as e:
            return f"Error: could not reach Prowlarr — {e}"
        except TimeoutError:
            return "Error: Prowlarr search timed out (indexers slow). Try again or narrow the query."
        except Exception as e:
            logger.exception("prowlarr tool failed")
            return f"Error: {e}"

    # -- Prowlarr HTTP --------------------------------------------------------

    async def _get(self, path: str, params: list[tuple[str, str]] | None = None) -> tuple[int, Any]:
        session = await self._get_session()
        async with session.get(
            f"{self.url}/api/v1{path}", params=params or [], headers={"X-Api-Key": self.api_key},
        ) as resp:
            if resp.status == 401:
                return 401, "Error: Invalid Prowlarr API key."
            try:
                return resp.status, await resp.json(content_type=None)
            except ValueError:
                return resp.status, await resp.text()

    async def _query(self, query: str, category: str, limit: int) -> list[dict] | str:
        params: list[tuple[str, str]] = [("query", query), ("type", "search"), ("limit", str(max(limit * 4, 40)))]
        cats = _CATEGORY_IDS.get(category, [])
        status, data = await self._get("/search", params + [("categories", str(c)) for c in cats])
        if status != 200 or not isinstance(data, list):
            return f"Error: Prowlarr returned HTTP {status}: {str(data)[:120]}"
        if not data and cats:
            # Public trackers frequently ignore categories — retry without
            status, data = await self._get("/search", params)
            if status != 200 or not isinstance(data, list):
                return f"Error: Prowlarr returned HTTP {status}"
        return [r for r in data if (r.get("protocol") or "torrent") == "torrent" and (r.get("downloadUrl") or r.get("magnetUrl"))]

    # -- Actions --------------------------------------------------------------

    def _remember(self, results: list[dict]) -> None:
        for r in results:
            rid = _result_id(r)
            self._results.pop(rid, None)
            self._results[rid] = r
        while len(self._results) > RESULT_CACHE_SIZE:
            self._results.popitem(last=False)

    async def _search(self, query: str, category: str, limit: int) -> str:
        if not query:
            return "Error: 'query' is required for search."
        if category not in _CATEGORY_IDS:
            return f"Error: category must be one of {', '.join(_CATEGORY_IDS)}."
        limit = max(1, min(limit, MAX_LIMIT))

        results = await self._query(query, category, limit)
        if isinstance(results, str):
            return results
        if not results:
            return f"No torrent results for '{query}'{' in ' + category if category != 'other' else ''}. Try fewer words or a different spelling."

        results.sort(key=lambda r: (r.get("seeders") or 0, r.get("size") or 0), reverse=True)
        shown = results[:limit]
        self._remember(shown)

        lines = [f"{len(results)} result(s) for '{query}' — top {len(shown)} by seeders "
                 f"(grab with result_id; default category '{_QBIT_CATEGORY.get(category, 'other')}'):"]
        for r in shown:
            q = _quality_tags(r.get("title") or "")
            lines.append(
                f"- [{_result_id(r)}] {r.get('title', '?')} — {_fmt_bytes(r.get('size'))}, "
                f"{r.get('seeders', 0)} seeders/{r.get('leechers', 0)} leechers, {r.get('indexer', '?')}"
                + (f", {q}" if q else "")
            )
        return "\n".join(lines)

    async def _grab(self, result_id: str, category: str | None) -> str:
        if not result_id:
            return "Error: 'result_id' from a previous search is required."
        r = self._results.get(result_id)
        if r is None:
            return f"No cached result with id '{result_id}'. Run the search again and use an id from it."
        if self._qbit is None:
            return "Error: qBittorrent is not configured, so I can't download this."
        url = r.get("magnetUrl") or r.get("downloadUrl")
        if not url:
            return "Error: that result has no download link."
        cat = (category or "").lower().strip()
        if not cat:
            # Infer from the result's Newznab categories
            ids = {c.get("id") for c in (r.get("categories") or []) if isinstance(c, dict)}
            cat = ("movies" if any(2000 <= (i or 0) < 3000 for i in ids)
                   else "tv" if any(5000 <= (i or 0) < 6000 for i in ids)
                   else "audiobooks" if 3030 in ids
                   else "ebooks" if any(7000 <= (i or 0) < 8000 for i in ids)
                   else "other")
        out = await self._qbit.add(url, cat)
        if out.startswith("Error"):
            return out
        return f"Grabbed '{r.get('title', '?')}' ({_fmt_bytes(r.get('size'))}, {r.get('seeders', 0)} seeders). {out}"

    async def _indexers(self) -> str:
        status, data = await self._get("/indexer")
        if status != 200 or not isinstance(data, list):
            return f"Error: Prowlarr returned HTTP {status}"
        if not data:
            return "No indexers configured in Prowlarr."
        lines = [f"{len(data)} indexer(s):"]
        for ix in data:
            caps = ix.get("capabilities") or {}
            cats = sorted({c.get("name", "") for c in caps.get("categories", []) if isinstance(c, dict)})[:4]
            lines.append(
                f"- {ix.get('name', '?')} — {'enabled' if ix.get('enable') else 'disabled'}, "
                f"{ix.get('protocol', '?')}, {ix.get('privacy', '?')}"
                + (f", categories: {', '.join(cats)}" if cats else "")
            )
        return "\n".join(lines)
