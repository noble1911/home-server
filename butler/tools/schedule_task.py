"""Scheduled task tool for Butler.

Lets the LLM create, list, and delete cron-based tasks stored in
butler.scheduled_tasks. The background TaskScheduler (api/scheduler.py)
picks these up and executes them.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .memory import DatabaseTool


class ScheduleTaskTool(DatabaseTool):
    """Create, list, or delete scheduled tasks."""

    @property
    def name(self) -> str:
        return "schedule_task"

    @property
    def description(self) -> str:
        return (
            "Manage scheduled tasks: reminders, health checks, and 'ask' tasks where Butler "
            "itself runs on a schedule with the user's email, calendar, weather and memory, "
            "then reports back (e.g. 'every weekday at 7:30 check my email and calendar and "
            "tell me if anything needs attention'). Actions: 'create', 'list', 'delete'. "
            "Cron times are local time (e.g. '30 7 * * 1-5' = weekdays 7:30am); omit "
            "cron_expression for a one-off run."
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
                    "enum": ["reminder", "ask", "automation", "check"],
                    "description": (
                        "Task type (required for 'create'). "
                        "reminder: send a fixed notification (push by default). "
                        "ask: Butler runs `prompt` with the user's email, calendar, weather and "
                        "memory, then sends what it finds (use for briefings, digests, "
                        "'tell me if anything important…'). "
                        "automation: execute one tool with fixed params. "
                        "check: run a health check tool and notify on threshold."
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": (
                        "For 'ask': what Butler should do each run, in the user's words, "
                        "including when to tell them, e.g. 'Check my email from the last day "
                        "and today's calendar; tell me if anything is important or needs a "
                        "reply.' Butler notifies only when that condition is met (every run "
                        "if the prompt sets none)."
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
                "channel": {
                    "type": "string",
                    "enum": ["push", "whatsapp", "both"],
                    "description": (
                        "Notification channel (for reminder/check/ask). "
                        "'push' (default): browser push notification, "
                        "falls back to WhatsApp if no subscriptions. "
                        "'whatsapp': WhatsApp only. "
                        "'both': send via both channels."
                    ),
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
            return "Error: 'action_type' is required (reminder, ask, automation, or check)."

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
        elif action_type == "ask":
            prompt = (kwargs.get("prompt") or "").strip()
            if not prompt:
                return "Error: 'prompt' is required for ask type (what Butler should do each run)."
            task_action["prompt"] = prompt

        # Add notification channel
        if action_type in ("reminder", "check", "ask"):
            channel = kwargs.get("channel")
            if channel:
                task_action["channel"] = channel

        # Compute next_run (cron is local time)
        from api.scheduler import next_cron_run

        now = datetime.now(timezone.utc)
        if cron_expr:
            try:
                next_run = next_cron_run(cron_expr, now)
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
            task_action,  # the pool's JSONB codec encodes it (json.dumps would double-encode)
            next_run,
        )

        task_id = row["id"]
        schedule = f"cron '{cron_expr}'" if cron_expr else "one-time"
        return f"Created task '{name}' (ID: {task_id}, {schedule}, next run: {_local(next_run)})"

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
            next_run = _local(r["next_run"]) if r["next_run"] else "none"
            channel = action.get("channel", "push")
            detail = f": \"{action['prompt'][:80]}\"" if action.get("type") == "ask" else ""
            lines.append(
                f"- [{r['id']}] {r['name']} ({action.get('type')}, {schedule}, {status}, "
                f"via {channel}, next: {next_run}){detail}"
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


def _local(when: datetime) -> str:
    """A UTC timestamp as household local time, for the model to repeat to the user."""
    from api.config import settings

    tz = settings.local_timezone
    return f"{when.astimezone(ZoneInfo(tz)):%a %d %b %H:%M} ({tz})"
