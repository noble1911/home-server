"""Notification sender: browsers (Web Push) and the Android app (#214).

send_push_to_user() applies the user's notification preferences, then sends
encrypted Web Push to subscribed browsers (stale subscriptions, HTTP 404/410,
are removed) and queues/pushes to the user's Android app devices (api/devices.py).

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

from datetime import datetime
from zoneinfo import ZoneInfo

from pywebpush import WebPushException, webpush

from .config import settings

logger = logging.getLogger(__name__)


# Categories the user can switch off in Settings (same list WhatsApp uses).
USER_CATEGORIES = {"download", "reminder", "weather", "smart_home", "calendar", "general"}
# Always delivered, with sound: the user asked for these just now.
ALWAYS_LOUD = {"approval", "test"}


def _in_quiet_hours(start: str | None, end: str | None, now: datetime) -> bool:
    if not start or not end:
        return False
    try:
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
    except (ValueError, AttributeError):
        return False
    cur, s_min, e_min = now.hour * 60 + now.minute, sh * 60 + sm, eh * 60 + em
    if s_min <= e_min:
        return s_min <= cur < e_min
    return cur >= s_min or cur < e_min  # overnight, e.g. 22:00-07:00


def delivery_mode(prefs: dict | None, category: str, now: datetime | None = None) -> str:
    """'send', 'silent' (quiet hours: show without sound) or 'skip'.

    Shared by web push and the Android app so both follow the user's
    Settings > Notifications. Quiet hours are local time (LOCAL_TIMEZONE).
    """
    if category in ALWAYS_LOUD:
        return "send"
    prefs = prefs or {}
    if not prefs.get("enabled", True):
        return "skip"
    if category in USER_CATEGORIES and category not in prefs.get("categories", USER_CATEGORIES):
        return "skip"
    if now is None:
        now = datetime.now(ZoneInfo(settings.local_timezone))
    if _in_quiet_hours(prefs.get("quiet_hours_start"), prefs.get("quiet_hours_end"), now):
        return "silent"
    return "send"


async def _load_prefs(pool: Any, user_id: str) -> dict | None:
    raw = await pool.pool.fetchval("SELECT notification_prefs FROM butler.users WHERE id = $1", user_id)
    return json.loads(raw) if isinstance(raw, str) else raw


async def send_push_to_user(
    pool: Any,
    user_id: str,
    title: str,
    body: str,
    url: str = "/",
    category: str = "general",
) -> int:
    """Notify all of a user's devices: browsers (Web Push) and the Android app.

    Follows the user's notification preferences (see delivery_mode).

    Args:
        pool: DatabasePool instance (has `pool` attribute for asyncpg pool).
        user_id: Target user ID.
        title: Notification title.
        body: Notification body text.
        url: URL to open when notification is clicked.
        category: Notification category tag for grouping.

    Returns:
        Number of devices that will get it.
    """
    from . import devices

    mode = delivery_mode(await _load_prefs(pool, user_id), category)
    if mode == "skip":
        logger.info("Push skipped for %s: '%s' notifications are off", user_id, category)
        return 0
    silent = mode == "silent"

    sent = await _send_web_push(pool, user_id, title, body, url, category, silent)
    try:
        sent += await devices.deliver(pool, user_id, title, body, url, category, silent)
    except Exception:
        logger.exception("App notification delivery failed for %s", user_id)
    return sent


async def _send_web_push(
    pool: Any, user_id: str, title: str, body: str, url: str, category: str, silent: bool,
) -> int:
    if not settings.vapid_private_key:
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
        "silent": silent,
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
        # Server alerts go to admins (as WhatsApp alerts do): they can act on them.
        admins = await pool.pool.fetch("SELECT id FROM butler.users WHERE role = 'admin'")
        friendly = alert_title(severity, title)
        count = 0
        for row in admins:
            count += await send_push_to_user(pool, row["id"], friendly, message, url="/dashboard", category="alert")
        return count > 0

    return channel


def alert_title(severity: str, raw_title: str) -> str:
    """'[CRITICAL] health:jellyfin:down' -> 'Server problem' (the message says what)."""
    key = raw_title.split("] ", 1)[-1]
    area = "Storage" if key.startswith("storage") else "Server"
    level = {"critical": "problem", "warning": "warning"}.get(severity.lower(), "notice")
    return f"{area} {level}"


def create_whatsapp_channel(pool: Any, gateway_url: str):
    """Create a NotificationDispatcher-compatible WhatsApp channel.

    Sends alerts to all admin users via WhatsApp.

    Returns:
        Async callable with signature (severity, title, message) -> bool.
    """
    from tools import WhatsAppTool

    tool = WhatsAppTool(gateway_url=gateway_url, db_pool=pool)

    async def channel(severity: str, title: str, message: str) -> bool:
        db = pool.pool
        admins = await db.fetch(
            "SELECT id FROM butler.users WHERE role = 'admin'"
        )
        sent = False
        for row in admins:
            try:
                await tool.execute(
                    action="send_message",
                    user_id=row["id"],
                    message=f"{title}\n{message}",
                    category="general",
                )
                sent = True
            except Exception:
                logger.exception(
                    "WhatsApp alert failed for user=%s", row["id"]
                )
        return sent

    return channel
