"""Tests for the Google Calendar tool (#212). No network, no OAuth.

Run with: pytest butler/tools/test_google_calendar.py -v
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from .google_calendar import GoogleCalendarTool, _describe_when, execute_approved

EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"
TZ = "Europe/London"


def _tool(*, can_read=True, can_write=True, scopes=(EVENTS_SCOPE,)):
    t = GoogleCalendarTool(db_pool=MagicMock(), user_id="ron", can_read=can_read, can_write=can_write)
    t._get_token = AsyncMock(return_value="tok")
    t._granted_scopes = AsyncMock(return_value=set(scopes))
    return t


def _card():
    return {"id": "ap1"}


def _http(method: str, status=200, json_body=None, text=""):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_body or {})
    resp.text = AsyncMock(return_value=text)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    setattr(session, method, MagicMock(return_value=ctx))
    cls = MagicMock()
    cls.return_value.__aenter__ = AsyncMock(return_value=session)
    cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return cls, session


DENTIST = {
    "id": "ev1", "summary": "Dentist",
    "start": {"dateTime": "2026-10-08T10:00:00+01:00"},
    "end": {"dateTime": "2026-10-08T10:30:00+01:00"},
}


class TestCapabilities:
    def test_read_only_by_default(self):
        t = GoogleCalendarTool(db_pool=MagicMock(), user_id="ron")
        assert t.parameters["properties"]["action"]["enum"] == ["list_events", "search_events"]
        assert "event_id" not in t.parameters["properties"]

    def test_write_adds_actions_and_mentions_approval(self):
        t = _tool()
        assert t.parameters["properties"]["action"]["enum"][-3:] == ["create_event", "update_event", "delete_event"]
        assert "approve" in t.description.lower()

    @pytest.mark.asyncio
    async def test_write_without_scope_asks_to_reconnect(self):
        t = _tool(scopes=())
        out = await t.execute(action="create_event", summary="x", start="2026-10-09T15:00")
        assert "Reconnect" in out


class TestReading:
    @pytest.mark.asyncio
    async def test_today_starts_at_local_midnight_not_utc(self):
        t = _tool(can_write=False)
        cls, session = _http("get", json_body={"items": []})
        fake_now = datetime(2026, 10, 7, 0, 30, tzinfo=ZoneInfo(TZ))  # 23:30 UTC the day before
        with patch("tools.google_calendar.aiohttp.ClientSession", cls), \
             patch("tools.google_calendar.datetime") as dt:
            dt.now.return_value = fake_now
            dt.side_effect = lambda *a, **k: datetime(*a, **k)
            await t.execute(action="list_events")
        params = session.get.call_args.kwargs["params"]
        assert params["timeMin"] == "2026-10-07T00:00:00+01:00"
        assert params["timeZone"] == TZ

    @pytest.mark.asyncio
    async def test_api_errors_are_reported_not_hidden_as_no_events(self):
        t = _tool(can_write=False)
        cls, _ = _http("get", status=500, text="boom")
        with patch("tools.google_calendar.aiohttp.ClientSession", cls):
            out = await t.execute(action="list_events", date="2026-10-07")
        assert "error" in out.lower() and "No events" not in out

    def test_ids_shown_only_when_writable(self):
        assert "[id: ev1]" in _tool()._format_events([DENTIST], TZ)
        assert "[id:" not in _tool(can_write=False)._format_events([DENTIST], TZ)


class TestDrafts:
    @pytest.mark.asyncio
    async def test_create_defaults_to_one_hour(self):
        t = _tool()
        with patch("api.approvals.create_pending_action", AsyncMock(return_value=_card())) as create:
            out = await t.execute(action="create_event", summary="Haircut", start="2026-10-09T15:00",
                                  location="High St")
        assert "waiting for the user's approval" in out
        p = create.call_args.kwargs["params"]
        assert p["event"]["start"] == {"dateTime": "2026-10-09T15:00:00", "timeZone": TZ}
        assert p["event"]["end"] == {"dateTime": "2026-10-09T16:00:00", "timeZone": TZ}
        assert p["send_updates"] == "none"
        fields = dict(create.call_args.kwargs["summary"]["fields"])
        assert fields["When"] == "Fri 9 Oct 2026, 15:00–16:00" and fields["Where"] == "High St"

    @pytest.mark.asyncio
    async def test_all_day_end_is_exclusive(self):
        t = _tool()
        with patch("api.approvals.create_pending_action", AsyncMock(return_value=_card())) as create:
            await t.execute(action="create_event", summary="Holiday", start="2026-10-12", end="2026-10-16")
        ev = create.call_args.kwargs["params"]["event"]
        assert ev["start"] == {"date": "2026-10-12"} and ev["end"] == {"date": "2026-10-17"}

    @pytest.mark.asyncio
    async def test_guests_get_invitations(self):
        t = _tool()
        with patch("api.approvals.create_pending_action", AsyncMock(return_value=_card())) as create:
            await t.execute(action="create_event", summary="Lunch", start="2026-10-09T12:00",
                            attendees=["sam@example.com"])
        p = create.call_args.kwargs["params"]
        assert p["event"]["attendees"] == [{"email": "sam@example.com"}] and p["send_updates"] == "all"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kwargs,needle", [
        ({"summary": "x"}, "start"),
        ({"summary": "x", "start": "2026-10-09T15:00", "end": "2026-10-09T14:00"}, "after the start"),
        ({"summary": "x", "start": "2026-10-09T15:00", "end": "2026-10-10"}, "both be"),
        ({"summary": "x", "start": "next friday"}, "Invalid date"),
    ])
    async def test_create_validation(self, kwargs, needle):
        t = _tool()
        with patch("api.approvals.create_pending_action", AsyncMock()) as create:
            out = await t.execute(action="create_event", **kwargs)
        assert needle in out
        create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_moves_and_keeps_duration(self):
        t = _tool()
        t._get_event = AsyncMock(return_value=DENTIST)
        with patch("api.approvals.create_pending_action", AsyncMock(return_value=_card())) as create:
            await t.execute(action="update_event", event_id="ev1", start="2026-10-09T15:00")
        p = create.call_args.kwargs["params"]
        assert p["event_id"] == "ev1"
        assert p["patch"] == {
            "start": {"dateTime": "2026-10-09T15:00:00", "timeZone": TZ, "date": None},
            "end": {"dateTime": "2026-10-09T15:30:00", "timeZone": TZ, "date": None},
        }
        fields = dict(create.call_args.kwargs["summary"]["fields"])
        assert fields["When"] == "Thu 8 Oct 2026, 10:00–10:30 → Fri 9 Oct 2026, 15:00–15:30"

    @pytest.mark.asyncio
    async def test_update_end_only_keeps_start(self):
        t = _tool()
        t._get_event = AsyncMock(return_value=DENTIST)
        with patch("api.approvals.create_pending_action", AsyncMock(return_value=_card())) as create:
            await t.execute(action="update_event", event_id="ev1", end="2026-10-08T11:00")
        patch_body = create.call_args.kwargs["params"]["patch"]
        assert patch_body["start"]["dateTime"] == "2026-10-08T10:00:00"
        assert patch_body["end"]["dateTime"] == "2026-10-08T11:00:00"

    @pytest.mark.asyncio
    async def test_update_to_all_day_clears_the_time_fields(self):
        t = _tool()
        t._get_event = AsyncMock(return_value=DENTIST)
        with patch("api.approvals.create_pending_action", AsyncMock(return_value=_card())) as create:
            await t.execute(action="update_event", event_id="ev1", start="2026-10-09")
        patch_body = create.call_args.kwargs["params"]["patch"]
        # PATCH merges nested objects: without the nulls Google keeps dateTime too.
        assert patch_body["start"] == {"date": "2026-10-09", "dateTime": None, "timeZone": None}
        assert patch_body["end"] == {"date": "2026-10-10", "dateTime": None, "timeZone": None}

    @pytest.mark.asyncio
    async def test_event_id_is_escaped_in_urls(self):
        cls, session = _http("delete", status=204)
        with patch("api.oauth.get_valid_token", AsyncMock(return_value="tok")), \
             patch("tools.google_calendar.aiohttp.ClientSession", cls):
            await execute_approved(MagicMock(), "ron", "calendar.delete", {"event_id": "../../x", "summary": "x"})
        assert session.delete.call_args.args[0].endswith("/events/..%2F..%2Fx")

    @pytest.mark.asyncio
    async def test_update_with_nothing_to_change(self):
        t = _tool()
        t._get_event = AsyncMock(return_value=DENTIST)
        assert "Nothing to change" in await t.execute(action="update_event", event_id="ev1")

    @pytest.mark.asyncio
    async def test_delete_shows_what_goes(self):
        t = _tool()
        t._get_event = AsyncMock(return_value={**DENTIST, "attendees": [{"email": "sam@example.com"}]})
        with patch("api.approvals.create_pending_action", AsyncMock(return_value=_card())) as create:
            await t.execute(action="delete_event", event_id="ev1")
        assert create.call_args.args[2] == "calendar.delete"
        p = create.call_args.kwargs["params"]
        assert p == {"event_id": "ev1", "send_updates": "all", "summary": "Dentist"}

    @pytest.mark.asyncio
    async def test_unknown_event_id(self):
        t = _tool()
        t._get_event = AsyncMock(return_value="No event with id nope — search for it again to get the current id.")
        assert "No event" in await t.execute(action="delete_event", event_id="nope")


class TestExecuteApproved:
    @pytest.mark.asyncio
    async def test_create_posts_the_stored_event(self):
        ev = {"summary": "Haircut", "start": {"dateTime": "2026-10-09T15:00:00", "timeZone": TZ},
              "end": {"dateTime": "2026-10-09T16:00:00", "timeZone": TZ}}
        cls, session = _http("post", status=200)
        with patch("api.oauth.get_valid_token", AsyncMock(return_value="tok")), \
             patch("tools.google_calendar.aiohttp.ClientSession", cls):
            out = await execute_approved(MagicMock(), "ron", "calendar.create", {"event": ev, "send_updates": "none"})
        assert out == "Added “Haircut” — Fri 9 Oct 2026, 15:00–16:00."
        assert session.post.call_args.kwargs["json"] == ev
        assert session.post.call_args.kwargs["params"] == {"sendUpdates": "none"}

    @pytest.mark.asyncio
    async def test_delete_of_already_deleted_event_is_fine(self):
        cls, _ = _http("delete", status=410)
        with patch("api.oauth.get_valid_token", AsyncMock(return_value="tok")), \
             patch("tools.google_calendar.aiohttp.ClientSession", cls):
            out = await execute_approved(MagicMock(), "ron", "calendar.delete",
                                         {"event_id": "ev1", "summary": "Dentist"})
        assert "already gone" in out

    @pytest.mark.asyncio
    async def test_forbidden_becomes_retryable_reconnect_message(self):
        from api.approvals import ApprovalRetryable as ApprovalError

        cls, _ = _http("patch", status=403)
        with patch("api.oauth.get_valid_token", AsyncMock(return_value="tok")), \
             patch("tools.google_calendar.aiohttp.ClientSession", cls), \
             pytest.raises(ApprovalError, match="Reconnect"):
            await execute_approved(MagicMock(), "ron", "calendar.update",
                                   {"event_id": "ev1", "patch": {"summary": "x"}})


def test_describe_when_all_day_range():
    from datetime import date
    assert _describe_when(date(2026, 10, 12), date(2026, 10, 17)) == "Mon 12 Oct – Fri 16 Oct (all day)"
    assert _describe_when(date(2026, 10, 12), date(2026, 10, 13)) == "Mon 12 Oct 2026 (all day)"
