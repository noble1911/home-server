"""Web Push notification sender.

Sends encrypted push notifications to subscribed browsers via the Web Push
protocol.  Stale subscriptions (HTTP 404/410) are automatically removed.

Usage:
    from api.push import send_push_to_user

    count = await send_push_to_user(
        pool=db_pool,
        user_id="ron",
        title="Download complete",
        body="Dune audiobook is ready in your library",
    )
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pywebpush import WebPushException, webpush

from .config import settings

logger = logging.getLogger(__name__)


async def send_push_to_user(
    pool: Any,
    user_id: str,
    title: str,
    body: str,
    url: str = "/",
    category: str = "general",
) -> int:
    """Send a push notification to all of a user's subscribed devices.

    Args:
        pool: DatabasePool instance (has `pool` attribute for asyncpg pool).
        user_id: Target user ID.
        title: Notification title.
        body: Notification body text.
        url: URL to open when notification is clicked.
        category: Notification category tag for grouping.

    Returns:
        Number of devices successfully notified.
    """
    if not settings.vapid_private_key:
        logger.warning("Push notification skipped: VAPID keys not configured")
        return 0

    db = pool.pool
    rows = await db.fetch(
        "SELECT id, endpoint, key_p256dh, key_auth "
        "FROM butler.push_subscriptions WHERE user_id = $1",
        user_id,
    )

    if not rows:
        return 0

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "category": category,
    })

    sent = 0
    stale_ids: list[int] = []

    for row in rows:
        subscription_info = {
            "endpoint": row["endpoint"],
            "keys": {
                "p256dh": row["key_p256dh"],
                "auth": row["key_auth"],
            },
        }
        try:
            await asyncio.to_thread(
                webpush,
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
            )
            sent += 1
            # Update last_used_at
            await db.execute(
                "UPDATE butler.push_subscriptions SET last_used_at = NOW() WHERE id = $1",
                row["id"],
            )
        except WebPushException as e:
            status = getattr(e, "response", None)
            status_code = getattr(status, "status_code", 0) if status else 0
            if status_code in (404, 410):
                # Subscription expired or unsubscribed — mark for removal
                stale_ids.append(row["id"])
                logger.info("Removing stale push subscription %d (HTTP %d)", row["id"], status_code)
            else:
                logger.warning("Push failed for subscription %d: %s", row["id"], e)
        except Exception:
            logger.exception("Unexpected error sending push to subscription %d", row["id"])

    # Clean up stale subscriptions
    if stale_ids:
        try:
            await db.execute(
                "DELETE FROM butler.push_subscriptions WHERE id = ANY($1::int[])",
                stale_ids,
            )
        except Exception:
            logger.exception("Failed to cleanup %d stale push subscriptions", len(stale_ids))

    return sent


async def send_push_broadcast(
    pool: Any,
    title: str,
    body: str,
    url: str = "/",
    category: str = "general",
) -> int:
    """Send a push notification to ALL subscribed users/devices.

    Useful for system-wide announcements.

    Returns:
        Total number of devices successfully notified.
    """
    db = pool.pool
    rows = await db.fetch(
        "SELECT DISTINCT user_id FROM butler.push_subscriptions"
    )

    total = 0
    for row in rows:
        total += await send_push_to_user(pool, row["user_id"], title, body, url, category)
    return total


def create_push_channel(pool: Any):
    """Create a NotificationDispatcher-compatible push channel.

    Returns:
        Async callable with signature (severity, title, message) -> bool.
    """

    async def channel(severity: str, title: str, message: str) -> bool:
        count = await send_push_broadcast(pool, title, message, url="/", category="alert")
        return count > 0

    return channel
