"""Storage monitoring tool for Butler.

Checks disk usage on the external drive and internal SSD, with
configurable alert thresholds that fire once per crossing.

Usage:
    alert_mgr = AlertStateManager(db_pool)
    tool = StorageMonitorTool(db_pool=db_pool, alert_manager=alert_mgr)
    result = await tool.execute(action="check_all")

    # When shutting down (no resources to release, but for consistency)
    await tool.close()
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from typing import Any

from .alerting import AlertStateManager
from .base import Tool
from .memory import DatabasePool

logger = logging.getLogger(__name__)

# Known category directories under the external drive
# (relative to the external drive mount point)
EXTERNAL_CATEGORIES = {
    "Movies": "Media/Movies",
    "TV Shows": "Media/TV",
    "Photos": "Photos/Immich",
    "eBooks": "Books/eBooks",
    "Audiobooks": "Books/Audiobooks",
    "Downloads": "Downloads",
    "Documents": "Documents/Nextcloud",
    "Backups": "Backups",
}

DEFAULT_THRESHOLDS = (70, 80, 90)

SEVERITY_MAP = {70: "warning", 80: "critical", 90: "emergency"}


def _format_bytes(n: int) -> str:
    """Format byte count into a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class StorageMonitorTool(Tool):
    """Monitor disk usage and alert on threshold crossings.

    Checks the external drive (8 TB) and internal SSD, firing
    alerts when configurable percentage thresholds are exceeded.
    """

    def __init__(
        self,
        db_pool: DatabasePool,
        alert_manager: AlertStateManager,
        external_drive_path: str = "/mnt/external",
        thresholds: tuple[int, ...] = DEFAULT_THRESHOLDS,
    ):
        """Initialize the storage monitor tool.

        Args:
            db_pool: Shared database pool (kept for consistency).
            alert_manager: AlertStateManager for deduplication.
            external_drive_path: Mount path for the external drive inside the container.
            thresholds: Percentage thresholds that trigger alerts (ascending).
        """
        self._db_pool = db_pool
        self._alert_manager = alert_manager
        self._external_path = external_drive_path
        self._thresholds = tuple(sorted(thresholds))

    async def close(self) -> None:
        """No resources to release."""

    # -- Tool interface -------------------------------------------------------

    @property
    def name(self) -> str:
        return "storage_monitor"

    @property
    def description(self) -> str:
        return (
            "Monitor disk usage on the home server. "
            "Use 'check_all' for a full report, 'check_external' for the "
            "external drive with per-category breakdown, 'check_ssd' for "
            "internal SSD, or 'get_alerts' for active storage alerts."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["check_all", "check_external", "check_ssd", "get_alerts"],
                    "description": (
                        "check_all: Report on all volumes. "
                        "check_external: External drive usage with category breakdown. "
                        "check_ssd: Internal SSD usage. "
                        "get_alerts: Show active storage alerts."
                    ),
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")

        try:
            if action == "check_all":
                return await self._check_all()
            elif action == "check_external":
                return await self._check_external()
            elif action == "check_ssd":
                return await self._check_ssd()
            elif action == "get_alerts":
                return await self._get_alerts()
            else:
                return f"Error: Unknown action '{action}'. Use check_all, check_external, check_ssd, or get_alerts."
        except Exception as e:
            logger.exception("Storage check failed")
            return f"Error running storage check: {e}"

    # -- Internals ------------------------------------------------------------

    def _check_volume(self, path: str) -> dict[str, Any] | None:
        """Get disk usage for a path.  Returns None if path doesn't exist."""
        if not os.path.exists(path):
            return None
        usage = shutil.disk_usage(path)
        percent = round(usage.used / usage.total * 100) if usage.total > 0 else 0
        return {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": percent,
        }

    async def _get_category_sizes(self) -> dict[str, int]:
        """Get sizes of known category directories via du -s."""
        sizes: dict[str, int] = {}
        tasks = []

        for label, rel_path in EXTERNAL_CATEGORIES.items():
            full_path = os.path.join(self._external_path, rel_path)
            if os.path.isdir(full_path):
                tasks.append((label, full_path))

        results = await asyncio.gather(
            *[self._du(path) for _, path in tasks],
            return_exceptions=True,
        )

        for (label, _), result in zip(tasks, results):
            if isinstance(result, int):
                sizes[label] = result

        return sizes

    async def _du(self, path: str) -> int:
        """Run ``du -sb <path>`` and return total bytes."""
        proc = await asyncio.create_subprocess_exec(
            "du", "-sb", path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return 0
        # du output: "<bytes>\t<path>\n"
        parts = stdout.decode().strip().split("\t")
        return int(parts[0]) if parts else 0

    def _severity_for(self, percent: int) -> str:
        """Return the severity for a given usage percentage."""
        severity = "info"
        for threshold in self._thresholds:
            if percent >= threshold:
                severity = SEVERITY_MAP.get(threshold, "warning")
        return severity

    def _status_label(self, percent: int) -> str:
        """Return a human-readable status label for a given usage percentage."""
        for threshold in reversed(self._thresholds):
            if percent >= threshold:
                sev = SEVERITY_MAP.get(threshold, "WARNING")
                return sev.upper()
        return "OK"

    async def _update_threshold_alerts(
        self, volume_name: str, percent: int,
    ) -> None:
        """Trigger or resolve alerts for each configured threshold."""
        for threshold in self._thresholds:
            alert_key = f"storage:{volume_name}:{threshold}"
            if percent >= threshold:
                severity = SEVERITY_MAP.get(threshold, "warning")
                await self._alert_manager.trigger_alert(
                    alert_key=alert_key,
                    alert_type="storage_threshold",
                    severity=severity,
                    message=(
                        f"{volume_name.capitalize()} storage is {percent}% full "
                        f"(threshold: {threshold}%)"
                    ),
                    metadata={"volume": volume_name, "percent": percent,
                              "threshold": threshold},
                )
            else:
                await self._alert_manager.resolve_alert(alert_key)

    async def _check_external(self) -> str:
        """Check external drive usage with category breakdown."""
        usage = self._check_volume(self._external_path)
        if usage is None:
            return (
                f"External drive not available at {self._external_path}. "
                "Is the volume mounted?"
            )

        await self._update_threshold_alerts("external", usage["percent"])

        lines = [
            f"External Drive: {_format_bytes(usage['used'])} / "
            f"{_format_bytes(usage['total'])} ({usage['percent']}%) "
            f"— {self._status_label(usage['percent'])}",
        ]

        # Category breakdown
        categories = await self._get_category_sizes()
        if categories:
            parts = [f"{label}: {_format_bytes(size)}"
                     for label, size in sorted(categories.items(),
                                               key=lambda x: x[1], reverse=True)]
            lines.append("  " + " | ".join(parts))

        return "\n".join(lines)

    async def _check_ssd(self) -> str:
        """Check internal SSD usage."""
        # Inside Docker, "/" is the container's overlay filesystem.
        # If /mnt/host is mounted, use that for host SSD stats.
        # Otherwise fall back to "/" which shows container disk usage.
        usage = self._check_volume("/")
        if usage is None:
            return "Could not determine SSD usage."

        await self._update_threshold_alerts("ssd", usage["percent"])

        return (
            f"Internal SSD: {_format_bytes(usage['used'])} / "
            f"{_format_bytes(usage['total'])} ({usage['percent']}%) "
            f"— {self._status_label(usage['percent'])}"
        )

    async def _check_all(self) -> str:
        """Check all volumes."""
        parts = []

        ext = await self._check_external()
        parts.append(ext)

        ssd = await self._check_ssd()
        parts.append(ssd)

        # Alert summary
        alerts = await self._alert_manager.get_active_alerts("storage_threshold")
        parts.append(f"\nActive Storage Alerts: {len(alerts)}")

        return "Storage Report:\n  " + "\n  ".join(parts)

    async def _get_alerts(self) -> str:
        """List all active storage alerts."""
        alerts = await self._alert_manager.get_active_alerts("storage_threshold")
        if not alerts:
            return "No active storage alerts."

        lines = [f"Active Storage Alerts ({len(alerts)}):"]
        for a in alerts:
            lines.append(f"  [{a['severity'].upper()}] {a['message']}")
        return "\n".join(lines)
