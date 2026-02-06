"""Tests for server health monitoring tool.

Run with: pytest nanobot/tools/test_server_health.py -v

These tests use mocked HTTP responses - no real services required.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

import aiohttp

from .alerting import AlertStateManager
from .memory import DatabasePool
from .server_health import ServerHealthTool


TEST_SERVICES = {
    "svc-a": {"url": "http://svc-a:80/health", "stack": "test"},
    "svc-b": {"url": "http://svc-b:80/health", "stack": "test"},
    "svc-c": {"url": "http://svc-c:80/health", "stack": "other"},
}


@pytest.fixture
def mock_pool():
    """Create a mock database pool."""
    pool = MagicMock(spec=DatabasePool)
    pool.pool = AsyncMock()
    return pool


@pytest.fixture
def alert_manager(mock_pool):
    """Create an AlertStateManager with a mock pool."""
    mgr = AlertStateManager(mock_pool)
    mgr.trigger_alert = AsyncMock(return_value=True)
    mgr.resolve_alert = AsyncMock(return_value=True)
    mgr.get_active_alerts = AsyncMock(return_value=[])
    return mgr


@pytest.fixture
def tool(mock_pool, alert_manager):
    """Create a ServerHealthTool with test services."""
    return ServerHealthTool(
        db_pool=mock_pool,
        alert_manager=alert_manager,
        services=TEST_SERVICES,
        timeout=2,
    )


def _make_cm(resp):
    """Wrap a mock response in an async context manager (like aiohttp returns)."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _mock_response(status=200):
    """Create a mock aiohttp response with the given status."""
    resp = MagicMock()
    resp.status = status
    return resp


def _all_healthy_session():
    """Session where every .get() returns 200."""
    session = MagicMock()
    session.closed = False
    session.get = MagicMock(return_value=_make_cm(_mock_response(200)))
    return session


class TestServerHealthToolProperties:
    """Test tool interface properties."""

    def test_name(self, tool):
        assert tool.name == "server_health"

    def test_description(self, tool):
        assert "health" in tool.description.lower()

    def test_parameters(self, tool):
        params = tool.parameters
        assert params["type"] == "object"
        assert "action" in params["properties"]
        assert params["required"] == ["action"]

    def test_to_schema(self, tool):
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "server_health"


class TestCheckAll:
    """Tests for check_all action."""

    @pytest.mark.asyncio
    async def test_all_healthy(self, tool, alert_manager):
        """All services returning 200."""
        tool._session = _all_healthy_session()

        result = await tool.execute(action="check_all")

        assert "3/3 healthy" in result
        assert "svc-a" in result
        # All services healthy → resolve_alert called for each
        assert alert_manager.resolve_alert.call_count == 3

    @pytest.mark.asyncio
    async def test_some_down(self, tool, alert_manager):
        """Mix of healthy and unreachable services."""
        def mock_get(url, **kwargs):
            if "svc-b" in url:
                cm = MagicMock()
                cm.__aenter__ = AsyncMock(
                    side_effect=aiohttp.ClientConnectorError(
                        MagicMock(), OSError("Connection refused")
                    )
                )
                cm.__aexit__ = AsyncMock(return_value=False)
                return cm
            return _make_cm(_mock_response(200))

        session = MagicMock()
        session.closed = False
        session.get = mock_get
        tool._session = session

        result = await tool.execute(action="check_all")

        assert "2/3 healthy" in result
        assert "svc-b" in result
        assert "Connection refused" in result
        assert alert_manager.trigger_alert.call_count >= 1

    @pytest.mark.asyncio
    async def test_degraded_service(self, tool, alert_manager):
        """Service returning HTTP 500."""
        def mock_get(url, **kwargs):
            if "svc-c" in url:
                return _make_cm(_mock_response(500))
            return _make_cm(_mock_response(200))

        session = MagicMock()
        session.closed = False
        session.get = mock_get
        tool._session = session

        result = await tool.execute(action="check_all")

        assert "2/3 healthy" in result
        assert "Degraded" in result
        assert "svc-c" in result

    @pytest.mark.asyncio
    async def test_timeout(self, tool, alert_manager):
        """Service that times out."""
        def mock_get(url, **kwargs):
            if "svc-a" in url:
                cm = MagicMock()
                cm.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
                cm.__aexit__ = AsyncMock(return_value=False)
                return cm
            return _make_cm(_mock_response(200))

        session = MagicMock()
        session.closed = False
        session.get = mock_get
        tool._session = session

        result = await tool.execute(action="check_all")

        assert "2/3 healthy" in result
        assert "Timeout" in result


class TestCheckService:
    """Tests for check_service action."""

    @pytest.mark.asyncio
    async def test_healthy_service(self, tool, alert_manager):
        """Check a single healthy service."""
        tool._session = _all_healthy_session()

        result = await tool.execute(action="check_service", service="svc-a")

        assert "healthy" in result
        assert "svc-a" in result
        alert_manager.resolve_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_service(self, tool):
        """Check a service that doesn't exist."""
        result = await tool.execute(action="check_service", service="nonexistent")

        assert "Unknown service" in result
        assert "svc-a" in result  # Lists available services

    @pytest.mark.asyncio
    async def test_missing_service_param(self, tool):
        """Missing service parameter."""
        result = await tool.execute(action="check_service")

        assert "required" in result.lower()

    @pytest.mark.asyncio
    async def test_down_service_triggers_alert(self, tool, alert_manager):
        """Down service triggers an alert."""
        def mock_get(url, **kwargs):
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(
                side_effect=aiohttp.ClientConnectorError(
                    MagicMock(), OSError("Connection refused")
                )
            )
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        session = MagicMock()
        session.closed = False
        session.get = mock_get
        tool._session = session

        result = await tool.execute(action="check_service", service="svc-a")

        assert "unreachable" in result
        alert_manager.trigger_alert.assert_called_once()
        call_kwargs = alert_manager.trigger_alert.call_args[1]
        assert call_kwargs["alert_key"] == "health:svc-a:down"


class TestGetAlerts:
    """Tests for get_alerts action."""

    @pytest.mark.asyncio
    async def test_no_alerts(self, tool, alert_manager):
        """No active alerts."""
        result = await tool.execute(action="get_alerts")

        assert "No active health alerts" in result

    @pytest.mark.asyncio
    async def test_with_alerts(self, tool, alert_manager):
        """Active alerts returned."""
        alert_manager.get_active_alerts = AsyncMock(return_value=[
            {"severity": "critical", "message": "svc-b (test-stack): Connection refused"},
        ])

        result = await tool.execute(action="get_alerts")

        assert "1" in result
        assert "CRITICAL" in result
        assert "svc-b" in result


class TestUnknownAction:
    """Test invalid action handling."""

    @pytest.mark.asyncio
    async def test_unknown_action(self, tool):
        result = await tool.execute(action="bad_action")
        assert "Unknown action" in result


class TestApiKeyResolution:
    """Test that API key placeholders are resolved correctly."""

    def test_resolve_with_keys(self, mock_pool, alert_manager):
        """Services with API keys are included when keys are provided."""
        services = {
            "radarr": {
                "url": "http://radarr:7878/api/v3/health",
                "stack": "media",
                "headers": {"X-Api-Key": "{radarr_api_key}"},
            },
            "plain": {
                "url": "http://plain:80",
                "stack": "test",
            },
        }
        tool = ServerHealthTool(
            db_pool=mock_pool,
            alert_manager=alert_manager,
            api_keys={"radarr_api_key": "secret123"},
            services=services,
        )
        assert "radarr" in tool._services
        assert tool._services["radarr"]["headers"]["X-Api-Key"] == "secret123"
        assert "plain" in tool._services

    def test_resolve_without_keys(self, mock_pool, alert_manager):
        """Services with missing API keys are excluded."""
        services = {
            "radarr": {
                "url": "http://radarr:7878/api/v3/health",
                "stack": "media",
                "headers": {"X-Api-Key": "{radarr_api_key}"},
            },
            "plain": {
                "url": "http://plain:80",
                "stack": "test",
            },
        }
        tool = ServerHealthTool(
            db_pool=mock_pool,
            alert_manager=alert_manager,
            api_keys={},
            services=services,
        )
        assert "radarr" not in tool._services
        assert "plain" in tool._services
