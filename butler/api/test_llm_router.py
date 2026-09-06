"""Tests for the tool router (no network)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from . import llm
from .llm import _ToolRouter, _run_tool_block, _web_search_tool, _request_kwargs


def _tool(name: str, desc: str = "Does a thing. More detail."):
    t = MagicMock()
    t.name = name
    t.description = desc
    t.parameters = {"type": "object", "properties": {}}
    t.execute = AsyncMock(return_value=f"{name}-ok")
    return t


def _toolset():
    names = ["weather", "radarr", "books", "server_health", "storage_monitor",
             "jellyfin", "home_assistant", "list_ha_entities"]
    return {n: _tool(n) for n in names}


class TestRouter:
    def test_starts_with_core_only_and_catalogs_the_rest(self):
        r = _ToolRouter(_toolset(), [])
        assert set(r.active_tools) == {"weather", "radarr", "books"}
        names = [d["name"] for d in r.tool_definitions]
        assert "request_tools" in names and "jellyfin" not in names
        catalog = r.system_blocks[-1]["text"]
        assert "- jellyfin:" in catalog and "- weather:" not in catalog

    def test_catalog_lists_actions_and_more_than_first_sentence(self):
        tools = _toolset()
        tools["jellyfin"].description = "Search and control media on Jellyfin. See what's playing or recently added."
        tools["jellyfin"].parameters = {"type": "object", "properties": {"action": {"enum": ["search_library", "get_latest"]}}}
        r = _ToolRouter(tools, [])
        line = next(l for l in r.system_blocks[-1]["text"].splitlines() if l.startswith("- jellyfin:"))
        assert "recently added" in line and "[actions: search_library, get_latest]" in line

    def test_request_tools_activates_and_drops_from_catalog(self):
        r = _ToolRouter(_toolset(), [])
        msg = r.handle_request_tools(["jellyfin", "nope"])
        assert "jellyfin" in r.active_tools and "Unknown tools" in msg
        assert "- jellyfin:" not in r.system_blocks[-1]["text"]
        assert "request_tools" in [d["name"] for d in r.tool_definitions]  # others still inactive

    def test_direct_call_auto_activates(self):
        """Claude sometimes calls a catalogued tool by name without request_tools."""
        r = _ToolRouter(_toolset(), [])
        assert r.resolve("server_health") is not None
        assert "server_health" in r.active_tools
        assert r.resolve("does_not_exist") is None

    def test_catalog_disappears_when_everything_is_active(self):
        tools = _toolset()
        r = _ToolRouter(tools, [{"type": "text", "text": "base"}])
        r.handle_request_tools(list(tools))
        assert r.system_blocks == [{"type": "text", "text": "base"}]
        assert "request_tools" not in [d["name"] for d in r.tool_definitions]

    def test_model_switches_to_main_after_first_tool(self):
        r = _ToolRouter(_toolset(), [])
        with patch.object(llm.settings, "routing_model", "claude-haiku-4-5"), \
             patch.object(llm.settings, "anthropic_model", "claude-opus-5"):
            assert r.model == "claude-haiku-4-5"
            r.note_tool_use()
            assert r.model == "claude-opus-5"

    def test_no_routing_model_means_main_model_throughout(self):
        r = _ToolRouter(_toolset(), [])
        with patch.object(llm.settings, "routing_model", ""), \
             patch.object(llm.settings, "anthropic_model", "claude-opus-5"):
            assert r.model == "claude-opus-5"


class TestPerModelRequestShape:
    def test_web_search_variant(self):
        assert _web_search_tool("claude-opus-5")["type"] == "web_search_20260209"
        assert _web_search_tool("claude-haiku-4-5")["type"] == "web_search_20250305"

    def test_effort_only_where_supported(self):
        with patch.object(llm.settings, "chat_effort", "medium"):
            assert _request_kwargs("claude-opus-5") == {"output_config": {"effort": "medium"}}
            assert _request_kwargs("claude-haiku-4-5") == {}


class TestRunToolBlock:
    @pytest.mark.asyncio
    async def test_runs_auto_activated_tool_and_audits(self):
        tools = _toolset()
        r = _ToolRouter(tools, [])
        block = MagicMock()
        block.name = "jellyfin"
        block.input = {"action": "get_sessions"}
        pool = MagicMock()
        pool.pool = AsyncMock()
        out = await _run_tool_block(block, r, db_pool=pool, user_id="u", channel="pwa")
        assert out == "jellyfin-ok"
        tools["jellyfin"].execute.assert_awaited_once_with(action="get_sessions")
        pool.pool.execute.assert_awaited()  # audit row
        assert r.model == llm.settings.anthropic_model  # tools used → main model

    @pytest.mark.asyncio
    async def test_unknown_tool_reports_not_crashes(self):
        r = _ToolRouter(_toolset(), [])
        block = MagicMock()
        block.name = "teleport"
        block.input = {}
        out = await _run_tool_block(block, r, db_pool=None, user_id="u", channel="pwa")
        assert "Unknown tool" in out
