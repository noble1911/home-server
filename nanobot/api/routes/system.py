"""System observability routes.

GET /api/admin/tool-usage — Recent tool calls with optional filters (admin only)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from tools import DatabasePool

from ..deps import get_admin_user, get_db_pool
from ..models import ToolUsageEntry, ToolUsageResponse, ToolUsageSummary

router = APIRouter()


@router.get("/tool-usage", response_model=ToolUsageResponse)
async def get_tool_usage(
    admin_id: str = Depends(get_admin_user),
    pool: DatabasePool = Depends(get_db_pool),
    tool_name: str | None = Query(None, description="Filter by tool name"),
    user_id: str | None = Query(None, description="Filter by user"),
    errors_only: bool = Query(False, description="Show only failed calls"),
    limit: int = Query(50, ge=1, le=500),
):
    """Return recent tool usage logs with optional filters. Admin only."""
    db = pool.pool

    # Build query dynamically based on filters
    conditions: list[str] = []
    params: list = []
    idx = 1

    if tool_name:
        conditions.append(f"tool_name = ${idx}")
        params.append(tool_name)
        idx += 1

    if user_id:
        conditions.append(f"user_id = ${idx}")
        params.append(user_id)
        idx += 1

    if errors_only:
        conditions.append("error IS NOT NULL")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    params.append(limit)

    rows = await db.fetch(
        f"""
        SELECT id, user_id, tool_name, parameters, result_summary,
               error, duration_ms, channel, created_at
        FROM butler.tool_usage
        {where}
        ORDER BY created_at DESC
        LIMIT ${idx}
        """,
        *params,
    )

    entries = [
        ToolUsageEntry(
            id=row["id"],
            userId=row["user_id"],
            toolName=row["tool_name"],
            parameters=row["parameters"] or {},
            resultSummary=row["result_summary"],
            error=row["error"],
            durationMs=row["duration_ms"],
            channel=row["channel"],
            createdAt=row["created_at"].isoformat(),
        )
        for row in rows
    ]

    # Summary stats for the last 24 hours
    summary_row = await db.fetchrow(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE error IS NOT NULL) AS errors,
            COALESCE(ROUND(AVG(duration_ms)), 0) AS avg_duration_ms
        FROM butler.tool_usage
        WHERE created_at > NOW() - INTERVAL '24 hours'
        """
    )

    summary = ToolUsageSummary(
        totalCalls24h=summary_row["total"],
        errorCount24h=summary_row["errors"],
        avgDurationMs=int(summary_row["avg_duration_ms"]),
    )

    return ToolUsageResponse(entries=entries, summary=summary)
