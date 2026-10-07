"""Native app notification delivery, without Firebase (#214).

The Butler Android app holds a WebSocket to /api/notifications/ws (from a
foreground service), authenticated with a per-device credential. Butler
pushes notifications down it as they happen. Every notification is also
written to butler.notifications, so a phone that was offline (tunnel down,
Doze, no signal) gets what it missed when it reconnects with ``since``.

butler-api runs as a single uvicorn process, so an in-memory registry of
open sockets is enough.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Any

logger = logging.getLogger(__name__)

# A device that hasn't connected for this long no longer counts as "will get
# it" (so scheduler fallbacks such as WhatsApp still kick in).
ACTIVE_DEVICE_DAYS = 7
BACKLOG_DAYS = 7
BACKLOG_LIMIT = 100


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class NotificationHub:
    """Open notification sockets, by user."""

    def __init__(self) -> None:
        self._sockets: dict[str, set[Any]] = {}

    def add(self, user_id: str, ws: Any) -> None:
        self._sockets.setdefault(user_id, set()).add(ws)

    def remove(self, user_id: str, ws: Any) -> None:
        sockets = self._sockets.get(user_id)
        if sockets:
            sockets.discard(ws)
            if not sockets:
                del self._sockets[user_id]

    def connected(self, user_id: str) -> int:
        return len(self._sockets.get(user_id, ()))

    async def send(self, user_id: str, message: dict) -> int:
        delivered = 0
        for ws in list(self._sockets.get(user_id, ())):
            try:
                await ws.send_json(message)
                delivered += 1
            except Exception:  # dead socket: its handler will clean up
                logger.info("Dropping a notification socket for %s", user_id)
                self.remove(user_id, ws)
        return delivered


hub = NotificationHub()


# -- devices -----------------------------------------------------------------

async def register_device(pool, user_id: str, name: str, platform: str = "android") -> dict:
    """Create a device and return its credential. The token is shown only once."""
    device_id = secrets.token_urlsafe(9)
    token = secrets.token_urlsafe(32)
    await pool.pool.execute(
        "INSERT INTO butler.devices (id, user_id, name, platform, token_hash) VALUES ($1, $2, $3, $4, $5)",
        device_id, user_id, (name or "Android phone")[:80], platform[:20], _hash(token),
    )
    logger.info("Registered %s device %s for %s", platform, device_id, user_id)
    return {"deviceId": device_id, "deviceToken": token}


async def authenticate_device(pool, token: str) -> tuple[str, str] | None:
    """(device_id, user_id) for a device token, refreshing last_seen_at."""
    if not token:
        return None
    row = await pool.pool.fetchrow(
        "UPDATE butler.devices SET last_seen_at = NOW() WHERE token_hash = $1 RETURNING id, user_id",
        _hash(token),
    )
    return (row["id"], row["user_id"]) if row else None


async def touch_device(pool, device_id: str) -> None:
    await pool.pool.execute("UPDATE butler.devices SET last_seen_at = NOW() WHERE id = $1", device_id)


async def unregister_device(pool, user_id: str, device_id: str) -> bool:
    row = await pool.pool.fetchrow(
        "DELETE FROM butler.devices WHERE id = $1 AND user_id = $2 RETURNING id", device_id, user_id,
    )
    return row is not None


async def list_devices(pool, user_id: str) -> list[dict]:
    rows = await pool.pool.fetch(
        "SELECT id, name, platform, created_at, last_seen_at FROM butler.devices "
        "WHERE user_id = $1 ORDER BY created_at",
        user_id,
    )
    return [
        {
            "id": r["id"], "name": r["name"], "platform": r["platform"],
            "createdAt": r["created_at"].isoformat(), "lastSeenAt": r["last_seen_at"].isoformat(),
            "connected": hub.connected(user_id) > 0,
        }
        for r in rows
    ]


# -- delivery ----------------------------------------------------------------

def _message(row, title: str, body: str, url: str, category: str, silent: bool) -> dict:
    return {
        "type": "notification", "id": row["id"], "title": title, "body": body, "url": url,
        "category": category, "silent": silent, "createdAt": row["created_at"].isoformat(),
    }


async def deliver(pool, user_id: str, title: str, body: str, url: str, category: str, silent: bool) -> int:
    """Queue for the user's app devices and push to any that are connected.

    Returns how many devices will get it (connected now, or active recently
    and so will catch up), so callers can decide whether to fall back.
    """
    active = await pool.pool.fetchval(
        "SELECT count(*) FROM butler.devices WHERE user_id = $1 "
        "AND last_seen_at > NOW() - make_interval(days => $2)",
        user_id, ACTIVE_DEVICE_DAYS,
    )
    if not active:
        return 0
    row = await pool.pool.fetchrow(
        "INSERT INTO butler.notifications (user_id, title, body, url, category, silent) "
        "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id, created_at",
        user_id, title, body, url, category, silent,
    )
    await hub.send(user_id, _message(row, title, body, url, category, silent))
    return int(active)


async def backlog(pool, user_id: str, since_id: int) -> list[dict]:
    """Notifications the device hasn't seen (newer than since_id), oldest first."""
    rows = await pool.pool.fetch(
        "SELECT id, title, body, url, category, silent, created_at FROM butler.notifications "
        "WHERE user_id = $1 AND id > $2 AND created_at > NOW() - make_interval(days => $3) "
        "ORDER BY id DESC LIMIT $4",
        user_id, since_id, BACKLOG_DAYS, BACKLOG_LIMIT,
    )
    return [_message(r, r["title"], r["body"], r["url"], r["category"], r["silent"]) for r in reversed(rows)]


async def latest_id(pool, user_id: str) -> int:
    return int(await pool.pool.fetchval(
        "SELECT COALESCE(MAX(id), 0) FROM butler.notifications WHERE user_id = $1", user_id,
    ))


async def cleanup_notifications(pool, days: int = BACKLOG_DAYS) -> int:
    result = await pool.pool.execute(
        "DELETE FROM butler.notifications WHERE created_at < NOW() - make_interval(days => $1)", days,
    )
    return int(result.split()[-1])
