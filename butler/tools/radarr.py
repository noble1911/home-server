"""Radarr integration tool for Butler.

This tool allows the agent to manage movies via Radarr's REST API,
enabling voice and text-based movie library management.

Usage:
    The tool is automatically registered when RADARR_URL is configured.
    Requires RADARR_URL and RADARR_API_KEY in the application settings.

Example:
    tool = RadarrTool(base_url="http://radarr:7878", api_key="abc123")
    result = await tool.execute(action="search_movie", title="Inception")

    # When shutting down
    await tool.close()

API Reference:
    https://radarr.video/docs/api/
"""

from __future__ import annotations

from typing import Any

import aiohttp

from .base import Tool

# Default timeout for HTTP requests (seconds)
DEFAULT_TIMEOUT = 30


class RadarrTool(Tool):
    """Manage movies in Radarr via REST API.

    Supports searching TMDB for movies, adding them to the library,
    checking library status, deleting movies, and viewing the download queue.

    The tool reuses HTTP sessions for better performance and
    caches quality profiles / root folders to minimise API calls.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Initialize the Radarr tool.

        Args:
            base_url: Radarr URL (e.g. http://radarr:7878)
            api_key: Radarr API key (Settings > General > Security)
            timeout: HTTP request timeout in seconds (default: 30)
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
        return "radarr"

    @property
    def description(self) -> str:
        return (
            "Manage movies in Radarr. Search for movies on TMDB, add them to "
            "your library, check if a movie exists and its download status, "
            "view active downloads, or delete movies from your collection."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "search_movie",
                        "add_movie",
                        "check_library",
                        "delete_movie",
                        "get_queue",
                    ],
                    "description": (
                        "search_movie: Find movies on TMDB. "
                        "add_movie: Add a movie (needs tmdb_id from search). "
                        "check_library: Check if a movie exists and its status. "
                        "delete_movie: Remove a movie (needs movie_id from check). "
                        "get_queue: Show active downloads with progress."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": (
                        "Movie title to search for. "
                        "Used by search_movie, add_movie, and check_library."
                    ),
                },
                "tmdb_id": {
                    "type": "integer",
                    "description": (
                        "TMDB ID from search results. Required for add_movie."
                    ),
                },
                "movie_id": {
                    "type": "integer",
                    "description": (
                        "Radarr movie ID from check_library results. "
                        "Required for delete_movie."
                    ),
                },
                "delete_files": {
                    "type": "boolean",
                    "description": (
                        "Also delete movie files from disk (default: false). "
                        "Only used with delete_movie."
                    ),
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]

        if not self.base_url or not self.api_key:
            return "Error: RADARR_URL and RADARR_API_KEY must be configured."

        try:
            if action == "search_movie":
                return await self._search_movie(kwargs.get("title", ""))
            elif action == "add_movie":
                return await self._add_movie(
                    tmdb_id=kwargs.get("tmdb_id"),
                    title=kwargs.get("title", ""),
                )
            elif action == "check_library":
                return await self._check_library(kwargs.get("title", ""))
            elif action == "delete_movie":
                return await self._delete_movie(
                    movie_id=kwargs.get("movie_id"),
                    delete_files=kwargs.get("delete_files", False),
                )
            elif action == "get_queue":
                return await self._get_queue()
            else:
                return f"Error: Unknown action '{action}'"
        except aiohttp.ClientError as e:
            return f"Error connecting to Radarr: {e}"
        except TimeoutError:
            return "Error: Radarr request timed out"
        except Exception as e:
            return f"Error: {e}"

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def _search_movie(self, title: str) -> str:
        """Search TMDB for movies via Radarr's lookup endpoint."""
        if not title:
            return "Error: title is required for search_movie"

        session = await self._get_session()
        url = f"{self.base_url}/api/v3/movie/lookup"

        async with session.get(url, params={"term": title}) as resp:
            if resp.status == 401:
                return "Error: Invalid Radarr API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            results = await resp.json()
            if not results or not isinstance(results, list):
                return f"No movies found for '{title}'"

            return self._format_search_results(results[:5], title)

    async def _add_movie(
        self,
        tmdb_id: int | None,
        title: str,
    ) -> str:
        """Add a movie to Radarr using its TMDB ID."""
        if not tmdb_id:
            return "Error: tmdb_id is required for add_movie (get it from search_movie)"

        session = await self._get_session()

        # Fetch full movie data from TMDB via Radarr
        lookup_url = f"{self.base_url}/api/v3/movie/lookup/tmdb"
        async with session.get(lookup_url, params={"tmdbId": tmdb_id}) as resp:
            if resp.status != 200:
                return f"Error fetching movie details: HTTP {resp.status}"
            movie_data = await resp.json()

        if not movie_data or not isinstance(movie_data, dict):
            return f"Error: Could not find movie data for TMDB ID {tmdb_id}."

        # Auto-detect quality profile, content type, and root folder
        quality_profile_id = await self._get_default_quality_profile_id()
        if quality_profile_id is None:
            return "Error: No quality profiles configured in Radarr."

        is_anime = self._is_anime(movie_data)
        root_folder_path = await self._get_root_folder(is_anime=is_anime)
        if root_folder_path is None:
            return "Error: No root folders configured in Radarr."

        # Build payload
        payload = {
            **movie_data,
            "qualityProfileId": quality_profile_id,
            "rootFolderPath": root_folder_path,
            "monitored": True,
            "addOptions": {"searchForMovie": True},
        }

        async with session.post(
            f"{self.base_url}/api/v3/movie", json=payload
        ) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                movie_title = result.get("title", title or "Movie")
                year = result.get("year", "")
                library = "Anime Movies" if is_anime else "Movies"
                return (
                    f"Added '{movie_title}' ({year}) to Radarr. "
                    f"Library: {library}. Searching for releases now."
                )
            elif resp.status == 400:
                error = await resp.text()
                if "already" in error.lower():
                    return f"'{title or 'This movie'}' is already in your library."
                return f"Error adding movie: {error}"
            else:
                return f"Error: HTTP {resp.status}"

    async def _check_library(self, title: str) -> str:
        """Check if a movie exists in the Radarr library."""
        if not title:
            return "Error: title is required for check_library"

        session = await self._get_session()

        async with session.get(f"{self.base_url}/api/v3/movie") as resp:
            if resp.status == 401:
                return "Error: Invalid Radarr API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            movies = await resp.json()

        # Case-insensitive partial match
        title_lower = title.lower()
        matches = [
            m for m in movies if title_lower in m.get("title", "").lower()
        ]

        if not matches:
            return f"'{title}' not found in library."

        return self._format_library_results(matches[:5])

    async def _delete_movie(
        self,
        movie_id: int | None,
        delete_files: bool,
    ) -> str:
        """Delete a movie from Radarr."""
        if not movie_id:
            return "Error: movie_id is required for delete_movie (get it from check_library)"

        session = await self._get_session()
        url = f"{self.base_url}/api/v3/movie/{movie_id}"
        params = {"deleteFiles": str(delete_files).lower()}

        async with session.delete(url, params=params) as resp:
            if resp.status in (200, 204):
                files_note = " and deleted files from disk" if delete_files else ""
                return f"Removed movie (ID {movie_id}) from Radarr{files_note}."
            elif resp.status == 404:
                return f"Error: Movie ID {movie_id} not found in Radarr."
            else:
                return f"Error: HTTP {resp.status}"

    async def _get_queue(self) -> str:
        """Get active downloads from the Radarr queue."""
        session = await self._get_session()

        async with session.get(f"{self.base_url}/api/v3/queue") as resp:
            if resp.status == 401:
                return "Error: Invalid Radarr API key."
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

        Anime movies are routed to the folder containing 'anime' in its path
        (e.g. /anime-movies), while regular movies go to the standard folder
        (e.g. /movies).  Falls back to the first available folder.
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
    def _is_anime(movie_data: dict) -> bool:
        """Detect anime from TMDB genres and original language.

        TMDB tags anime as 'Animation' genre with Japanese original language,
        which distinguishes it from Western animation (Pixar, Disney, etc.).
        """
        genres = [g.lower() for g in movie_data.get("genres", [])]
        original_language = (
            movie_data.get("originalLanguage", {}).get("name", "").lower()
        )
        return "animation" in genres and original_language == "japanese"

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _format_search_results(self, results: list[dict], query: str) -> str:
        """Format TMDB search results for LLM consumption."""
        lines = [f"Found {len(results)} result(s) for '{query}':\n"]
        for i, movie in enumerate(results, 1):
            title = movie.get("title", "Unknown")
            year = movie.get("year", "")
            tmdb_id = movie.get("tmdbId", "?")
            overview = movie.get("overview", "")
            # Truncate overview to keep response concise
            if len(overview) > 100:
                overview = overview[:100] + "..."

            lines.append(f"{i}. {title} ({year}) [TMDB: {tmdb_id}]")
            if overview:
                lines.append(f"   {overview}")
        return "\n".join(lines)

    def _format_library_results(self, movies: list[dict]) -> str:
        """Format library matches for LLM consumption."""
        lines = []
        for movie in movies:
            title = movie.get("title", "Unknown")
            year = movie.get("year", "")
            movie_id = movie.get("id", "?")
            monitored = "Monitored" if movie.get("monitored") else "Unmonitored"
            has_file = movie.get("hasFile", False)

            if has_file:
                movie_file = movie.get("movieFile") or {}
                quality_name = (
                    movie_file.get("quality", {})
                    .get("quality", {})
                    .get("name", "Unknown")
                )
                size_bytes = movie_file.get("size") or 0
                size_gb = size_bytes / (1024 ** 3)
                lines.append(f"{title} ({year}) [ID: {movie_id}]")
                lines.append(
                    f"  Status: Downloaded - {quality_name} ({size_gb:.1f} GB)"
                )
            else:
                lines.append(f"{title} ({year}) [ID: {movie_id}]")
                lines.append("  Status: Missing")

            lines.append(f"  {monitored}")
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
