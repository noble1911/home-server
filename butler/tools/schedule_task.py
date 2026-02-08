"""Scheduled task tool for Butler.

Lets the LLM create, list, and delete cron-based tasks stored in
butler.scheduled_tasks. The background TaskScheduler (api/scheduler.py)
picks these up and executes them.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from croniter import croniter

from .memory import DatabaseTool


class ScheduleTaskTool(DatabaseTool):
    """Create, list, or delete scheduled tasks."""

    @property
    def name(self) -> str:
        return "schedule_task"

    @property
    def description(self) -> str:
        return (
            "Manage scheduled tasks for reminders, automations, or health checks. "
            "Actions: 'create' a new task, 'list' existing tasks, or 'delete' one. "
            "Supports cron expressions for recurring tasks (e.g., '0 9 * * *' = daily at 9am) "
            "or one-time execution when cron_expression is omitted."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "delete"],
                    "description": "Action to perform.",
                },
                "user_id": {
                    "type": "string",
                    "description": "User ID (required for all actions).",
                },
                "name": {
                    "type": "string",
                    "description": "Task name (required for 'create').",
                },
                "cron_expression": {
                    "type": "string",
                    "description": (
                        "Cron schedule for recurring tasks. Examples: "
                        "'0 9 * * *' (daily 9am), '0 */6 * * *' (every 6h), "
                        "'30 8 * * 1-5' (weekdays 8:30am). Omit for one-time."
                    ),
                },
                "action_type": {
                    "type": "string",
                    "enum": ["reminder", "automation", "check"],
                    "description": (
                        "Task type (required for 'create'). "
                        "reminder: send WhatsApp message. "
                        "automation: execute a tool. "
                        "check: run health check and notify on threshold."
                    ),
                },
                "message": {
                    "type": "string",
                    "description": "Message text (for reminder type).",
                },
                "tool": {
                    "type": "string",
                    "description": "Tool name to execute (for automation/check type).",
                },
                "params": {
                    "type": "object",
                    "description": "Parameters to pass to the tool (for automation/check).",
                },
                "category": {
                    "type": "string",
                    "description": "Notification category for reminders.",
                },
                "notify_on": {
                    "type": "string",
                    "enum": ["warning", "critical", "always"],
                    "description": "When to notify for check type (default: warning).",
                },
                "task_id": {
                    "type": "integer",
                    "description": "Task ID (required for 'delete').",
                },
            },
            "required": ["action", "user_id"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]
        user_id = kwargs["user_id"]

        if action == "create":
            return await self._create(user_id, kwargs)
        elif action == "list":
            return await self._list(user_id)
        elif action == "delete":
            return await self._delete(user_id, kwargs.get("task_id"))
        else:
            return f"Unknown action: {action}"

    async def _create(self, user_id: str, kwargs: dict) -> str:
        name = kwargs.get("name")
        if not name:
            return "Error: 'name' is required to create a task."

        action_type = kwargs.get("action_type")
        if not action_type:
            return "Error: 'action_type' is required (reminder, automation, or check)."

        cron_expr = kwargs.get("cron_expression")

        # Build the action JSONB payload
        task_action: dict[str, Any] = {"type": action_type}
        if action_type == "reminder":
            task_action["message"] = kwargs.get("message", "Reminder")
            task_action["category"] = kwargs.get("category", "general")
        elif action_type == "automation":
            if not kwargs.get("tool"):
                return "Error: 'tool' is required for automation type."
            task_action["tool"] = kwargs["tool"]
            task_action["params"] = kwargs.get("params", {})
        elif action_type == "check":
            if not kwargs.get("tool"):
                return "Error: 'tool' is required for check type."
            task_action["tool"] = kwargs["tool"]
            task_action["params"] = kwargs.get("params", {})
            task_action["notifyOn"] = kwargs.get("notify_on", "warning")

        # Compute next_run
        now = datetime.now(timezone.utc)
        if cron_expr:
            try:
                next_run = croniter(cron_expr, now).get_next(datetime)
            except (ValueError, KeyError) as e:
                return f"Error: Invalid cron expression '{cron_expr}': {e}"
        else:
            next_run = now  # One-time: execute on next poll

        pool = await self._get_pool()
        row = await pool.fetchrow(
            """
            INSERT INTO butler.scheduled_tasks
                (user_id, name, cron_expression, action, next_run)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            RETURNING id
            """,
            user_id,
            name,
            cron_expr,
            json.dumps(task_action),
            next_run,
        )

        task_id = row["id"]
        schedule = f"cron '{cron_expr}'" if cron_expr else "one-time"
        return f"Created task '{name}' (ID: {task_id}, {schedule}, next run: {next_run:%Y-%m-%d %H:%M UTC})"

    async def _list(self, user_id: str) -> str:
        pool = await self._get_pool()
        rows = await pool.fetch(
            """
            SELECT id, name, cron_expression, action, enabled, last_run, next_run
            FROM butler.scheduled_tasks
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user_id,
        )

        if not rows:
            return "No scheduled tasks found."

        lines = []
        for r in rows:
            status = "enabled" if r["enabled"] else "disabled"
            action = json.loads(r["action"]) if isinstance(r["action"], str) else r["action"]
            schedule = r["cron_expression"] or "one-time"
            next_run = r["next_run"].strftime("%Y-%m-%d %H:%M UTC") if r["next_run"] else "none"
            lines.append(
                f"- [{r['id']}] {r['name']} ({action.get('type')}, {schedule}, {status}, next: {next_run})"
            )

        return f"Scheduled tasks ({len(rows)}):\n" + "\n".join(lines)

    async def _delete(self, user_id: str, task_id: int | None) -> str:
        if task_id is None:
            return "Error: 'task_id' is required to delete a task."

        pool = await self._get_pool()
        result = await pool.execute(
            "DELETE FROM butler.scheduled_tasks WHERE id = $1 AND user_id = $2",
            task_id,
            user_id,
        )

        if result == "DELETE 0":
            return f"Task {task_id} not found or doesn't belong to you."
        return f"Deleted task {task_id}."
