"""System monitoring routes for the PWA Dashboard.

GET /api/system/health  — Service health statuses for all Docker services
GET /api/system/storage — Disk usage for SSD + external drive
GET /api/system/stats   — Basic system metrics (uptime, memory)
"""

from __future__ import annotations

import asyncio
import logging
import platform
from typing import Any

from fastapi import APIRouter, Depends

from tools import ServerHealthTool, StorageMonitorTool, Tool

from ..deps import get_current_user, get_tools

logger = logging.getLogger(__name__)

router = APIRouter()


def _format_bytes(n: int) -> str:
    """Format byte count into a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


@router.get("/system/health")
async def system_health(
    _user_id: str = Depends(get_current_user),
    tools: dict[str, Tool] = Depends(get_tools),
) -> dict[str, Any]:
    """Service health statuses for all monitored services."""
    health_tool = tools.get("server_health")
    if not isinstance(health_tool, ServerHealthTool):
        return {"services": [], "summary": {"total": 0, "healthy": 0}}

    probes = await asyncio.gather(
        *(health_tool._probe(name, svc) for name, svc in health_tool._services.items())
    )

    services = []
    for r in probes:
        services.append({
            "name": r["name"],
            "status": "online" if r["status"] == "healthy" else "offline",
            "stack": r.get("stack", ""),
            "detail": r.get("detail"),
        })

    healthy = sum(1 for s in services if s["status"] == "online")

    return {
        "services": services,
        "summary": {"total": len(services), "healthy": healthy},
    }


@router.get("/system/storage")
async def system_storage(
    _user_id: str = Depends(get_current_user),
    tools: dict[str, Tool] = Depends(get_tools),
) -> dict[str, Any]:
    """Disk usage for SSD and external drive."""
    storage_tool = tools.get("storage_monitor")
    if not isinstance(storage_tool, StorageMonitorTool):
        return {"volumes": []}

    volumes = []

    # External drive
    ext = storage_tool._check_volume(storage_tool._external_path)
    if ext:
        categories = await storage_tool._get_category_sizes()
        volumes.append({
            "name": "External Drive",
            "total": ext["total"],
            "used": ext["used"],
            "free": ext["free"],
            "percent": ext["percent"],
            "totalFormatted": _format_bytes(ext["total"]),
            "usedFormatted": _format_bytes(ext["used"]),
            "freeFormatted": _format_bytes(ext["free"]),
            "categories": {k: {"bytes": v, "formatted": _format_bytes(v)} for k, v in categories.items()},
        })

    # Internal SSD
    ssd = storage_tool._check_volume("/")
    if ssd:
        volumes.append({
            "name": "Internal SSD",
            "total": ssd["total"],
            "used": ssd["used"],
            "free": ssd["free"],
            "percent": ssd["percent"],
            "totalFormatted": _format_bytes(ssd["total"]),
            "usedFormatted": _format_bytes(ssd["used"]),
            "freeFormatted": _format_bytes(ssd["free"]),
        })

    return {"volumes": volumes}


def _read_proc_uptime() -> int | None:
    """Read uptime in seconds from /proc/uptime (Linux only)."""
    try:
        with open("/proc/uptime") as f:
            return int(float(f.read().split()[0]))
    except (FileNotFoundError, ValueError, IndexError):
        return None


def _read_proc_meminfo() -> dict[str, Any] | None:
    """Read memory info from /proc/meminfo (Linux only)."""
    try:
        meminfo: dict[str, int] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip().split()[0]
                    meminfo[key] = int(val) * 1024  # kB → bytes

        total = meminfo.get("MemTotal", 0)
        available = meminfo.get("MemAvailable", 0)
        used = total - available
        return {
            "total": total,
            "used": used,
            "available": available,
            "percent": round(used / total * 100) if total > 0 else 0,
            "totalFormatted": _format_bytes(total),
            "usedFormatted": _format_bytes(used),
        }
    except (FileNotFoundError, ValueError):
        return None


def _format_uptime(seconds: int) -> str:
    """Format uptime seconds into a human-readable string like '14d 3h'."""
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60

    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


@router.get("/system/stats")
async def system_stats(
    _user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Basic system metrics (uptime, memory, platform)."""
    uptime_seconds = _read_proc_uptime()
    memory = _read_proc_meminfo()

    return {
        "platform": platform.system(),
        "architecture": platform.machine(),
        "uptimeSeconds": uptime_seconds,
        "uptimeFormatted": _format_uptime(uptime_seconds) if uptime_seconds else None,
        "memory": memory,
    }
