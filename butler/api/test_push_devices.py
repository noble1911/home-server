"""Tests for notification preferences, push fan-out and the app socket (#214).

Run with: pytest butler/api/test_push_devices.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("pywebpush", MagicMock())

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from . import devices, push  # noqa: E402
from .push import alert_title, delivery_mode  # noqa: E402
from .routes import devices as device_routes  # noqa: E402

AT = lambda h, m=0: datetime(2026, 10, 7, h, m, tzinfo=timezone.utc)  # noqa: E731
QUIET = {"enabled": True, "categories": ["reminder", "general"], "quiet_hours_start": "22:00", "quiet_hours_end": "07:00"}


@pytest.fixture
def pool():
    p = MagicMock()
    p.pool = AsyncMock()
    return p


class TestDeliveryMode:
    def test_defaults_send(self):
        assert delivery_mode(None, "general", AT(12)) == "send"

    def test_disabled_skips_everything_except_approvals_and_tests(self):
        prefs = {"enabled": False}
        assert delivery_mode(prefs, "reminder", AT(12)) == "skip"
        assert delivery_mode(prefs, "alert", AT(12)) == "skip"
        assert delivery_mode(prefs, "approval", AT(12)) == "send"
        assert delivery_mode(prefs, "test", AT(12)) == "send"

    def test_switched_off_category_is_skipped(self):
        assert delivery_mode(QUIET, "download", AT(12)) == "skip"
        assert delivery_mode(QUIET, "reminder", AT(12)) == "send"

    def test_system_categories_cant_be_switched_off(self):
        assert delivery_mode(QUIET, "alert", AT(12)) == "send"

    @pytest.mark.parametrize("hour,expected", [(23, "silent"), (3, "silent"), (7, "send"), (21, "send")])
    def test_overnight_quiet_hours_are_silent_not_dropped(self, hour, expected):
        assert delivery_mode(QUIET, "reminder", AT(hour)) == expected

    def test_approvals_ring_even_in_quiet_hours(self):
        assert delivery_mode(QUIET, "approval", AT(23)) == "send"

    def test_bad_quiet_hours_are_ignored(self):
        assert delivery_mode({"quiet_hours_start": "late", "quiet_hours_end": "7"}, "general", AT(3)) == "send"


def test_alert_titles_are_readable():
    assert alert_title("critical", "[CRITICAL] health:jellyfin:down") == "Server problem"
    assert alert_title("warning", "[WARNING] storage:homeserver2:90") == "Storage warning"


class TestSendPushToUser:
    @pytest.mark.asyncio
    async def test_fans_out_to_browsers_and_app(self, pool):
        pool.pool.fetchval.return_value = None  # default prefs
        with patch.object(push, "_send_web_push", AsyncMock(return_value=1)) as web, \
             patch.object(devices, "deliver", AsyncMock(return_value=2)) as app:
            assert await push.send_push_to_user(pool, "ron", "Hi", "Body", "/x", "reminder") == 3
        assert web.call_args.args[-1] is False and app.call_args.args[-1] is False  # not silent

    @pytest.mark.asyncio
    async def test_skipped_category_reaches_nobody(self, pool):
        pool.pool.fetchval.return_value = {"enabled": True, "categories": []}
        with patch.object(push, "_send_web_push", AsyncMock()) as web, patch.object(devices, "deliver", AsyncMock()) as app:
            assert await push.send_push_to_user(pool, "ron", "Hi", "Body", category="download") == 0
        web.assert_not_awaited()
        app.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_app_still_notified_without_vapid_keys(self, pool):
        pool.pool.fetchval.return_value = None
        with patch.object(push.settings, "vapid_private_key", ""), \
             patch.object(devices, "deliver", AsyncMock(return_value=1)):
            assert await push.send_push_to_user(pool, "ron", "Hi", "Body") == 1


class FakeSocket:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def send_json(self, msg):
        if self.fail:
            raise RuntimeError("closed")
        self.sent.append(msg)


class TestHubAndDeliver:
    @pytest.mark.asyncio
    async def test_hub_drops_dead_sockets(self):
        hub = devices.NotificationHub()
        good, dead = FakeSocket(), FakeSocket(fail=True)
        hub.add("ron", good)
        hub.add("ron", dead)
        assert await hub.send("ron", {"type": "notification"}) == 1
        assert hub.connected("ron") == 1 and good.sent

    @pytest.mark.asyncio
    async def test_no_active_devices_means_nothing_queued(self, pool):
        pool.pool.fetchval.return_value = 0
        assert await devices.deliver(pool, "ron", "t", "b", "/", "general", False) == 0
        pool.pool.fetchrow.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_queues_then_pushes_to_open_sockets(self, pool):
        pool.pool.fetchval.return_value = 2
        pool.pool.fetchrow.return_value = {"id": 41, "created_at": AT(12)}
        sock = FakeSocket()
        devices.hub.add("ron", sock)
        try:
            assert await devices.deliver(pool, "ron", "Reminder", "Bins", "/", "reminder", True) == 2
        finally:
            devices.hub.remove("ron", sock)
        assert sock.sent[0] == {
            "type": "notification", "id": 41, "title": "Reminder", "body": "Bins", "url": "/",
            "category": "reminder", "silent": True, "createdAt": AT(12).isoformat(),
        }


def _app(pool):
    app = FastAPI()
    app.include_router(device_routes.router, prefix="/api")
    app.dependency_overrides[device_routes.get_db_pool] = lambda: pool
    app.dependency_overrides[device_routes.get_current_user] = lambda: "ron"
    return app


class TestRoutes:
    def test_register_returns_token_once_and_starts_from_now(self, pool):
        with patch.object(devices, "register_device", AsyncMock(return_value={"deviceId": "d1", "deviceToken": "secret"})), \
             patch.object(devices, "latest_id", AsyncMock(return_value=99)):
            r = TestClient(_app(pool)).post("/api/devices", json={"name": "Pixel 9"})
        assert r.status_code == 201
        assert r.json() == {"deviceId": "d1", "deviceToken": "secret", "sinceId": 99}

    def test_only_android_platform(self, pool):
        r = TestClient(_app(pool)).post("/api/devices", json={"platform": "ios"})
        assert r.status_code == 422

    def test_socket_refuses_bad_token(self, pool):
        with patch.object(device_routes, "get_db_pool", return_value=pool), \
             patch.object(devices, "authenticate_device", AsyncMock(return_value=None)):
            with pytest.raises(WebSocketDisconnect) as e:
                with TestClient(_app(pool)).websocket_connect("/api/notifications/ws", headers={"Authorization": "Device nope"}):
                    pass
        assert e.value.code == 4401

    def test_socket_replays_missed_then_answers_pings(self, pool):
        missed = [{"type": "notification", "id": 6, "title": "Missed"}]
        auth = AsyncMock(return_value=("d1", "ron"))
        with patch.object(device_routes, "get_db_pool", return_value=pool), \
             patch.object(devices, "authenticate_device", auth), \
             patch.object(devices, "backlog", AsyncMock(return_value=missed)) as backlog:
            with TestClient(_app(pool)).websocket_connect(
                "/api/notifications/ws?since=5", headers={"Authorization": "Device tok"},
            ) as ws:
                assert ws.receive_json() == missed[0]
                ws.send_json({"type": "ping"})
                assert ws.receive_json() == {"type": "pong"}
                assert devices.hub.connected("ron") == 1
        auth.assert_awaited_once_with(pool, "tok")
        assert backlog.call_args.args[1:] == ("ron", 5)
        assert devices.hub.connected("ron") == 0  # removed on disconnect
