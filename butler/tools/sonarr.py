"""Sonarr integration tool for Butler.

This tool allows the agent to manage TV series via Sonarr's REST API,
enabling voice and text-based TV library management.

Usage:
    The tool is automatically registered when SONARR_URL is configured.
    Requires SONARR_URL and SONARR_API_KEY in the application settings.

Example:
    tool = SonarrTool(base_url="http://sonarr:8989", api_key="abc123")
    result = await tool.execute(action="search_series", title="Breaking Bad")

    # When shutting down
    await tool.close()

API Reference:
    https://sonarr.tv/docs/api/
"""

from __future__ import annotations

from typing import Any

import aiohttp

from .base import Tool

# Default timeout for HTTP requests (seconds)
DEFAULT_TIMEOUT = 10


class SonarrTool(Tool):
    """Manage TV series in Sonarr via REST API.

    Supports searching TVDB for series, adding them to the library,
    checking library status, deleting series, and viewing the download queue.

    The tool reuses HTTP sessions for better performance and
    caches quality profiles / root folders to minimise API calls.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Initialize the Sonarr tool.

        Args:
            base_url: Sonarr URL (e.g. http://sonarr:8989)
            api_key: Sonarr API key (Settings > General > Security)
            timeout: HTTP request timeout in seconds (default: 10)
        """
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None
        # Cached config for auto-detection
        self._quality_profiles: list[dict] | None = None
        self._root_folders: list[dict] | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"X-Api-Key": self.api_key},
                timeout=self.timeout,
            )
        return self._session

    async def close(self) -> None:
        """Close the HTTP session.

        Should be called when shutting down to cleanly release connections.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "sonarr"

    @property
    def description(self) -> str:
        return (
            "Manage TV series in Sonarr. Search for shows on TVDB, add them to "
            "your library, check if a series exists and its download status, "
            "view active downloads, or delete series from your collection."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "search_series",
                        "add_series",
                        "check_library",
                        "delete_series",
                        "get_queue",
                    ],
                    "description": (
                        "search_series: Find TV shows on TVDB. "
                        "add_series: Add a series (needs tvdb_id from search). "
                        "check_library: Check if a series exists and its status. "
                        "delete_series: Remove a series (needs series_id from check). "
                        "get_queue: Show active downloads with progress."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": (
                        "Series title to search for. "
                        "Used by search_series, add_series, and check_library."
                    ),
                },
                "tvdb_id": {
                    "type": "integer",
                    "description": (
                        "TVDB ID from search results. Required for add_series."
                    ),
                },
                "series_id": {
                    "type": "integer",
                    "description": (
                        "Sonarr series ID from check_library results. "
                        "Required for delete_series."
                    ),
                },
                "delete_files": {
                    "type": "boolean",
                    "description": (
                        "Also delete episode files from disk (default: false). "
                        "Only used with delete_series."
                    ),
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]

        if not self.base_url or not self.api_key:
            return "Error: SONARR_URL and SONARR_API_KEY must be configured."

        try:
            if action == "search_series":
                return await self._search_series(kwargs.get("title", ""))
            elif action == "add_series":
                return await self._add_series(
                    tvdb_id=kwargs.get("tvdb_id"),
                    title=kwargs.get("title", ""),
                )
            elif action == "check_library":
                return await self._check_library(kwargs.get("title", ""))
            elif action == "delete_series":
                return await self._delete_series(
                    series_id=kwargs.get("series_id"),
                    delete_files=kwargs.get("delete_files", False),
                )
            elif action == "get_queue":
                return await self._get_queue()
            else:
                return f"Error: Unknown action '{action}'"
        except aiohttp.ClientError as e:
            return f"Error connecting to Sonarr: {e}"
        except TimeoutError:
            return "Error: Sonarr request timed out"
        except Exception as e:
            return f"Error: {e}"

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def _search_series(self, title: str) -> str:
        """Search TVDB for series via Sonarr's lookup endpoint."""
        if not title:
            return "Error: title is required for search_series"

        session = await self._get_session()
        url = f"{self.base_url}/api/v3/series/lookup"

        async with session.get(url, params={"term": title}) as resp:
            if resp.status == 401:
                return "Error: Invalid Sonarr API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            results = await resp.json()
            if not results or not isinstance(results, list):
                return f"No series found for '{title}'"

            return self._format_search_results(results[:5], title)

    async def _add_series(
        self,
        tvdb_id: int | None,
        title: str,
    ) -> str:
        """Add a series to Sonarr using its TVDB ID."""
        if not tvdb_id:
            return "Error: tvdb_id is required for add_series (get it from search_series)"

        session = await self._get_session()

        # Fetch full series data from TVDB via Sonarr
        lookup_url = f"{self.base_url}/api/v3/series/lookup"
        async with session.get(lookup_url, params={"term": f"tvdb:{tvdb_id}"}) as resp:
            if resp.status != 200:
                return f"Error fetching series details: HTTP {resp.status}"
            results = await resp.json()

        if not results or not isinstance(results, list) or len(results) == 0:
            return f"Error: Could not find series data for TVDB ID {tvdb_id}."

        series_data = results[0]

        # Auto-detect quality profile, content type, and root folder
        quality_profile_id = await self._get_default_quality_profile_id()
        if quality_profile_id is None:
            return "Error: No quality profiles configured in Sonarr."

        is_anime = self._is_anime(series_data)
        root_folder_path = await self._get_root_folder(is_anime=is_anime)
        if root_folder_path is None:
            return "Error: No root folders configured in Sonarr."

        # Build payload
        payload = {
            **series_data,
            "qualityProfileId": quality_profile_id,
            "rootFolderPath": root_folder_path,
            "seriesType": "anime" if is_anime else "standard",
            "monitored": True,
            "addOptions": {"searchForMissingEpisodes": True},
        }

        async with session.post(
            f"{self.base_url}/api/v3/series", json=payload
        ) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                series_title = result.get("title", title or "Series")
                year = result.get("year", "")
                season_count = result.get("seasonCount", 0)
                seasons = f"{season_count} season{'s' if season_count != 1 else ''}"
                library = "Anime Series" if is_anime else "TV Shows"
                return (
                    f"Added '{series_title}' ({year}) to Sonarr ({seasons}). "
                    f"Library: {library}. Searching for missing episodes now."
                )
            elif resp.status == 400:
                error = await resp.text()
                if "already" in error.lower():
                    return f"'{title or 'This series'}' is already in your library."
                return f"Error adding series: {error}"
            else:
                return f"Error: HTTP {resp.status}"

    async def _check_library(self, title: str) -> str:
        """Check if a series exists in the Sonarr library."""
        if not title:
            return "Error: title is required for check_library"

        session = await self._get_session()

        async with session.get(f"{self.base_url}/api/v3/series") as resp:
            if resp.status == 401:
                return "Error: Invalid Sonarr API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            series_list = await resp.json()

        # Case-insensitive partial match
        title_lower = title.lower()
        matches = [
            s for s in series_list if title_lower in s.get("title", "").lower()
        ]

        if not matches:
            return f"'{title}' not found in library."

        return self._format_library_results(matches[:5])

    async def _delete_series(
        self,
        series_id: int | None,
        delete_files: bool,
    ) -> str:
        """Delete a series from Sonarr."""
        if not series_id:
            return "Error: series_id is required for delete_series (get it from check_library)"

        session = await self._get_session()
        url = f"{self.base_url}/api/v3/series/{series_id}"
        params = {"deleteFiles": str(delete_files).lower()}

        async with session.delete(url, params=params) as resp:
            if resp.status in (200, 204):
                files_note = " and deleted files from disk" if delete_files else ""
                return f"Removed series (ID {series_id}) from Sonarr{files_note}."
            elif resp.status == 404:
                return f"Error: Series ID {series_id} not found in Sonarr."
            else:
                return f"Error: HTTP {resp.status}"

    async def _get_queue(self) -> str:
        """Get active downloads from the Sonarr queue."""
        session = await self._get_session()

        async with session.get(f"{self.base_url}/api/v3/queue") as resp:
            if resp.status == 401:
                return "Error: Invalid Sonarr API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            data = await resp.json()

        records = data.get("records", [])
        if not records:
            return "Download queue is empty."

        return self._format_queue(records)

    # ------------------------------------------------------------------
    # Auto-detection helpers (cached)
    # ------------------------------------------------------------------

    async def _get_default_quality_profile_id(self) -> int | None:
        """Return the first quality profile ID, caching after first call."""
        if self._quality_profiles is None:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/api/v3/qualityprofile"
            ) as resp:
                if resp.status != 200:
                    return None
                self._quality_profiles = await resp.json()

        if self._quality_profiles:
            return self._quality_profiles[0].get("id")
        return None

    async def _get_root_folder(self, is_anime: bool = False) -> str | None:
        """Return the appropriate root folder path based on content type.

        Anime series are routed to the folder containing 'anime' in its path
        (e.g. /anime-series), while regular TV goes to the standard folder
        (e.g. /tv).  Falls back to the first available folder.
        """
        if self._root_folders is None:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/api/v3/rootfolder"
            ) as resp:
                if resp.status != 200:
                    return None
                self._root_folders = await resp.json()

        if not self._root_folders:
            return None

        if is_anime:
            for folder in self._root_folders:
                if "anime" in folder.get("path", "").lower():
                    return folder["path"]

        # Default: prefer non-anime folder, fall back to first
        for folder in self._root_folders:
            if "anime" not in folder.get("path", "").lower():
                return folder["path"]
        return self._root_folders[0].get("path")

    @staticmethod
    def _is_anime(series_data: dict) -> bool:
        """Detect anime from TVDB genre tags."""
        genres = [g.lower() for g in series_data.get("genres", [])]
        return "anime" in genres

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _format_search_results(self, results: list[dict], query: str) -> str:
        """Format TVDB search results for LLM consumption."""
        lines = [f"Found {len(results)} result(s) for '{query}':\n"]
        for i, series in enumerate(results, 1):
            title = series.get("title", "Unknown")
            year = series.get("year", "")
            tvdb_id = series.get("tvdbId", "?")
            season_count = series.get("seasonCount", 0)
            status = series.get("status", "unknown")
            overview = series.get("overview", "")
            # Truncate overview to keep response concise
            if len(overview) > 100:
                overview = overview[:100] + "..."

            lines.append(
                f"{i}. {title} ({year}) [TVDB: {tvdb_id}] - "
                f"{season_count} season{'s' if season_count != 1 else ''}, {status}"
            )
            if overview:
                lines.append(f"   {overview}")
        return "\n".join(lines)

    def _format_library_results(self, series_list: list[dict]) -> str:
        """Format library matches for LLM consumption."""
        lines = []
        for series in series_list:
            title = series.get("title", "Unknown")
            year = series.get("year", "")
            series_id = series.get("id", "?")
            monitored = "Monitored" if series.get("monitored") else "Unmonitored"
            status = series.get("status", "unknown")

            stats = series.get("statistics") or {}
            episode_file_count = stats.get("episodeFileCount", 0)
            episode_count = stats.get("episodeCount", 0)
            size_bytes = stats.get("sizeOnDisk") or 0
            size_gb = size_bytes / (1024 ** 3)

            lines.append(f"{title} ({year}) [ID: {series_id}]")
            lines.append(
                f"  Episodes: {episode_file_count}/{episode_count} downloaded"
                f" ({size_gb:.1f} GB)"
            )
            lines.append(f"  Status: {status} | {monitored}")
            lines.append("")

        return "\n".join(lines).rstrip()

    def _format_queue(self, records: list[dict]) -> str:
        """Format download queue for LLM consumption."""
        lines = [f"Active downloads ({len(records)}):\n"]
        for item in records:
            title = item.get("title", "Unknown")
            status = item.get("status", "unknown")
            size = item.get("size") or 0
            size_left = item.get("sizeleft") or 0
            time_left = item.get("timeleft", "unknown")

            if size > 0:
                progress_pct = ((size - size_left) / size) * 100
            else:
                progress_pct = 0.0

            lines.append(f"- {title}")
            lines.append(
                f"  {status} - {progress_pct:.1f}% complete (ETA: {time_left})"
            )
        return "\n".join(lines)
