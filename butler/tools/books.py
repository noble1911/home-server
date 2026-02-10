"""Book search and download tool for Butler.

Searches for books via Open Library, finds torrents via Prowlarr,
and sends them to qBittorrent for download — bypassing the unreliable
Readarr/Bookshelf metadata chain entirely.

Usage:
    tool = BookTool(
        prowlarr_url="http://prowlarr:9696",
        prowlarr_api_key="abc123",
        qbit_url="http://qbittorrent:8081",
        qbit_user="admin",
        qbit_pass="password",
    )
    result = await tool.execute(action="search", query="Dune Frank Herbert")

    # When shutting down
    await tool.close()
"""

from __future__ import annotations

import logging
import re
from typing import Any

import aiohttp

from .base import Tool

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15

# Words to strip from query on fallback retry (format-specific noise)
_FORMAT_NOISE = re.compile(
    r"\b(audiobook|ebook|e-book|epub|pdf|m4b|mp3|mobi|kindle)\b",
    re.IGNORECASE,
)


class BookTool(Tool):
    """Search and download books via Open Library + Prowlarr + qBittorrent.

    Actions:
        search: Find books by title/author using Open Library.
        download: Search Prowlarr for a book torrent and send it to qBittorrent.
    """

    def __init__(
        self,
        prowlarr_url: str = "",
        prowlarr_api_key: str = "",
        qbit_url: str = "",
        qbit_user: str = "admin",
        qbit_pass: str = "",
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.prowlarr_url = prowlarr_url.rstrip("/")
        self.prowlarr_api_key = prowlarr_api_key
        self.qbit_url = qbit_url.rstrip("/")
        self.qbit_user = qbit_user
        self.qbit_pass = qbit_pass
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None
        self._qbit_sid: str | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "books"

    @property
    def description(self) -> str:
        return (
            "Search for books and download them. "
            "Use 'search' to find books by title or author (via Open Library). "
            "Use 'download' to find and download a book torrent."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "download"],
                    "description": (
                        "search: Find books by title/author. "
                        "download: Search for a torrent and start downloading."
                    ),
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Search query — book title, author, or both. "
                        "For download, be specific (e.g. 'Dune Frank Herbert epub')."
                    ),
                },
                "format": {
                    "type": "string",
                    "enum": ["audiobook", "ebook"],
                    "description": (
                        "Whether to download as audiobook or ebook. "
                        "Defaults to ebook."
                    ),
                },
            },
            "required": ["action", "query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        query = kwargs.get("query", "").strip()

        if not query:
            return "Error: query is required."

        try:
            if action == "search":
                return await self._search(query)
            elif action == "download":
                fmt = kwargs.get("format", "ebook")
                return await self._download(query, fmt=fmt)
            else:
                return f"Error: Unknown action '{action}'"
        except aiohttp.ClientError as e:
            return f"Error: Connection failed — {e}"
        except TimeoutError:
            return "Error: Request timed out."
        except Exception as e:
            return f"Error: {e}"

    # ------------------------------------------------------------------
    # Search via Open Library
    # ------------------------------------------------------------------

    async def _search(self, query: str) -> str:
        """Search Open Library for books."""
        session = await self._get_session()
        url = "https://openlibrary.org/search.json"
        params = {
            "q": query,
            "fields": "key,title,author_name,first_publish_year,isbn,edition_count",
            "limit": 5,
        }

        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                return f"Error: Open Library returned HTTP {resp.status}"
            data = await resp.json()

        docs = data.get("docs", [])
        if not docs:
            return f"No books found for '{query}'."

        lines = [f"Found {len(docs)} result(s) for '{query}':\n"]
        for i, doc in enumerate(docs, 1):
            title = doc.get("title", "Unknown")
            authors = ", ".join(doc.get("author_name", ["Unknown"]))
            year = doc.get("first_publish_year", "")
            year_str = f" ({year})" if year else ""
            lines.append(f"{i}. {title} by {authors}{year_str}")

        lines.append(
            "\nTo download, use action='download' with a specific query "
            "like 'Dune Frank Herbert epub'."
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Download via Prowlarr → qBittorrent
    # ------------------------------------------------------------------

    async def _download(self, query: str, fmt: str = "ebook") -> str:
        """Search Prowlarr for book torrents and send the best one to qBittorrent."""
        if not self.prowlarr_api_key:
            return "Error: PROWLARR_API_KEY not configured."
        if not self.qbit_url:
            return "Error: QBITTORRENT_URL not configured."

        # 1. Search Prowlarr (unfiltered — public trackers don't use Newznab categories)
        session = await self._get_session()
        search_url = f"{self.prowlarr_url}/api/v1/search"
        params: dict[str, Any] = {"query": query, "limit": 20}
        headers = {"X-Api-Key": self.prowlarr_api_key}

        async with session.get(search_url, params=params, headers=headers) as resp:
            if resp.status == 401:
                return "Error: Invalid Prowlarr API key."
            if resp.status != 200:
                return f"Error: Prowlarr returned HTTP {resp.status}"
            results = await resp.json()

        if not results:
            # Retry with format-noise words stripped (e.g. "Dune audiobook" → "Dune")
            cleaned = _FORMAT_NOISE.sub("", query).strip()
            cleaned = re.sub(r"\s{2,}", " ", cleaned)  # collapse double spaces
            if cleaned and cleaned.lower() != query.lower():
                params["query"] = cleaned
                async with session.get(search_url, params=params, headers=headers) as resp:
                    if resp.status == 200:
                        results = await resp.json()

        if not results:
            return f"No torrents found for '{query}'. Try a different search term."

        # 2. Pick best result (most seeders with reasonable size)
        results = [r for r in results if r.get("downloadUrl")]
        if not results:
            return f"Found results but no downloadable torrents for '{query}'."

        results.sort(key=lambda r: r.get("seeders", 0), reverse=True)
        best = results[0]

        title = best.get("title", "Unknown")
        size_mb = (best.get("size", 0) or 0) / (1024 ** 2)
        seeders = best.get("seeders", 0)
        indexer = best.get("indexer", "Unknown")
        download_url = best["downloadUrl"]

        # 3. Send to qBittorrent with format-aware path
        if fmt == "audiobook":
            savepath = "/audiobooks"
            category = "audiobooks"
        else:
            savepath = "/ebooks"
            category = "ebooks"

        add_result = await self._qbit_add(
            download_url, category=category, savepath=savepath
        )
        if add_result is not None:
            return add_result  # Error message

        return (
            f"Downloading {fmt}: {title}\n"
            f"Size: {size_mb:.1f} MB | Seeders: {seeders} | Source: {indexer}\n"
            f"Sent to qBittorrent (category: {category}). "
            f"It will appear in Audiobookshelf once complete."
        )

    # ------------------------------------------------------------------
    # qBittorrent helpers
    # ------------------------------------------------------------------

    async def _qbit_login(self) -> str | None:
        """Authenticate with qBittorrent. Returns error message or None on success."""
        session = await self._get_session()
        try:
            async with session.post(
                f"{self.qbit_url}/api/v2/auth/login",
                data={"username": self.qbit_user, "password": self.qbit_pass},
            ) as resp:
                if resp.status != 200 or (await resp.text()).strip() != "Ok.":
                    return "Error: Failed to authenticate with qBittorrent."
                sid = resp.cookies.get("SID")
                if not sid:
                    return "Error: No SID cookie from qBittorrent."
                self._qbit_sid = sid.value
                return None
        except Exception as e:
            return f"Error connecting to qBittorrent: {e}"

    async def _qbit_add(
        self, download_url: str, category: str = "", savepath: str = ""
    ) -> str | None:
        """Add a torrent to qBittorrent. Returns error message or None on success."""
        if not self._qbit_sid:
            err = await self._qbit_login()
            if err:
                return err

        session = await self._get_session()
        data: dict[str, str] = {"urls": download_url}
        if category:
            data["category"] = category
        if savepath:
            data["savepath"] = savepath

        async with session.post(
            f"{self.qbit_url}/api/v2/torrents/add",
            data=data,
            cookies={"SID": self._qbit_sid},
        ) as resp:
            if resp.status == 403:
                # Re-login and retry once
                err = await self._qbit_login()
                if err:
                    return err
                async with session.post(
                    f"{self.qbit_url}/api/v2/torrents/add",
                    data=data,
                    cookies={"SID": self._qbit_sid},
                ) as retry_resp:
                    if retry_resp.status != 200:
                        return f"Error: qBittorrent returned HTTP {retry_resp.status}"
            elif resp.status != 200:
                return f"Error: qBittorrent returned HTTP {resp.status}"

        return None
