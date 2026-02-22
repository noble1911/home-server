"""System monitoring and observability routes.

GET /api/system/health     — Service health statuses for all Docker services
GET /api/system/storage    — Disk usage for SSD + external drive
GET /api/system/stats      — Basic system metrics (uptime, memory)
GET /api/system/tool-usage — Recent tool calls with optional filters (admin only)
"""

from __future__ import annotations

import asyncio
import logging
import platform
from typing import Any

from fastapi import APIRouter, Depends, Query

from tools import DatabasePool, ServerHealthTool, StorageMonitorTool, Tool

from ..config import settings
from ..deps import get_admin_user, get_current_user, get_db_pool, get_tools
from ..models import ToolUsageEntry, ToolUsageResponse, ToolUsageSummary

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
    """Disk usage for SSD and external drive.

    When has_external_drive=False: single "Mac SSD" volume from /mnt/external
    (which IS the Mac SSD via bind mount — statvfs returns host partition stats).

    When has_external_drive=True: "External Drive" from /mnt/external (with
    category breakdown) + "Mac SSD" from /mnt/host-ssd.
    """
    storage_tool = tools.get("storage_monitor")
    if not isinstance(storage_tool, StorageMonitorTool):
        return {"volumes": []}

    volumes = []

    if storage_tool._has_external_drive:
        # Two-volume mode: external drive + Mac SSD
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

        ssd = storage_tool._check_volume(storage_tool._ssd_path)
        if ssd:
            volumes.append({
                "name": "Mac SSD",
                "total": ssd["total"],
                "used": ssd["used"],
                "free": ssd["free"],
                "percent": ssd["percent"],
                "totalFormatted": _format_bytes(ssd["total"]),
                "usedFormatted": _format_bytes(ssd["used"]),
                "freeFormatted": _format_bytes(ssd["free"]),
            })
    else:
        # Single-volume mode: /mnt/external IS the Mac SSD
        ssd = storage_tool._check_volume(storage_tool._external_path)
        if ssd:
            categories = await storage_tool._get_category_sizes()
            volumes.append({
                "name": "Mac SSD",
                "total": ssd["total"],
                "used": ssd["used"],
                "free": ssd["free"],
                "percent": ssd["percent"],
                "totalFormatted": _format_bytes(ssd["total"]),
                "usedFormatted": _format_bytes(ssd["used"]),
                "freeFormatted": _format_bytes(ssd["free"]),
                "categories": {k: {"bytes": v, "formatted": _format_bytes(v)} for k, v in categories.items()},
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
    """Read memory info from /proc/meminfo (Linux only).

    Returns raw VM/container memory values — caller is responsible for
    overlaying the host total if HOST_MEMORY_TOTAL_GB is set.
    """
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


async def _read_cpu_percent() -> float | None:
    """Sample CPU usage % from /proc/stat over 0.5 s.

    Reads the aggregate 'cpu' line twice and computes:
        percent = (1 - Δidle / Δtotal) * 100
    iowait is counted as idle so we measure active CPU pressure only.
    """
    def _sample() -> tuple[int, int] | None:
        try:
            with open("/proc/stat") as f:
                line = f.readline()
            parts = line.split()
            if not parts or parts[0] != "cpu":
                return None
            values = [int(x) for x in parts[1:]]
            # fields: user nice system idle iowait irq softirq steal guest guest_nice
            idle = values[3] + (values[4] if len(values) > 4 else 0)  # idle + iowait
            total = sum(values)
            return idle, total
        except Exception:
            return None

    s1 = _sample()
    if s1 is None:
        return None
    await asyncio.sleep(0.5)
    s2 = _sample()
    if s2 is None:
        return None

    diff_total = s2[1] - s1[1]
    diff_idle = s2[0] - s1[0]
    if diff_total <= 0:
        return 0.0
    return round((1.0 - diff_idle / diff_total) * 100, 1)


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
    """System metrics: uptime, CPU, memory (Docker VM vs Mac host).

    Memory is split into two views:
    - dockerMemory: what /proc/meminfo sees (the OrbStack Linux VM allocation)
    - hostTotalGb: the Mac's physical RAM (from HOST_MEMORY_TOTAL_GB env var)

    CPU is sampled from /proc/stat over 0.5 s — reflects the Linux VM's
    CPU load, which maps directly to overall Docker workload.
    """
    uptime_seconds, cpu_percent, vm_memory = await asyncio.gather(
        asyncio.to_thread(_read_proc_uptime),
        _read_cpu_percent(),
        asyncio.to_thread(_read_proc_meminfo),
    )

    memory_out: dict[str, Any] | None = None
    if vm_memory:
        memory_out = {
            "dockerUsed": vm_memory["used"],
            "dockerTotal": vm_memory["total"],
            "dockerPercent": vm_memory["percent"],
            "dockerUsedFormatted": vm_memory["usedFormatted"],
            "dockerTotalFormatted": vm_memory["totalFormatted"],
            "hostTotalGb": settings.host_memory_total_gb if settings.host_memory_total_gb > 0 else None,
        }

    return {
        "platform": settings.host_platform or platform.system(),
        "architecture": settings.host_architecture or platform.machine(),
        "uptimeSeconds": uptime_seconds,
        "uptimeFormatted": _format_uptime(uptime_seconds) if uptime_seconds else None,
        "cpu": {"percent": cpu_percent} if cpu_percent is not None else None,
        "memory": memory_out,
    }


@router.get("/system/tool-usage", response_model=ToolUsageResponse)
async def get_tool_usage(
    admin_id: str = Depends(get_admin_user),
    pool: DatabasePool = Depends(get_db_pool),
    tool_name: str | None = Query(None, description="Filter by tool name"),
    user_id: str | None = Query(None, description="Filter by user"),
    errors_only: bool = Query(False, description="Show only failed calls"),
    limit: int = Query(50, ge=1, le=500),
):
    """Return recent tool usage logs with optional filters. Admin only."""
    db = pool.pool

    # Build query dynamically based on filters
    conditions: list[str] = []
    params: list = []
    idx = 1

    if tool_name:
        conditions.append(f"tool_name = ${idx}")
        params.append(tool_name)
        idx += 1

    if user_id:
        conditions.append(f"user_id = ${idx}")
        params.append(user_id)
        idx += 1

    if errors_only:
        conditions.append("error IS NOT NULL")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    params.append(limit)

    rows = await db.fetch(
        f"""
        SELECT id, user_id, tool_name, parameters, result_summary,
               error, duration_ms, channel, created_at
        FROM butler.tool_usage
        {where}
        ORDER BY created_at DESC
        LIMIT ${idx}
        """,
        *params,
    )

    entries = [
        ToolUsageEntry(
            id=row["id"],
            userId=row["user_id"],
            toolName=row["tool_name"],
            parameters=row["parameters"] or {},
            resultSummary=row["result_summary"],
            error=row["error"],
            durationMs=row["duration_ms"],
            channel=row["channel"],
            createdAt=row["created_at"].isoformat(),
        )
        for row in rows
    ]

    # Summary stats for the last 24 hours
    summary_row = await db.fetchrow(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE error IS NOT NULL) AS errors,
            COALESCE(ROUND(AVG(duration_ms)), 0) AS avg_duration_ms
        FROM butler.tool_usage
        WHERE created_at > NOW() - INTERVAL '24 hours'
        """
    )

    summary = ToolUsageSummary(
        totalCalls24h=summary_row["total"],
        errorCount24h=summary_row["errors"],
        avgDurationMs=int(summary_row["avg_duration_ms"]),
    )

    return ToolUsageResponse(entries=entries, summary=summary)
