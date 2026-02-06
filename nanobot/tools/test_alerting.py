"""Tests for alert state management.

Run with: pytest nanobot/tools/test_alerting.py -v

These tests use mocked database responses - no real PostgreSQL required.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from .alerting import AlertStateManager, NotificationDispatcher
from .memory import DatabasePool


@pytest.fixture
def mock_pool():
    """Create a mock database pool."""
    pool = MagicMock(spec=DatabasePool)
    pool.pool = AsyncMock()
    return pool


@pytest.fixture
def alert_manager(mock_pool):
    """Create an AlertStateManager with a mock pool."""
    return AlertStateManager(mock_pool)


class TestAlertStateManager:
    """Tests for AlertStateManager."""

    @pytest.mark.asyncio
    async def test_trigger_new_alert(self, alert_manager, mock_pool):
        """Triggering a new alert returns True."""
        mock_pool.pool.fetchrow = AsyncMock(
            return_value={"inserted": True, "needs_notify": True}
        )

        result = await alert_manager.trigger_alert(
            alert_key="health:jellyfin:down",
            alert_type="service_down",
            severity="critical",
            message="Jellyfin is not responding",
        )

        assert result is True
        mock_pool.pool.fetchrow.assert_called_once()
        call_args = mock_pool.pool.fetchrow.call_args
        assert "health:jellyfin:down" in call_args[0]
        assert "service_down" in call_args[0]

    @pytest.mark.asyncio
    async def test_trigger_duplicate_alert(self, alert_manager, mock_pool):
        """Triggering an already-active alert returns False."""
        mock_pool.pool.fetchrow = AsyncMock(
            return_value={"inserted": False, "needs_notify": False}
        )

        result = await alert_manager.trigger_alert(
            alert_key="health:jellyfin:down",
            alert_type="service_down",
            severity="critical",
            message="Jellyfin is not responding",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_trigger_refired_after_resolve(self, alert_manager, mock_pool):
        """Re-triggering a previously resolved alert returns True."""
        mock_pool.pool.fetchrow = AsyncMock(
            return_value={"inserted": False, "needs_notify": True}
        )

        result = await alert_manager.trigger_alert(
            alert_key="health:jellyfin:down",
            alert_type="service_down",
            severity="critical",
            message="Jellyfin is not responding again",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_trigger_with_metadata(self, alert_manager, mock_pool):
        """Metadata is passed through as JSON."""
        mock_pool.pool.fetchrow = AsyncMock(
            return_value={"inserted": True, "needs_notify": True}
        )

        await alert_manager.trigger_alert(
            alert_key="storage:external:80",
            alert_type="storage_threshold",
            severity="critical",
            message="External drive is 80% full",
            metadata={"percent": 82, "path": "/mnt/external"},
        )

        call_args = mock_pool.pool.fetchrow.call_args[0]
        # The 5th positional arg is the JSON metadata string
        assert '"percent": 82' in call_args[5]

    @pytest.mark.asyncio
    async def test_resolve_active_alert(self, alert_manager, mock_pool):
        """Resolving an active alert returns True."""
        mock_pool.pool.execute = AsyncMock(return_value="UPDATE 1")

        result = await alert_manager.resolve_alert("health:jellyfin:down")

        assert result is True
        mock_pool.pool.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_already_resolved(self, alert_manager, mock_pool):
        """Resolving an already-resolved alert returns False."""
        mock_pool.pool.execute = AsyncMock(return_value="UPDATE 0")

        result = await alert_manager.resolve_alert("health:jellyfin:down")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_active_alerts_all(self, alert_manager, mock_pool):
        """Get all active alerts without filtering."""
        mock_pool.pool.fetch = AsyncMock(return_value=[
            {"id": 1, "alert_key": "health:jellyfin:down", "alert_type": "service_down",
             "severity": "critical", "message": "Jellyfin is down",
             "first_triggered_at": None, "last_triggered_at": None, "metadata": {}},
        ])

        alerts = await alert_manager.get_active_alerts()

        assert len(alerts) == 1
        assert alerts[0]["alert_key"] == "health:jellyfin:down"

    @pytest.mark.asyncio
    async def test_get_active_alerts_filtered(self, alert_manager, mock_pool):
        """Get active alerts filtered by type."""
        mock_pool.pool.fetch = AsyncMock(return_value=[])

        alerts = await alert_manager.get_active_alerts(alert_type="storage_threshold")

        assert len(alerts) == 0
        call_args = mock_pool.pool.fetch.call_args[0]
        assert "storage_threshold" in call_args

    @pytest.mark.asyncio
    async def test_get_unsent_alerts(self, alert_manager, mock_pool):
        """Get alerts that haven't been notified."""
        mock_pool.pool.fetch = AsyncMock(return_value=[
            {"id": 1, "alert_key": "storage:external:80",
             "alert_type": "storage_threshold", "severity": "critical",
             "message": "80% full", "metadata": {}},
        ])

        unsent = await alert_manager.get_unsent_alerts()

        assert len(unsent) == 1
        assert unsent[0]["alert_key"] == "storage:external:80"

    @pytest.mark.asyncio
    async def test_mark_sent(self, alert_manager, mock_pool):
        """Mark an alert as having been notified."""
        mock_pool.pool.execute = AsyncMock()

        await alert_manager.mark_sent(42)

        mock_pool.pool.execute.assert_called_once()
        call_args = mock_pool.pool.execute.call_args[0]
        assert 42 in call_args


class TestNotificationDispatcher:
    """Tests for NotificationDispatcher."""

    @pytest.mark.asyncio
    async def test_dispatch_no_channels(self, alert_manager, mock_pool):
        """With no channels registered, dispatch returns 0."""
        dispatcher = NotificationDispatcher(alert_manager)

        count = await dispatcher.dispatch_pending()

        assert count == 0

    @pytest.mark.asyncio
    async def test_dispatch_with_channel(self, alert_manager, mock_pool):
        """Dispatches unsent alerts through registered channels."""
        mock_pool.pool.fetch = AsyncMock(return_value=[
            {"id": 1, "alert_key": "health:jellyfin:down",
             "alert_type": "service_down", "severity": "critical",
             "message": "Jellyfin is down", "metadata": {}},
        ])
        mock_pool.pool.execute = AsyncMock()

        channel = AsyncMock(return_value=True)
        dispatcher = NotificationDispatcher(alert_manager)
        dispatcher.register_channel(channel)

        count = await dispatcher.dispatch_pending()

        assert count == 1
        channel.assert_called_once()
        # Verify mark_sent was called
        mock_pool.pool.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_channel_failure(self, alert_manager, mock_pool):
        """If channel raises, alert is not marked as sent."""
        mock_pool.pool.fetch = AsyncMock(return_value=[
            {"id": 1, "alert_key": "health:jellyfin:down",
             "alert_type": "service_down", "severity": "critical",
             "message": "Jellyfin is down", "metadata": {}},
        ])

        channel = AsyncMock(side_effect=Exception("Connection failed"))
        dispatcher = NotificationDispatcher(alert_manager)
        dispatcher.register_channel(channel)

        count = await dispatcher.dispatch_pending()

        assert count == 0

    @pytest.mark.asyncio
    async def test_dispatch_multiple_alerts(self, alert_manager, mock_pool):
        """Dispatches all unsent alerts."""
        mock_pool.pool.fetch = AsyncMock(return_value=[
            {"id": 1, "alert_key": "a", "alert_type": "t",
             "severity": "warning", "message": "m1", "metadata": {}},
            {"id": 2, "alert_key": "b", "alert_type": "t",
             "severity": "critical", "message": "m2", "metadata": {}},
        ])
        mock_pool.pool.execute = AsyncMock()

        channel = AsyncMock(return_value=True)
        dispatcher = NotificationDispatcher(alert_manager)
        dispatcher.register_channel(channel)

        count = await dispatcher.dispatch_pending()

        assert count == 2
        assert channel.call_count == 2
