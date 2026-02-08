"""Background task scheduler for cron automations.

Polls butler.scheduled_tasks every 60 seconds for due tasks and executes
them based on their action type (reminder, automation, check).

Started/stopped via the FastAPI lifespan in deps.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from croniter import croniter

from tools import DatabasePool, Tool

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60


class TaskScheduler:
    """Background scheduler that executes cron-based tasks from the database."""

    def __init__(
        self,
        db_pool: DatabasePool,
        tools: dict[str, Tool],
    ):
        self._db_pool = db_pool
        self._tools = tools
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        """Start the background polling loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("TaskScheduler started (poll every %ds)", POLL_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """Stop the background task gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("TaskScheduler stopped")

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Main loop — poll DB every POLL_INTERVAL_SECONDS."""
        while self._running:
            try:
                await self._poll_and_execute()
            except Exception:
                logger.exception("TaskScheduler poll error")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _poll_and_execute(self) -> None:
        """Find due tasks and execute them sequentially."""
        pool = self._db_pool.pool
        rows = await pool.fetch(
            """
            SELECT id, user_id, name, cron_expression, action
            FROM butler.scheduled_tasks
            WHERE enabled = TRUE AND next_run <= NOW()
            ORDER BY next_run ASC
            """,
        )
        if not rows:
            return

        logger.info("Found %d due task(s)", len(rows))
        for row in rows:
            await self._execute_task(row)

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    async def _execute_task(self, row: Any) -> None:
        """Execute a single task and update its timestamps."""
        task_id: int = row["id"]
        user_id: str = row["user_id"]
        name: str = row["name"]
        cron_expr: str | None = row["cron_expression"]
        action: dict = json.loads(row["action"]) if isinstance(row["action"], str) else row["action"]

        logger.info("Executing task %d '%s' for user %s", task_id, name, user_id)

        try:
            action_type = action.get("type")
            if action_type == "reminder":
                await self._send_reminder(action, user_id)
            elif action_type == "automation":
                await self._run_automation(action)
            elif action_type == "check":
                await self._run_check(action, user_id)
            else:
                logger.warning("Task %d has unknown action type: %s", task_id, action_type)
        except Exception:
            logger.exception("Task %d '%s' execution failed", task_id, name)

        # Always update timestamps so we don't re-execute on failure
        now = datetime.now(timezone.utc)
        next_run = _compute_next_run(cron_expr, now)

        await self._db_pool.pool.execute(
            """
            UPDATE butler.scheduled_tasks
            SET last_run = $2, next_run = $3
            WHERE id = $1
            """,
            task_id,
            now,
            next_run,
        )

    async def _send_reminder(self, action: dict, user_id: str) -> None:
        """Send a WhatsApp reminder message."""
        whatsapp = self._tools.get("whatsapp")
        if not whatsapp:
            logger.warning("WhatsApp tool not configured — skipping reminder")
            return

        await whatsapp.execute(
            action="send_message",
            user_id=user_id,
            message=action.get("message", "Reminder"),
            category=action.get("category", "general"),
        )

    async def _run_automation(self, action: dict) -> None:
        """Execute a tool with the given parameters."""
        tool_name = action.get("tool")
        if not tool_name or tool_name not in self._tools:
            logger.error("Automation tool not found: %s", tool_name)
            return

        params = action.get("params", {})
        result = await self._tools[tool_name].execute(**params)
        logger.info("Automation '%s' result: %s", tool_name, result[:200])

    async def _run_check(self, action: dict, user_id: str) -> None:
        """Run a health check tool and notify if threshold breached."""
        tool_name = action.get("tool")
        if not tool_name or tool_name not in self._tools:
            logger.error("Check tool not found: %s", tool_name)
            return

        params = action.get("params", {})
        result = await self._tools[tool_name].execute(**params)

        notify_on = action.get("notifyOn", "warning")
        result_lower = result.lower()
        should_notify = (
            notify_on == "always"
            or (notify_on == "warning" and ("warning" in result_lower or "critical" in result_lower))
            or (notify_on == "critical" and "critical" in result_lower)
        )

        if should_notify:
            whatsapp = self._tools.get("whatsapp")
            if whatsapp:
                await whatsapp.execute(
                    action="send_message",
                    user_id=user_id,
                    message=f"Health check alert: {result[:500]}",
                    category="general",
                )
            else:
                logger.warning("Check triggered notification but WhatsApp not configured")


def _compute_next_run(cron_expression: str | None, after: datetime) -> datetime | None:
    """Compute the next run time from a cron expression.

    Returns None for one-time tasks (no cron) or invalid expressions,
    which effectively disables the task.
    """
    if not cron_expression:
        return None

    try:
        return croniter(cron_expression, after).get_next(datetime)
    except (ValueError, KeyError) as e:
        logger.error("Invalid cron expression '%s': %s", cron_expression, e)
        return None
