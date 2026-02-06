"""Immich photo search tool for Butler (read-only).

This tool allows the agent to search photos in Immich using CLIP-based
semantic search, date ranges, location, and facial recognition.

Usage:
    The tool is automatically registered when IMMICH_URL is configured.
    Requires IMMICH_URL and IMMICH_API_KEY in the application settings.

Example:
    tool = ImmichTool(base_url="http://immich-server:2283", api_key="abc123")
    result = await tool.execute(action="search_photos", query="sunset at beach")

    # When shutting down
    await tool.close()

API Reference:
    https://immich.app/docs/api/
"""

from __future__ import annotations

from typing import Any

import aiohttp

from .base import Tool

# Default timeout for HTTP requests (seconds)
DEFAULT_TIMEOUT = 15

# Maximum results per search
DEFAULT_PAGE_SIZE = 10


class ImmichTool(Tool):
    """Search photos in Immich via REST API (read-only).

    Supports CLIP-based semantic search (natural language descriptions),
    metadata search by date range and location, and person/face lookup.
    No upload, delete, or modify operations are exposed.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Initialize the Immich tool.

        Args:
            base_url: Immich URL (e.g. http://immich-server:2283)
            api_key: Immich API key (Profile > Account Settings > API Keys)
            timeout: HTTP request timeout in seconds (default: 15)
        """
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"x-api-key": self.api_key},
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
        return "immich"

    @property
    def description(self) -> str:
        return (
            "Search photos in Immich. Find photos by natural language description "
            "(CLIP search), date range, location, or person. Use find_person first "
            "to get a person's ID, then pass it to search_photos. Read-only — "
            "no upload or delete operations."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "search_photos",
                        "find_person",
                    ],
                    "description": (
                        "search_photos: Search for photos using text description "
                        "(CLIP/AI), date range, location, or person ID. At least "
                        "one filter must be provided. "
                        "find_person: Look up a person by name to get their ID "
                        "for use in search_photos."
                    ),
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Natural language description of what to find "
                        '(e.g. "birthday cake", "sunset at beach", "dog playing"). '
                        "Used by search_photos for CLIP-based AI search."
                    ),
                },
                "taken_after": {
                    "type": "string",
                    "description": (
                        "ISO date for start of date range "
                        '(e.g. "2024-12-25"). Photos taken on or after this date.'
                    ),
                },
                "taken_before": {
                    "type": "string",
                    "description": (
                        "ISO date for end of date range "
                        '(e.g. "2024-12-31"). Photos taken on or before this date.'
                    ),
                },
                "person_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Person IDs to filter by (from find_person results). "
                        "Used by search_photos to find photos of specific people."
                    ),
                },
                "city": {
                    "type": "string",
                    "description": "Filter photos by city name.",
                },
                "country": {
                    "type": "string",
                    "description": "Filter photos by country name.",
                },
                "person_name": {
                    "type": "string",
                    "description": (
                        "Name of the person to look up. Used by find_person."
                    ),
                },
                "page": {
                    "type": "integer",
                    "description": (
                        "Page number for pagination (default: 1). "
                        "Use when there are more results to browse."
                    ),
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]

        if not self.base_url or not self.api_key:
            return "Error: IMMICH_URL and IMMICH_API_KEY must be configured."

        try:
            if action == "search_photos":
                return await self._search_photos(
                    query=kwargs.get("query"),
                    taken_after=kwargs.get("taken_after"),
                    taken_before=kwargs.get("taken_before"),
                    person_ids=kwargs.get("person_ids"),
                    city=kwargs.get("city"),
                    country=kwargs.get("country"),
                    page=kwargs.get("page", 1),
                )
            elif action == "find_person":
                return await self._find_person(kwargs.get("person_name", ""))
            else:
                return f"Error: Unknown action '{action}'"
        except aiohttp.ClientError as e:
            return f"Error connecting to Immich: {e}"
        except TimeoutError:
            return "Error: Immich request timed out"
        except Exception as e:
            return f"Error: {e}"

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def _search_photos(
        self,
        query: str | None = None,
        taken_after: str | None = None,
        taken_before: str | None = None,
        person_ids: list[str] | None = None,
        city: str | None = None,
        country: str | None = None,
        page: int = 1,
    ) -> str:
        """Search photos using CLIP (smart) or metadata search."""
        # Build the request body with only provided filters
        body: dict[str, Any] = {
            "size": DEFAULT_PAGE_SIZE,
            "page": page,
            "withExif": True,
        }

        if taken_after:
            body["takenAfter"] = _normalize_date(taken_after, start=True)
        if taken_before:
            body["takenBefore"] = _normalize_date(taken_before, start=False)
        if person_ids:
            body["personIds"] = person_ids
        if city:
            body["city"] = city
        if country:
            body["country"] = country

        # Use smart search (CLIP) when a text query is provided,
        # metadata search otherwise (for date/location/person-only queries).
        if query:
            body["query"] = query
            endpoint = "/api/search/smart"
        else:
            # Metadata search needs at least one filter
            has_filter = any(
                k in body
                for k in ("takenAfter", "takenBefore", "personIds", "city", "country")
            )
            if not has_filter:
                return (
                    "Error: search_photos requires at least one filter — "
                    "query, taken_after, taken_before, person_ids, city, or country."
                )
            body["withPeople"] = True
            endpoint = "/api/search/metadata"

        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"

        async with session.post(url, json=body) as resp:
            if resp.status == 401:
                return "Error: Invalid Immich API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            data = await resp.json()

        assets = data.get("assets", {})
        items = assets.get("items", [])

        if not items:
            return self._format_no_results(query, taken_after, taken_before)

        total = assets.get("total", len(items))
        next_page = assets.get("nextPage")

        return self._format_photo_results(items, total, page, next_page)

    async def _find_person(self, name: str) -> str:
        """Search for a person by name in Immich's face recognition database."""
        if not name:
            return "Error: person_name is required for find_person"

        session = await self._get_session()
        url = f"{self.base_url}/api/search/person"

        async with session.get(url, params={"name": name}) as resp:
            if resp.status == 401:
                return "Error: Invalid Immich API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            results = await resp.json()

        if not results:
            return f"No person found matching '{name}'."

        return self._format_person_results(results, name)

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _format_photo_results(
        self,
        items: list[dict],
        total: int,
        page: int,
        next_page: str | None,
    ) -> str:
        """Format photo search results for LLM consumption."""
        lines = [f"Found {total} photo(s) (showing page {page}):\n"]

        for i, asset in enumerate(items, 1):
            asset_id = asset.get("id", "?")
            filename = asset.get("originalFileName", "unknown")
            asset_type = asset.get("type", "IMAGE")
            taken_at = asset.get("localDateTime") or asset.get("fileCreatedAt", "")
            is_favorite = asset.get("isFavorite", False)

            # Date display (just the date part)
            date_display = taken_at[:10] if taken_at else "Unknown date"

            lines.append(f"{i}. {filename} ({date_display})")

            # Location from EXIF
            exif = asset.get("exifInfo") or {}
            location_parts = []
            if exif.get("city"):
                location_parts.append(exif["city"])
            if exif.get("state"):
                location_parts.append(exif["state"])
            if exif.get("country"):
                location_parts.append(exif["country"])
            if location_parts:
                lines.append(f"   Location: {', '.join(location_parts)}")

            # Camera info
            if exif.get("make") or exif.get("model"):
                camera = f"{exif.get('make', '')} {exif.get('model', '')}".strip()
                lines.append(f"   Camera: {camera}")

            # People in photo
            people = asset.get("people") or []
            if people:
                names = [p.get("name", "Unknown") for p in people if p.get("name")]
                if names:
                    lines.append(f"   People: {', '.join(names)}")

            # Type and favorite
            extras = []
            if asset_type != "IMAGE":
                extras.append(asset_type.lower())
            if is_favorite:
                extras.append("favorite")
            if extras:
                lines.append(f"   [{', '.join(extras)}]")

            # Browseable URL
            thumbnail_url = f"{self.base_url}/api/assets/{asset_id}/thumbnail?size=preview"
            lines.append(f"   Preview: {thumbnail_url}")
            lines.append("")

        if next_page:
            lines.append(f"More results available — use page={page + 1} to see next page.")

        return "\n".join(lines).rstrip()

    def _format_person_results(self, results: list[dict], query: str) -> str:
        """Format person search results for LLM consumption."""
        lines = [f"Found {len(results)} person(s) matching '{query}':\n"]

        for person in results:
            person_id = person.get("id", "?")
            name = person.get("name", "Unknown")
            birth_date = person.get("birthDate")

            line = f"- {name} [ID: {person_id}]"
            if birth_date:
                line += f" (born: {birth_date})"
            lines.append(line)

            # Thumbnail URL for person face
            lines.append(
                f"  Face thumbnail: {self.base_url}/api/people/{person_id}/thumbnail"
            )

        lines.append(
            "\nUse the person ID in search_photos with person_ids to find their photos."
        )
        return "\n".join(lines)

    def _format_no_results(
        self,
        query: str | None,
        taken_after: str | None,
        taken_before: str | None,
    ) -> str:
        """Format a helpful no-results message."""
        parts = []
        if query:
            parts.append(f"query '{query}'")
        if taken_after and taken_before:
            parts.append(f"date range {taken_after} to {taken_before}")
        elif taken_after:
            parts.append(f"after {taken_after}")
        elif taken_before:
            parts.append(f"before {taken_before}")

        filter_desc = " with ".join(parts) if parts else "the given filters"
        return f"No photos found for {filter_desc}."


def _normalize_date(date_str: str, *, start: bool) -> str:
    """Ensure a date string is in ISO 8601 format with time component.

    If only a date is given (YYYY-MM-DD), append start-of-day or
    end-of-day time so the Immich API range is inclusive.
    """
    if "T" in date_str:
        return date_str
    if start:
        return f"{date_str}T00:00:00.000Z"
    return f"{date_str}T23:59:59.999Z"
