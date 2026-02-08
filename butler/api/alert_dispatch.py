"""Background alert dispatch loop.

Polls for unsent alerts every 60 seconds and dispatches them through
registered notification channels (Web Push, WhatsApp).

Started/stopped via the FastAPI lifespan in deps.py.
"""

from __future__ import annotations

import asyncio
import logging

from tools.alerting import NotificationDispatcher

logger = logging.getLogger(__name__)

_INTERVAL_SECONDS = 60
_dispatch_task: asyncio.Task | None = None


async def _dispatch_loop(dispatcher: NotificationDispatcher) -> None:
    """Infinite loop that dispatches pending alerts."""
    while True:
        try:
            sent = await dispatcher.dispatch_pending()
            if sent:
                logger.info("Dispatched %d alert(s)", sent)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Alert dispatch error")
        await asyncio.sleep(_INTERVAL_SECONDS)


def start_alert_dispatch(dispatcher: NotificationDispatcher) -> None:
    """Spawn the background alert dispatch task."""
    global _dispatch_task
    _dispatch_task = asyncio.create_task(
        _dispatch_loop(dispatcher),
        name="butler-alert-dispatch",
    )
    logger.info("Alert dispatch started (interval=%ds)", _INTERVAL_SECONDS)


async def stop_alert_dispatch() -> None:
    """Cancel the background alert dispatch task if running."""
    global _dispatch_task
    if _dispatch_task is not None:
        _dispatch_task.cancel()
        try:
            await _dispatch_task
        except asyncio.CancelledError:
            pass
        _dispatch_task = None
        logger.info("Alert dispatch stopped")
