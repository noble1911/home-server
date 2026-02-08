"""Google Calendar integration tool for Butler.

Provides read-only access to a user's Google Calendar, enabling
the agent to answer questions like "What's on my schedule today?"
or "Do I have any meetings tomorrow morning?"

Requires the user to have connected their Google Calendar via OAuth
in the Settings page. If not connected, returns a helpful message
directing the user to connect.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from .base import Tool

logger = logging.getLogger(__name__)

CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarTool(Tool):
    """Read-only access to a user's Google Calendar.

    This tool is user-scoped: it's created per-request with a specific
    user_id, unlike global tools (HA, memory) which are created once
    at startup.
    """

    def __init__(self, db_pool, user_id: str):
        self._pool = db_pool
        self._user_id = user_id

    @property
    def name(self) -> str:
        return "google_calendar"

    @property
    def description(self) -> str:
        return (
            "Check the user's Google Calendar. Can list upcoming events "
            "or search for events by keyword. Only works if the user has "
            "connected their Google Calendar in Settings."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_events", "search_events"],
                    "description": (
                        "list_events: get upcoming events for a date range. "
                        "search_events: find events matching a keyword."
                    ),
                },
                "date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD) to start from. Defaults to today.",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days to look ahead (default: 1, max: 14).",
                    "minimum": 1,
                    "maximum": 14,
                },
                "query": {
                    "type": "string",
                    "description": "Search keyword for search_events (e.g., 'dentist', 'team meeting').",
                },
                "timezone": {
                    "type": "string",
                    "description": (
                        "IANA timezone (e.g., 'Europe/London', 'America/New_York'). "
                        "Used to determine the correct 'today' and format times. "
                        "Defaults to the calendar's configured timezone."
                    ),
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "list_events")

        # Import here to avoid circular imports at module level
        from api.oauth import get_valid_token

        access_token = await get_valid_token(self._pool, self._user_id, "google")
        if not access_token:
            return (
                "Google is not connected. "
                "Please connect it in the Settings page of the Butler app."
            )

        try:
            if action == "list_events":
                return await self._list_events(access_token, kwargs)
            elif action == "search_events":
                return await self._search_events(access_token, kwargs)
            else:
                return f"Unknown action: {action}. Use 'list_events' or 'search_events'."
        except aiohttp.ClientError as e:
            return f"Error connecting to Google Calendar: {e}"
        except Exception as e:
            logger.exception("Google Calendar tool error")
            return f"Error: {e}"

    async def _list_events(self, access_token: str, kwargs: dict) -> str:
        """List events for a date range."""
        date_str = kwargs.get("date")
        days = min(kwargs.get("days", 1), 14)
        tz = kwargs.get("timezone")

        if date_str:
            try:
                start = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
            except ValueError:
                return f"Invalid date format: {date_str}. Use YYYY-MM-DD."
        else:
            start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        end = start + timedelta(days=days)

        result = await self._fetch_events(
            access_token,
            time_min=start.isoformat(),
            time_max=end.isoformat(),
            timezone=tz,
        )
        if isinstance(result, str):
            return result  # Error message
        if not result:
            if days == 1:
                return f"No events scheduled for {start.strftime('%A, %B %d')}."
            return f"No events in the next {days} days."

        return self._format_events(result)

    async def _search_events(self, access_token: str, kwargs: dict) -> str:
        """Search for events matching a query."""
        query = kwargs.get("query", "")
        if not query:
            return "Please provide a search query."

        days = min(kwargs.get("days", 14), 14)
        start = datetime.now(timezone.utc)
        end = start + timedelta(days=days)

        tz = kwargs.get("timezone")

        result = await self._fetch_events(
            access_token,
            time_min=start.isoformat(),
            time_max=end.isoformat(),
            query=query,
            timezone=tz,
        )
        if isinstance(result, str):
            return result  # Error message
        if not result:
            return f"No events matching '{query}' in the next {days} days."

        return self._format_events(result)

    async def _fetch_events(
        self,
        access_token: str,
        time_min: str,
        time_max: str,
        query: str | None = None,
        timezone: str | None = None,
    ) -> list[dict] | str:
        """Fetch events from Google Calendar API.

        Returns a list of event dicts on success, or an error string
        if the request fails (e.g. 401 needing re-auth).
        """
        params: dict[str, str | int] = {
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 20,
        }
        if query:
            params["q"] = query
        if timezone:
            params["timeZone"] = timezone

        url = f"{CALENDAR_API_BASE}/calendars/primary/events"
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            ) as resp:
                if resp.status == 401:
                    logger.warning("Google Calendar API returned 401 for user=%s — token may need re-auth", self._user_id)
                    return (
                        "Google Calendar access has expired. "
                        "Please reconnect in Settings > Connected Services."
                    )
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning("Google Calendar API %d: %s", resp.status, text[:200])
                    return []
                data = await resp.json()
                return data.get("items", [])

    def _format_events(self, events: list[dict]) -> str:
        """Format Google Calendar events as readable text."""
        lines: list[str] = []
        current_date = ""

        for event in events:
            start = event.get("start", {})
            end = event.get("end", {})

            # All-day events use 'date', timed events use 'dateTime'
            if "dateTime" in start:
                start_dt = datetime.fromisoformat(start["dateTime"])
                end_dt = datetime.fromisoformat(end["dateTime"])
                date_label = start_dt.strftime("%A, %B %d")
                time_str = f"{start_dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')}"
            elif "date" in start:
                date_label = datetime.fromisoformat(start["date"]).strftime("%A, %B %d")
                time_str = "All day"
            else:
                continue

            # Group by date
            if date_label != current_date:
                if lines:
                    lines.append("")
                lines.append(f"📅 {date_label}")
                current_date = date_label

            summary = event.get("summary", "(No title)")
            line = f"  • {time_str}: {summary}"

            location = event.get("location")
            if location:
                line += f" @ {location}"

            lines.append(line)

        return "\n".join(lines)

