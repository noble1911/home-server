"""WhatsApp outbound notification tool for Butler.

This tool allows the agent to send WhatsApp messages to users for
proactive notifications (download complete, reminders, weather alerts, etc.).

Usage:
    The tool is automatically registered when WHATSAPP_GATEWAY_URL is configured.
    Requires a running whatsapp-web.js gateway container (docker/messaging-stack).

Example:
    tool = WhatsAppTool(gateway_url="http://whatsapp-gateway:3000", db_pool=pool)
    result = await tool.execute(
        action="send_message",
        user_id="ron",
        message="Dune audiobook is ready in your library",
        category="download",
    )

    # When shutting down
    await tool.close()
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Tool
from .memory import DatabasePool

logger = logging.getLogger(__name__)

# Default timeout for HTTP requests (seconds)
DEFAULT_TIMEOUT = 10

# Rate limiting: max messages per user per hour
MAX_MESSAGES_PER_HOUR = 10

# Valid notification categories
VALID_CATEGORIES = frozenset(
    ["download", "reminder", "weather", "smart_home", "calendar", "general"]
)

# Default preferences when a user has no explicit notification_preferences
DEFAULT_NOTIFICATION_PREFS = {
    "enabled": True,
    "categories": list(VALID_CATEGORIES),
}


class WhatsAppTool(Tool):
    """Send outbound WhatsApp notifications via the gateway REST API.

    Supports sending text messages to users and checking gateway status.
    Enforces per-user notification preferences, rate limiting, and quiet hours.
    """

    def __init__(
        self,
        gateway_url: str | None = None,
        db_pool: DatabasePool | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Initialize the WhatsApp tool.

        Args:
            gateway_url: WhatsApp gateway URL (e.g. http://whatsapp-gateway:3000)
            db_pool: Shared database pool for user lookups
            timeout: HTTP request timeout in seconds (default: 10)
        """
        self.gateway_url = (gateway_url or "").rstrip("/")
        self._db_pool = db_pool
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None
        # In-memory rate limiting: user_id -> list of send timestamps
        self._rate_limits: dict[str, list[float]] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self) -> None:
        """Close the HTTP session.

        Should be called when shutting down to cleanly release connections.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "whatsapp"

    @property
    def description(self) -> str:
        return (
            "Send outbound WhatsApp notifications to users. Use this for "
            "proactive messages like download complete alerts, reminders, "
            "weather warnings, and smart home updates. Each message requires "
            "a user_id and respects the user's notification preferences, "
            "rate limits (max 10/hour), and quiet hours."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["send_message", "check_status"],
                    "description": (
                        "send_message: Send a WhatsApp notification to a user. "
                        "check_status: Check if the WhatsApp gateway is connected."
                    ),
                },
                "user_id": {
                    "type": "string",
                    "description": (
                        "User ID to send the message to. "
                        "The user must have a phone number configured in their profile."
                    ),
                },
                "message": {
                    "type": "string",
                    "description": "The message text to send.",
                },
                "category": {
                    "type": "string",
                    "enum": sorted(VALID_CATEGORIES),
                    "description": (
                        "Notification category. Must match a category the user "
                        "has enabled. Defaults to 'general' if not specified."
                    ),
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]

        if not self.gateway_url:
            return "Error: WHATSAPP_GATEWAY_URL must be configured."

        try:
            if action == "send_message":
                return await self._send_message(
                    user_id=kwargs.get("user_id", ""),
                    message=kwargs.get("message", ""),
                    category=kwargs.get("category", "general"),
                )
            elif action == "check_status":
                return await self._check_status()
            else:
                return f"Error: Unknown action '{action}'"
        except aiohttp.ClientError as e:
            return f"Error connecting to WhatsApp gateway: {e}"
        except TimeoutError:
            return "Error: WhatsApp gateway request timed out"
        except Exception as e:
            return f"Error: {e}"

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def _send_message(
        self,
        user_id: str,
        message: str,
        category: str,
    ) -> str:
        """Send a WhatsApp message to a user, checking preferences first."""
        if not user_id:
            return "Error: user_id is required for send_message"
        if not message:
            return "Error: message is required for send_message"

        # Look up user in database
        phone, prefs, error = await self._get_user_whatsapp_config(user_id)
        if error:
            return error

        # Check notification preferences
        pref_error = self._check_preferences(user_id, prefs, category)
        if pref_error:
            return pref_error

        # Check rate limit
        if not self._check_rate_limit(user_id):
            return (
                f"Rate limit exceeded for user '{user_id}' "
                f"(max {MAX_MESSAGES_PER_HOUR} messages/hour). Try again later."
            )

        # Send via gateway
        session = await self._get_session()
        payload = {"to": phone, "message": message}

        async with session.post(
            f"{self.gateway_url}/send", json=payload
        ) as resp:
            data = await resp.json()

            if resp.status != 200 and not data.get("ok"):
                return f"Error sending WhatsApp message: {data.get('error', f'HTTP {resp.status}')}"

            if not data.get("ok"):
                return f"Error: {data.get('error', 'Unknown error')}"

        # Record successful send for rate limiting
        self._record_send(user_id)

        if data.get("queued"):
            return (
                f"WhatsApp message to {user_id} queued for delivery "
                "(gateway is temporarily disconnected)."
            )
        return f"WhatsApp message sent to {user_id}."

    async def _check_status(self) -> str:
        """Check WhatsApp gateway connection status."""
        session = await self._get_session()

        async with session.get(f"{self.gateway_url}/status") as resp:
            if resp.status != 200:
                return "WhatsApp gateway is not responding."

            data = await resp.json()

        if data.get("connected"):
            info = data.get("info") or {}
            name = info.get("pushname", "")
            name_str = f" as {name}" if name else ""
            queue = data.get("queueSize", 0)
            queue_str = f" ({queue} queued messages)" if queue else ""
            return f"WhatsApp gateway is connected{name_str} and ready.{queue_str}"

        return (
            "WhatsApp gateway is running but not connected to WhatsApp. "
            "Scan the QR code to authenticate (check gateway logs)."
        )

    # ------------------------------------------------------------------
    # User preferences
    # ------------------------------------------------------------------

    async def _get_user_whatsapp_config(
        self, user_id: str
    ) -> tuple[str, dict, str | None]:
        """Look up user's WhatsApp phone and notification preferences.

        Returns:
            (phone, notification_prefs, error_message)
            If error_message is not None, the other values are empty.
        """
        if not self._db_pool:
            return "", {}, "Error: Database pool not available."

        pool = self._db_pool.pool
        row = await pool.fetchrow(
            "SELECT phone, notification_prefs FROM butler.users WHERE id = $1",
            user_id,
        )

        if row is None:
            return "", {}, f"Error: User '{user_id}' not found."

        phone = row["phone"] or ""
        if not phone:
            return "", {}, (
                f"User '{user_id}' does not have a WhatsApp phone configured. "
                "Set it in Settings > WhatsApp Notifications."
            )

        raw_prefs = row["notification_prefs"]
        prefs = (
            json.loads(raw_prefs) if isinstance(raw_prefs, str) else raw_prefs
        ) if raw_prefs is not None else DEFAULT_NOTIFICATION_PREFS

        return phone, prefs, None

    def _check_preferences(
        self, user_id: str, prefs: dict, category: str
    ) -> str | None:
        """Check if the user's notification preferences allow this message.

        Returns an error string if blocked, None if allowed.
        """
        if not prefs.get("enabled", True):
            return f"Notifications are disabled for user '{user_id}'."

        allowed_categories = prefs.get("categories", list(VALID_CATEGORIES))
        if category not in allowed_categories:
            return (
                f"User '{user_id}' has not opted in to '{category}' notifications."
            )

        # Check quiet hours
        quiet_start = prefs.get("quiet_hours_start")
        quiet_end = prefs.get("quiet_hours_end")
        if quiet_start and quiet_end:
            if self._is_quiet_hours(quiet_start, quiet_end):
                return (
                    f"Message not sent — user '{user_id}' is in quiet hours "
                    f"({quiet_start}-{quiet_end}). Message will not be queued."
                )

        return None

    @staticmethod
    def _is_quiet_hours(start: str, end: str) -> bool:
        """Check if the current UTC time falls within quiet hours.

        Args:
            start: Start time as "HH:MM" string
            end: End time as "HH:MM" string

        Returns:
            True if current time is within quiet hours.
        """
        try:
            now = datetime.now(timezone.utc)
            current_minutes = now.hour * 60 + now.minute
            start_h, start_m = map(int, start.split(":"))
            end_h, end_m = map(int, end.split(":"))
            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m

            if start_minutes <= end_minutes:
                # Same-day range (e.g. 09:00-17:00)
                return start_minutes <= current_minutes < end_minutes
            else:
                # Overnight range (e.g. 23:00-07:00)
                return current_minutes >= start_minutes or current_minutes < end_minutes
        except (ValueError, AttributeError):
            return False

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _check_rate_limit(self, user_id: str) -> bool:
        """Return True if the user is within rate limits."""
        now = time.time()
        one_hour_ago = now - 3600

        timestamps = self._rate_limits.get(user_id, [])
        # Prune old entries
        timestamps = [t for t in timestamps if t > one_hour_ago]
        self._rate_limits[user_id] = timestamps

        return len(timestamps) < MAX_MESSAGES_PER_HOUR

    def _record_send(self, user_id: str) -> None:
        """Record a message send for rate limiting."""
        if user_id not in self._rate_limits:
            self._rate_limits[user_id] = []
        self._rate_limits[user_id].append(time.time())
