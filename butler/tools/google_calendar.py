"""Google Calendar integration tool for Butler.

Reads a user's Google Calendar ("What's on my schedule today?") and, for users
with the ``calendar_write`` permission, drafts new events, changes and
deletions. Drafts never apply on their own: they become a pending approval the
user taps in the Butler app (see api/approvals.py), and ``execute_approved``
below runs only after that tap.

Requires the user to have connected their Google Calendar via OAuth
in the Settings page. If not connected, returns a helpful message
directing the user to connect.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp

from .base import Tool

logger = logging.getLogger(__name__)

CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
EVENTS_URL = f"{CALENDAR_API_BASE}/calendars/primary/events"

READ_ACTIONS = ["list_events", "search_events"]
WRITE_ACTIONS = ["create_event", "update_event", "delete_event"]

_RECONNECT_FOR_WRITE = (
    "Changing the calendar needs extra Google permission that this account hasn't granted yet. "
    "Ask the user to tap Reconnect next to Google in Settings > Connected Services, then try again."
)

_AWAITING_APPROVAL = (
    "Calendar change drafted and waiting for the user's approval (approval id {id}). "
    "Nothing has changed yet. Tell the user it's ready to review — they tap Approve "
    "in the Butler app. Do not say the calendar was updated."
)


def _default_tz() -> str:
    from api.config import settings

    return settings.local_timezone


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or _default_tz())
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(_default_tz())


# All datetimes in this module are *naive local time in ``tz``*, so they can be
# compared and shifted freely; _event_time() attaches the zone for Google.


def _parse_when(value: str, tz: str) -> date | datetime:
    """'YYYY-MM-DD' -> date (all-day); 'YYYY-MM-DDTHH:MM[:SS]' -> naive local datetime."""
    value = value.strip()
    if len(value) == 10:
        return date.fromisoformat(value)
    dt = datetime.fromisoformat(value)
    return dt.astimezone(_zone(tz)).replace(tzinfo=None) if dt.tzinfo else dt


def _event_time(value: date | datetime, tz: str) -> dict:
    if isinstance(value, datetime):
        return {"dateTime": value.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": tz}
    return {"date": value.isoformat()}


def _patch_time(value: date | datetime, tz: str) -> dict:
    """Like _event_time, but nulls the other form: PATCH merges nested objects, so
    turning a timed event all-day (or back) would otherwise keep both and fail."""
    if isinstance(value, datetime):
        return {**_event_time(value, tz), "date": None}
    return {**_event_time(value, tz), "dateTime": None, "timeZone": None}


def _event_url(event_id: str) -> str:
    return f"{EVENTS_URL}/{quote(event_id, safe='')}"


def _from_event_time(t: dict, tz: str) -> date | datetime | None:
    if "dateTime" in t:
        dt = datetime.fromisoformat(t["dateTime"])
        if dt.tzinfo is None:  # Google sent local time with a separate timeZone
            dt = dt.replace(tzinfo=_zone(t.get("timeZone") or tz))
        return dt.astimezone(_zone(tz)).replace(tzinfo=None)
    if "date" in t:
        return date.fromisoformat(t["date"])
    return None


def _same_kind(a: date | datetime | None, b: date | datetime | None) -> bool:
    return isinstance(a, datetime) == isinstance(b, datetime)


def _describe_when(start: date | datetime | None, end: date | datetime | None) -> str:
    if start is None:
        return "(unknown time)"
    if not isinstance(start, datetime):
        last = (end - timedelta(days=1)) if isinstance(end, date) and not isinstance(end, datetime) else start
        if last and last > start:
            return f"{start:%a} {start.day} {start:%b} – {last:%a} {last.day} {last:%b} (all day)"
        return f"{start:%a} {start.day} {start:%b %Y} (all day)"
    text = f"{start:%a} {start.day} {start:%b %Y}, {start:%H:%M}"
    if isinstance(end, datetime):
        text += f"–{end:%H:%M}" if end.date() == start.date() else f" – {end:%a} {end.day} {end:%b}, {end:%H:%M}"
    return text


class GoogleCalendarTool(Tool):
    """Access to a user's Google Calendar: read, and (with approval) change.

    This tool is user-scoped: it's created per-request with a specific
    user_id, unlike global tools (HA, memory) which are created once
    at startup.
    """

    def __init__(self, db_pool, user_id: str, *, can_read: bool = True, can_write: bool = False):
        self._pool = db_pool
        self._user_id = user_id
        self._can_read = can_read
        self._can_write = can_write

    @property
    def name(self) -> str:
        return "google_calendar"

    @property
    def _actions(self) -> list[str]:
        return (READ_ACTIONS if self._can_read else []) + (WRITE_ACTIONS if self._can_write else [])

    @property
    def description(self) -> str:
        if not self._can_write:
            return (
                "Check the user's Google Calendar. Can list upcoming events "
                "or search for events by keyword. Only works if the user has "
                "connected their Google Calendar in Settings."
            )
        reading = "Check the user's Google Calendar (list or search events, which show each event's id). " if self._can_read else ""
        return (
            f"{reading}Draft new events (create_event), changes (update_event) and deletions "
            "(delete_event) on their primary calendar. Times are local (household timezone) "
            "unless a timezone is given. Changes are NOT applied immediately: the user must "
            "approve each one in the Butler app. After drafting, tell the user it's waiting for "
            "their approval — never say the calendar was changed. Find an event's id with "
            "list_events/search_events before updating or deleting it. Only works if the user "
            "has connected Google in Settings."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        descriptions = {
            "list_events": "list_events: get upcoming events for a date range.",
            "search_events": "search_events: find events matching a keyword.",
            "create_event": "create_event: draft a new event (summary, start, optional end/location/description/attendees).",
            "update_event": "update_event: draft a change to an event by event_id (only the fields given change).",
            "delete_event": "delete_event: draft deleting an event by event_id.",
        }
        props: dict[str, Any] = {
            "action": {
                "type": "string",
                "enum": self._actions,
                "description": " ".join(descriptions[a] for a in self._actions),
            },
            "timezone": {
                "type": "string",
                "description": (
                    "IANA timezone (e.g., 'Europe/London', 'America/New_York'). "
                    "Used to determine the correct 'today' and format times. "
                    "Defaults to the household timezone."
                ),
            },
        }
        if self._can_read:
            props.update({
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
            })
        if self._can_write:
            props.update({
                "event_id": {"type": "string", "description": "Event id (from list/search) for update_event or delete_event."},
                "summary": {"type": "string", "description": "Event title."},
                "start": {
                    "type": "string",
                    "description": "Start: 'YYYY-MM-DDTHH:MM' (local time) or 'YYYY-MM-DD' for an all-day event.",
                },
                "end": {
                    "type": "string",
                    "description": (
                        "End, same format as start. Optional: defaults to 1 hour after start "
                        "(or the same day for all-day); on update, keeps the original duration."
                    ),
                },
                "location": {"type": "string", "description": "Event location."},
                "description": {"type": "string", "description": "Event notes."},
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Guest email addresses for create_event; Google emails them an invitation.",
                },
            })
        return {"type": "object", "properties": props, "required": ["action"]}

    async def _get_token(self) -> str | None:
        from api.oauth import get_valid_token

        return await get_valid_token(self._pool, self._user_id, "google")

    async def _granted_scopes(self) -> set[str]:
        from api.oauth import get_granted_scopes

        return await get_granted_scopes(self._pool, self._user_id, "google")

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", self._actions[0] if self._actions else "")
        if action not in self._actions:
            return f"Unknown action: {action}. Use one of: {', '.join(self._actions)}."

        access_token = await self._get_token()
        if not access_token:
            return (
                "Google is not connected. "
                "Please connect it in the Settings page of the Butler app."
            )

        try:
            if action == "list_events":
                return await self._list_events(access_token, kwargs)
            if action == "search_events":
                return await self._search_events(access_token, kwargs)

            from api.oauth import CALENDAR_EVENTS_SCOPE

            if CALENDAR_EVENTS_SCOPE not in await self._granted_scopes():
                return _RECONNECT_FOR_WRITE
            if action == "create_event":
                return await self._draft_create(kwargs)
            if action == "update_event":
                return await self._draft_update(access_token, kwargs)
            return await self._draft_delete(access_token, kwargs)
        except ValueError as e:
            return f"Invalid date/time: {e}. Use 'YYYY-MM-DDTHH:MM' or 'YYYY-MM-DD'."
        except aiohttp.ClientError as e:
            return f"Error connecting to Google Calendar: {e}"
        except Exception as e:
            logger.exception("Google Calendar tool error")
            return f"Error: {e}"

    # -- reading -------------------------------------------------------------

    async def _list_events(self, access_token: str, kwargs: dict) -> str:
        """List events for a date range, starting at local midnight."""
        tz = kwargs.get("timezone") or _default_tz()
        zone = _zone(tz)
        days = min(kwargs.get("days", 1), 14)

        if date_str := kwargs.get("date"):
            try:
                day = date.fromisoformat(date_str)
            except ValueError:
                return f"Invalid date format: {date_str}. Use YYYY-MM-DD."
        else:
            day = datetime.now(zone).date()
        start = datetime(day.year, day.month, day.day, tzinfo=zone)
        end = start + timedelta(days=days)

        result = await self._fetch_events(
            access_token, time_min=start.isoformat(), time_max=end.isoformat(), timezone=tz,
        )
        if isinstance(result, str):
            return result  # Error message
        if not result:
            if days == 1:
                return f"No events scheduled for {start:%A, %B} {start.day}."
            return f"No events in the next {days} days."

        return self._format_events(result, tz)

    async def _search_events(self, access_token: str, kwargs: dict) -> str:
        """Search for events matching a query."""
        query = kwargs.get("query", "")
        if not query:
            return "Please provide a search query."

        tz = kwargs.get("timezone") or _default_tz()
        days = min(kwargs.get("days", 14), 14)
        start = datetime.now(_zone(tz))
        end = start + timedelta(days=days)

        result = await self._fetch_events(
            access_token, time_min=start.isoformat(), time_max=end.isoformat(),
            query=query, timezone=tz,
        )
        if isinstance(result, str):
            return result  # Error message
        if not result:
            return f"No events matching '{query}' in the next {days} days."

        return self._format_events(result, tz)

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
        if the request fails (so a failure is never reported as "no events").
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

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                EVENTS_URL,
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
                    if resp.status == 403:
                        return "Google Calendar refused access — reconnect Google in Settings > Connected Services."
                    return f"Google Calendar API error (status {resp.status})."
                data = await resp.json()
                return data.get("items", [])

    async def _get_event(self, access_token: str, event_id: str) -> dict | str:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                _event_url(event_id),
                headers={"Authorization": f"Bearer {access_token}"},
            ) as resp:
                if resp.status in (404, 410):
                    return f"No event with id {event_id} — search for it again to get the current id."
                if resp.status != 200:
                    return f"Google Calendar API error (status {resp.status})."
                return await resp.json()

    def _format_events(self, events: list[dict], tz: str | None = None) -> str:
        """Format Google Calendar events as readable text."""
        tz = tz or _default_tz()
        lines: list[str] = []
        current_date = ""

        for event in events:
            start = _from_event_time(event.get("start", {}), tz)
            end = _from_event_time(event.get("end", {}), tz)
            if start is None:
                continue

            date_label = f"{start:%A, %B} {start.day}"
            if isinstance(start, datetime) and isinstance(end, datetime):
                time_str = f"{start.strftime('%I:%M %p')} - {end.strftime('%I:%M %p')}"
            else:
                time_str = "All day"

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
            if self._can_write and event.get("id"):
                line += f"  [id: {event['id']}]"

            lines.append(line)

        return "\n".join(lines)

    # -- drafting (creates a pending approval; nothing changes here) ----------

    async def _draft_create(self, kwargs: dict) -> str:
        from api.approvals import create_pending_action

        summary = (kwargs.get("summary") or "").strip()
        start_raw = (kwargs.get("start") or "").strip()
        if not summary or not start_raw:
            return "Please provide at least a summary (title) and a start time."
        tz = kwargs.get("timezone") or _default_tz()

        start = _parse_when(start_raw, tz)
        if end_raw := (kwargs.get("end") or "").strip():
            end = _parse_when(end_raw, tz)
        elif isinstance(start, datetime):
            end = start + timedelta(hours=1)
        else:
            end = start
        if not _same_kind(start, end):
            return "Start and end must both be times, or both be dates (all-day)."
        # Google's all-day end date is exclusive.
        api_end = end + timedelta(days=1) if not isinstance(end, datetime) else end
        if api_end <= start:
            return "The end must be after the start."

        event: dict[str, Any] = {
            "summary": summary,
            "start": _event_time(start, tz),
            "end": _event_time(api_end, tz),
        }
        if loc := (kwargs.get("location") or "").strip():
            event["location"] = loc
        if desc := (kwargs.get("description") or "").strip():
            event["description"] = desc
        attendees = [a.strip() for a in kwargs.get("attendees") or [] if a and "@" in a]
        if attendees:
            event["attendees"] = [{"email": a} for a in attendees]

        fields = [["Event", summary], ["When", _describe_when(start, api_end)]]
        if loc:
            fields.append(["Where", loc])
        if attendees:
            fields.append(["Guests", ", ".join(attendees) + " (Google emails them an invitation)"])
        card = await create_pending_action(
            self._pool, self._user_id, "calendar.create",
            params={"event": event, "send_updates": "all" if attendees else "none"},
            summary={"title": "Add calendar event", "fields": fields, "body": event.get("description")},
        )
        return _AWAITING_APPROVAL.format(id=card["id"])

    async def _draft_update(self, access_token: str, kwargs: dict) -> str:
        from api.approvals import create_pending_action

        event_id = (kwargs.get("event_id") or "").strip()
        if not event_id:
            return "Please provide the event_id (find it with list_events or search_events)."
        existing = await self._get_event(access_token, event_id)
        if isinstance(existing, str):
            return existing
        tz = kwargs.get("timezone") or _default_tz()

        patch: dict[str, Any] = {}
        fields = [["Event", existing.get("summary", "(No title)")]]
        if summary := (kwargs.get("summary") or "").strip():
            patch["summary"] = summary
            fields.append(["Title", f"{existing.get('summary', '')} → {summary}"])

        old_start = _from_event_time(existing.get("start", {}), tz)
        old_end = _from_event_time(existing.get("end", {}), tz)
        start_raw, end_raw = (kwargs.get("start") or "").strip(), (kwargs.get("end") or "").strip()
        if start_raw or end_raw:
            start = _parse_when(start_raw, tz) if start_raw else old_start
            if end_raw:
                end = _parse_when(end_raw, tz)
                if not isinstance(end, datetime):
                    end = end + timedelta(days=1)  # Google's all-day end is exclusive
            elif old_start is not None and old_end is not None and _same_kind(start, old_start):
                end = start + (old_end - old_start)  # keep the original duration
            elif isinstance(start, datetime):
                end = start + timedelta(hours=1)
            else:
                end = start + timedelta(days=1)
            if start is None or not _same_kind(start, end):
                return "Start and end must both be times, or both be dates (all-day)."
            if end <= start:
                return "The end must be after the start."
            patch["start"] = _patch_time(start, tz)
            patch["end"] = _patch_time(end, tz)
            fields.append(["When", f"{_describe_when(old_start, old_end)} → {_describe_when(start, end)}"])
        if (loc := kwargs.get("location")) is not None and loc.strip() != (existing.get("location") or ""):
            patch["location"] = loc.strip()
            fields.append(["Where", loc.strip() or "(removed)"])
        if (desc := kwargs.get("description")) is not None:
            patch["description"] = desc.strip()
        if not patch:
            return "Nothing to change — give a new summary, start/end, location or description."
        if "When" not in [f[0] for f in fields]:
            fields.insert(1, ["When", _describe_when(old_start, old_end)])

        has_guests = bool(existing.get("attendees"))
        card = await create_pending_action(
            self._pool, self._user_id, "calendar.update",
            params={"event_id": event_id, "patch": patch, "send_updates": "all" if has_guests else "none",
                    "summary": existing.get("summary", "")},
            summary={"title": "Change calendar event", "fields": fields, "body": patch.get("description")},
        )
        return _AWAITING_APPROVAL.format(id=card["id"])

    async def _draft_delete(self, access_token: str, kwargs: dict) -> str:
        from api.approvals import create_pending_action

        event_id = (kwargs.get("event_id") or "").strip()
        if not event_id:
            return "Please provide the event_id (find it with list_events or search_events)."
        existing = await self._get_event(access_token, event_id)
        if isinstance(existing, str):
            return existing
        tz = kwargs.get("timezone") or _default_tz()
        title = existing.get("summary", "(No title)")
        when = _describe_when(
            _from_event_time(existing.get("start", {}), tz), _from_event_time(existing.get("end", {}), tz),
        )
        fields = [["Event", title], ["When", when]]
        has_guests = bool(existing.get("attendees"))
        if has_guests:
            fields.append(["Guests", "Google will tell them it's cancelled"])
        card = await create_pending_action(
            self._pool, self._user_id, "calendar.delete",
            params={"event_id": event_id, "send_updates": "all" if has_guests else "none", "summary": title},
            summary={"title": "Delete calendar event", "fields": fields, "body": None},
        )
        return _AWAITING_APPROVAL.format(id=card["id"])


async def execute_approved(pool, user_id: str, kind: str, params: dict) -> str:
    """Run an approved calendar.create / .update / .delete. Called only by api.approvals."""
    from api.approvals import ApprovalError, ApprovalRetryable
    from api.oauth import get_valid_token

    token = await get_valid_token(pool, user_id, "google")
    if not token:
        raise ApprovalRetryable("Google needs reconnecting — tap Reconnect next to Google in Settings, then tap Approve again.")

    query = {"sendUpdates": params.get("send_updates", "none")}
    headers = {"Authorization": f"Bearer {token}"}
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if kind == "calendar.create":
                req = session.post(EVENTS_URL, params=query, json=params["event"], headers=headers)
            elif kind == "calendar.update":
                req = session.patch(_event_url(params["event_id"]), params=query, json=params["patch"], headers=headers)
            elif kind == "calendar.delete":
                req = session.delete(_event_url(params["event_id"]), params=query, headers=headers)
            else:
                raise ApprovalError(f"Unknown calendar action: {kind}")
            async with req as resp:
                status = resp.status
                text = await resp.text()
    except aiohttp.ClientConnectorError as e:
        # Never connected, so nothing changed; anything later is ambiguous.
        raise ApprovalRetryable(f"Couldn't reach Google Calendar ({e}) — nothing changed. Tap Approve to try again.") from e
    except aiohttp.ClientError as e:
        raise ApprovalError(f"Google Calendar error: {e}. Check the calendar before trying again.") from e

    if status in (200, 201, 204):
        if kind == "calendar.create":
            ev = params["event"]
            when = _describe_when(
                _from_event_time(ev["start"], _default_tz()), _from_event_time(ev["end"], _default_tz()),
            )
            return f"Added “{ev['summary']}” — {when}."
        if kind == "calendar.update":
            return f"Updated “{params.get('summary') or 'event'}”."
        return f"Deleted “{params.get('summary') or 'event'}”."
    logger.warning("Calendar %s failed %d: %s", kind, status, text[:300])
    if status == 401:
        raise ApprovalRetryable("Google access has expired — reconnect Google in Settings, then tap Approve again.")
    if status == 403:
        raise ApprovalRetryable(
            "Google hasn't given Butler permission to change your calendar — "
            "tap Reconnect next to Google in Settings, then tap Approve again."
        )
    if status in (404, 410):
        if kind == "calendar.delete":
            return f"“{params.get('summary') or 'That event'}” was already gone."
        raise ApprovalError("That event no longer exists.")
    raise ApprovalError(f"Google Calendar refused the change (status {status}).")
