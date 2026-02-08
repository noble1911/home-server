"""Jellyfin integration tool for Butler.

This tool allows the agent to search the media library, see what's playing,
get "continue watching" lists, and control playback on connected devices
via Jellyfin's REST API.

Usage:
    tool = JellyfinTool(base_url="http://jellyfin:8096", api_key="abc123")
    result = await tool.execute(action="search_library", query="Inception")

    # When shutting down
    await tool.close()

API Reference:
    https://jellyfin.org/docs/
"""

from __future__ import annotations

from typing import Any

import aiohttp

from .base import Tool

# Default timeout for HTTP requests (seconds)
DEFAULT_TIMEOUT = 10


class JellyfinTool(Tool):
    """Search and control media playback via Jellyfin REST API.

    Supports searching the library, viewing continue-watching and recently
    added items, listing active playback sessions, starting playback on a
    device, and sending playstate commands (pause, unpause, stop, seek).

    The tool reuses HTTP sessions for better performance and caches the
    admin user ID to minimise API calls.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Initialize the Jellyfin tool.

        Args:
            base_url: Jellyfin URL (e.g. http://jellyfin:8096)
            api_key: Jellyfin API key (Dashboard > API Keys)
            timeout: HTTP request timeout in seconds (default: 10)
        """
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None
        # Cached admin user ID (fetched once on first use)
        self._user_id: str | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f'MediaBrowser Token="{self.api_key}"',
                },
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
        return "jellyfin"

    @property
    def description(self) -> str:
        return (
            "Search and control media on Jellyfin. Search the library for "
            "movies, TV shows, or music. See what's currently playing, get "
            "the continue-watching list or recently added items. Start "
            "playback on a device or pause/stop/seek."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "search_library",
                        "get_resume",
                        "get_latest",
                        "get_sessions",
                        "play_media",
                        "playstate_command",
                    ],
                    "description": (
                        "search_library: Find movies/shows/music by title. "
                        "get_resume: Continue-watching list. "
                        "get_latest: Recently added media. "
                        "get_sessions: Active playback sessions on all devices. "
                        "play_media: Start an item on a session (needs session_id and item_id). "
                        "playstate_command: Pause/Unpause/Stop/Seek on a session (needs session_id and command)."
                    ),
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Search term. Used by search_library."
                    ),
                },
                "media_type": {
                    "type": "string",
                    "enum": ["Movie", "Series", "Episode", "Audio", "MusicAlbum"],
                    "description": (
                        "Filter by media type. Optional for search_library, "
                        "get_resume, and get_latest."
                    ),
                },
                "session_id": {
                    "type": "string",
                    "description": (
                        "Jellyfin session ID from get_sessions results. "
                        "Required for play_media and playstate_command."
                    ),
                },
                "item_id": {
                    "type": "string",
                    "description": (
                        "Jellyfin item ID from search/resume/latest results. "
                        "Required for play_media."
                    ),
                },
                "command": {
                    "type": "string",
                    "enum": [
                        "PlayPause",
                        "Pause",
                        "Unpause",
                        "Stop",
                        "NextTrack",
                        "PreviousTrack",
                        "Seek",
                    ],
                    "description": (
                        "Playstate command. Required for playstate_command."
                    ),
                },
                "seek_position_ticks": {
                    "type": "integer",
                    "description": (
                        "Position in ticks (1 tick = 100 nanoseconds, "
                        "10,000,000 ticks = 1 second). Only used with Seek command."
                    ),
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]

        if not self.base_url or not self.api_key:
            return "Error: JELLYFIN_URL and JELLYFIN_API_KEY must be configured."

        try:
            if action == "search_library":
                return await self._search_library(
                    query=kwargs.get("query", ""),
                    media_type=kwargs.get("media_type"),
                )
            elif action == "get_resume":
                return await self._get_resume(
                    media_type=kwargs.get("media_type"),
                )
            elif action == "get_latest":
                return await self._get_latest(
                    media_type=kwargs.get("media_type"),
                )
            elif action == "get_sessions":
                return await self._get_sessions()
            elif action == "play_media":
                return await self._play_media(
                    session_id=kwargs.get("session_id", ""),
                    item_id=kwargs.get("item_id", ""),
                )
            elif action == "playstate_command":
                return await self._playstate_command(
                    session_id=kwargs.get("session_id", ""),
                    command=kwargs.get("command", ""),
                    seek_position_ticks=kwargs.get("seek_position_ticks"),
                )
            else:
                return f"Error: Unknown action '{action}'"
        except aiohttp.ClientError as e:
            return f"Error connecting to Jellyfin: {e}"
        except TimeoutError:
            return "Error: Jellyfin request timed out"
        except Exception as e:
            return f"Error: {e}"

    # ------------------------------------------------------------------
    # User ID resolution (cached)
    # ------------------------------------------------------------------

    async def _get_user_id(self) -> str | None:
        """Return the first admin user ID, caching after first call."""
        if self._user_id is not None:
            return self._user_id

        session = await self._get_session()
        async with session.get(f"{self.base_url}/Users") as resp:
            if resp.status != 200:
                return None
            users = await resp.json()

        if not users:
            return None

        # Prefer the first admin user, fall back to first user
        for user in users:
            policy = user.get("Policy") or {}
            if policy.get("IsAdministrator"):
                self._user_id = user["Id"]
                return self._user_id

        self._user_id = users[0]["Id"]
        return self._user_id

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def _search_library(
        self,
        query: str,
        media_type: str | None = None,
    ) -> str:
        """Search the Jellyfin library by title."""
        if not query:
            return "Error: query is required for search_library"

        user_id = await self._get_user_id()
        if not user_id:
            return "Error: Could not determine Jellyfin user."

        session = await self._get_session()
        params: dict[str, Any] = {
            "searchTerm": query,
            "Recursive": "true",
            "Limit": "10",
            "Fields": "Overview,Path",
        }
        if media_type:
            params["IncludeItemTypes"] = media_type

        url = f"{self.base_url}/Users/{user_id}/Items"
        async with session.get(url, params=params) as resp:
            if resp.status == 401:
                return "Error: Invalid Jellyfin API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            data = await resp.json()

        items = data.get("Items", [])
        if not items:
            return f"No results found for '{query}'"

        return self._format_items(items, f"Results for '{query}'")

    async def _get_resume(self, media_type: str | None = None) -> str:
        """Get the continue-watching list."""
        user_id = await self._get_user_id()
        if not user_id:
            return "Error: Could not determine Jellyfin user."

        session = await self._get_session()
        params: dict[str, Any] = {
            "Limit": "10",
            "Fields": "Overview",
        }
        if media_type:
            params["IncludeItemTypes"] = media_type

        url = f"{self.base_url}/Users/{user_id}/Items/Resume"
        async with session.get(url, params=params) as resp:
            if resp.status == 401:
                return "Error: Invalid Jellyfin API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            data = await resp.json()

        items = data.get("Items", [])
        if not items:
            return "Nothing in continue watching."

        return self._format_items(items, "Continue Watching")

    async def _get_latest(self, media_type: str | None = None) -> str:
        """Get recently added media."""
        user_id = await self._get_user_id()
        if not user_id:
            return "Error: Could not determine Jellyfin user."

        session = await self._get_session()
        params: dict[str, Any] = {
            "Limit": "10",
            "Fields": "Overview",
        }
        if media_type:
            params["IncludeItemTypes"] = media_type

        url = f"{self.base_url}/Users/{user_id}/Items/Latest"
        async with session.get(url, params=params) as resp:
            if resp.status == 401:
                return "Error: Invalid Jellyfin API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            items = await resp.json()

        if not items:
            return "No recently added media."

        return self._format_items(items, "Recently Added")

    async def _get_sessions(self) -> str:
        """Get active playback sessions."""
        session = await self._get_session()

        async with session.get(f"{self.base_url}/Sessions") as resp:
            if resp.status == 401:
                return "Error: Invalid Jellyfin API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            sessions = await resp.json()

        if not sessions:
            return "No active sessions."

        # Filter to sessions with NowPlayingItem or at least a device name
        active = [s for s in sessions if s.get("NowPlayingItem")]
        idle = [s for s in sessions if not s.get("NowPlayingItem")]

        return self._format_sessions(active, idle)

    async def _play_media(self, session_id: str, item_id: str) -> str:
        """Start playing an item on a session."""
        if not session_id:
            return "Error: session_id is required for play_media (get it from get_sessions)"
        if not item_id:
            return "Error: item_id is required for play_media (get it from search_library)"

        session = await self._get_session()
        url = f"{self.base_url}/Sessions/{session_id}/Playing"
        params = {
            "ItemIds": item_id,
            "PlayCommand": "PlayNow",
        }

        async with session.post(url, params=params) as resp:
            if resp.status == 204:
                return f"Started playback on session {session_id}."
            elif resp.status == 401:
                return "Error: Invalid Jellyfin API key."
            elif resp.status == 404:
                return f"Error: Session '{session_id}' not found. Use get_sessions to find active sessions."
            else:
                return f"Error: HTTP {resp.status}"

    async def _playstate_command(
        self,
        session_id: str,
        command: str,
        seek_position_ticks: int | None = None,
    ) -> str:
        """Send a playstate command to a session."""
        if not session_id:
            return "Error: session_id is required for playstate_command"
        if not command:
            return "Error: command is required for playstate_command"

        valid_commands = {
            "PlayPause", "Pause", "Unpause", "Stop",
            "NextTrack", "PreviousTrack", "Seek",
        }
        if command not in valid_commands:
            return f"Error: Invalid command '{command}'. Must be one of: {', '.join(sorted(valid_commands))}"

        session = await self._get_session()
        url = f"{self.base_url}/Sessions/{session_id}/Playing/{command}"
        params: dict[str, Any] = {}
        if command == "Seek" and seek_position_ticks is not None:
            params["SeekPositionTicks"] = str(seek_position_ticks)

        async with session.post(url, params=params) as resp:
            if resp.status == 204:
                return f"Sent '{command}' to session {session_id}."
            elif resp.status == 401:
                return "Error: Invalid Jellyfin API key."
            elif resp.status == 404:
                return f"Error: Session '{session_id}' not found."
            else:
                return f"Error: HTTP {resp.status}"

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _format_items(self, items: list[dict], heading: str) -> str:
        """Format library items for LLM consumption."""
        lines = [f"{heading} ({len(items)} item{'s' if len(items) != 1 else ''}):\n"]
        for i, item in enumerate(items, 1):
            name = item.get("Name", "Unknown")
            item_type = item.get("Type", "")
            item_id = item.get("Id", "?")
            year = item.get("ProductionYear", "")
            overview = item.get("Overview", "")

            # Build the main line
            year_str = f" ({year})" if year else ""
            type_str = f" [{item_type}]" if item_type else ""
            lines.append(f"{i}. {name}{year_str}{type_str} [ID: {item_id}]")

            # Show series info for episodes
            series_name = item.get("SeriesName")
            if series_name:
                season = item.get("ParentIndexNumber", "?")
                episode = item.get("IndexNumber", "?")
                lines.append(f"   {series_name} S{season:02d}E{episode:02d}" if isinstance(season, int) and isinstance(episode, int) else f"   {series_name} S{season}E{episode}")

            # Show playback progress if available
            ticks = item.get("UserData", {}).get("PlaybackPositionTicks", 0)
            if ticks and ticks > 0:
                runtime_ticks = item.get("RunTimeTicks", 0)
                pos_min = ticks // 600_000_000
                if runtime_ticks:
                    pct = (ticks / runtime_ticks) * 100
                    lines.append(f"   Progress: {pos_min}min ({pct:.0f}%)")
                else:
                    lines.append(f"   Progress: {pos_min}min")

            # Truncate overview
            if overview and len(overview) > 100:
                overview = overview[:100] + "..."
            if overview:
                lines.append(f"   {overview}")

        return "\n".join(lines)

    def _format_sessions(
        self,
        active: list[dict],
        idle: list[dict],
    ) -> str:
        """Format session list for LLM consumption."""
        lines: list[str] = []

        if active:
            lines.append(f"Now playing ({len(active)}):\n")
            for s in active:
                session_id = s.get("Id", "?")
                device = s.get("DeviceName", "Unknown device")
                client = s.get("Client", "")
                user = s.get("UserName", "")

                np = s.get("NowPlayingItem", {})
                item_name = np.get("Name", "Unknown")
                item_type = np.get("Type", "")

                # Show series info for episodes
                series = np.get("SeriesName")
                if series:
                    season = np.get("ParentIndexNumber", "?")
                    episode = np.get("IndexNumber", "?")
                    if isinstance(season, int) and isinstance(episode, int):
                        item_name = f"{series} S{season:02d}E{episode:02d} - {item_name}"
                    else:
                        item_name = f"{series} S{season}E{episode} - {item_name}"

                lines.append(f"- {item_name} [{item_type}]")
                lines.append(f"  Device: {device} ({client}) | User: {user}")
                lines.append(f"  Session ID: {session_id}")

                # Playback state
                play_state = s.get("PlayState", {})
                is_paused = play_state.get("IsPaused", False)
                position_ticks = play_state.get("PositionTicks", 0)
                pos_min = position_ticks // 600_000_000 if position_ticks else 0
                state = "Paused" if is_paused else "Playing"
                lines.append(f"  State: {state} at {pos_min}min")
                lines.append("")

        if idle:
            lines.append(f"Idle sessions ({len(idle)}):")
            for s in idle:
                session_id = s.get("Id", "?")
                device = s.get("DeviceName", "Unknown device")
                user = s.get("UserName", "")
                lines.append(f"- {device} (User: {user}) [Session: {session_id}]")

        if not active and not idle:
            return "No active sessions."

        return "\n".join(lines).rstrip()
