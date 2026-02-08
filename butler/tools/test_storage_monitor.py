"""Tests for storage monitoring tool.

Run with: pytest butler/tools/test_storage_monitor.py -v

These tests use mocked filesystem calls - no real drives required.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from .alerting import AlertStateManager
from .memory import DatabasePool
from .storage_monitor import StorageMonitorTool, _format_bytes


@pytest.fixture
def mock_pool():
    """Create a mock database pool."""
    pool = MagicMock(spec=DatabasePool)
    pool.pool = AsyncMock()
    return pool


@pytest.fixture
def alert_manager(mock_pool):
    """Create an AlertStateManager with mocked methods."""
    mgr = AlertStateManager(mock_pool)
    mgr.trigger_alert = AsyncMock(return_value=True)
    mgr.resolve_alert = AsyncMock(return_value=True)
    mgr.get_active_alerts = AsyncMock(return_value=[])
    return mgr


@pytest.fixture
def tool(mock_pool, alert_manager):
    """Create a StorageMonitorTool with default config."""
    return StorageMonitorTool(
        db_pool=mock_pool,
        alert_manager=alert_manager,
        external_drive_path="/mnt/external",
    )


# Helper: create a mock disk_usage result
def _usage(total_gb: int, used_gb: int):
    """Create a shutil.disk_usage-compatible named tuple."""
    total = total_gb * (1024 ** 3)
    used = used_gb * (1024 ** 3)
    free = total - used
    return MagicMock(total=total, used=used, free=free)


class TestStorageMonitorProperties:
    """Test tool interface properties."""

    def test_name(self, tool):
        assert tool.name == "storage_monitor"

    def test_description(self, tool):
        assert "storage" in tool.description.lower() or "disk" in tool.description.lower()

    def test_parameters(self, tool):
        params = tool.parameters
        assert params["type"] == "object"
        assert "action" in params["properties"]
        assert params["required"] == ["action"]

    def test_to_schema(self, tool):
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "storage_monitor"


class TestFormatBytes:
    """Test the _format_bytes helper."""

    def test_bytes(self):
        assert _format_bytes(500) == "500.0 B"

    def test_kilobytes(self):
        assert _format_bytes(1536) == "1.5 KB"

    def test_megabytes(self):
        assert _format_bytes(10 * 1024 * 1024) == "10.0 MB"

    def test_gigabytes(self):
        assert _format_bytes(5 * 1024 ** 3) == "5.0 GB"

    def test_terabytes(self):
        assert _format_bytes(8 * 1024 ** 4) == "8.0 TB"


class TestCheckExternal:
    """Tests for check_external action."""

    @pytest.mark.asyncio
    async def test_normal_usage(self, tool, alert_manager):
        """External drive at 50% — no alerts triggered."""
        with patch("os.path.exists", return_value=True), \
             patch("shutil.disk_usage", return_value=_usage(8000, 4000)), \
             patch("os.path.isdir", return_value=False):

            result = await tool.execute(action="check_external")

        assert "50%" in result
        assert "OK" in result
        # All thresholds are below 50%, so resolve_alert called for each
        assert alert_manager.resolve_alert.call_count == 3

    @pytest.mark.asyncio
    async def test_warning_threshold(self, tool, alert_manager):
        """External drive at 72% — warning threshold crossed."""
        with patch("os.path.exists", return_value=True), \
             patch("shutil.disk_usage", return_value=_usage(8000, 5760)), \
             patch("os.path.isdir", return_value=False):

            result = await tool.execute(action="check_external")

        assert "72%" in result
        assert "WARNING" in result
        # 70% threshold triggered, 80% and 90% resolved
        trigger_calls = alert_manager.trigger_alert.call_args_list
        triggered_keys = [c[1]["alert_key"] for c in trigger_calls]
        assert "storage:external:70" in triggered_keys

    @pytest.mark.asyncio
    async def test_critical_threshold(self, tool, alert_manager):
        """External drive at 85% — critical threshold crossed."""
        with patch("os.path.exists", return_value=True), \
             patch("shutil.disk_usage", return_value=_usage(8000, 6800)), \
             patch("os.path.isdir", return_value=False):

            result = await tool.execute(action="check_external")

        assert "85%" in result
        assert "CRITICAL" in result
        trigger_calls = alert_manager.trigger_alert.call_args_list
        triggered_keys = [c[1]["alert_key"] for c in trigger_calls]
        assert "storage:external:70" in triggered_keys
        assert "storage:external:80" in triggered_keys

    @pytest.mark.asyncio
    async def test_emergency_threshold(self, tool, alert_manager):
        """External drive at 93% — emergency threshold crossed."""
        with patch("os.path.exists", return_value=True), \
             patch("shutil.disk_usage", return_value=_usage(8000, 7440)), \
             patch("os.path.isdir", return_value=False):

            result = await tool.execute(action="check_external")

        assert "93%" in result
        assert "EMERGENCY" in result

    @pytest.mark.asyncio
    async def test_path_not_found(self, tool):
        """External drive not mounted — graceful error."""
        with patch("os.path.exists", return_value=False):
            result = await tool.execute(action="check_external")

        assert "not available" in result

    @pytest.mark.asyncio
    async def test_category_breakdown(self, tool, alert_manager):
        """Category sizes are included in the output."""
        async def mock_du(path):
            sizes = {
                "Media/Movies": 2_000_000_000_000,
                "Media/TV": 1_500_000_000_000,
            }
            for key, val in sizes.items():
                if key in path:
                    return val
            return 0

        with patch("os.path.exists", return_value=True), \
             patch("shutil.disk_usage", return_value=_usage(8000, 4000)), \
             patch("os.path.isdir", return_value=True):
            tool._du = AsyncMock(side_effect=mock_du)

            result = await tool.execute(action="check_external")

        assert "Movies" in result
        assert "TV Shows" in result


class TestCheckSSD:
    """Tests for check_ssd action."""

    @pytest.mark.asyncio
    async def test_ssd_healthy(self, tool, alert_manager):
        """SSD at 35% — all OK."""
        with patch("os.path.exists", return_value=True), \
             patch("shutil.disk_usage", return_value=_usage(512, 180)):

            result = await tool.execute(action="check_ssd")

        assert "35%" in result
        assert "OK" in result

    @pytest.mark.asyncio
    async def test_ssd_warning(self, tool, alert_manager):
        """SSD at 75% — warning."""
        with patch("os.path.exists", return_value=True), \
             patch("shutil.disk_usage", return_value=_usage(512, 384)):

            result = await tool.execute(action="check_ssd")

        assert "75%" in result
        assert "WARNING" in result


class TestCheckAll:
    """Tests for check_all action."""

    @pytest.mark.asyncio
    async def test_combined_report(self, tool, alert_manager):
        """check_all includes both volumes."""
        call_count = 0
        def mock_exists(path):
            return True

        def mock_disk_usage(path):
            if "external" in path:
                return _usage(8000, 4000)
            return _usage(512, 180)

        with patch("os.path.exists", side_effect=mock_exists), \
             patch("shutil.disk_usage", side_effect=mock_disk_usage), \
             patch("os.path.isdir", return_value=False):

            result = await tool.execute(action="check_all")

        assert "Storage Report" in result
        assert "External Drive" in result
        assert "Internal SSD" in result
        assert "Active Storage Alerts" in result


class TestGetAlerts:
    """Tests for get_alerts action."""

    @pytest.mark.asyncio
    async def test_no_alerts(self, tool, alert_manager):
        """No active storage alerts."""
        result = await tool.execute(action="get_alerts")
        assert "No active storage alerts" in result

    @pytest.mark.asyncio
    async def test_with_alerts(self, tool, alert_manager):
        """Active storage alerts displayed."""
        alert_manager.get_active_alerts = AsyncMock(return_value=[
            {"severity": "warning", "message": "External storage is 72% full (threshold: 70%)"},
        ])

        result = await tool.execute(action="get_alerts")

        assert "1" in result
        assert "WARNING" in result
        assert "72%" in result


class TestUnknownAction:
    """Test invalid action handling."""

    @pytest.mark.asyncio
    async def test_unknown_action(self, tool):
        result = await tool.execute(action="bad_action")
        assert "Unknown action" in result
