"""Tests for the Home Assistant provisioning helpers (no network)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from .provisioning import _ha_error, _ha_ws_call


class TestHaError:
    def test_strips_echoed_values(self):
        msg = {"error": {"code": "invalid_format",
                         "message": "extra keys not allowed @ data['password']. Got 'hunter2'\nmore"}}
        out = _ha_error(msg)
        assert "hunter2" not in out
        assert out == "extra keys not allowed @ data['password']"

    def test_falls_back_to_code_then_unknown(self):
        assert _ha_error({"error": {"code": "not_found"}}) == "not_found"
        assert _ha_error({}) == "unknown error"


class TestHaWsCall:
    @pytest.mark.asyncio
    async def test_skips_unrelated_events_and_returns_result(self):
        ws = MagicMock()
        ws.send_json = AsyncMock()
        ws.receive_json = AsyncMock(side_effect=[
            {"id": 7, "type": "event"},               # unrelated
            {"id": 1, "success": True, "result": {"user": {"id": "abc"}}},
        ])
        result = await _ha_ws_call(ws, 1, {"type": "config/auth/create", "name": "x"})
        assert result == {"user": {"id": "abc"}}
        ws.send_json.assert_awaited_once_with({"id": 1, "type": "config/auth/create", "name": "x"})

    @pytest.mark.asyncio
    async def test_raises_scrubbed_error(self):
        ws = MagicMock()
        ws.send_json = AsyncMock()
        ws.receive_json = AsyncMock(return_value={
            "id": 1, "success": False,
            "error": {"message": "extra keys not allowed @ data['username']. Got 'bob'"},
        })
        with pytest.raises(RuntimeError) as ei:
            await _ha_ws_call(ws, 1, {"type": "x"})
        assert "bob" not in str(ei.value)
