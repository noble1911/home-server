"""Tests for Gmail tool.

Run with: pytest nanobot/tools/test_gmail.py -v

These tests use mocked responses — no real Gmail API or OAuth required.
"""

import base64
import pytest
import aiohttp
from unittest.mock import AsyncMock, patch, MagicMock

from .gmail import GmailTool, _extract_body, _strip_html, _parse_email_date


# ---------------------------------------------------------------------------
# Sample API responses for mocking
# ---------------------------------------------------------------------------

SAMPLE_MESSAGE_LIST = {
    "messages": [
        {"id": "msg_001", "threadId": "thread_001"},
        {"id": "msg_002", "threadId": "thread_002"},
    ],
}

SAMPLE_MESSAGE_LIST_EMPTY = {}

SAMPLE_MESSAGE_METADATA = {
    "id": "msg_001",
    "threadId": "thread_001",
    "labelIds": ["INBOX", "UNREAD"],
    "snippet": "Your order has shipped and is on the way",
    "payload": {
        "headers": [
            {"name": "From", "value": "Amazon <ship-confirm@amazon.co.uk>"},
            {"name": "To", "value": "ron@example.com"},
            {"name": "Subject", "value": "Your order has shipped!"},
            {"name": "Date", "value": "Thu, 06 Feb 2026 10:30:00 +0000"},
        ],
    },
}

SAMPLE_MESSAGE_METADATA_READ = {
    "id": "msg_002",
    "threadId": "thread_002",
    "labelIds": ["INBOX"],
    "snippet": "Meeting agenda for tomorrow",
    "payload": {
        "headers": [
            {"name": "From", "value": "Alice <alice@example.com>"},
            {"name": "To", "value": "ron@example.com"},
            {"name": "Subject", "value": "Team standup notes"},
            {"name": "Date", "value": "Wed, 05 Feb 2026 14:00:00 +0000"},
        ],
    },
}

_PLAIN_BODY = base64.urlsafe_b64encode(b"Hello, your flight is confirmed for Feb 10.").decode()
_HTML_BODY = base64.urlsafe_b64encode(
    b"<html><body><p>Hello, your flight is <b>confirmed</b> for Feb 10.</p></body></html>"
).decode()

SAMPLE_FULL_MESSAGE_PLAIN = {
    "id": "msg_001",
    "threadId": "thread_001",
    "labelIds": ["INBOX", "UNREAD"],
    "snippet": "Hello, your flight is confirmed",
    "payload": {
        "mimeType": "text/plain",
        "headers": [
            {"name": "From", "value": "Airline <bookings@airline.com>"},
            {"name": "To", "value": "ron@example.com"},
            {"name": "Subject", "value": "Flight Confirmation - LHR to JFK"},
            {"name": "Date", "value": "Thu, 06 Feb 2026 09:00:00 +0000"},
        ],
        "body": {"data": _PLAIN_BODY, "size": 44},
    },
}

SAMPLE_FULL_MESSAGE_MULTIPART = {
    "id": "msg_002",
    "threadId": "thread_002",
    "labelIds": ["INBOX"],
    "snippet": "Hello, your flight is confirmed",
    "payload": {
        "mimeType": "multipart/alternative",
        "headers": [
            {"name": "From", "value": "Airline <bookings@airline.com>"},
            {"name": "To", "value": "ron@example.com"},
            {"name": "Subject", "value": "Flight Confirmation"},
            {"name": "Date", "value": "Thu, 06 Feb 2026 09:00:00 +0000"},
        ],
        "body": {"size": 0},
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"data": _PLAIN_BODY, "size": 44},
            },
            {
                "mimeType": "text/html",
                "body": {"data": _HTML_BODY, "size": 80},
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tool():
    """Create a tool instance with a mock db pool and user_id."""
    mock_pool = MagicMock()
    return GmailTool(db_pool=mock_pool, user_id="user_123")


def _mock_aiohttp_get(responses):
    """Helper to mock aiohttp.ClientSession with sequential GET responses.

    `responses` is a list of AsyncMock response objects. Each session.get()
    call returns the next response in sequence.
    """
    mock_cls = MagicMock()
    mock_session = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    call_index = {"i": 0}

    def get_side_effect(*args, **kwargs):
        ctx = MagicMock()
        resp = responses[call_index["i"]]
        call_index["i"] += 1
        ctx.__aenter__ = AsyncMock(return_value=resp)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    mock_session.get = MagicMock(side_effect=get_side_effect)
    return mock_cls


# ---------------------------------------------------------------------------
# Tests: Tool Properties
# ---------------------------------------------------------------------------


class TestGmailToolProperties:
    """Verify tool metadata."""

    def test_name(self, tool):
        assert tool.name == "gmail"

    def test_description_mentions_gmail(self, tool):
        assert "gmail" in tool.description.lower()

    def test_description_mentions_read_only(self, tool):
        assert "read-only" in tool.description.lower()

    def test_parameters_has_action(self, tool):
        props = tool.parameters["properties"]
        assert "action" in props
        assert set(props["action"]["enum"]) == {
            "list_recent",
            "search_emails",
            "read_email",
        }

    def test_required_fields(self, tool):
        assert tool.parameters["required"] == ["action"]

    def test_to_schema(self, tool):
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "gmail"
        assert "parameters" in schema["function"]


# ---------------------------------------------------------------------------
# Tests: No OAuth Connection
# ---------------------------------------------------------------------------


class TestNoConnection:
    """Test behavior when Google is not connected."""

    @pytest.mark.asyncio
    async def test_not_connected(self, tool):
        tool._get_token = AsyncMock(return_value=None)
        result = await tool.execute(action="list_recent")
        assert "not connected" in result.lower()
        assert "Settings" in result


# ---------------------------------------------------------------------------
# Tests: list_recent
# ---------------------------------------------------------------------------


class TestListRecent:
    """Tests for the list_recent action."""

    @pytest.mark.asyncio
    async def test_list_recent_returns_emails(self, tool):
        tool._get_token = AsyncMock(return_value="fake_token")

        # Mock: list returns 2 messages, then fetch metadata for each
        list_resp = AsyncMock(status=200)
        list_resp.json = AsyncMock(return_value=SAMPLE_MESSAGE_LIST)

        meta_resp_1 = AsyncMock(status=200)
        meta_resp_1.json = AsyncMock(return_value=SAMPLE_MESSAGE_METADATA)

        meta_resp_2 = AsyncMock(status=200)
        meta_resp_2.json = AsyncMock(return_value=SAMPLE_MESSAGE_METADATA_READ)

        mock_cls = _mock_aiohttp_get([list_resp, meta_resp_1, meta_resp_2])

        with patch("tools.gmail.aiohttp.ClientSession", mock_cls):
            result = await tool.execute(action="list_recent")

            assert "2 email(s)" in result
            assert "Amazon" in result
            assert "Your order has shipped" in result
            assert "[UNREAD]" in result
            assert "Alice" in result

    @pytest.mark.asyncio
    async def test_list_recent_empty(self, tool):
        tool._get_token = AsyncMock(return_value="fake_token")

        list_resp = AsyncMock(status=200)
        list_resp.json = AsyncMock(return_value=SAMPLE_MESSAGE_LIST_EMPTY)

        mock_cls = _mock_aiohttp_get([list_resp])

        with patch("tools.gmail.aiohttp.ClientSession", mock_cls):
            result = await tool.execute(action="list_recent")
            assert "No emails found" in result

    @pytest.mark.asyncio
    async def test_list_recent_401(self, tool):
        tool._get_token = AsyncMock(return_value="fake_token")

        list_resp = AsyncMock(status=401)

        mock_cls = _mock_aiohttp_get([list_resp])

        with patch("tools.gmail.aiohttp.ClientSession", mock_cls):
            result = await tool.execute(action="list_recent")
            assert "expired" in result.lower()


# ---------------------------------------------------------------------------
# Tests: search_emails
# ---------------------------------------------------------------------------


class TestSearchEmails:
    """Tests for the search_emails action."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self, tool):
        tool._get_token = AsyncMock(return_value="fake_token")

        list_resp = AsyncMock(status=200)
        list_resp.json = AsyncMock(return_value={
            "messages": [{"id": "msg_001", "threadId": "thread_001"}],
        })

        meta_resp = AsyncMock(status=200)
        meta_resp.json = AsyncMock(return_value=SAMPLE_MESSAGE_METADATA)

        mock_cls = _mock_aiohttp_get([list_resp, meta_resp])

        with patch("tools.gmail.aiohttp.ClientSession", mock_cls):
            result = await tool.execute(action="search_emails", query="from:amazon")

            assert "1 email(s)" in result
            assert "Amazon" in result

    @pytest.mark.asyncio
    async def test_search_no_results(self, tool):
        tool._get_token = AsyncMock(return_value="fake_token")

        list_resp = AsyncMock(status=200)
        list_resp.json = AsyncMock(return_value={})

        mock_cls = _mock_aiohttp_get([list_resp])

        with patch("tools.gmail.aiohttp.ClientSession", mock_cls):
            result = await tool.execute(action="search_emails", query="from:nobody")
            assert "No emails matching" in result

    @pytest.mark.asyncio
    async def test_search_missing_query(self, tool):
        tool._get_token = AsyncMock(return_value="fake_token")
        result = await tool.execute(action="search_emails")
        assert "provide a search query" in result.lower()


# ---------------------------------------------------------------------------
# Tests: read_email
# ---------------------------------------------------------------------------


class TestReadEmail:
    """Tests for the read_email action."""

    @pytest.mark.asyncio
    async def test_read_plain_text_email(self, tool):
        tool._get_token = AsyncMock(return_value="fake_token")

        msg_resp = AsyncMock(status=200)
        msg_resp.json = AsyncMock(return_value=SAMPLE_FULL_MESSAGE_PLAIN)

        mock_cls = _mock_aiohttp_get([msg_resp])

        with patch("tools.gmail.aiohttp.ClientSession", mock_cls):
            result = await tool.execute(action="read_email", message_id="msg_001")

            assert "Flight Confirmation" in result
            assert "Airline" in result
            assert "flight is confirmed" in result
            assert "Feb 10" in result

    @pytest.mark.asyncio
    async def test_read_multipart_email(self, tool):
        tool._get_token = AsyncMock(return_value="fake_token")

        msg_resp = AsyncMock(status=200)
        msg_resp.json = AsyncMock(return_value=SAMPLE_FULL_MESSAGE_MULTIPART)

        mock_cls = _mock_aiohttp_get([msg_resp])

        with patch("tools.gmail.aiohttp.ClientSession", mock_cls):
            result = await tool.execute(action="read_email", message_id="msg_002")

            # Should prefer plain text over HTML
            assert "flight is confirmed" in result
            assert "<html>" not in result

    @pytest.mark.asyncio
    async def test_read_email_not_found(self, tool):
        tool._get_token = AsyncMock(return_value="fake_token")

        msg_resp = AsyncMock(status=404)

        mock_cls = _mock_aiohttp_get([msg_resp])

        with patch("tools.gmail.aiohttp.ClientSession", mock_cls):
            result = await tool.execute(action="read_email", message_id="nonexistent")
            assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_read_missing_message_id(self, tool):
        tool._get_token = AsyncMock(return_value="fake_token")
        result = await tool.execute(action="read_email")
        assert "provide a message_id" in result.lower()


# ---------------------------------------------------------------------------
# Tests: Body Extraction Helpers
# ---------------------------------------------------------------------------


class TestExtractBody:
    """Tests for the _extract_body helper."""

    def test_plain_text_body(self):
        payload = {
            "mimeType": "text/plain",
            "body": {"data": base64.urlsafe_b64encode(b"Hello world").decode()},
        }
        assert _extract_body(payload) == "Hello world"

    def test_html_body_gets_stripped(self):
        html = "<html><body><p>Hello <b>world</b></p></body></html>"
        payload = {
            "mimeType": "text/html",
            "body": {"data": base64.urlsafe_b64encode(html.encode()).decode()},
        }
        result = _extract_body(payload)
        assert "Hello" in result
        assert "world" in result
        assert "<html>" not in result

    def test_multipart_prefers_plain(self):
        plain = base64.urlsafe_b64encode(b"Plain text version").decode()
        html = base64.urlsafe_b64encode(b"<p>HTML version</p>").decode()
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": plain}},
                {"mimeType": "text/html", "body": {"data": html}},
            ],
        }
        assert _extract_body(payload) == "Plain text version"

    def test_multipart_falls_back_to_html(self):
        html = base64.urlsafe_b64encode(b"<p>Only HTML</p>").decode()
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {}},
                {"mimeType": "text/html", "body": {"data": html}},
            ],
        }
        result = _extract_body(payload)
        assert "Only HTML" in result

    def test_empty_body(self):
        payload = {"mimeType": "text/plain", "body": {}}
        assert _extract_body(payload) == "(No body content)"


class TestStripHtml:
    """Tests for the _strip_html helper."""

    def test_removes_tags(self):
        assert _strip_html("<p>Hello</p>") == "Hello"

    def test_removes_style_blocks(self):
        html = "<style>.foo { color: red; }</style><p>Content</p>"
        result = _strip_html(html)
        assert "Content" in result
        assert "color" not in result

    def test_br_to_newline(self):
        assert "\n" in _strip_html("Line1<br>Line2")


class TestParseDateHelper:
    """Tests for the _parse_email_date helper."""

    def test_valid_rfc2822(self):
        result = _parse_email_date("Thu, 06 Feb 2026 10:30:00 +0000")
        assert "Feb 06, 2026" in result
        assert "10:30 AM" in result

    def test_empty_string(self):
        assert _parse_email_date("") == "Unknown date"

    def test_unparseable_falls_back_to_raw(self):
        result = _parse_email_date("some weird date")
        assert result == "some weird date"


# ---------------------------------------------------------------------------
# Tests: Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_unknown_action(self, tool):
        tool._get_token = AsyncMock(return_value="fake_token")
        result = await tool.execute(action="send_email")
        assert "Unknown action" in result

    @pytest.mark.asyncio
    async def test_connection_error(self, tool):
        tool._get_token = AsyncMock(return_value="fake_token")

        mock_cls = MagicMock()
        mock_session = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Connection refused"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=ctx)

        with patch("tools.gmail.aiohttp.ClientSession", mock_cls):
            result = await tool.execute(action="list_recent")
            assert "Error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
