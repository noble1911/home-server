"""Media inbox routes — file completed downloads into the library.

GET  /api/media/inbox                 items in Downloads/Complete + what Sonarr/Radarr make of them
POST /api/media/inbox/import          {names: [...]} → Sonarr/Radarr ManualImport (move, or copy if seeding)
POST /api/media/inbox/move            {name, destination} → host-agent move into a library root
GET  /api/media/inbox/jobs            *arr command status + host-agent move jobs
POST /api/media/library/refresh       ask Jellyfin to rescan

All admin-only: these move terabytes around.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import host_agent, media_inbox
from ..deps import get_admin_user

logger = logging.getLogger(__name__)

router = APIRouter()

# Commands we've queued this process lifetime, so /jobs can report on them.
_recent_commands: list[dict[str, Any]] = []


class ImportRequest(BaseModel):
    names: list[str] = Field(min_length=1, max_length=100)


class MoveRequest(BaseModel):
    name: str
    destination: str


@router.get("/media/inbox")
async def inbox(_admin: str = Depends(get_admin_user)) -> dict[str, Any]:
    return await media_inbox.scan()


@router.post("/media/inbox/import")
async def inbox_import(req: ImportRequest, _admin: str = Depends(get_admin_user)) -> dict[str, Any]:
    results = await media_inbox.import_items(req.names)
    for r in results:
        if r.get("commandId"):
            _recent_commands.append({"name": r["name"], "app": r["app"], "commandId": r["commandId"], "mode": r["mode"]})
    del _recent_commands[:-50]
    return {"results": results}


@router.post("/media/inbox/move")
async def inbox_move(req: MoveRequest, _admin: str = Depends(get_admin_user)) -> dict[str, Any]:
    try:
        job = await media_inbox.move_item(req.name, req.destination)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"job": job}


@router.get("/media/inbox/jobs")
async def inbox_jobs(_admin: str = Depends(get_admin_user)) -> dict[str, Any]:
    commands = []
    for c in _recent_commands[-20:]:
        st = await media_inbox.command_status(c["app"], c["commandId"])
        commands.append({**c, **(st or {"status": "unknown"})})
    return {"commands": commands, "moves": await host_agent.get_jobs()}


@router.post("/media/library/refresh")
async def library_refresh(_admin: str = Depends(get_admin_user)) -> dict[str, Any]:
    return {"ok": await media_inbox.refresh_jellyfin()}
