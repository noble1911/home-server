"""Gmail integration tool for Butler.

Reads a user's Gmail ("Do I have any emails from Amazon?") and, for users with
the ``email_send`` permission, drafts emails and replies to send from their
account. Drafts never go out on their own: they become a pending approval the
user taps to send in the Butler app (see api/approvals.py), and
``execute_approved`` below runs only after that tap.

Requires the user to have connected their Google account via OAuth
in the Settings page. If not connected, returns a helpful message
directing the user to connect.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import secrets
from email.message import EmailMessage
from urllib.parse import quote
from email.utils import getaddresses, parseaddr
from html import unescape
from typing import Any

import aiohttp

from .base import Tool

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
# Media-upload endpoint: takes the raw RFC 822 message (up to 35 MB), so
# attachments such as ebooks don't need base64 inside JSON.
GMAIL_UPLOAD_SEND_URL = "https://gmail.googleapis.com/upload/gmail/v1/users/me/messages/send"

READ_ACTIONS = ["list_recent", "search_emails", "read_email"]
SEND_ACTIONS = ["send_email", "reply_email"]

_EMAIL_RE = re.compile(r"^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+$")

_RECONNECT_FOR_SEND = (
    "Sending email needs extra Google permission that this account hasn't granted yet. "
    "Ask the user to tap Reconnect next to Google in Settings > Connected Services, "
    "then try again."
)

_AWAITING_APPROVAL = (
    "Draft created and waiting for the user's approval (approval id {id}). "
    "Nothing has been sent yet. Tell the user it's ready to review — they tap "
    "Send in the Butler app. Do not say the email was sent."
)


class GmailSendError(Exception):
    """Gmail refused a send; the message is user-facing.

    ``retryable`` means Gmail rejected it outright (nothing was sent), so the
    user can fix the cause (e.g. reconnect Google) and tap Send again.
    """

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def _one_line(value: str | None) -> str:
    """Header values can't contain line breaks (EmailMessage refuses them)."""
    return " ".join((value or "").split())


class GmailTool(Tool):
    """Access to a user's Gmail: read, and (with approval) send.

    This tool is user-scoped: it's created per-request with a specific
    user_id, unlike global tools (HA, memory) which are created once
    at startup.
    """

    def __init__(self, db_pool, user_id: str, *, can_read: bool = True, can_send: bool = False):
        self._pool = db_pool
        self._user_id = user_id
        self._can_read = can_read
        self._can_send = can_send

    @property
    def name(self) -> str:
        return "gmail"

    @property
    def _actions(self) -> list[str]:
        return (READ_ACTIONS if self._can_read else []) + (SEND_ACTIONS if self._can_send else [])

    @property
    def description(self) -> str:
        if not self._can_send:
            return (
                "Search and read the user's Gmail. Can list recent emails, "
                "search by query (sender, subject, date, label), or read a "
                "specific email. Read-only — cannot send, delete, or modify. "
                "Only works if the user has connected Google in Settings."
            )
        reading = (
            "Search and read the user's Gmail (list recent, search by query, read by ID), "
            if self._can_read else ""
        )
        return (
            f"{reading}Draft new emails (send_email) and replies (reply_email) from the "
            "user's own Gmail. Drafts are NOT sent immediately: the user must approve each "
            "one in the Butler app. After drafting, tell the user it's waiting for their "
            "approval — never say it was sent. Write the body in the user's voice, plain "
            "text, and only include what they asked for. Only works if the user has "
            "connected Google in Settings."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        descriptions = {
            "list_recent": "list_recent: get the N most recent emails.",
            "search_emails": "search_emails: find emails matching a Gmail query.",
            "read_email": "read_email: get the full content of a specific email by ID.",
            "send_email": "send_email: draft a new email (to, subject, body) for the user to approve.",
            "reply_email": (
                "reply_email: draft a reply to an email by message_id (body; reply_all "
                "to include everyone) for the user to approve."
            ),
        }
        props: dict[str, Any] = {
            "action": {
                "type": "string",
                "enum": self._actions,
                "description": " ".join(descriptions[a] for a in self._actions),
            },
        }
        if self._can_read:
            props.update({
                "query": {
                    "type": "string",
                    "description": (
                        "Gmail search query for search_emails. Supports Gmail operators: "
                        "from:, to:, subject:, after:, before:, label:, has:attachment, "
                        "is:unread, newer_than:2d, etc."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Number of emails to return (default: 10, max: 20).",
                    "minimum": 1,
                    "maximum": 20,
                },
            })
        props["message_id"] = {
            "type": "string",
            "description": "Gmail message ID (from a list/search result) for read_email or reply_email.",
        }
        if self._can_send:
            props.update({
                "to": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Recipient email addresses for send_email.",
                },
                "cc": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional CC addresses for send_email.",
                },
                "subject": {"type": "string", "description": "Subject line for send_email."},
                "body": {"type": "string", "description": "Plain-text body for send_email or reply_email."},
                "reply_all": {
                    "type": "boolean",
                    "description": "reply_email: also reply to everyone on the original (default false).",
                },
            })
        return {"type": "object", "properties": props, "required": ["action"]}

    async def _get_token(self) -> str | None:
        """Get a valid Google OAuth token, refreshing if needed."""
        from api.oauth import get_valid_token

        return await get_valid_token(self._pool, self._user_id, "google")

    async def _granted_scopes(self) -> set[str]:
        from api.oauth import get_granted_scopes

        return await get_granted_scopes(self._pool, self._user_id, "google")

    async def _account_email(self) -> str | None:
        from api.oauth import get_account_email

        return await get_account_email(self._pool, self._user_id, "google")

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", self._actions[0] if self._actions else "")
        if action not in self._actions:
            return f"Unknown action: {action}. Use one of: {', '.join(self._actions)}."

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
            elif action == "send_email":
                return await self._draft_send(kwargs)
            else:  # reply_email
                return await self._draft_reply(access_token, kwargs)
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

    # -- drafting (creates a pending approval; nothing is sent here) ----------

    async def _draft_send(self, kwargs: dict) -> str:
        from api.approvals import create_pending_action
        from api.oauth import GMAIL_SEND_SCOPE

        if GMAIL_SEND_SCOPE not in await self._granted_scopes():
            return _RECONNECT_FOR_SEND

        to = _address_list(kwargs.get("to"))
        cc = _address_list(kwargs.get("cc"))
        subject = _one_line(kwargs.get("subject"))
        body = (kwargs.get("body") or "").strip()
        if not to:
            return "Please provide at least one recipient email address (to)."
        bad = [a for a in to + cc if not _EMAIL_RE.match(a)]
        if bad:
            return f"These don't look like email addresses: {', '.join(bad)}. Ask the user for the exact address."
        if not body:
            return "Please provide the email body."

        fields = [["To", ", ".join(to)]]
        if cc:
            fields.append(["Cc", ", ".join(cc)])
        fields.append(["Subject", subject or "(no subject)"])
        card = await create_pending_action(
            self._pool, self._user_id, "gmail.send",
            params={"to": to, "cc": cc, "subject": subject, "body": body},
            summary={"title": "Send email", "fields": fields, "body": body},
        )
        return _AWAITING_APPROVAL.format(id=card["id"])

    async def _draft_reply(self, access_token: str, kwargs: dict) -> str:
        from api.approvals import create_pending_action
        from api.oauth import GMAIL_SEND_SCOPE

        if GMAIL_SEND_SCOPE not in await self._granted_scopes():
            return _RECONNECT_FOR_SEND

        message_id = kwargs.get("message_id", "")
        body = (kwargs.get("body") or "").strip()
        if not message_id:
            return "Please provide the message_id of the email to reply to."
        if not body:
            return "Please provide the reply body."

        original = await self._fetch_message(access_token, message_id, fmt="metadata")
        if isinstance(original, str):
            return original
        headers = {
            h["name"].lower(): h["value"]
            for h in original.get("payload", {}).get("headers", [])
        }
        own = ((await self._account_email()) or "").lower()

        to = [a for _, a in getaddresses([headers.get("reply-to") or headers.get("from", "")]) if a]
        if own and to and all(a.lower() == own for a in to):
            # Replying to something the user sent: go back to its recipients.
            to = [a for _, a in getaddresses([headers.get("to", "")]) if a]
        cc: list[str] = []
        if kwargs.get("reply_all"):
            seen = {a.lower() for a in to} | {own}
            for _, a in getaddresses([headers.get("to", ""), headers.get("cc", "")]):
                if a and a.lower() not in seen:
                    cc.append(a)
                    seen.add(a.lower())
        if not to:
            return "Couldn't work out who to reply to for that email."

        subject = _one_line(headers.get("subject"))
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}".strip()
        msg_id_header = _one_line(headers.get("message-id"))
        references = _one_line(f"{headers.get('references', '')} {msg_id_header}")

        fields = [["To", ", ".join(to)]]
        if cc:
            fields.append(["Cc", ", ".join(cc)])
        fields.append(["Subject", subject])
        card = await create_pending_action(
            self._pool, self._user_id, "gmail.reply",
            params={
                "to": to, "cc": cc, "subject": subject, "body": body,
                "thread_id": original.get("threadId"),
                "in_reply_to": msg_id_header, "references": references,
            },
            summary={"title": "Send reply", "fields": fields, "body": body},
        )
        return _AWAITING_APPROVAL.format(id=card["id"])

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
        url = f"{GMAIL_API_BASE}/messages/{quote(message_id, safe='')}"
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


# ── Sending (shared with send_to_kindle) ────────────────────────────────


def _address_list(value: Any) -> list[str]:
    """Normalise a to/cc argument (list, or comma-separated string) to bare addresses."""
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    return [addr.strip() for _, addr in getaddresses([str(i) for i in items]) if addr.strip()]


def build_mime(
    to: list[str],
    subject: str,
    body: str,
    *,
    cc: list[str] | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> bytes:
    """Build an RFC 822 message. ``attachments`` are ``(filename, data, mime_type)``.

    No From header: Gmail fills in the authenticated account's address.
    """
    msg = EmailMessage()
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg.set_content(body)
    for filename, data, mime_type in attachments or []:
        maintype, _, subtype = mime_type.partition("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream", filename=filename)
    return msg.as_bytes(policy=msg.policy.clone(linesep="\r\n"))


async def send_mime(access_token: str, raw: bytes, *, thread_id: str | None = None) -> dict:
    """Send a raw message via Gmail's multipart upload. Raises GmailSendError."""
    boundary = f"butler-{secrets.token_hex(12)}"
    meta = json.dumps({"threadId": thread_id} if thread_id else {}).encode()
    b = boundary.encode()
    payload = (
        b"--" + b + b"\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n" + meta
        + b"\r\n--" + b + b"\r\nContent-Type: message/rfc822\r\n\r\n" + raw
        + b"\r\n--" + b + b"--\r\n"
    )
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            GMAIL_UPLOAD_SEND_URL,
            params={"uploadType": "multipart"},
            data=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            text = await resp.text()
            logger.warning("Gmail send %d: %s", resp.status, text[:300])
            if resp.status == 401:
                raise GmailSendError(
                    "Google access has expired — reconnect Google in Settings, then tap Send again.",
                    retryable=True,
                )
            if resp.status == 403:
                raise GmailSendError(
                    "Google hasn't given Butler permission to send email — "
                    "tap Reconnect next to Google in Settings, then tap Send again.",
                    retryable=True,
                )
            if resp.status == 413:
                raise GmailSendError("The email is too large for Gmail to send.")
            raise GmailSendError(f"Gmail refused the email (status {resp.status}).")


async def execute_approved(pool, user_id: str, kind: str, params: dict) -> str:
    """Run an approved gmail.send / gmail.reply. Called only by api.approvals."""
    from api.approvals import ApprovalError, ApprovalRetryable
    from api.oauth import get_valid_token

    token = await get_valid_token(pool, user_id, "google")
    if not token:
        raise ApprovalRetryable("Google needs reconnecting — tap Reconnect next to Google in Settings, then tap Send again.")
    raw = build_mime(
        params["to"], params.get("subject", ""), params["body"],
        cc=params.get("cc") or None,
        in_reply_to=params.get("in_reply_to") or None,
        references=params.get("references") or None,
    )
    try:
        await send_mime(token, raw, thread_id=params.get("thread_id"))
    except GmailSendError as e:
        raise (ApprovalRetryable if e.retryable else ApprovalError)(str(e)) from e
    except aiohttp.ClientConnectorError as e:
        # Never connected, so nothing was sent. Anything later (disconnect,
        # timeout) is ambiguous — it may have gone — so that's a final failure.
        raise ApprovalRetryable(f"Couldn't reach Gmail ({e}) — nothing was sent. Tap Send to try again.") from e
    except aiohttp.ClientError as e:
        raise ApprovalError(f"Gmail error: {e}. Check your Sent folder before trying again.") from e
    what = "Reply" if kind == "gmail.reply" else "Email"
    return f"{what} sent to {', '.join(params['to'])}."


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
