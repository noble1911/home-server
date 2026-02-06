"""Scheduled tasks CRUD routes.

POST   /api/tasks          — create a task
GET    /api/tasks          — list user's tasks
DELETE /api/tasks/{task_id} — delete a task
PATCH  /api/tasks/{task_id} — update a task (name, cron, action, enabled)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, Response

from tools import DatabasePool

from ..deps import get_current_user, get_db_pool
from ..models import (
    CreateTaskRequest,
    ScheduledTaskResponse,
    TaskAction,
    UpdateTaskRequest,
)

router = APIRouter()


def _row_to_response(row) -> ScheduledTaskResponse:
    """Convert an asyncpg Row to a ScheduledTaskResponse."""
    action = json.loads(row["action"]) if isinstance(row["action"], str) else row["action"]
    return ScheduledTaskResponse(
        id=row["id"],
        userId=row["user_id"],
        name=row["name"],
        cronExpression=row["cron_expression"],
        action=TaskAction(**action),
        enabled=row["enabled"],
        lastRun=row["last_run"].isoformat() if row["last_run"] else None,
        nextRun=row["next_run"].isoformat() if row["next_run"] else None,
        createdAt=row["created_at"].isoformat(),
    )


@router.post("/tasks", response_model=ScheduledTaskResponse, status_code=201)
async def create_task(
    req: CreateTaskRequest,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Create a new scheduled task."""
    now = datetime.now(timezone.utc)
    next_run = now  # Default for one-time tasks

    if req.cronExpression:
        try:
            next_run = croniter(req.cronExpression, now).get_next(datetime)
        except (ValueError, KeyError) as e:
            raise HTTPException(400, f"Invalid cron expression: {e}")

    row = await pool.pool.fetchrow(
        """
        INSERT INTO butler.scheduled_tasks
            (user_id, name, cron_expression, action, enabled, next_run)
        VALUES ($1, $2, $3, $4::jsonb, $5, $6)
        RETURNING *
        """,
        user_id,
        req.name,
        req.cronExpression,
        json.dumps(req.action.model_dump(exclude_none=True)),
        req.enabled,
        next_run,
    )

    return _row_to_response(row)


@router.get("/tasks", response_model=list[ScheduledTaskResponse])
async def list_tasks(
    enabled: bool | None = None,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """List all scheduled tasks for the authenticated user."""
    if enabled is not None:
        rows = await pool.pool.fetch(
            """
            SELECT * FROM butler.scheduled_tasks
            WHERE user_id = $1 AND enabled = $2
            ORDER BY created_at DESC
            """,
            user_id,
            enabled,
        )
    else:
        rows = await pool.pool.fetch(
            """
            SELECT * FROM butler.scheduled_tasks
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user_id,
        )

    return [_row_to_response(r) for r in rows]


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: int,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Delete a scheduled task."""
    result = await pool.pool.execute(
        "DELETE FROM butler.scheduled_tasks WHERE id = $1 AND user_id = $2",
        task_id,
        user_id,
    )

    if result == "DELETE 0":
        raise HTTPException(404, "Task not found")

    return Response(status_code=204)


@router.patch("/tasks/{task_id}", response_model=ScheduledTaskResponse)
async def update_task(
    task_id: int,
    req: UpdateTaskRequest,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Update a scheduled task (any combination of fields)."""
    # Verify ownership
    existing = await pool.pool.fetchrow(
        "SELECT * FROM butler.scheduled_tasks WHERE id = $1 AND user_id = $2",
        task_id,
        user_id,
    )
    if not existing:
        raise HTTPException(404, "Task not found")

    # Build SET clauses dynamically from provided fields
    updates: list[str] = []
    values: list = [task_id]
    idx = 2

    if req.name is not None:
        updates.append(f"name = ${idx}")
        values.append(req.name)
        idx += 1

    if req.enabled is not None:
        updates.append(f"enabled = ${idx}")
        values.append(req.enabled)
        idx += 1

    if req.action is not None:
        updates.append(f"action = ${idx}::jsonb")
        values.append(json.dumps(req.action.model_dump(exclude_none=True)))
        idx += 1

    if req.cronExpression is not None:
        # Validate and recompute next_run
        now = datetime.now(timezone.utc)
        try:
            next_run = croniter(req.cronExpression, now).get_next(datetime)
        except (ValueError, KeyError) as e:
            raise HTTPException(400, f"Invalid cron expression: {e}")

        updates.append(f"cron_expression = ${idx}")
        values.append(req.cronExpression)
        idx += 1
        updates.append(f"next_run = ${idx}")
        values.append(next_run)
        idx += 1

    if not updates:
        raise HTTPException(400, "No fields to update")

    row = await pool.pool.fetchrow(
        f"UPDATE butler.scheduled_tasks SET {', '.join(updates)} WHERE id = $1 RETURNING *",
        *values,
    )

    return _row_to_response(row)
