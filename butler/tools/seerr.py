"""Seerr integration tool for Butler.

This tool allows the agent to search for and request movies/TV shows via
Seerr's REST API, enabling voice and text-based media request management.

Usage:
    The tool is automatically registered when SEERR_URL is configured.
    Requires SEERR_URL and SEERR_API_KEY in the application settings.

Example:
    tool = SeerrTool(base_url="http://seerr:5055", api_key="abc123")
    result = await tool.execute(action="search", query="Inception")

    # When shutting down
    await tool.close()

API Reference:
    Seerr API docs available at http://<host>:5055/api-docs
"""

from __future__ import annotations

from typing import Any

import aiohttp

from .base import Tool

DEFAULT_TIMEOUT = 30


class SeerrTool(Tool):
    """Search for and request movies/TV shows via Seerr.

    Supports searching for media, creating requests, listing pending
    requests, and checking request status. Seerr routes movie requests
    to Radarr and TV requests to Sonarr automatically.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"X-Api-Key": self.api_key},
                timeout=self.timeout,
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # -- Tool interface -------------------------------------------------------

    @property
    def name(self) -> str:
        return "seerr"

    @property
    def description(self) -> str:
        return (
            "Search for movies and TV shows, request them for download, "
            "and check the status of pending requests via Seerr. "
            "Requests are automatically routed to Radarr (movies) or Sonarr (TV)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "search",
                        "request_movie",
                        "request_tv",
                        "get_requests",
                        "get_movie",
                        "get_tv",
                    ],
                    "description": (
                        "search: Find movies/TV on TMDB via Seerr. "
                        "request_movie: Request a movie (needs tmdb_id from search). "
                        "request_tv: Request a TV show (needs tmdb_id from search). "
                        "get_requests: List pending/approved/available requests. "
                        "get_movie: Get details and availability for a movie. "
                        "get_tv: Get details and availability for a TV show."
                    ),
                },
                "query": {
                    "type": "string",
                    "description": "Search query for finding movies or TV shows.",
                },
                "tmdb_id": {
                    "type": "integer",
                    "description": (
                        "TMDB ID from search results. "
                        "Required for request_movie, request_tv, get_movie, get_tv."
                    ),
                },
                "seasons": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": (
                        "Season numbers to request for TV shows. "
                        "If omitted, requests all available seasons."
                    ),
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]

        if not self.base_url or not self.api_key:
            return "Error: SEERR_URL and SEERR_API_KEY must be configured."

        try:
            if action == "search":
                return await self._search(kwargs.get("query", ""))
            elif action == "request_movie":
                return await self._request_movie(kwargs.get("tmdb_id"))
            elif action == "request_tv":
                return await self._request_tv(
                    kwargs.get("tmdb_id"), kwargs.get("seasons"),
                )
            elif action == "get_requests":
                return await self._get_requests()
            elif action == "get_movie":
                return await self._get_movie(kwargs.get("tmdb_id"))
            elif action == "get_tv":
                return await self._get_tv(kwargs.get("tmdb_id"))
            else:
                return f"Error: Unknown action '{action}'"
        except aiohttp.ClientError as e:
            return f"Error connecting to Seerr: {e}"
        except TimeoutError:
            return "Error: Seerr request timed out"
        except Exception as e:
            return f"Error: {e}"

    # -- Actions --------------------------------------------------------------

    async def _search(self, query: str) -> str:
        if not query:
            return "Error: query is required for search"

        session = await self._get_session()
        url = f"{self.base_url}/api/v1/search"

        async with session.get(url, params={"query": query, "page": 1}) as resp:
            if resp.status == 401:
                return "Error: Invalid Seerr API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            data = await resp.json()

        results = data.get("results", [])
        if not results:
            return f"No results found for '{query}'"

        return self._format_search_results(results[:8], query)

    async def _request_movie(self, tmdb_id: int | None) -> str:
        if not tmdb_id:
            return "Error: tmdb_id is required (get it from search)"

        session = await self._get_session()
        url = f"{self.base_url}/api/v1/request"
        payload = {"mediaType": "movie", "mediaId": tmdb_id}

        async with session.post(url, json=payload) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                status = result.get("status", "unknown")
                media = result.get("media", {})
                title = media.get("title", f"TMDB:{tmdb_id}")
                status_text = {
                    1: "pending approval",
                    2: "approved",
                    3: "declined",
                }.get(status, f"status {status}")
                return f"Requested movie '{title}' — {status_text}. Seerr will route to Radarr."
            elif resp.status == 409:
                return "This movie has already been requested."
            else:
                body = await resp.text()
                return f"Error requesting movie: HTTP {resp.status} — {body[:200]}"

    async def _request_tv(
        self, tmdb_id: int | None, seasons: list[int] | None,
    ) -> str:
        if not tmdb_id:
            return "Error: tmdb_id is required (get it from search)"

        session = await self._get_session()
        url = f"{self.base_url}/api/v1/request"
        payload: dict[str, Any] = {"mediaType": "tv", "mediaId": tmdb_id}
        if seasons:
            payload["seasons"] = seasons

        async with session.post(url, json=payload) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                status = result.get("status", "unknown")
                status_text = {
                    1: "pending approval",
                    2: "approved",
                    3: "declined",
                }.get(status, f"status {status}")
                season_note = f" (seasons {seasons})" if seasons else " (all seasons)"
                return f"Requested TV show (TMDB:{tmdb_id}){season_note} — {status_text}. Seerr will route to Sonarr."
            elif resp.status == 409:
                return "This TV show has already been requested."
            else:
                body = await resp.text()
                return f"Error requesting TV show: HTTP {resp.status} — {body[:200]}"

    async def _get_requests(self) -> str:
        session = await self._get_session()
        url = f"{self.base_url}/api/v1/request"

        async with session.get(url, params={"take": 20, "skip": 0, "sort": "added"}) as resp:
            if resp.status == 401:
                return "Error: Invalid Seerr API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            data = await resp.json()

        results = data.get("results", [])
        if not results:
            return "No media requests found."

        return self._format_requests(results)

    async def _get_movie(self, tmdb_id: int | None) -> str:
        if not tmdb_id:
            return "Error: tmdb_id is required"

        session = await self._get_session()
        url = f"{self.base_url}/api/v1/movies/{tmdb_id}"

        async with session.get(url) as resp:
            if resp.status == 404:
                return f"Movie with TMDB ID {tmdb_id} not found."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            movie = await resp.json()

        return self._format_movie_detail(movie)

    async def _get_tv(self, tmdb_id: int | None) -> str:
        if not tmdb_id:
            return "Error: tmdb_id is required"

        session = await self._get_session()
        url = f"{self.base_url}/api/v1/tv/{tmdb_id}"

        async with session.get(url) as resp:
            if resp.status == 404:
                return f"TV show with TMDB ID {tmdb_id} not found."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            show = await resp.json()

        return self._format_tv_detail(show)

    # -- Formatting -----------------------------------------------------------

    def _format_search_results(self, results: list[dict], query: str) -> str:
        lines = [f"Found {len(results)} result(s) for '{query}':\n"]
        for i, item in enumerate(results, 1):
            media_type = item.get("mediaType", "unknown")
            tmdb_id = item.get("id", "?")
            overview = item.get("overview", "")
            if len(overview) > 120:
                overview = overview[:120] + "..."

            if media_type == "movie":
                title = item.get("title", "Unknown")
                year = item.get("releaseDate", "")[:4]
                lines.append(f"{i}. [Movie] {title} ({year}) [TMDB: {tmdb_id}]")
            elif media_type == "tv":
                title = item.get("name", "Unknown")
                year = item.get("firstAirDate", "")[:4]
                lines.append(f"{i}. [TV] {title} ({year}) [TMDB: {tmdb_id}]")
            else:
                name = item.get("name") or item.get("title", "Unknown")
                lines.append(f"{i}. [{media_type}] {name} [ID: {tmdb_id}]")

            # Show availability status if present
            media_info = item.get("mediaInfo")
            if media_info:
                status = media_info.get("status")
                status_text = {
                    1: "unknown",
                    2: "pending",
                    3: "processing",
                    4: "partially available",
                    5: "available",
                }.get(status, "")
                if status_text:
                    lines.append(f"   Status: {status_text}")

            if overview:
                lines.append(f"   {overview}")
        return "\n".join(lines)

    def _format_requests(self, requests: list[dict]) -> str:
        status_map = {1: "Pending", 2: "Approved", 3: "Declined"}
        lines = [f"Media Requests ({len(requests)}):\n"]
        for req in requests:
            req_id = req.get("id", "?")
            media_type = req.get("type", req.get("media", {}).get("mediaType", "?"))
            status = status_map.get(req.get("status", 0), "Unknown")
            media = req.get("media", {})
            tmdb_id = media.get("tmdbId", "?")

            # Requester info
            requester = req.get("requestedBy", {})
            user_name = requester.get("displayName", requester.get("username", "?"))

            lines.append(f"- #{req_id}: [{media_type}] TMDB:{tmdb_id} — {status} (by {user_name})")

        return "\n".join(lines)

    def _format_movie_detail(self, movie: dict) -> str:
        title = movie.get("title", "Unknown")
        year = movie.get("releaseDate", "")[:4]
        overview = movie.get("overview", "")
        if len(overview) > 200:
            overview = overview[:200] + "..."
        runtime = movie.get("runtime", 0)

        media_info = movie.get("mediaInfo")
        if media_info:
            status = media_info.get("status", 1)
            status_text = {
                1: "Unknown", 2: "Pending", 3: "Processing",
                4: "Partially Available", 5: "Available",
            }.get(status, "Unknown")
        else:
            status_text = "Not Requested"

        lines = [
            f"{title} ({year})",
            f"  Runtime: {runtime} min" if runtime else "",
            f"  Status: {status_text}",
            f"  {overview}" if overview else "",
        ]
        return "\n".join(line for line in lines if line)

    def _format_tv_detail(self, show: dict) -> str:
        title = show.get("name", "Unknown")
        year = show.get("firstAirDate", "")[:4]
        overview = show.get("overview", "")
        if len(overview) > 200:
            overview = overview[:200] + "..."
        seasons_count = show.get("numberOfSeasons", 0)

        media_info = show.get("mediaInfo")
        if media_info:
            status = media_info.get("status", 1)
            status_text = {
                1: "Unknown", 2: "Pending", 3: "Processing",
                4: "Partially Available", 5: "Available",
            }.get(status, "Unknown")
        else:
            status_text = "Not Requested"

        lines = [
            f"{title} ({year})",
            f"  Seasons: {seasons_count}" if seasons_count else "",
            f"  Status: {status_text}",
            f"  {overview}" if overview else "",
        ]
        return "\n".join(line for line in lines if line)
