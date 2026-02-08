"""Alert state management for health and storage monitoring.

Provides deduplication so the same alert is not fired repeatedly, and a
notification abstraction that future channels (WhatsApp, email) can plug
into.

Usage:
    pool = await DatabasePool.create()
    alert_mgr = AlertStateManager(pool)

    # Trigger an alert (returns True if this is genuinely new)
    is_new = await alert_mgr.trigger_alert(
        alert_key="health:jellyfin:down",
        alert_type="service_down",
        severity="critical",
        message="Jellyfin is not responding",
    )

    # Resolve when the condition clears
    await alert_mgr.resolve_alert("health:jellyfin:down")
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .memory import DatabasePool

logger = logging.getLogger(__name__)


class AlertStateManager:
    """Manages alert state in PostgreSQL to prevent notification spam.

    Each alert is identified by a unique ``alert_key``.  When triggered:
    - If no row exists → INSERT (new alert, returns True).
    - If a row exists and is still active → UPDATE timestamp only (returns False).
    - If a row exists but was resolved → re-activate it (returns True).
    """

    def __init__(self, db_pool: DatabasePool) -> None:
        self._db_pool = db_pool

    async def trigger_alert(
        self,
        alert_key: str,
        alert_type: str,
        severity: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Record an alert.  Returns True if this is a NEW or re-fired alert."""
        pool = self._db_pool.pool
        meta_json = json.dumps(metadata or {})

        # Use a single upsert.  The CASE in the RETURNING clause tells us
        # whether this was genuinely new (inserted) or re-fired (was resolved).
        row = await pool.fetchrow(
            """
            INSERT INTO butler.alert_state
                (alert_key, alert_type, severity, message, metadata,
                 first_triggered_at, last_triggered_at, resolved_at, notification_sent)
            VALUES ($1, $2, $3, $4, $5::jsonb, NOW(), NOW(), NULL, FALSE)
            ON CONFLICT (alert_key) DO UPDATE SET
                severity           = EXCLUDED.severity,
                message            = EXCLUDED.message,
                metadata           = EXCLUDED.metadata,
                last_triggered_at  = NOW(),
                -- Re-activate if it was resolved
                resolved_at        = NULL,
                -- Reset notification flag only when re-activating
                notification_sent  = CASE
                    WHEN butler.alert_state.resolved_at IS NOT NULL THEN FALSE
                    ELSE butler.alert_state.notification_sent
                END
            RETURNING
                (xmax = 0) AS inserted,
                resolved_at IS NULL AND notification_sent = FALSE AS needs_notify
            """,
            alert_key, alert_type, severity, message, meta_json,
        )

        # inserted=True → brand new row.  needs_notify=True → was resolved, now re-fired.
        is_new = bool(row and (row["inserted"] or row["needs_notify"]))
        if is_new:
            logger.info("Alert triggered: %s — %s", alert_key, message)
        return is_new

    async def resolve_alert(self, alert_key: str) -> bool:
        """Mark an alert as resolved.  Returns True if it was actually active."""
        pool = self._db_pool.pool
        result = await pool.execute(
            """
            UPDATE butler.alert_state
            SET resolved_at = NOW()
            WHERE alert_key = $1 AND resolved_at IS NULL
            """,
            alert_key,
        )
        resolved = result == "UPDATE 1"
        if resolved:
            logger.info("Alert resolved: %s", alert_key)
        return resolved

    async def get_active_alerts(
        self, alert_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return all active (unresolved) alerts, optionally filtered by type."""
        pool = self._db_pool.pool
        if alert_type:
            rows = await pool.fetch(
                """
                SELECT id, alert_key, alert_type, severity, message,
                       first_triggered_at, last_triggered_at, metadata
                FROM butler.alert_state
                WHERE resolved_at IS NULL AND alert_type = $1
                ORDER BY last_triggered_at DESC
                """,
                alert_type,
            )
        else:
            rows = await pool.fetch(
                """
                SELECT id, alert_key, alert_type, severity, message,
                       first_triggered_at, last_triggered_at, metadata
                FROM butler.alert_state
                WHERE resolved_at IS NULL
                ORDER BY last_triggered_at DESC
                """,
            )
        return [dict(r) for r in rows]

    async def get_unsent_alerts(self) -> list[dict[str, Any]]:
        """Return active alerts that haven't been notified yet."""
        pool = self._db_pool.pool
        rows = await pool.fetch(
            """
            SELECT id, alert_key, alert_type, severity, message, metadata
            FROM butler.alert_state
            WHERE resolved_at IS NULL AND notification_sent = FALSE
            ORDER BY last_triggered_at DESC
            """,
        )
        return [dict(r) for r in rows]

    async def mark_sent(self, alert_id: int) -> None:
        """Mark a specific alert as having been notified."""
        pool = self._db_pool.pool
        await pool.execute(
            "UPDATE butler.alert_state SET notification_sent = TRUE WHERE id = $1",
            alert_id,
        )


class NotificationDispatcher:
    """Dispatches alerts via available notification channels.

    When no channels are registered (e.g. WhatsApp not yet built), alerts
    remain in the database for Butler to surface during conversations.

    Channels are async callables with signature:
        async def send(severity: str, title: str, message: str) -> bool
    """

    def __init__(self, alert_manager: AlertStateManager) -> None:
        self._alert_manager = alert_manager
        self._channels: list[Callable[[str, str, str], Awaitable[bool]]] = []

    def register_channel(
        self, channel: Callable[[str, str, str], Awaitable[bool]],
    ) -> None:
        """Register a notification channel (e.g. WhatsApp, email)."""
        self._channels.append(channel)

    async def dispatch_pending(self) -> int:
        """Send all unsent alerts through registered channels.

        Returns the number of alerts successfully dispatched.
        """
        if not self._channels:
            return 0

        unsent = await self._alert_manager.get_unsent_alerts()
        sent_count = 0
        for alert in unsent:
            title = f"[{alert['severity'].upper()}] {alert['alert_key']}"
            success = await self._dispatch_one(
                alert["severity"], title, alert["message"],
            )
            if success:
                await self._alert_manager.mark_sent(alert["id"])
                sent_count += 1
        return sent_count

    async def _dispatch_one(
        self, severity: str, title: str, message: str,
    ) -> bool:
        """Send a single notification through all registered channels."""
        any_success = False
        for channel in self._channels:
            try:
                if await channel(severity, title, message):
                    any_success = True
            except Exception:
                logger.exception("Notification channel failed for: %s", title)
        return any_success
