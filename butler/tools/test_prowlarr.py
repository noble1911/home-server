"""Tests for the Prowlarr search/grab tool (HTTP mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from .prowlarr import ProwlarrTool, _quality_tags, _result_id

RESULTS = [
    {"guid": "g1", "title": "Dune.2021.1080p.BluRay.x265-GRP", "size": 4_000_000_000, "seeders": 120, "leechers": 4,
     "indexer": "1337x", "protocol": "torrent", "downloadUrl": "http://prowlarr/dl/1", "magnetUrl": "magnet:?xt=1",
     "categories": [{"id": 2000, "name": "Movies"}]},
    {"guid": "g2", "title": "Dune 2021 2160p WEB-DL HDR", "size": 12_000_000_000, "seeders": 300, "leechers": 20,
     "indexer": "LimeTorrents", "protocol": "torrent", "downloadUrl": "http://prowlarr/dl/2",
     "categories": [{"id": 2045, "name": "Movies/UHD"}]},
    {"guid": "g3", "title": "Dune (usenet)", "size": 1, "seeders": 0, "protocol": "usenet", "downloadUrl": "http://x"},
    {"guid": "g4", "title": "Dune no link", "size": 1, "seeders": 999, "protocol": "torrent"},
]


@pytest.fixture
def qbit():
    q = AsyncMock()
    q.add = AsyncMock(return_value="Added to qBittorrent (category: movies, saving under /downloads/Complete).")
    return q


@pytest.fixture
def tool(qbit):
    t = ProwlarrTool(url="http://prowlarr:9696", api_key="k", qbit=qbit)
    t._get = AsyncMock(return_value=(200, RESULTS))
    return t


class TestSearch:
    @pytest.mark.asyncio
    async def test_ranks_by_seeders_and_drops_unusable(self, tool):
        out = await tool.execute(action="search", query="Dune", category="movies", limit=5)
        lines = out.splitlines()
        assert "2 result(s)" in lines[0] and "default category 'movies'" in lines[0]
        assert lines[1].startswith(f"- [{_result_id(RESULTS[1])}] Dune 2021 2160p")   # most seeders first
        assert "300 seeders/20 leechers, LimeTorrents, 2160P WEB-DL HDR" in lines[1]
        assert "usenet" not in out and "no link" not in out
        params = tool._get.call_args.args[1]
        assert ("categories", "2000") in params and ("query", "Dune") in params

    @pytest.mark.asyncio
    async def test_retries_without_categories_when_empty(self, tool):
        tool._get.side_effect = [(200, []), (200, RESULTS)]
        out = await tool.execute(action="search", query="Dune", category="tv")
        assert "2 result(s)" in out
        assert not any(k == "categories" for k, _ in tool._get.call_args.args[1])

    @pytest.mark.asyncio
    async def test_requires_query(self, tool):
        assert (await tool.execute(action="search")).startswith("Error")


class TestGrab:
    @pytest.mark.asyncio
    async def test_grab_uses_magnet_and_inferred_category(self, tool, qbit):
        await tool.execute(action="search", query="Dune", category="other")
        rid = _result_id(RESULTS[0])
        out = await tool.execute(action="grab", result_id=rid)
        assert out.startswith("Grabbed 'Dune.2021.1080p.BluRay.x265-GRP' (3.7 GB, 120 seeders)")
        qbit.add.assert_awaited_once_with("magnet:?xt=1", "movies")

    @pytest.mark.asyncio
    async def test_grab_category_override_and_download_url_fallback(self, tool, qbit):
        await tool.execute(action="search", query="Dune")
        await tool.execute(action="grab", result_id=_result_id(RESULTS[1]), category="anime")
        qbit.add.assert_awaited_once_with("http://prowlarr/dl/2", "anime")

    @pytest.mark.asyncio
    async def test_grab_unknown_id(self, tool):
        out = await tool.execute(action="grab", result_id="zzzzzz")
        assert "No cached result" in out

    @pytest.mark.asyncio
    async def test_grab_without_qbit(self):
        t = ProwlarrTool(url="http://p", api_key="k", qbit=None)
        t._get = AsyncMock(return_value=(200, RESULTS))
        await t.execute(action="search", query="Dune")
        assert "qBittorrent is not configured" in await t.execute(action="grab", result_id=_result_id(RESULTS[0]))


class TestIndexers:
    @pytest.mark.asyncio
    async def test_lists_indexers(self, tool):
        tool._get.return_value = (200, [
            {"name": "1337x", "enable": True, "protocol": "torrent", "privacy": "public",
             "capabilities": {"categories": [{"name": "Movies"}, {"name": "TV"}]}},
            {"name": "Old", "enable": False, "protocol": "torrent", "privacy": "private", "capabilities": {}},
        ])
        out = await tool.execute(action="indexers")
        assert "- 1337x — enabled, torrent, public, categories: Movies, TV" in out
        assert "- Old — disabled" in out


def test_quality_tags():
    assert _quality_tags("Show.S01.1080p.WEB-DL.x265.HEVC-GRP") == "1080P WEB-DL X265 HEVC"
    assert _quality_tags("Plain title") == ""
