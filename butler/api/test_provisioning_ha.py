"""Tests for the provisioning helpers: Home Assistant and Nextcloud (no network)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from .provisioning import _ha_error, _ha_ws_call, _ocs_error


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


class TestOcsError:
    """Nextcloud OCS v1 replies HTTP 200 even when it refuses a change."""

    def test_success_codes(self):
        assert _ocs_error({"ocs": {"meta": {"statuscode": 100}}}) is None
        assert _ocs_error({"ocs": {"meta": {"statuscode": 200}}}) is None

    def test_refused_password_is_an_error(self):
        data = {"ocs": {"meta": {"statuscode": 403, "message": "Password needs to be at least 10 characters long."}}}
        assert _ocs_error(data) == "Nextcloud OCS error: Password needs to be at least 10 characters long."

    def test_breached_password_message(self):
        data = {"ocs": {"meta": {"statuscode": 403, "message": "Password is present in compromised password list"}}}
        assert "known data breach" in _ocs_error(data)

    def test_missing_meta(self):
        assert _ocs_error({}) == "Nextcloud OCS error: Unknown"
