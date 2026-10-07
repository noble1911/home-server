"""Tests for the admin-selected chat model and refusal fallback (#215). No network.

Run with: pytest butler/api/test_model_settings.py -v
"""

from __future__ import annotations

from types import SimpleNamespace as Block
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from . import llm, model_settings
from .llm import FALLBACK_BETA, _ToolRouter, _request_kwargs, _turn_content, chat_with_tools
from .routes import admin as admin_routes


@pytest.fixture(autouse=True)
def reset_choice():
    model_settings._selected = None
    yield
    model_settings._selected = None


@pytest.fixture
def pool():
    p = MagicMock()
    p.pool = AsyncMock()
    return p


class TestSetting:
    def test_defaults_to_the_server_model(self):
        with patch.object(model_settings.settings, "anthropic_model", "claude-opus-5"):
            assert model_settings.current_model() == "claude-opus-5"
            assert model_settings.selected_model() is None

    @pytest.mark.asyncio
    async def test_choose_then_go_back_to_default(self, pool):
        assert await model_settings.set_model(pool, "claude-sonnet-5-5", "ron") == "claude-sonnet-5-5"
        assert pool.pool.execute.call_args.args[1:] == ("chat_model", "claude-sonnet-5-5", "ron")
        assert model_settings.current_model() == "claude-sonnet-5-5"
        with patch.object(model_settings.settings, "anthropic_model", "claude-opus-5"):
            assert await model_settings.set_model(pool, None, "ron") == "claude-opus-5"
        assert "DELETE" in pool.pool.execute.call_args.args[0]

    @pytest.mark.asyncio
    async def test_unknown_models_are_refused(self, pool):
        with pytest.raises(ValueError):
            await model_settings.set_model(pool, "claude-instant-1", "ron")
        pool.pool.execute.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("saved,expected", [("claude-opus-5-5", "claude-opus-5-5"), ("gpt-4", None), (None, None)])
    async def test_load(self, pool, saved, expected):
        pool.pool.fetchval.return_value = saved
        await model_settings.load(pool)
        assert model_settings.selected_model() == expected

    @pytest.mark.asyncio
    async def test_load_survives_a_db_error(self, pool):
        pool.pool.fetchval.side_effect = RuntimeError("no table yet")
        await model_settings.load(pool)
        assert model_settings.selected_model() is None


class TestRouterModel:
    def test_router_uses_the_choice(self):
        model_settings._selected = "claude-sonnet-5-5"
        with patch.object(llm.settings, "routing_model", ""):
            assert _ToolRouter({}, []).model == "claude-sonnet-5-5"

    def test_pinned_models_are_untouched(self):
        model_settings._selected = "claude-sonnet-5-5"
        assert _ToolRouter({}, [], model_override="claude-haiku-4-5").model == "claude-haiku-4-5"


class TestRequestOptions:
    @pytest.mark.parametrize("model", ["claude-opus-5-5", "claude-sonnet-5-5", "claude-opus-5"])
    def test_refusal_fallback_on_classifier_models(self, model):
        kw = _request_kwargs(model)
        assert kw["fallbacks"] == "default" and kw["betas"] == [FALLBACK_BETA]
        assert "effort" in kw["output_config"]

    def test_no_fallback_elsewhere(self):
        assert _request_kwargs("claude-haiku-4-5") == {}
        assert "fallbacks" not in _request_kwargs("claude-opus-4-8")


def _b(type_, **kw):
    return Block(type=type_, **kw)


class TestTurnContent:
    def test_unchanged_without_a_fallback(self):
        content = [_b("text", text="hi"), _b("tool_use", id="t1", name="weather", input={})]
        assert _turn_content(content) == content

    def test_declined_attempt_is_trimmed(self):
        content = [
            _b("thinking", thinking=""),
            _b("text", text="Let me check"),
            _b("server_tool_use", id="s1", name="web_search", input={}),
            _b("web_search_tool_result", tool_use_id="s1", content=[]),
            _b("server_tool_use", id="s2", name="web_search", input={}),  # unanswered
            _b("tool_use", id="t1", name="gmail", input={"action": "send_email"}),
            _b("fallback", model="claude-opus-4-8"),
            _b("text", text="Here you go"),
            _b("tool_use", id="t2", name="weather", input={}),
        ]
        kept = [(b.type, getattr(b, "id", None) or getattr(b, "tool_use_id", None)) for b in _turn_content(content)]
        assert kept == [
            ("text", None), ("server_tool_use", "s1"), ("web_search_tool_result", "s1"),
            ("text", None), ("tool_use", "t2"),
        ]


class TestFallbackInTheLoop:
    @pytest.mark.asyncio
    async def test_uses_beta_api_and_skips_the_declined_tool_call(self):
        model_settings._selected = "claude-opus-5-5"
        declined = _b("tool_use", id="t1", name="gmail", input={"action": "send_email"})
        response = Block(
            stop_reason="end_turn",
            content=[declined, _b("fallback", model="claude-opus-4-8"), _b("text", text="Done.")],
        )
        client = MagicMock()
        client.beta.messages.create = AsyncMock(return_value=response)
        gmail = MagicMock()
        gmail.execute = AsyncMock()
        with patch.object(llm, "_get_client", return_value=client), \
             patch.object(llm.settings, "routing_model", ""):
            out = await chat_with_tools([], "email Sam", {"gmail": gmail})
        assert out == "Done."
        gmail.execute.assert_not_awaited()
        kwargs = client.beta.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-opus-5-5"
        assert kwargs["fallbacks"] == "default" and kwargs["betas"] == [FALLBACK_BETA]
        client.messages.create.assert_not_called()


class TestAdminRoutes:
    def _app(self, pool, admin=True):
        app = FastAPI()
        app.include_router(admin_routes.router, prefix="/api/admin")
        app.dependency_overrides[admin_routes.get_db_pool] = lambda: pool

        def admin_user():
            if not admin:
                raise HTTPException(403, "Admin access required")
            return "ron"

        app.dependency_overrides[admin_routes.get_admin_user] = admin_user
        return TestClient(app)

    def test_get_lists_the_choices(self, pool):
        with patch.object(model_settings.settings, "anthropic_model", "claude-opus-5"):
            body = self._app(pool).get("/api/admin/model").json()
        assert body["current"] == "claude-opus-5" and body["selected"] is None
        assert [o["id"] for o in body["options"]] == ["claude-opus-5-5", "claude-sonnet-5-5"]

    def test_put_switches_model(self, pool):
        r = self._app(pool).put("/api/admin/model", json={"model": "claude-sonnet-5-5"})
        assert r.status_code == 200 and r.json()["current"] == "claude-sonnet-5-5"

    def test_put_unknown_model(self, pool):
        assert self._app(pool).put("/api/admin/model", json={"model": "nope"}).status_code == 422

    def test_non_admins_cannot_change_it(self, pool):
        r = self._app(pool, admin=False).put("/api/admin/model", json={"model": "claude-sonnet-5-5"})
        assert r.status_code == 403
        assert model_settings.selected_model() is None
