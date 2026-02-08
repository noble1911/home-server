"""Tool usage audit logging.

Records every tool execution for debugging, observability, and cost analysis.
Logging failures are silent — they must never break the user's conversation.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from tools import DatabasePool, Tool

logger = logging.getLogger(__name__)

_MAX_RESULT_LENGTH = 500
_RETENTION_DAYS = 30


async def execute_and_log_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    tools: dict[str, Tool],
    *,
    db_pool: DatabasePool | None = None,
    user_id: str | None = None,
    channel: str | None = None,
) -> str:
    """Execute a tool and log the result to butler.tool_usage.

    Single entry point for all tool execution across batch, streaming,
    and event-streaming LLM modes. Handles timing, error capture,
    result truncation, and audit logging.

    Returns:
        Tool execution result string (or error message).
    """
    if tool_name not in tools:
        result = f"Unknown tool: {tool_name}"
        await _log_usage(
            db_pool, user_id, tool_name, tool_input,
            result_summary=result, error=result, duration_ms=0, channel=channel,
        )
        return result

    # Override user_id in tool input with the authenticated user so the LLM
    # can't accidentally create phantom users by guessing names.
    if user_id and "user_id" in tool_input:
        tool_input = {**tool_input, "user_id": user_id}

    start = time.monotonic()
    error_msg: str | None = None
    try:
        result = await tools[tool_name].execute(**tool_input)
    except Exception as e:
        logger.exception("Tool %s execution failed", tool_name)
        error_msg = f"{type(e).__name__}: {e}"
        result = f"Error executing {tool_name}: {e}"

    duration_ms = int((time.monotonic() - start) * 1000)

    await _log_usage(
        db_pool, user_id, tool_name, tool_input,
        result_summary=result[:_MAX_RESULT_LENGTH],
        error=error_msg,
        duration_ms=duration_ms,
        channel=channel,
    )

    return result


async def _log_usage(
    db_pool: DatabasePool | None,
    user_id: str | None,
    tool_name: str,
    parameters: dict[str, Any],
    *,
    result_summary: str,
    error: str | None,
    duration_ms: int,
    channel: str | None,
) -> None:
    """Insert a record into butler.tool_usage. Silent on failure."""
    if db_pool is None:
        return

    try:
        await db_pool.pool.execute(
            """
            INSERT INTO butler.tool_usage
                (user_id, tool_name, parameters, result_summary, error, duration_ms, channel)
            VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7)
            """,
            user_id,
            tool_name,
            parameters,
            result_summary,
            error,
            duration_ms,
            channel,
        )
    except Exception:
        logger.exception("Failed to log tool usage for %s", tool_name)


async def cleanup_tool_usage_logs(
    db_pool: DatabasePool,
    retention_days: int = _RETENTION_DAYS,
) -> int:
    """Delete tool usage records older than retention_days.

    Returns the number of deleted rows.
    Ready to be called by the background job system (Issue #75).
    """
    result = await db_pool.pool.execute(
        "DELETE FROM butler.tool_usage WHERE created_at < NOW() - INTERVAL '1 day' * $1",
        retention_days,
    )
    count = int(result.split()[-1])
    if count > 0:
        logger.info("Cleaned up %d tool usage logs older than %d days", count, retention_days)
    return count
