"""Gmail integration tool for Butler.

Provides read-only access to a user's Gmail, enabling the agent to
answer questions like "Do I have any emails from Amazon?" or
"What's my latest flight confirmation?"

Requires the user to have connected their Google account via OAuth
in the Settings page. If not connected, returns a helpful message
directing the user to connect.
"""

from __future__ import annotations

import base64
import logging
import re
from datetime import datetime, timezone
from email.utils import parseaddr
from html import unescape
from typing import Any

import aiohttp

from .base import Tool

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailTool(Tool):
    """Read-only access to a user's Gmail.

    This tool is user-scoped: it's created per-request with a specific
    user_id, unlike global tools (HA, memory) which are created once
    at startup.
    """

    def __init__(self, db_pool, user_id: str):
        self._pool = db_pool
        self._user_id = user_id

    @property
    def name(self) -> str:
        return "gmail"

    @property
    def description(self) -> str:
        return (
            "Search and read the user's Gmail. Can list recent emails, "
            "search by query (sender, subject, date, label), or read a "
            "specific email. Read-only — cannot send, delete, or modify. "
            "Only works if the user has connected Google in Settings."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_recent", "search_emails", "read_email"],
                    "description": (
                        "list_recent: get the N most recent emails. "
                        "search_emails: find emails matching a Gmail query. "
                        "read_email: get the full content of a specific email by ID."
                    ),
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Gmail search query for search_emails. Supports Gmail operators: "
                        "from:, to:, subject:, after:, before:, label:, has:attachment, "
                        "is:unread, newer_than:2d, etc."
                    ),
                },
                "message_id": {
                    "type": "string",
                    "description": "Gmail message ID for read_email action.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Number of emails to return (default: 10, max: 20).",
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": ["action"],
        }

    async def _get_token(self) -> str | None:
        """Get a valid Google OAuth token, refreshing if needed."""
        from api.oauth import get_valid_token

        return await get_valid_token(self._pool, self._user_id, "google")

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "list_recent")

        access_token = await self._get_token()
        if not access_token:
            return (
                "Google is not connected. "
                "Please connect it in the Settings page of the Butler app."
            )

        try:
            if action == "list_recent":
                return await self._list_recent(access_token, kwargs)
            elif action == "search_emails":
                return await self._search_emails(access_token, kwargs)
            elif action == "read_email":
                return await self._read_email(access_token, kwargs)
            else:
                return f"Unknown action: {action}. Use 'list_recent', 'search_emails', or 'read_email'."
        except aiohttp.ClientError as e:
            return f"Error connecting to Gmail: {e}"
        except Exception as e:
            logger.exception("Gmail tool error")
            return f"Error: {e}"

    async def _list_recent(self, access_token: str, kwargs: dict) -> str:
        """List the most recent emails."""
        max_results = min(kwargs.get("max_results", 10), 20)
        messages = await self._fetch_message_list(access_token, max_results=max_results)
        if isinstance(messages, str):
            return messages
        if not messages:
            return "No emails found."
        return await self._format_message_list(access_token, messages)

    async def _search_emails(self, access_token: str, kwargs: dict) -> str:
        """Search emails using a Gmail query."""
        query = kwargs.get("query", "")
        if not query:
            return "Please provide a search query."

        max_results = min(kwargs.get("max_results", 10), 20)
        messages = await self._fetch_message_list(
            access_token, query=query, max_results=max_results
        )
        if isinstance(messages, str):
            return messages
        if not messages:
            return f"No emails matching '{query}'."
        return await self._format_message_list(access_token, messages)

    async def _read_email(self, access_token: str, kwargs: dict) -> str:
        """Read the full content of a specific email."""
        message_id = kwargs.get("message_id", "")
        if not message_id:
            return "Please provide a message_id."

        message = await self._fetch_message(access_token, message_id)
        if isinstance(message, str):
            return message
        return self._format_full_message(message)

    async def _fetch_message_list(
        self,
        access_token: str,
        query: str | None = None,
        max_results: int = 10,
    ) -> list[dict] | str:
        """Fetch a list of message IDs from Gmail.

        Returns a list of {id, threadId} dicts, or an error string.
        """
        params: dict[str, str | int] = {"maxResults": max_results}
        if query:
            params["q"] = query

        url = f"{GMAIL_API_BASE}/messages"
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            ) as resp:
                if resp.status == 401:
                    logger.warning(
                        "Gmail API returned 401 for user=%s — token may need re-auth",
                        self._user_id,
                    )
                    return (
                        "Google access has expired. "
                        "Please reconnect in Settings > Connected Services."
                    )
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning("Gmail API %d: %s", resp.status, text[:200])
                    return f"Gmail API error (status {resp.status})."
                data = await resp.json()
                return data.get("messages", [])

    async def _fetch_message(
        self,
        access_token: str,
        message_id: str,
        fmt: str = "full",
    ) -> dict | str:
        """Fetch a single message by ID.

        Returns the message dict, or an error string.
        """
        url = f"{GMAIL_API_BASE}/messages/{message_id}"
        params = {"format": fmt}
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            ) as resp:
                if resp.status == 401:
                    return (
                        "Google access has expired. "
                        "Please reconnect in Settings > Connected Services."
                    )
                if resp.status == 404:
                    return f"Email not found (ID: {message_id})."
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning("Gmail API %d: %s", resp.status, text[:200])
                    return f"Gmail API error (status {resp.status})."
                return await resp.json()

    async def _format_message_list(
        self, access_token: str, messages: list[dict]
    ) -> str:
        """Fetch metadata for each message and format as a readable list."""
        lines: list[str] = []

        # Batch-fetch metadata for all messages
        details = []
        for msg in messages:
            result = await self._fetch_message(access_token, msg["id"], fmt="metadata")
            if isinstance(result, str):
                continue  # skip errors for individual messages
            details.append(result)

        for msg in details:
            headers = {
                h["name"].lower(): h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            subject = headers.get("subject", "(No subject)")
            from_raw = headers.get("from", "Unknown")
            date_str = headers.get("date", "")
            msg_id = msg.get("id", "")

            # Parse sender into a clean format
            sender_name, sender_email = parseaddr(from_raw)
            sender = sender_name if sender_name else sender_email

            # Parse date
            date_display = _parse_email_date(date_str)

            # Check for unread
            labels = msg.get("labelIds", [])
            unread = " [UNREAD]" if "UNREAD" in labels else ""

            snippet = unescape(msg.get("snippet", ""))
            # Truncate snippet
            if len(snippet) > 100:
                snippet = snippet[:100] + "..."

            lines.append(
                f"{'─' * 40}\n"
                f"  From: {sender}\n"
                f"  Subject: {subject}{unread}\n"
                f"  Date: {date_display}\n"
                f"  Preview: {snippet}\n"
                f"  ID: {msg_id}"
            )

        if not lines:
            return "No emails found."

        return f"Found {len(lines)} email(s):\n" + "\n".join(lines)

    def _format_full_message(self, message: dict) -> str:
        """Format a full message for reading."""
        headers = {
            h["name"].lower(): h["value"]
            for h in message.get("payload", {}).get("headers", [])
        }

        subject = headers.get("subject", "(No subject)")
        from_raw = headers.get("from", "Unknown")
        to_raw = headers.get("to", "Unknown")
        date_str = headers.get("date", "")
        msg_id = message.get("id", "")

        sender_name, sender_email = parseaddr(from_raw)
        sender = f"{sender_name} <{sender_email}>" if sender_name else sender_email

        date_display = _parse_email_date(date_str)

        body = _extract_body(message.get("payload", {}))

        # Truncate very long bodies to avoid overwhelming the LLM
        if len(body) > 3000:
            body = body[:3000] + "\n\n... (truncated — email is very long)"

        labels = message.get("labelIds", [])
        label_str = ", ".join(labels) if labels else "None"

        return (
            f"Subject: {subject}\n"
            f"From: {sender}\n"
            f"To: {to_raw}\n"
            f"Date: {date_display}\n"
            f"Labels: {label_str}\n"
            f"ID: {msg_id}\n"
            f"{'─' * 40}\n"
            f"{body}"
        )


def _parse_email_date(date_str: str) -> str:
    """Parse an email Date header into a readable format."""
    if not date_str:
        return "Unknown date"
    try:
        # Email dates can have various formats; try common ones
        # Remove timezone name in parentheses e.g., "(UTC)"
        clean = re.sub(r"\s*\([^)]*\)\s*$", "", date_str.strip())
        # Try RFC 2822 parsing
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(clean)
        return dt.strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return date_str


def _extract_body(payload: dict) -> str:
    """Extract plain text body from a Gmail message payload.

    Gmail messages can be simple (body directly in payload) or multipart
    (body nested in parts). We prefer text/plain, falling back to a
    stripped text/html.
    """
    # Simple message (no parts)
    if "parts" not in payload:
        body_data = payload.get("body", {}).get("data", "")
        mime = payload.get("mimeType", "")
        if body_data:
            decoded = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
            if "html" in mime:
                return _strip_html(decoded)
            return decoded
        return "(No body content)"

    # Multipart — look for text/plain first, then text/html
    plain_text = ""
    html_text = ""

    for part in payload["parts"]:
        mime = part.get("mimeType", "")
        body_data = part.get("body", {}).get("data", "")

        if mime == "text/plain" and body_data:
            plain_text = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
        elif mime == "text/html" and body_data:
            html_text = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
        elif mime.startswith("multipart/"):
            # Recurse into nested multipart
            nested = _extract_body(part)
            if nested and nested != "(No body content)":
                return nested

    if plain_text:
        return plain_text
    if html_text:
        return _strip_html(html_text)

    return "(No body content)"


def _strip_html(html: str) -> str:
    """Rough HTML-to-text conversion for email bodies."""
    # Remove style and script blocks
    text = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Replace <br> and block elements with newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|tr|li|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities
    text = unescape(text)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
