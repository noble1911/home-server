"""Tests for scheduled 'ask' tasks (Butler runs on a schedule) and local-time cron.

Run with: pytest butler/api/test_scheduler_ask.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("pywebpush", MagicMock())

from . import scheduler as sched  # noqa: E402
from .scheduler import NOTHING_TO_REPORT, TaskScheduler, _preview, next_cron_run  # noqa: E402

TASK = "Morning briefing"
PROMPT = "Check my email and calendar and tell me anything important."


def _tool(name):
    t = MagicMock()
    t.name = name
    return t


@pytest.fixture
def scheduler():
    pool = MagicMock()
    pool.pool = AsyncMock()
    s = TaskScheduler(db_pool=pool, tools={})
    s._tools_for_user = AsyncMock(return_value={
        n: _tool(n) for n in ["gmail", "google_calendar", "weather", "home_assistant", "run_claude_code", "qbittorrent"]
    })
    s._notify_user = AsyncMock()
    return s


def _patched(answer):
    ctx = SimpleNamespace(system_prompt=[{"type": "text", "text": "You are Butler."}])
    return (
        patch("api.context.load_user_context", AsyncMock(return_value=ctx)),
        patch("api.deps.get_embedding_service", return_value=None),
        patch("api.llm.chat_with_tools", AsyncMock(return_value=answer)),
    )


async def _run(scheduler, answer, **action):
    a, b, c = _patched(answer)
    with a as load_ctx, b, c as chat:
        await scheduler._run_ask({"type": "ask", "prompt": PROMPT, **action}, "ron", TASK)
    return load_ctx, chat


class TestAskTask:
    @pytest.mark.asyncio
    async def test_runs_butler_with_only_unattended_tools(self, scheduler):
        load_ctx, chat = await _run(scheduler, "Sam needs the contract signed by Friday.")
        system, prompt, tools = chat.call_args.args
        assert prompt == PROMPT
        assert set(tools) == {"gmail", "google_calendar", "weather"}  # no shell, home control or downloads
        assert chat.call_args.kwargs["channel"] == "scheduler" and chat.call_args.kwargs["user_id"] == "ron"
        assert "not watching" in system[-1]["text"] and NOTHING_TO_REPORT in system[-1]["text"]
        assert load_ctx.call_args.kwargs["history_limit"] == 0

    @pytest.mark.asyncio
    async def test_reports_to_chat_and_phone(self, scheduler):
        await _run(scheduler, "**Needs you:** Sam needs the contract signed by Friday.", channel="push")
        sql, user, text, meta = scheduler._db_pool.pool.execute.call_args.args
        assert "conversation_history" in sql and "'scheduled'" in sql
        assert (user, meta) == ("ron", {"task": TASK}) and text.startswith("**Needs you:**")
        kw = scheduler._notify_user.call_args.kwargs
        assert kw["title"] == TASK and kw["channel"] == "push"
        assert kw["message"] == "Needs you: Sam needs the contract signed by Friday."

    @pytest.mark.asyncio
    async def test_quiet_when_nothing_matters(self, scheduler):
        await _run(scheduler, NOTHING_TO_REPORT)
        scheduler._notify_user.assert_not_awaited()
        scheduler._db_pool.pool.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_always_mode_reports_even_quiet_days(self, scheduler):
        _, chat = await _run(scheduler, "All quiet: no new important email, two meetings today.", notify="always")
        instructions = chat.call_args.args[0][-1]["text"]
        assert "Always write the report" in instructions and NOTHING_TO_REPORT not in instructions
        scheduler._notify_user.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_prompt_does_nothing(self, scheduler):
        a, b, c = _patched("x")
        with a, b, c as chat:
            await scheduler._run_ask({"type": "ask"}, "ron", TASK)
        chat.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatched_from_execute_task(self, scheduler):
        scheduler._run_ask = AsyncMock()
        row = {"id": 7, "user_id": "ron", "name": TASK, "cron_expression": "30 7 * * 1-5",
               "action": {"type": "ask", "prompt": PROMPT}}
        await scheduler._execute_task(row)
        scheduler._run_ask.assert_awaited_once_with({"type": "ask", "prompt": PROMPT}, "ron", TASK)


def test_preview_flattens_and_trims():
    text = "## Needs you\n- Sam: contract by **Friday**\n- Dentist moved\n" + "word " * 200
    p = _preview(text)
    assert p.startswith("Needs you · Sam: contract by Friday · Dentist moved")
    assert len(p) <= sched.NOTIFICATION_PREVIEW_CHARS + 1 and p.endswith("…")


class TestLocalCron:
    @pytest.mark.parametrize("now,expected_utc", [
        (datetime(2026, 10, 7, 5, 0, tzinfo=timezone.utc), datetime(2026, 10, 7, 6, 30, tzinfo=timezone.utc)),   # BST
        (datetime(2026, 12, 1, 5, 0, tzinfo=timezone.utc), datetime(2026, 12, 1, 7, 30, tzinfo=timezone.utc)),   # GMT
        (datetime(2026, 10, 23, 7, 0, tzinfo=timezone.utc), datetime(2026, 10, 26, 7, 30, tzinfo=timezone.utc)),  # over the clock change
    ])
    def test_weekday_730_is_local_time(self, now, expected_utc):
        with patch.object(sched.settings, "local_timezone", "Europe/London"):
            assert next_cron_run("30 7 * * 1-5", now) == expected_utc

    def test_invalid_cron_disables(self):
        assert sched._compute_next_run("not a cron", datetime.now(timezone.utc)) is None


class TestScheduleTaskTool:
    @pytest.mark.asyncio
    async def test_create_ask_task(self):
        from tools.schedule_task import ScheduleTaskTool

        tool = ScheduleTaskTool.__new__(ScheduleTaskTool)
        pool = AsyncMock()
        pool.fetchrow.return_value = {"id": 12}
        tool._get_pool = AsyncMock(return_value=pool)
        with patch.object(sched.settings, "local_timezone", "Europe/London"):
            out = await tool.execute(action="create", user_id="ron", name=TASK, action_type="ask",
                                     cron_expression="30 7 * * 1-5", prompt=PROMPT)
        assert "Created task" in out and "(Europe/London)" in out
        stored = pool.fetchrow.call_args.args[4]
        assert stored == {"type": "ask", "prompt": PROMPT, "notify": "important"}  # a dict, not a JSON string

    @pytest.mark.asyncio
    async def test_ask_needs_a_prompt(self):
        from tools.schedule_task import ScheduleTaskTool

        tool = ScheduleTaskTool.__new__(ScheduleTaskTool)
        tool._get_pool = AsyncMock()
        out = await tool.execute(action="create", user_id="ron", name=TASK, action_type="ask")
        assert "'prompt' is required" in out
