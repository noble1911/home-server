"""Tests for the qBittorrent tool (HTTP mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from .qbittorrent import QBittorrentTool, _fmt_eta

TORRENTS = [
    {"name": "Berserk 1997", "hash": "abc123def456", "state": "downloading", "progress": 0.42,
     "size": 6_900_000_000, "dlspeed": 3_000_000, "upspeed": 0, "eta": 900, "category": "tv"},
    {"name": "Dune epub", "hash": "ffff0000", "state": "uploading", "progress": 1.0,
     "size": 1_200_000, "dlspeed": 0, "upspeed": 12_000, "eta": 8_640_000, "category": "ebooks"},
    {"name": "Dune audiobook", "hash": "eeee1111", "state": "pausedUP", "progress": 1.0,
     "size": 900_000_000, "dlspeed": 0, "upspeed": 0, "eta": 8_640_000, "category": "audiobooks"},
]


@pytest.fixture
def tool():
    t = QBittorrentTool(url="http://qb:8081", username="u", password="p")
    t._sid = "sid"
    t._request = AsyncMock()
    return t


class TestList:
    @pytest.mark.asyncio
    async def test_lists_with_state_and_hash(self, tool):
        tool._request.return_value = (200, TORRENTS)
        out = await tool.execute(action="list", filter="downloading")
        assert "3 torrent(s) (downloading)" in out
        assert "Berserk 1997 — 42% · downloading · 6.4 GB · ↓2.9 MB/s eta 15m · [tv] (hash abc123def456)" in out
        params = tool._request.call_args.kwargs["params"]
        assert params["filter"] == "downloading"

    @pytest.mark.asyncio
    async def test_unknown_filter_falls_back_to_all(self, tool):
        tool._request.return_value = (200, [])
        out = await tool.execute(action="list", filter="bogus")
        assert out == "No torrents."
        assert tool._request.call_args.kwargs["params"]["filter"] == "all"


class TestAdd:
    @pytest.mark.asyncio
    async def test_rejects_non_links(self, tool):
        out = await tool.execute(action="add", url="Berserk 1997")
        assert out.startswith("Error:") and not tool._request.called

    @pytest.mark.asyncio
    async def test_adds_magnet_with_category_and_savepath(self, tool):
        tool._request.return_value = (200, "Ok.")
        out = await tool.execute(action="add", url="magnet:?xt=urn:btih:abc", category="ebooks")
        assert "Added to qBittorrent" in out and "/ebooks" in out
        data = tool._request.call_args.kwargs["data"]
        assert data == {"urls": "magnet:?xt=urn:btih:abc", "category": "ebooks", "savepath": "/ebooks"}

    @pytest.mark.asyncio
    async def test_movie_add_warns_about_import(self, tool):
        tool._request.return_value = (200, "Ok.")
        out = await tool.execute(action="add", url="https://x/y.torrent", category="movies")
        assert "Radarr/Sonarr will not import it" in out
        assert "savepath" not in tool._request.call_args.kwargs["data"]

    @pytest.mark.asyncio
    async def test_bad_category(self, tool):
        out = await tool.execute(action="add", url="magnet:?x", category="stuff")
        assert "category must be one of" in out


class TestControl:
    @pytest.mark.asyncio
    async def test_pause_by_name_fragment(self, tool):
        tool._request.side_effect = [(200, TORRENTS), (200, "")]
        out = await tool.execute(action="pause", name="berserk")
        assert out == "Paused: Berserk 1997"
        assert tool._request.call_args.args[1] == "/api/v2/torrents/stop"
        assert tool._request.call_args.kwargs["data"] == {"hashes": "abc123def456"}

    @pytest.mark.asyncio
    async def test_ambiguous_name_asks_for_precision(self, tool):
        tool._request.return_value = (200, TORRENTS)
        out = await tool.execute(action="resume", name="dune")
        assert out.startswith("2 torrents match")

    @pytest.mark.asyncio
    async def test_delete_keeps_files_by_default(self, tool):
        tool._request.side_effect = [(200, TORRENTS), (200, "")]
        out = await tool.execute(action="delete", hash="ffff")
        assert out == "Deleted: Dune epub (files kept)"
        assert tool._request.call_args.kwargs["data"]["deleteFiles"] == "false"

    @pytest.mark.asyncio
    async def test_needs_hash_or_name(self, tool):
        tool._request.return_value = (200, TORRENTS)
        out = await tool.execute(action="delete")
        assert "give a 'hash'" in out


def test_eta_formatting():
    assert _fmt_eta(8_640_000) == "∞" and _fmt_eta(45) == "45s" and _fmt_eta(5400) == "1h 30m"
