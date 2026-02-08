"""FastAPI dependencies for shared resources and authentication.

Resources (db pool, tool instances) are initialized once at startup via the
lifespan handler in server.py, then injected into route handlers via Depends().
"""

from __future__ import annotations

from typing import Annotated

import jwt as pyjwt
from fastapi import Depends, Header, HTTPException

from tools import (
    AlertStateManager,
    DatabasePool,
    EmbeddingService,
    GmailTool,
    GoogleCalendarTool,
    HomeAssistantTool,
    ImmichTool,
    JellyfinTool,
    ListEntitiesByDomainTool,
    PhoneLocationTool,
    RadarrTool,
    ReadarrTool,
    RecallFactsTool,
    RememberFactTool,
    GetUserTool,
    ScheduleTaskTool,
    ServerHealthTool,
    SonarrTool,
    StorageMonitorTool,
    Tool,
    WeatherTool,
    WhatsAppTool,
)

from .scheduler import TaskScheduler

from .auth import decode_user_jwt
from .cleanup import start_cleanup, stop_cleanup
from .config import settings
from .ratelimit import start_ratelimit_cleanup, stop_ratelimit_cleanup

# ── Permission system ────────────────────────────────────────────────
# Tools in ALWAYS_ALLOWED bypass permission checks entirely.
# PERMISSION_TOOL_MAP maps permission group names → tool names.

ALWAYS_ALLOWED_TOOLS: set[str] = {
    "remember_fact", "recall_facts", "get_user",
    "weather", "server_health", "storage_monitor",
}

PERMISSION_TOOL_MAP: dict[str, list[str]] = {
    "media": ["radarr", "readarr", "sonarr", "immich", "jellyfin"],
    "home": ["home_assistant", "list_ha_entities"],
    "location": ["phone_location"],
    "calendar": ["google_calendar"],
    "email": ["gmail"],
    "automation": ["schedule_task"],
    "communication": ["whatsapp"],
}

ALL_PERMISSION_GROUPS: list[str] = sorted(PERMISSION_TOOL_MAP.keys())

DEFAULT_PERMISSIONS: list[str] = ["media", "home"]

# Module-level state, set during lifespan startup
_db_pool: DatabasePool | None = None
_tools: dict[str, Tool] | None = None
_scheduler: TaskScheduler | None = None


async def init_resources() -> None:
    """Initialize database pool and tool instances. Called once at startup."""
    global _db_pool, _tools, _scheduler
    _db_pool = await DatabasePool.create(settings.database_url)

    # Embedding service for semantic memory search (optional)
    embedding_service = EmbeddingService(settings.ollama_url) if settings.ollama_url else None

    _tools = {
        "remember_fact": RememberFactTool(_db_pool, embedding_service),
        "recall_facts": RecallFactsTool(_db_pool, embedding_service),
        "get_user": GetUserTool(_db_pool),
    }

    # Only register HA tools if configured
    if settings.home_assistant_url:
        _tools["home_assistant"] = HomeAssistantTool(
            base_url=settings.home_assistant_url,
            token=settings.home_assistant_token,
        )
        _tools["list_ha_entities"] = ListEntitiesByDomainTool(
            base_url=settings.home_assistant_url,
            token=settings.home_assistant_token,
        )
        _tools["phone_location"] = PhoneLocationTool(
            base_url=settings.home_assistant_url,
            token=settings.home_assistant_token,
        )

    # Only register weather tool if configured
    if settings.openweathermap_api_key:
        _tools["weather"] = WeatherTool(
            api_key=settings.openweathermap_api_key,
        )

    # Only register Radarr tool if configured
    if settings.radarr_url:
        _tools["radarr"] = RadarrTool(
            base_url=settings.radarr_url,
            api_key=settings.radarr_api_key,
        )

    # Only register Readarr tool if configured
    if settings.readarr_url:
        _tools["readarr"] = ReadarrTool(
            base_url=settings.readarr_url,
            api_key=settings.readarr_api_key,
        )

    # Only register Immich tool if configured
    if settings.immich_url:
        _tools["immich"] = ImmichTool(
            base_url=settings.immich_url,
            api_key=settings.immich_api_key,
        )

    # Only register Sonarr tool if configured
    if settings.sonarr_url:
        _tools["sonarr"] = SonarrTool(
            base_url=settings.sonarr_url,
            api_key=settings.sonarr_api_key,
        )

    # Only register Jellyfin tool if configured
    if settings.jellyfin_url:
        _tools["jellyfin"] = JellyfinTool(
            base_url=settings.jellyfin_url,
            api_key=settings.jellyfin_api_key,
        )

    # Only register WhatsApp tool if configured
    if settings.whatsapp_gateway_url:
        _tools["whatsapp"] = WhatsAppTool(
            gateway_url=settings.whatsapp_gateway_url,
            db_pool=_db_pool,
        )

    # Health & storage monitoring (always registered — degrade gracefully)
    alert_manager = AlertStateManager(_db_pool)

    # Collect API keys for services that need authenticated health checks
    api_keys = {}
    if settings.radarr_api_key:
        api_keys["radarr_api_key"] = settings.radarr_api_key
    if settings.sonarr_api_key:
        api_keys["sonarr_api_key"] = settings.sonarr_api_key
    if settings.readarr_api_key:
        api_keys["readarr_api_key"] = settings.readarr_api_key
    if settings.prowlarr_api_key:
        api_keys["prowlarr_api_key"] = settings.prowlarr_api_key
    if settings.home_assistant_token:
        api_keys["ha_token"] = settings.home_assistant_token

    thresholds = tuple(
        int(t) for t in settings.storage_thresholds.split(",") if t.strip()
    )

    _tools["server_health"] = ServerHealthTool(
        db_pool=_db_pool,
        alert_manager=alert_manager,
        api_keys=api_keys,
        timeout=settings.health_check_timeout,
    )
    _tools["storage_monitor"] = StorageMonitorTool(
        db_pool=_db_pool,
        alert_manager=alert_manager,
        external_drive_path=settings.external_drive_path,
        thresholds=thresholds,
    )

    # Schedule task tool (always registered — uses DB only)
    _tools["schedule_task"] = ScheduleTaskTool(_db_pool)

    # Start background scheduler
    _scheduler = TaskScheduler(db_pool=_db_pool, tools=_tools)
    await _scheduler.start()

    # Background cleanup for old conversations and expired facts
    start_cleanup(_db_pool, settings.cleanup_retention_days)

    # Background cleanup for rate limit buckets
    from .server import rate_limit_store  # lazy import to avoid circular dep

    start_ratelimit_cleanup(rate_limit_store)


async def cleanup_resources() -> None:
    """Release resources on shutdown."""
    global _db_pool, _tools, _scheduler
    if _scheduler:
        await _scheduler.stop()
    await stop_ratelimit_cleanup()
    await stop_cleanup()
    if _tools:
        for tool in _tools.values():
            if hasattr(tool, "close"):
                await tool.close()
    if _db_pool:
        await _db_pool.close()


def get_db_pool() -> DatabasePool:
    if _db_pool is None:
        raise HTTPException(503, "Database not initialized")
    return _db_pool


def get_tools() -> dict[str, Tool]:
    if _tools is None:
        raise HTTPException(503, "Tools not initialized")
    return _tools


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Extract user_id from JWT Bearer token in Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")

    token = authorization.removeprefix("Bearer ")
    try:
        payload = decode_user_jwt(token)
        return payload["sub"]
    except pyjwt.InvalidTokenError as e:
        raise HTTPException(401, f"Invalid token: {e}")


async def get_admin_user(
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
) -> str:
    """Require admin role. Returns user_id if admin, raises 403 otherwise."""
    db = pool.pool
    row = await db.fetchrow(
        "SELECT role FROM butler.users WHERE id = $1", user_id
    )
    if not row or row["role"] != "admin":
        raise HTTPException(403, "Admin access required")
    return user_id


async def get_internal_or_user(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> str | None:
    """Accept either JWT (user-facing) or X-API-Key (service-to-service).

    For internal calls (LiveKit Agents), returns None and user_id comes from
    the request body. For PWA calls, returns user_id from JWT.
    """
    if x_api_key and settings.internal_api_key and x_api_key == settings.internal_api_key:
        return None  # Internal call; user_id is in request body

    return await get_current_user(authorization)


async def get_user_tools(
    user_id: str,
    global_tools: dict[str, Tool],
    db_pool: DatabasePool,
) -> dict[str, Tool]:
    """Build a tool set filtered by the user's permissions.

    1. Query butler.users.permissions for the user's allowed groups.
    2. Compute which tool names are allowed (always-allowed + permission groups).
    3. Filter global tools and conditionally add per-user OAuth tools.
    """
    import json as _json

    db = db_pool.pool
    row = await db.fetchval(
        "SELECT permissions FROM butler.users WHERE id = $1", user_id
    )
    user_perms: list[str] = (
        _json.loads(row) if isinstance(row, str) else row
    ) if row is not None else DEFAULT_PERMISSIONS

    # Build the set of allowed tool names
    allowed: set[str] = set(ALWAYS_ALLOWED_TOOLS)
    for perm in user_perms:
        allowed.update(PERMISSION_TOOL_MAP.get(perm, []))

    # Filter global tools
    user_tools = {name: tool for name, tool in global_tools.items() if name in allowed}

    # Add per-user OAuth tools only if user has the corresponding permission
    if settings.google_client_id:
        if "calendar" in user_perms:
            user_tools["google_calendar"] = GoogleCalendarTool(db_pool, user_id)
        if "email" in user_perms:
            user_tools["gmail"] = GmailTool(db_pool, user_id)

    return user_tools
