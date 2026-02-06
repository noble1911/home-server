"""FastAPI dependencies for shared resources and authentication.

Resources (db pool, tool instances) are initialized once at startup via the
lifespan handler in server.py, then injected into route handlers via Depends().
"""

from __future__ import annotations

from typing import Annotated

import jwt as pyjwt
from fastapi import Depends, Header, HTTPException

from tools import (
    DatabasePool,
    GoogleCalendarTool,
    HomeAssistantTool,
    ListEntitiesByDomainTool,
    RecallFactsTool,
    RememberFactTool,
    GetUserTool,
    Tool,
    WeatherTool,
)

from .auth import decode_user_jwt
from .config import settings

# Module-level state, set during lifespan startup
_db_pool: DatabasePool | None = None
_tools: dict[str, Tool] | None = None


async def init_resources() -> None:
    """Initialize database pool and tool instances. Called once at startup."""
    global _db_pool, _tools
    _db_pool = await DatabasePool.create(settings.database_url)

    _tools = {
        "remember_fact": RememberFactTool(_db_pool),
        "recall_facts": RecallFactsTool(_db_pool),
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

    # Only register weather tool if configured
    if settings.openweathermap_api_key:
        _tools["weather"] = WeatherTool(
            api_key=settings.openweathermap_api_key,
        )


async def cleanup_resources() -> None:
    """Release resources on shutdown."""
    global _db_pool, _tools
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


def get_user_tools(
    user_id: str,
    global_tools: dict[str, Tool],
    db_pool: DatabasePool,
) -> dict[str, Tool]:
    """Merge global tools with per-user tools (e.g., Google Calendar).

    Per-user tools are created per-request because they depend on
    the authenticated user's OAuth tokens. Only registered when
    the corresponding service is configured.
    """
    user_tools = dict(global_tools)
    if settings.google_client_id:
        user_tools["google_calendar"] = GoogleCalendarTool(db_pool, user_id)
    return user_tools
