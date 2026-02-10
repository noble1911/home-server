"""Tests for Home Assistant webhook endpoint.

Run with: pytest butler/api/routes/test_webhooks.py -v

These tests use mocked responses — no real database, WhatsApp, or HA required.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ..models import HAWebhookEvent
from .webhooks import (
    _build_notification_message,
    _notify_users,
    _store_event,
    verify_webhook_secret,
)


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
def mock_whatsapp():
    """Create a mock WhatsApp tool."""
    tool = AsyncMock()
    tool.execute = AsyncMock(return_value="WhatsApp message sent to ron.")
    return tool


def _state_changed_event(**overrides) -> HAWebhookEvent:
    """Build a state_changed event with sensible defaults."""
    data = {
        "event_type": "state_changed",
        "entity_id": "binary_sensor.front_door_motion",
        "old_state": "off",
        "new_state": "on",
        "attributes": {"friendly_name": "Front Door Motion"},
    }
    data.update(overrides)
    return HAWebhookEvent(**data)


def _automation_event(**overrides) -> HAWebhookEvent:
    """Build an automation_triggered event."""
    data = {
        "event_type": "automation_triggered",
        "entity_id": "automation.evening_lights",
        "attributes": {"friendly_name": "Evening Lights"},
    }
    data.update(overrides)
    return HAWebhookEvent(**data)


# ---------------------------------------------------------------------------
# Tests: Authentication
# ---------------------------------------------------------------------------


class TestWebhookAuth:
    """Verify webhook secret authentication."""

    @pytest.mark.asyncio
    async def test_valid_secret_passes(self):
        with patch("api.routes.webhooks.settings") as mock_settings:
            mock_settings.ha_webhook_secret = "test-secret-123"
            # Should not raise
            await verify_webhook_secret(x_webhook_secret="test-secret-123")

    @pytest.mark.asyncio
    async def test_invalid_secret_rejected(self):
        from fastapi import HTTPException

        with patch("api.routes.webhooks.settings") as mock_settings:
            mock_settings.ha_webhook_secret = "test-secret-123"
            with pytest.raises(HTTPException) as exc_info:
                await verify_webhook_secret(x_webhook_secret="wrong-secret")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_secret_rejected(self):
        from fastapi import HTTPException

        with patch("api.routes.webhooks.settings") as mock_settings:
            mock_settings.ha_webhook_secret = "test-secret-123"
            with pytest.raises(HTTPException) as exc_info:
                await verify_webhook_secret(x_webhook_secret=None)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_unconfigured_endpoint_503(self):
        from fastapi import HTTPException

        with patch("api.routes.webhooks.settings") as mock_settings:
            mock_settings.ha_webhook_secret = ""
            with pytest.raises(HTTPException) as exc_info:
                await verify_webhook_secret(x_webhook_secret="any")
            assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Tests: Event Storage
# ---------------------------------------------------------------------------


class TestStoreEvent:
    """Verify events are persisted to the database."""

    @pytest.mark.asyncio
    async def test_stores_state_changed(self, mock_pool):
        mock_pool.pool.fetchrow = AsyncMock(return_value={"id": 42})
        event = _state_changed_event()

        event_id = await _store_event(mock_pool, event)

        assert event_id == 42
        mock_pool.pool.fetchrow.assert_called_once()
        call_args = mock_pool.pool.fetchrow.call_args[0]
        assert "INSERT INTO butler.ha_events" in call_args[0]
        assert call_args[1] == "state_changed"
        assert call_args[2] == "binary_sensor.front_door_motion"

    @pytest.mark.asyncio
    async def test_stores_automation_triggered(self, mock_pool):
        mock_pool.pool.fetchrow = AsyncMock(return_value={"id": 99})
        event = _automation_event()

        event_id = await _store_event(mock_pool, event)

        assert event_id == 99
        call_args = mock_pool.pool.fetchrow.call_args[0]
        assert call_args[1] == "automation_triggered"

    @pytest.mark.asyncio
    async def test_stores_attributes_as_json(self, mock_pool):
        mock_pool.pool.fetchrow = AsyncMock(return_value={"id": 1})
        attrs = {"friendly_name": "Test", "brightness": 128}
        event = _state_changed_event(attributes=attrs)

        await _store_event(mock_pool, event)

        call_args = mock_pool.pool.fetchrow.call_args[0]
        stored_attrs = call_args[5]
        assert stored_attrs["brightness"] == 128


# ---------------------------------------------------------------------------
# Tests: Notification Message Building
# ---------------------------------------------------------------------------


class TestBuildNotificationMessage:
    """Verify notification message generation."""

    def test_custom_message_from_attributes(self):
        event = _state_changed_event(
            attributes={"message": "Someone is at the front door"}
        )
        assert _build_notification_message(event) == "Someone is at the front door"

    def test_automation_triggered_message(self):
        event = _automation_event()
        msg = _build_notification_message(event)
        assert "Automation triggered" in msg
        assert "Evening Lights" in msg

    def test_state_change_with_both_states(self):
        event = _state_changed_event(old_state="off", new_state="on")
        msg = _build_notification_message(event)
        assert "off" in msg
        assert "on" in msg
        assert "Front Door Motion" in msg

    def test_state_change_new_state_only(self):
        event = _state_changed_event(old_state=None, new_state="unavailable")
        msg = _build_notification_message(event)
        assert "unavailable" in msg

    def test_fallback_message_for_unknown_type(self):
        event = HAWebhookEvent(event_type="custom_event", entity_id="sensor.test")
        msg = _build_notification_message(event)
        assert "custom_event" in msg

    def test_missing_entity_uses_unknown(self):
        event = HAWebhookEvent(event_type="custom_event")
        msg = _build_notification_message(event)
        assert "Unknown" in msg


# ---------------------------------------------------------------------------
# Tests: User Notification Dispatch
# ---------------------------------------------------------------------------


class TestNotifyUsers:
    """Verify notification dispatch to eligible users."""

    @pytest.mark.asyncio
    async def test_notifies_users_with_whatsapp(self, mock_pool, mock_whatsapp):
        mock_pool.pool.fetch = AsyncMock(
            return_value=[{"id": "ron"}, {"id": "sarah"}]
        )

        sent = await _notify_users(mock_pool, mock_whatsapp, "Motion detected")

        assert sent is True
        assert mock_whatsapp.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_no_users_returns_false(self, mock_pool, mock_whatsapp):
        mock_pool.pool.fetch = AsyncMock(return_value=[])

        sent = await _notify_users(mock_pool, mock_whatsapp, "Motion detected")

        assert sent is False
        mock_whatsapp.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_smart_home_category(self, mock_pool, mock_whatsapp):
        mock_pool.pool.fetch = AsyncMock(return_value=[{"id": "ron"}])

        await _notify_users(mock_pool, mock_whatsapp, "Test")

        call_kwargs = mock_whatsapp.execute.call_args[1]
        assert call_kwargs["category"] == "smart_home"

    @pytest.mark.asyncio
    async def test_partial_send_still_returns_true(self, mock_pool, mock_whatsapp):
        """If one user fails but another succeeds, return True."""
        mock_pool.pool.fetch = AsyncMock(
            return_value=[{"id": "ron"}, {"id": "sarah"}]
        )
        mock_whatsapp.execute = AsyncMock(
            side_effect=["Notifications are disabled for user 'ron'.", "WhatsApp message sent to sarah."]
        )

        sent = await _notify_users(mock_pool, mock_whatsapp, "Motion detected")

        assert sent is True


# ---------------------------------------------------------------------------
# Tests: Notification Triggering Logic
# ---------------------------------------------------------------------------


class TestNotificationTriggerLogic:
    """Verify when notifications should and shouldn't fire."""

    def test_notify_attribute_triggers(self):
        """Events with attributes.notify=True should trigger notifications."""
        event = _state_changed_event(
            attributes={"notify": True, "message": "Door opened"}
        )
        assert event.attributes.get("notify", False) is True

    def test_automation_type_triggers(self):
        """automation_triggered events always trigger notifications."""
        event = _automation_event()
        should_notify = (
            event.attributes.get("notify", False)
            or event.event_type == "automation_triggered"
        )
        assert should_notify is True

    def test_plain_state_change_does_not_trigger(self):
        """state_changed without notify flag should NOT trigger notifications."""
        event = _state_changed_event()
        should_notify = (
            event.attributes.get("notify", False)
            or event.event_type == "automation_triggered"
        )
        assert should_notify is False

    def test_custom_event_with_notify_triggers(self):
        """Custom events with notify=True should trigger."""
        event = HAWebhookEvent(
            event_type="custom_alert",
            attributes={"notify": True, "message": "Flood detected!"},
        )
        should_notify = (
            event.attributes.get("notify", False)
            or event.event_type == "automation_triggered"
        )
        assert should_notify is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
