"""Android app devices and their notification socket (#214).

HTTP (user JWT):
    POST   /api/devices            register this phone -> {deviceId, deviceToken, sinceId}
    GET    /api/devices            list the user's phones
    DELETE /api/devices/{id}       unregister (also on logout)

WebSocket (device token, not the login JWT):
    /api/notifications/ws?since=<last id seen>
        Authorization: Device <deviceToken>
    Server -> phone: {"type": "notification", ...} and {"type": "keepalive"}
    Phone -> server: {"type": "ping"} (answered with "pong"); anything else is ignored.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from tools import DatabasePool

from .. import devices
from ..deps import get_current_user, get_db_pool

logger = logging.getLogger(__name__)

router = APIRouter()

# Cloudflare drops a tunnel connection after ~100 s without traffic.
KEEPALIVE_SECONDS = 45
# Refresh last_seen_at at most this often while a socket stays open.
TOUCH_SECONDS = 600


class RegisterDeviceRequest(BaseModel):
    name: str = Field("Android phone", max_length=80)
    platform: str = Field("android", pattern=r"^(android)$")


@router.post("/devices", status_code=201)
async def register_device(
    req: RegisterDeviceRequest,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    created = await devices.register_device(pool, user_id, req.name, req.platform)
    # Start from now: a new phone shouldn't replay the last week of notifications.
    return {**created, "sinceId": await devices.latest_id(pool, user_id)}


@router.get("/devices")
async def get_devices(
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    return {"devices": await devices.list_devices(pool, user_id)}


@router.delete("/devices/{device_id}", status_code=204)
async def delete_device(
    device_id: str,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    if not await devices.unregister_device(pool, user_id, device_id):
        raise HTTPException(404, "Device not found")


def _device_token(ws: WebSocket) -> str:
    auth = ws.headers.get("authorization", "")
    if auth.lower().startswith("device "):
        return auth[7:].strip()
    return ""


@router.websocket("/notifications/ws")
async def notifications_ws(websocket: WebSocket, since: int = 0):
    pool = get_db_pool()
    auth = await devices.authenticate_device(pool, _device_token(websocket))
    if auth is None:
        await websocket.close(code=4401)  # before accept -> handshake refused
        return
    device_id, user_id = auth
    await websocket.accept()
    devices.hub.add(user_id, websocket)
    logger.info("Notification socket open: device=%s user=%s since=%d", device_id, user_id, since)
    loop = asyncio.get_running_loop()
    last_touch = loop.time()
    try:
        for message in await devices.backlog(pool, user_id, since):
            await websocket.send_json(message)
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=KEEPALIVE_SECONDS)
                if isinstance(msg, dict) and msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "keepalive"})
            except ValueError:
                pass  # not JSON: ignore
            if loop.time() - last_touch > TOUCH_SECONDS:
                await devices.touch_device(pool, device_id)
                last_touch = loop.time()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        devices.hub.remove(user_id, websocket)
        logger.info("Notification socket closed: device=%s", device_id)
