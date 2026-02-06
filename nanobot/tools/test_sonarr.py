"""Tests for Sonarr tool.

Run with: pytest nanobot/tools/test_sonarr.py -v

These tests use mocked responses — no real Sonarr instance required.
"""

import pytest
import aiohttp
from unittest.mock import AsyncMock, patch

from .sonarr import SonarrTool


# ---------------------------------------------------------------------------
# Sample API responses for mocking
# ---------------------------------------------------------------------------

SAMPLE_SEARCH_RESULTS = [
    {
        "title": "Breaking Bad",
        "year": 2008,
        "tvdbId": 81189,
        "seasonCount": 5,
        "status": "ended",
        "overview": "A high school chemistry teacher diagnosed with inoperable lung cancer turns to manufacturing methamphetamine.",
    },
    {
        "title": "Breaking Bad: Original Minisodes",
        "year": 2009,
        "tvdbId": 103311,
        "seasonCount": 2,
        "status": "ended",
        "overview": "Short webisodes set in the Breaking Bad universe.",
    },
]

SAMPLE_SERIES_LOOKUP = [
    {
        "title": "Breaking Bad",
        "year": 2008,
        "tvdbId": 81189,
        "seasonCount": 5,
        "seasons": [
            {"seasonNumber": 1, "monitored": True},
            {"seasonNumber": 2, "monitored": True},
            {"seasonNumber": 3, "monitored": True},
            {"seasonNumber": 4, "monitored": True},
            {"seasonNumber": 5, "monitored": True},
        ],
    },
]

SAMPLE_ADD_RESPONSE = {
    "id": 1,
    "title": "Breaking Bad",
    "year": 2008,
    "tvdbId": 81189,
    "seasonCount": 5,
    "path": "/tv/Breaking Bad",
}

SAMPLE_LIBRARY = [
    {
        "id": 1,
        "title": "Breaking Bad",
        "year": 2008,
        "monitored": True,
        "status": "ended",
        "statistics": {
            "episodeFileCount": 62,
            "episodeCount": 62,
            "totalEpisodeCount": 62,
            "sizeOnDisk": 128849018880,  # ~120 GB
        },
    },
    {
        "id": 2,
        "title": "The Office",
        "year": 2005,
        "monitored": True,
        "status": "ended",
        "statistics": {
            "episodeFileCount": 100,
            "episodeCount": 201,
            "totalEpisodeCount": 201,
            "sizeOnDisk": 53687091200,  # ~50 GB
        },
    },
]

SAMPLE_QUALITY_PROFILES = [
    {"id": 4, "name": "HD-1080p"},
    {"id": 6, "name": "Ultra-HD"},
]

SAMPLE_ROOT_FOLDERS = [
    {"id": 1, "path": "/tv"},
]

SAMPLE_QUEUE = {
    "records": [
        {
            "title": "Breaking Bad - S01E01 - Pilot",
            "status": "downloading",
            "size": 1073741824,
            "sizeleft": 214748364,
            "timeleft": "00:05:30",
        },
    ],
}

SAMPLE_QUEUE_EMPTY = {"records": []}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tool():
    """Create a tool instance with test config."""
    return SonarrTool(base_url="http://sonarr:8989", api_key="test_key_123")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSonarrToolProperties:
    """Verify tool metadata."""

    def test_name(self, tool):
        assert tool.name == "sonarr"

    def test_description_mentions_series(self, tool):
        assert "series" in tool.description.lower()

    def test_parameters_has_action(self, tool):
        props = tool.parameters["properties"]
        assert "action" in props
        assert set(props["action"]["enum"]) == {
            "search_series",
            "add_series",
            "check_library",
            "delete_series",
            "get_queue",
        }

    def test_required_fields(self, tool):
        assert tool.parameters["required"] == ["action"]

    def test_to_schema(self, tool):
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "sonarr"
        assert "parameters" in schema["function"]


class TestMissingConfig:
    """Error when Sonarr is not configured."""

    @pytest.mark.asyncio
    async def test_missing_url(self):
        tool = SonarrTool(base_url="", api_key="key")
        result = await tool.execute(action="search_series", title="test")
        assert "must be configured" in result

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        tool = SonarrTool(base_url="http://sonarr:8989", api_key="")
        result = await tool.execute(action="search_series", title="test")
        assert "must be configured" in result


class TestSearchSeries:
    """Tests for the search_series action."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self, tool):
        with patch("tools.sonarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SEARCH_RESULTS)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="search_series", title="Breaking Bad")

            assert "Breaking Bad" in result
            assert "2008" in result
            assert "81189" in result
            assert "2 result(s)" in result

    @pytest.mark.asyncio
    async def test_search_no_results(self, tool):
        with patch("tools.sonarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=[])
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="search_series", title="Nonexistentshow123"
            )

            assert "No series found" in result

    @pytest.mark.asyncio
    async def test_search_missing_title(self, tool):
        result = await tool.execute(action="search_series")
        assert "title is required" in result

    @pytest.mark.asyncio
    async def test_search_invalid_api_key(self, tool):
        with patch("tools.sonarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 401
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="search_series", title="Breaking Bad")

            assert "Invalid" in result


class TestAddSeries:
    """Tests for the add_series action."""

    @pytest.mark.asyncio
    async def test_add_success(self, tool):
        with patch("tools.sonarr.aiohttp.ClientSession") as mock_cls:
            mock_session = mock_cls.return_value

            # Sequence: lookup → qualityprofile → rootfolder → add
            lookup_resp = AsyncMock(status=200)
            lookup_resp.json = AsyncMock(return_value=SAMPLE_SERIES_LOOKUP)

            profile_resp = AsyncMock(status=200)
            profile_resp.json = AsyncMock(return_value=SAMPLE_QUALITY_PROFILES)

            folder_resp = AsyncMock(status=200)
            folder_resp.json = AsyncMock(return_value=SAMPLE_ROOT_FOLDERS)

            add_resp = AsyncMock(status=201)
            add_resp.json = AsyncMock(return_value=SAMPLE_ADD_RESPONSE)

            mock_session.get.return_value.__aenter__.side_effect = [
                lookup_resp,
                profile_resp,
                folder_resp,
            ]
            mock_session.post.return_value.__aenter__.return_value = add_resp

            result = await tool.execute(action="add_series", tvdb_id=81189)

            assert "Added" in result
            assert "Breaking Bad" in result
            assert "2008" in result
            assert "5 seasons" in result

    @pytest.mark.asyncio
    async def test_add_missing_tvdb_id(self, tool):
        result = await tool.execute(action="add_series", title="Breaking Bad")
        assert "tvdb_id is required" in result

    @pytest.mark.asyncio
    async def test_add_already_exists(self, tool):
        with patch("tools.sonarr.aiohttp.ClientSession") as mock_cls:
            mock_session = mock_cls.return_value

            lookup_resp = AsyncMock(status=200)
            lookup_resp.json = AsyncMock(return_value=SAMPLE_SERIES_LOOKUP)

            profile_resp = AsyncMock(status=200)
            profile_resp.json = AsyncMock(return_value=SAMPLE_QUALITY_PROFILES)

            folder_resp = AsyncMock(status=200)
            folder_resp.json = AsyncMock(return_value=SAMPLE_ROOT_FOLDERS)

            add_resp = AsyncMock(status=400)
            add_resp.text = AsyncMock(
                return_value='[{"errorMessage":"This series has already been added"}]'
            )

            mock_session.get.return_value.__aenter__.side_effect = [
                lookup_resp,
                profile_resp,
                folder_resp,
            ]
            mock_session.post.return_value.__aenter__.return_value = add_resp

            result = await tool.execute(action="add_series", tvdb_id=81189)

            assert "already" in result.lower()


class TestCheckLibrary:
    """Tests for the check_library action."""

    @pytest.mark.asyncio
    async def test_check_found_complete(self, tool):
        with patch("tools.sonarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_LIBRARY)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="check_library", title="Breaking Bad")

            assert "Breaking Bad" in result
            assert "62/62" in result
            assert "120.0 GB" in result

    @pytest.mark.asyncio
    async def test_check_found_partial(self, tool):
        with patch("tools.sonarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_LIBRARY)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="check_library", title="Office")

            assert "The Office" in result
            assert "100/201" in result

    @pytest.mark.asyncio
    async def test_check_not_in_library(self, tool):
        with patch("tools.sonarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_LIBRARY)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="check_library", title="Nonexistent")

            assert "not found in library" in result

    @pytest.mark.asyncio
    async def test_check_missing_title(self, tool):
        result = await tool.execute(action="check_library")
        assert "title is required" in result


class TestDeleteSeries:
    """Tests for the delete_series action."""

    @pytest.mark.asyncio
    async def test_delete_success(self, tool):
        with patch("tools.sonarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_cls.return_value.delete.return_value.__aenter__.return_value = (
                mock_resp
            )

            result = await tool.execute(action="delete_series", series_id=1)

            assert "Removed" in result

    @pytest.mark.asyncio
    async def test_delete_with_files(self, tool):
        with patch("tools.sonarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_cls.return_value.delete.return_value.__aenter__.return_value = (
                mock_resp
            )

            result = await tool.execute(
                action="delete_series", series_id=1, delete_files=True
            )

            assert "deleted files from disk" in result

    @pytest.mark.asyncio
    async def test_delete_not_found(self, tool):
        with patch("tools.sonarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 404
            mock_cls.return_value.delete.return_value.__aenter__.return_value = (
                mock_resp
            )

            result = await tool.execute(action="delete_series", series_id=999)

            assert "not found" in result

    @pytest.mark.asyncio
    async def test_delete_missing_id(self, tool):
        result = await tool.execute(action="delete_series")
        assert "series_id is required" in result


class TestGetQueue:
    """Tests for the get_queue action."""

    @pytest.mark.asyncio
    async def test_queue_with_items(self, tool):
        with patch("tools.sonarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_QUEUE)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="get_queue")

            assert "Breaking Bad" in result
            assert "downloading" in result
            assert "80.0%" in result
            assert "00:05:30" in result

    @pytest.mark.asyncio
    async def test_queue_empty(self, tool):
        with patch("tools.sonarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_QUEUE_EMPTY)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="get_queue")

            assert "empty" in result.lower()


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_unknown_action(self, tool):
        result = await tool.execute(action="explode")
        assert "Unknown action" in result

    @pytest.mark.asyncio
    async def test_connection_error(self, tool):
        with patch("tools.sonarr.aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.get.return_value.__aenter__.side_effect = (
                aiohttp.ClientError("Connection refused")
            )

            result = await tool.execute(action="search_series", title="test")

            assert "Error" in result

    @pytest.mark.asyncio
    async def test_timeout_error(self, tool):
        with patch("tools.sonarr.aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.get.return_value.__aenter__.side_effect = (
                TimeoutError()
            )

            result = await tool.execute(action="search_series", title="test")

            assert "timed out" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
