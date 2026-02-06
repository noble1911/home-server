"""Tests for ScheduleTaskTool and TaskScheduler.

Run with: pytest nanobot/tools/test_schedule_task.py -v

These tests use mocked database calls - no real PostgreSQL required.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .schedule_task import ScheduleTaskTool


@pytest.fixture
def mock_pool():
    """Create a mock DatabasePool."""
    pool = MagicMock()
    pool.pool = AsyncMock()
    return pool


@pytest.fixture
def tool(mock_pool):
    """Create a ScheduleTaskTool with a mocked pool."""
    return ScheduleTaskTool(db_pool=mock_pool)


class TestScheduleTaskTool:
    """Tests for ScheduleTaskTool."""

    def test_tool_properties(self, tool):
        """Verify tool has required properties."""
        assert tool.name == "schedule_task"
        assert "scheduled" in tool.description.lower() or "reminder" in tool.description.lower()
        assert "action" in tool.parameters["properties"]
        assert "user_id" in tool.parameters["properties"]
        assert tool.parameters["required"] == ["action", "user_id"]

    def test_to_schema(self, tool):
        """Verify OpenAI function schema format."""
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "schedule_task"
        assert "parameters" in schema["function"]

    @pytest.mark.asyncio
    async def test_create_reminder(self, tool, mock_pool):
        """Create a recurring reminder task."""
        mock_pool.pool.fetchrow = AsyncMock(return_value={"id": 1})

        result = await tool.execute(
            action="create",
            user_id="ron",
            name="Daily vitamins",
            cron_expression="0 9 * * *",
            action_type="reminder",
            message="Take your vitamins!",
            category="health",
        )

        assert "Created task" in result
        assert "Daily vitamins" in result
        assert "ID: 1" in result
        assert "cron '0 9 * * *'" in result

        # Verify DB insert was called
        call_args = mock_pool.pool.fetchrow.call_args
        assert call_args[0][1] == "ron"  # user_id
        assert call_args[0][2] == "Daily vitamins"  # name
        assert call_args[0][3] == "0 9 * * *"  # cron
        action_json = json.loads(call_args[0][4])
        assert action_json["type"] == "reminder"
        assert action_json["message"] == "Take your vitamins!"

    @pytest.mark.asyncio
    async def test_create_one_time(self, tool, mock_pool):
        """Create a one-time task (no cron)."""
        mock_pool.pool.fetchrow = AsyncMock(return_value={"id": 2})

        result = await tool.execute(
            action="create",
            user_id="ron",
            name="Set thermostat",
            action_type="automation",
            tool="home_assistant",
            params={"action": "call_service", "domain": "climate"},
        )

        assert "Created task" in result
        assert "one-time" in result

    @pytest.mark.asyncio
    async def test_create_check(self, tool, mock_pool):
        """Create a health check task."""
        mock_pool.pool.fetchrow = AsyncMock(return_value={"id": 3})

        result = await tool.execute(
            action="create",
            user_id="ron",
            name="Storage check",
            cron_expression="0 */6 * * *",
            action_type="check",
            tool="storage_monitor",
            notify_on="warning",
        )

        assert "Created task" in result
        call_args = mock_pool.pool.fetchrow.call_args
        action_json = json.loads(call_args[0][4])
        assert action_json["type"] == "check"
        assert action_json["notifyOn"] == "warning"

    @pytest.mark.asyncio
    async def test_create_missing_name(self, tool):
        """Error when name is missing."""
        result = await tool.execute(
            action="create",
            user_id="ron",
            action_type="reminder",
        )
        assert "Error" in result
        assert "name" in result.lower()

    @pytest.mark.asyncio
    async def test_create_missing_action_type(self, tool):
        """Error when action_type is missing."""
        result = await tool.execute(
            action="create",
            user_id="ron",
            name="Test",
        )
        assert "Error" in result
        assert "action_type" in result.lower()

    @pytest.mark.asyncio
    async def test_create_automation_missing_tool(self, tool):
        """Error when automation type has no tool."""
        result = await tool.execute(
            action="create",
            user_id="ron",
            name="Test",
            action_type="automation",
        )
        assert "Error" in result
        assert "tool" in result.lower()

    @pytest.mark.asyncio
    async def test_create_invalid_cron(self, tool):
        """Error on invalid cron expression."""
        result = await tool.execute(
            action="create",
            user_id="ron",
            name="Bad cron",
            cron_expression="not a cron",
            action_type="reminder",
            message="test",
        )
        assert "Error" in result
        assert "cron" in result.lower()

    @pytest.mark.asyncio
    async def test_list_tasks(self, tool, mock_pool):
        """List user's tasks."""
        mock_pool.pool.fetch = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "name": "Daily vitamins",
                    "cron_expression": "0 9 * * *",
                    "action": {"type": "reminder"},
                    "enabled": True,
                    "last_run": None,
                    "next_run": datetime(2025, 2, 10, 9, 0, tzinfo=timezone.utc),
                },
                {
                    "id": 2,
                    "name": "Storage check",
                    "cron_expression": None,
                    "action": json.dumps({"type": "check"}),
                    "enabled": False,
                    "last_run": datetime(2025, 2, 9, 12, 0, tzinfo=timezone.utc),
                    "next_run": None,
                },
            ]
        )

        result = await tool.execute(action="list", user_id="ron")

        assert "2" in result  # count
        assert "Daily vitamins" in result
        assert "Storage check" in result
        assert "enabled" in result
        assert "disabled" in result

    @pytest.mark.asyncio
    async def test_list_empty(self, tool, mock_pool):
        """List with no tasks."""
        mock_pool.pool.fetch = AsyncMock(return_value=[])

        result = await tool.execute(action="list", user_id="ron")

        assert "No scheduled tasks" in result

    @pytest.mark.asyncio
    async def test_delete_task(self, tool, mock_pool):
        """Delete a task by ID."""
        mock_pool.pool.execute = AsyncMock(return_value="DELETE 1")

        result = await tool.execute(action="delete", user_id="ron", task_id=1)

        assert "Deleted task 1" in result

    @pytest.mark.asyncio
    async def test_delete_not_found(self, tool, mock_pool):
        """Delete a task that doesn't exist."""
        mock_pool.pool.execute = AsyncMock(return_value="DELETE 0")

        result = await tool.execute(action="delete", user_id="ron", task_id=999)

        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_delete_missing_id(self, tool):
        """Error when task_id is missing for delete."""
        result = await tool.execute(action="delete", user_id="ron")

        assert "Error" in result
        assert "task_id" in result.lower()


class TestComputeNextRun:
    """Tests for cron next_run computation."""

    def test_daily_cron(self):
        """Verify daily cron computes correct next_run."""
        from api.scheduler import _compute_next_run

        base = datetime(2025, 2, 10, 10, 0, tzinfo=timezone.utc)
        next_run = _compute_next_run("0 9 * * *", base)

        # Next 9am after Feb 10 10:00 is Feb 11 9:00
        assert next_run is not None
        assert next_run.hour == 9
        assert next_run.day == 11

    def test_one_time_returns_none(self):
        """One-time tasks return None."""
        from api.scheduler import _compute_next_run

        base = datetime(2025, 2, 10, 10, 0, tzinfo=timezone.utc)
        assert _compute_next_run(None, base) is None

    def test_invalid_cron_returns_none(self):
        """Invalid cron returns None (disables task)."""
        from api.scheduler import _compute_next_run

        base = datetime(2025, 2, 10, 10, 0, tzinfo=timezone.utc)
        assert _compute_next_run("invalid cron", base) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
