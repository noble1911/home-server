"""Background cleanup jobs for conversation history and expired facts.

Runs as an asyncio task during the server lifespan. Executes daily
without blocking API requests.
"""

from __future__ import annotations

import asyncio
import logging

from tools import DatabasePool

logger = logging.getLogger(__name__)

_INTERVAL_SECONDS = 24 * 60 * 60  # 24 hours
_cleanup_task: asyncio.Task | None = None


async def delete_old_conversations(pool: DatabasePool, retention_days: int) -> int:
    """Delete conversation history older than *retention_days*. Returns row count."""
    result = await pool.pool.execute(
        """
        DELETE FROM butler.conversation_history
        WHERE created_at < NOW() - ($1 || ' days')::INTERVAL
        """,
        str(retention_days),
    )
    # asyncpg returns e.g. "DELETE 42"
    return int(result.split()[-1])


async def delete_expired_facts(pool: DatabasePool) -> int:
    """Delete user facts whose expires_at has passed. Returns row count."""
    result = await pool.pool.execute(
        """
        DELETE FROM butler.user_facts
        WHERE expires_at IS NOT NULL AND expires_at < NOW()
        """,
    )
    return int(result.split()[-1])


async def _run_cleanup(pool: DatabasePool, retention_days: int) -> None:
    """Execute both cleanup operations and log results."""
    conversations = await delete_old_conversations(pool, retention_days)
    facts = await delete_expired_facts(pool)
    logger.info(
        "Cleanup complete: %d old conversations, %d expired facts removed",
        conversations,
        facts,
    )


async def _cleanup_loop(pool: DatabasePool, retention_days: int) -> None:
    """Infinite loop that runs cleanup daily."""
    while True:
        try:
            await _run_cleanup(pool, retention_days)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Cleanup job failed")
        await asyncio.sleep(_INTERVAL_SECONDS)


def start_cleanup(pool: DatabasePool, retention_days: int) -> None:
    """Spawn the background cleanup task."""
    global _cleanup_task
    _cleanup_task = asyncio.create_task(
        _cleanup_loop(pool, retention_days),
        name="butler-cleanup",
    )
    logger.info(
        "Cleanup job started (retention=%d days, interval=24h)", retention_days
    )


async def stop_cleanup() -> None:
    """Cancel the background cleanup task if running."""
    global _cleanup_task
    if _cleanup_task is not None:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
        _cleanup_task = None
        logger.info("Cleanup job stopped")
