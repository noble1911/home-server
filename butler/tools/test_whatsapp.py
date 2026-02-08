"""Tests for WhatsApp notification tool.

Run with: pytest butler/tools/test_whatsapp.py -v

These tests use mocked responses — no real WhatsApp gateway or database required.
"""

import json
import time

import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock, patch

from .whatsapp import WhatsAppTool, MAX_MESSAGES_PER_HOUR, VALID_CATEGORIES


# ---------------------------------------------------------------------------
# Sample data for mocking
# ---------------------------------------------------------------------------

SAMPLE_PHONE = "+447123456789"

SAMPLE_PREFS = {
    "enabled": True,
    "categories": ["download", "reminder", "weather", "smart_home", "calendar", "general"],
    "quiet_hours_start": "23:00",
    "quiet_hours_end": "07:00",
}

SAMPLE_PREFS_DISABLED = {
    "enabled": False,
    "categories": [],
}

SAMPLE_PREFS_LIMITED = {
    "enabled": True,
    "categories": ["download"],
}

SAMPLE_SEND_SUCCESS = {"ok": True, "messageId": "true_447123456789@c.us_ABC123"}
SAMPLE_SEND_QUEUED = {"ok": True, "queued": True, "message": "Client disconnected"}
SAMPLE_SEND_ERROR = {"ok": False, "error": "Number not registered on WhatsApp"}

SAMPLE_STATUS_CONNECTED = {
    "connected": True,
    "info": {"pushname": "Butler", "phone": "447123456789"},
    "queueSize": 0,
}
SAMPLE_STATUS_DISCONNECTED = {"connected": False, "info": None, "queueSize": 2}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_pool():
    """Create a mock database pool."""
    pool = MagicMock()
    pool.pool = AsyncMock()
    return pool


@pytest.fixture
def tool(mock_pool):
    """Create a tool instance with test config."""
    return WhatsAppTool(
        gateway_url="http://whatsapp-gateway:3000",
        db_pool=mock_pool,
    )


def _mock_user_row(phone, prefs=None):
    """Create a mock database row with phone and notification_prefs columns."""
    return {
        "phone": phone,
        "notification_prefs": json.dumps(prefs) if prefs else None,
    }


# ---------------------------------------------------------------------------
# Tests: Tool Properties
# ---------------------------------------------------------------------------


class TestWhatsAppToolProperties:
    """Verify tool metadata."""

    def test_name(self, tool):
        assert tool.name == "whatsapp"

    def test_description_mentions_notifications(self, tool):
        assert "notification" in tool.description.lower()

    def test_parameters_has_action(self, tool):
        props = tool.parameters["properties"]
        assert "action" in props
        assert set(props["action"]["enum"]) == {"send_message", "check_status"}

    def test_parameters_has_user_id(self, tool):
        props = tool.parameters["properties"]
        assert "user_id" in props

    def test_parameters_has_message(self, tool):
        props = tool.parameters["properties"]
        assert "message" in props

    def test_parameters_has_category(self, tool):
        props = tool.parameters["properties"]
        assert "category" in props
        # All valid categories should be in the enum
        assert set(props["category"]["enum"]) == VALID_CATEGORIES

    def test_required_fields(self, tool):
        assert tool.parameters["required"] == ["action"]

    def test_to_schema(self, tool):
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "whatsapp"
        assert "parameters" in schema["function"]


# ---------------------------------------------------------------------------
# Tests: Missing Config
# ---------------------------------------------------------------------------


class TestMissingConfig:
    """Error when gateway is not configured."""

    @pytest.mark.asyncio
    async def test_missing_gateway_url(self, mock_pool):
        tool = WhatsAppTool(gateway_url="", db_pool=mock_pool)
        result = await tool.execute(action="send_message", user_id="ron", message="hi")
        assert "must be configured" in result

    @pytest.mark.asyncio
    async def test_missing_db_pool(self):
        tool = WhatsAppTool(gateway_url="http://gateway:3000", db_pool=None)
        result = await tool.execute(action="send_message", user_id="ron", message="hi")
        assert "Database pool" in result


# ---------------------------------------------------------------------------
# Tests: Send Message
# ---------------------------------------------------------------------------


class TestSendMessage:
    """Tests for the send_message action."""

    @pytest.mark.asyncio
    async def test_send_success(self, tool, mock_pool):
        mock_pool.pool.fetchrow = AsyncMock(
            return_value=_mock_user_row(SAMPLE_PHONE, SAMPLE_PREFS)
        )

        with patch("tools.whatsapp.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SEND_SUCCESS)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="send_message",
                user_id="ron",
                message="Dune audiobook is ready",
                category="download",
            )

            assert "sent to ron" in result

    @pytest.mark.asyncio
    async def test_send_queued_when_disconnected(self, tool, mock_pool):
        mock_pool.pool.fetchrow = AsyncMock(
            return_value=_mock_user_row(SAMPLE_PHONE, SAMPLE_PREFS)
        )

        with patch("tools.whatsapp.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SEND_QUEUED)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="send_message",
                user_id="ron",
                message="Test message",
            )

            assert "queued" in result.lower()

    @pytest.mark.asyncio
    async def test_send_missing_user_id(self, tool):
        result = await tool.execute(action="send_message", message="hi")
        assert "user_id is required" in result

    @pytest.mark.asyncio
    async def test_send_missing_message(self, tool):
        result = await tool.execute(action="send_message", user_id="ron")
        assert "message is required" in result

    @pytest.mark.asyncio
    async def test_send_user_not_found(self, tool, mock_pool):
        mock_pool.pool.fetchrow = AsyncMock(return_value=None)

        result = await tool.execute(
            action="send_message", user_id="nobody", message="hi"
        )

        assert "not found" in result

    @pytest.mark.asyncio
    async def test_send_user_no_phone(self, tool, mock_pool):
        mock_pool.pool.fetchrow = AsyncMock(
            return_value=_mock_user_row("", None)
        )

        result = await tool.execute(
            action="send_message", user_id="ron", message="hi"
        )

        assert "phone" in result.lower()

    @pytest.mark.asyncio
    async def test_send_notifications_disabled(self, tool, mock_pool):
        mock_pool.pool.fetchrow = AsyncMock(
            return_value=_mock_user_row(SAMPLE_PHONE, SAMPLE_PREFS_DISABLED)
        )

        result = await tool.execute(
            action="send_message", user_id="ron", message="hi"
        )

        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_send_category_not_opted_in(self, tool, mock_pool):
        mock_pool.pool.fetchrow = AsyncMock(
            return_value=_mock_user_row(SAMPLE_PHONE, SAMPLE_PREFS_LIMITED)
        )

        result = await tool.execute(
            action="send_message",
            user_id="ron",
            message="Rain tomorrow",
            category="weather",
        )

        assert "not opted in" in result

    @pytest.mark.asyncio
    async def test_send_defaults_to_general_category(self, tool, mock_pool):
        mock_pool.pool.fetchrow = AsyncMock(
            return_value=_mock_user_row(SAMPLE_PHONE, SAMPLE_PREFS)
        )

        with patch("tools.whatsapp.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SEND_SUCCESS)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="send_message",
                user_id="ron",
                message="Hello!",
                # No category specified — should default to "general"
            )

            assert "sent to ron" in result

    @pytest.mark.asyncio
    async def test_send_gateway_error(self, tool, mock_pool):
        mock_pool.pool.fetchrow = AsyncMock(
            return_value=_mock_user_row(SAMPLE_PHONE, SAMPLE_PREFS)
        )

        with patch("tools.whatsapp.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 500
            mock_resp.json = AsyncMock(return_value=SAMPLE_SEND_ERROR)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="send_message",
                user_id="ron",
                message="Test",
                category="download",
            )

            assert "Error" in result

    @pytest.mark.asyncio
    async def test_send_quiet_hours_blocks(self, tool, mock_pool):
        """Quiet hours should block the message."""
        prefs_all_day_quiet = {
            "enabled": True,
            "categories": ["general"],
            "quiet_hours_start": "00:00",
            "quiet_hours_end": "23:59",  # All day quiet
        }
        mock_pool.pool.fetchrow = AsyncMock(
            return_value=_mock_user_row(SAMPLE_PHONE, prefs_all_day_quiet)
        )

        result = await tool.execute(
            action="send_message", user_id="ron", message="Test"
        )

        assert "quiet hours" in result.lower()

    @pytest.mark.asyncio
    async def test_send_prefs_as_dict(self, tool, mock_pool):
        """Handle notification_prefs already parsed as dict (not JSON string)."""
        row = {"phone": SAMPLE_PHONE, "notification_prefs": SAMPLE_PREFS}
        mock_pool.pool.fetchrow = AsyncMock(return_value=row)

        with patch("tools.whatsapp.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SEND_SUCCESS)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="send_message",
                user_id="ron",
                message="Test",
                category="download",
            )

            assert "sent to ron" in result


# ---------------------------------------------------------------------------
# Tests: Check Status
# ---------------------------------------------------------------------------


class TestCheckStatus:
    """Tests for the check_status action."""

    @pytest.mark.asyncio
    async def test_status_connected(self, tool):
        with patch("tools.whatsapp.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_STATUS_CONNECTED)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="check_status")

            assert "connected" in result.lower()
            assert "Butler" in result
            assert "ready" in result

    @pytest.mark.asyncio
    async def test_status_disconnected(self, tool):
        with patch("tools.whatsapp.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_STATUS_DISCONNECTED)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="check_status")

            assert "not connected" in result
            assert "QR" in result

    @pytest.mark.asyncio
    async def test_status_gateway_down(self, tool):
        with patch("tools.whatsapp.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 500
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="check_status")

            assert "not responding" in result


# ---------------------------------------------------------------------------
# Tests: Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_unknown_action(self, tool):
        result = await tool.execute(action="explode")
        assert "Unknown action" in result

    @pytest.mark.asyncio
    async def test_connection_error(self, tool, mock_pool):
        mock_pool.pool.fetchrow = AsyncMock(
            return_value=_mock_user_row(SAMPLE_PHONE, SAMPLE_PREFS)
        )

        with patch("tools.whatsapp.aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.post.return_value.__aenter__.side_effect = (
                aiohttp.ClientError("Connection refused")
            )

            result = await tool.execute(
                action="send_message", user_id="ron", message="test"
            )

            assert "Error" in result

    @pytest.mark.asyncio
    async def test_timeout_error(self, tool, mock_pool):
        mock_pool.pool.fetchrow = AsyncMock(
            return_value=_mock_user_row(SAMPLE_PHONE, SAMPLE_PREFS)
        )

        with patch("tools.whatsapp.aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.post.return_value.__aenter__.side_effect = (
                TimeoutError()
            )

            result = await tool.execute(
                action="send_message", user_id="ron", message="test"
            )

            assert "timed out" in result


# ---------------------------------------------------------------------------
# Tests: Rate Limiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Tests for rate limiting logic."""

    @pytest.mark.asyncio
    async def test_rate_limit_allows_under_limit(self, tool, mock_pool):
        """Messages under the limit should succeed."""
        mock_pool.pool.fetchrow = AsyncMock(
            return_value=_mock_user_row(SAMPLE_PHONE, SAMPLE_PREFS)
        )

        with patch("tools.whatsapp.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SEND_SUCCESS)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            # Send 9 messages (under limit of 10)
            for i in range(9):
                result = await tool.execute(
                    action="send_message",
                    user_id="ron",
                    message=f"Message {i}",
                    category="general",
                )
                assert "sent to ron" in result

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_at_limit(self, tool, mock_pool):
        """The 11th message in an hour should be blocked."""
        # Pre-populate rate limits with 10 recent sends
        now = time.time()
        tool._rate_limits["ron"] = [now - i for i in range(MAX_MESSAGES_PER_HOUR)]

        mock_pool.pool.fetchrow = AsyncMock(
            return_value=_mock_user_row(SAMPLE_PHONE, SAMPLE_PREFS)
        )

        result = await tool.execute(
            action="send_message",
            user_id="ron",
            message="One too many",
            category="general",
        )

        assert "Rate limit exceeded" in result

    @pytest.mark.asyncio
    async def test_rate_limit_expires_old_entries(self, tool, mock_pool):
        """Timestamps older than 1 hour should be pruned."""
        # Populate with 10 timestamps from 2 hours ago
        old = time.time() - 7200
        tool._rate_limits["ron"] = [old - i for i in range(MAX_MESSAGES_PER_HOUR)]

        mock_pool.pool.fetchrow = AsyncMock(
            return_value=_mock_user_row(SAMPLE_PHONE, SAMPLE_PREFS)
        )

        with patch("tools.whatsapp.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SEND_SUCCESS)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="send_message",
                user_id="ron",
                message="Should work now",
                category="general",
            )

            assert "sent to ron" in result
            # Old entries should have been pruned
            assert len(tool._rate_limits["ron"]) == 1


# ---------------------------------------------------------------------------
# Tests: Quiet Hours
# ---------------------------------------------------------------------------


class TestQuietHours:
    """Tests for quiet hours logic."""

    def test_is_quiet_hours_overnight_range(self):
        """23:00-07:00 should be quiet at midnight."""
        with patch("tools.whatsapp.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 0
            mock_now.minute = 30
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            assert WhatsAppTool._is_quiet_hours("23:00", "07:00") is True

    def test_is_quiet_hours_same_day_range(self):
        """09:00-17:00 should be quiet at noon."""
        with patch("tools.whatsapp.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 12
            mock_now.minute = 0
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            assert WhatsAppTool._is_quiet_hours("09:00", "17:00") is True

    def test_not_quiet_hours(self):
        """23:00-07:00 should NOT be quiet at 14:00."""
        with patch("tools.whatsapp.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 14
            mock_now.minute = 0
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            assert WhatsAppTool._is_quiet_hours("23:00", "07:00") is False

    def test_invalid_quiet_hours_format(self):
        """Invalid format should return False (no crash)."""
        assert WhatsAppTool._is_quiet_hours("invalid", "07:00") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
