"""Tests for TaskScheduler._notify_user() channel routing.

Run with: pytest butler/api/test_scheduler_notify.py -v

These tests verify push/whatsapp/both routing and fallback behaviour.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock pywebpush before importing anything that touches api.push
sys.modules.setdefault("pywebpush", MagicMock())

from .scheduler import TaskScheduler  # noqa: E402


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    pool.pool = AsyncMock()
    return pool


@pytest.fixture
def whatsapp_tool():
    tool = MagicMock()
    tool.execute = AsyncMock(return_value="sent")
    return tool


@pytest.fixture
def scheduler_with_whatsapp(mock_pool, whatsapp_tool):
    return TaskScheduler(db_pool=mock_pool, tools={"whatsapp": whatsapp_tool})


@pytest.fixture
def scheduler_no_whatsapp(mock_pool):
    return TaskScheduler(db_pool=mock_pool, tools={})


class TestNotifyUser:
    """Tests for _notify_user channel routing."""

    @pytest.mark.asyncio
    @patch("api.push.send_push_to_user", new_callable=AsyncMock, return_value=1)
    async def test_push_default(self, mock_push, scheduler_with_whatsapp, whatsapp_tool):
        """Default channel (None) sends push; no WhatsApp when push succeeds."""
        await scheduler_with_whatsapp._notify_user(
            user_id="ron", title="Test", message="hello", channel=None,
        )

        mock_push.assert_awaited_once()
        whatsapp_tool.execute.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("api.push.send_push_to_user", new_callable=AsyncMock, return_value=0)
    async def test_push_fallback_to_whatsapp(self, mock_push, scheduler_with_whatsapp, whatsapp_tool):
        """When push returns 0 devices, fall back to WhatsApp."""
        await scheduler_with_whatsapp._notify_user(
            user_id="ron", title="Test", message="hello", channel=None,
        )

        mock_push.assert_awaited_once()
        whatsapp_tool.execute.assert_awaited_once_with(
            action="send_message", user_id="ron", message="hello", category="general",
        )

    @pytest.mark.asyncio
    @patch("api.push.send_push_to_user", new_callable=AsyncMock)
    async def test_whatsapp_explicit(self, mock_push, scheduler_with_whatsapp, whatsapp_tool):
        """Explicit 'whatsapp' channel skips push entirely."""
        await scheduler_with_whatsapp._notify_user(
            user_id="ron", title="Test", message="hello", channel="whatsapp",
        )

        mock_push.assert_not_awaited()
        whatsapp_tool.execute.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("api.push.send_push_to_user", new_callable=AsyncMock, return_value=2)
    async def test_both_channels(self, mock_push, scheduler_with_whatsapp, whatsapp_tool):
        """'both' sends via push AND WhatsApp."""
        await scheduler_with_whatsapp._notify_user(
            user_id="ron", title="Test", message="hello", channel="both",
        )

        mock_push.assert_awaited_once()
        whatsapp_tool.execute.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("api.push.send_push_to_user", new_callable=AsyncMock, return_value=0)
    async def test_push_no_fallback_no_whatsapp(self, mock_push, scheduler_no_whatsapp):
        """Push returns 0 and no WhatsApp configured — warning logged, no crash."""
        await scheduler_no_whatsapp._notify_user(
            user_id="ron", title="Test", message="hello", channel=None,
        )

        mock_push.assert_awaited_once()
        # No exception raised — notification silently lost with log warning

    @pytest.mark.asyncio
    @patch("api.push.send_push_to_user", new_callable=AsyncMock, return_value=1)
    async def test_push_passes_title_and_category(self, mock_push, scheduler_with_whatsapp):
        """Verify push receives correct title, body, and category."""
        await scheduler_with_whatsapp._notify_user(
            user_id="ron", title="Butler Alert", message="disk full",
            channel="push", category="health",
        )

        mock_push.assert_awaited_once_with(
            pool=scheduler_with_whatsapp._db_pool,
            user_id="ron",
            title="Butler Alert",
            body="disk full",
            url="/",
            category="health",
        )


class TestSendReminder:
    """Integration: _send_reminder delegates to _notify_user."""

    @pytest.mark.asyncio
    @patch("api.push.send_push_to_user", new_callable=AsyncMock, return_value=1)
    async def test_reminder_uses_push(self, mock_push, scheduler_with_whatsapp):
        """Reminder with no channel sends push."""
        action = {"type": "reminder", "message": "Take vitamins", "category": "health"}
        await scheduler_with_whatsapp._send_reminder(action, "ron")

        mock_push.assert_awaited_once()
        call_kw = mock_push.call_args
        assert call_kw.kwargs["body"] == "Take vitamins"
        assert call_kw.kwargs["category"] == "health"

    @pytest.mark.asyncio
    @patch("api.push.send_push_to_user", new_callable=AsyncMock)
    async def test_reminder_whatsapp_channel(self, mock_push, scheduler_with_whatsapp, whatsapp_tool):
        """Reminder with channel='whatsapp' skips push."""
        action = {"type": "reminder", "message": "Call dentist", "channel": "whatsapp"}
        await scheduler_with_whatsapp._send_reminder(action, "ron")

        mock_push.assert_not_awaited()
        whatsapp_tool.execute.assert_awaited_once()


class TestRunCheck:
    """Integration: _run_check delegates notification to _notify_user."""

    @pytest.mark.asyncio
    @patch("api.push.send_push_to_user", new_callable=AsyncMock, return_value=1)
    async def test_check_notifies_on_warning(self, mock_push, mock_pool):
        """Check with warning result sends push notification."""
        health_tool = MagicMock()
        health_tool.execute = AsyncMock(return_value="WARNING: disk usage 85%")

        scheduler = TaskScheduler(
            db_pool=mock_pool, tools={"server_health": health_tool},
        )
        action = {"type": "check", "tool": "server_health", "notifyOn": "warning"}
        with patch.object(
            TaskScheduler, "_tools_for_user",
            new=AsyncMock(return_value={"server_health": health_tool}),
        ):
            await scheduler._run_check(action, "system")

        mock_push.assert_awaited_once()
        assert "WARNING" in mock_push.call_args.kwargs["body"]

    @pytest.mark.asyncio
    @patch("api.push.send_push_to_user", new_callable=AsyncMock)
    async def test_check_no_notify_when_ok(self, mock_push, mock_pool):
        """Check with OK result does not notify."""
        health_tool = MagicMock()
        health_tool.execute = AsyncMock(return_value="All services healthy")

        scheduler = TaskScheduler(
            db_pool=mock_pool, tools={"server_health": health_tool},
        )
        action = {"type": "check", "tool": "server_health", "notifyOn": "warning"}
        with patch.object(
            TaskScheduler, "_tools_for_user",
            new=AsyncMock(return_value={"server_health": health_tool}),
        ):
            await scheduler._run_check(action, "system")

        mock_push.assert_not_awaited()


class TestScheduledToolPermissions:
    """Scheduled automations/checks run with the owner's permissions, not the global tool set."""

    @pytest.mark.asyncio
    async def test_automation_refused_when_tool_not_permitted(self, mock_pool):
        """A user who lost (or never had) a permission cannot run that tool via a task."""
        claude = MagicMock()
        claude.execute = AsyncMock(return_value="ran")
        scheduler = TaskScheduler(db_pool=mock_pool, tools={"run_claude_code": claude})
        action = {"type": "automation", "tool": "run_claude_code", "params": {"task": "rm -rf"}}

        with patch.object(TaskScheduler, "_tools_for_user", new=AsyncMock(return_value={})):
            await scheduler._run_automation(action, "guest")

        claude.execute.assert_not_awaited()
        mock_pool.pool.execute.assert_not_awaited()  # no audit row for a refused call

    @pytest.mark.asyncio
    async def test_automation_runs_permitted_tool_as_owner_and_audits(self, mock_pool):
        """Permitted tool runs with user_id pinned to the owner and an audit row written."""
        memory = MagicMock()
        memory.execute = AsyncMock(return_value="stored")
        scheduler = TaskScheduler(db_pool=mock_pool, tools={"memory": memory})
        # The stored params claim another user; the owner must win.
        action = {"type": "automation", "tool": "memory",
                  "params": {"user_id": "someone_else", "action": "store", "fact": "x"}}

        with patch.object(
            TaskScheduler, "_tools_for_user", new=AsyncMock(return_value={"memory": memory}),
        ):
            await scheduler._run_automation(action, "owner")

        memory.execute.assert_awaited_once()
        assert memory.execute.call_args.kwargs["user_id"] == "owner"
        mock_pool.pool.execute.assert_awaited_once()
        sql, *params = mock_pool.pool.execute.call_args.args
        assert "butler.tool_usage" in sql
        assert params[0] == "owner" and params[1] == "memory"
        assert params[-1] == "scheduler"

    @pytest.mark.asyncio
    async def test_unknown_tool_is_skipped_before_permission_lookup(self, mock_pool):
        scheduler = TaskScheduler(db_pool=mock_pool, tools={})
        lookup = AsyncMock(return_value={})
        with patch.object(TaskScheduler, "_tools_for_user", new=lookup):
            await scheduler._run_automation({"type": "automation", "tool": "nope"}, "u")
        lookup.assert_not_awaited()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
