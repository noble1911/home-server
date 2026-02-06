"""Tests for Radarr tool.

Run with: pytest nanobot/tools/test_radarr.py -v

These tests use mocked responses — no real Radarr instance required.
"""

import pytest
import aiohttp
from unittest.mock import AsyncMock, patch

from .radarr import RadarrTool


# ---------------------------------------------------------------------------
# Sample API responses for mocking
# ---------------------------------------------------------------------------

SAMPLE_SEARCH_RESULTS = [
    {
        "title": "Inception",
        "year": 2010,
        "tmdbId": 27205,
        "overview": "A thief who steals corporate secrets through dream-sharing technology is given the task of planting an idea.",
    },
    {
        "title": "Inception: The Cobol Job",
        "year": 2010,
        "tmdbId": 72007,
        "overview": "A prequel comic to the film Inception.",
    },
]

SAMPLE_MOVIE_LOOKUP = {
    "title": "Inception",
    "year": 2010,
    "tmdbId": 27205,
    "overview": "A thief who steals corporate secrets...",
}

SAMPLE_ADD_RESPONSE = {
    "id": 1,
    "title": "Inception",
    "year": 2010,
    "tmdbId": 27205,
    "path": "/movies/Inception (2010)",
}

SAMPLE_LIBRARY = [
    {
        "id": 1,
        "title": "Inception",
        "year": 2010,
        "hasFile": True,
        "monitored": True,
        "movieFile": {
            "quality": {"quality": {"name": "Bluray-1080p"}},
            "size": 8589934592,  # ~8 GB
        },
    },
    {
        "id": 2,
        "title": "The Dark Knight",
        "year": 2008,
        "hasFile": False,
        "monitored": True,
        "movieFile": None,
    },
]

SAMPLE_QUALITY_PROFILES = [
    {"id": 4, "name": "HD-1080p"},
    {"id": 6, "name": "Ultra-HD"},
]

SAMPLE_ROOT_FOLDERS = [
    {"id": 1, "path": "/movies"},
]

SAMPLE_QUEUE = {
    "records": [
        {
            "title": "The Matrix (1999) Bluray-1080p",
            "status": "downloading",
            "size": 5368709120,
            "sizeleft": 1073741824,
            "timeleft": "00:15:30",
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
    return RadarrTool(base_url="http://radarr:7878", api_key="test_key_123")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRadarrToolProperties:
    """Verify tool metadata."""

    def test_name(self, tool):
        assert tool.name == "radarr"

    def test_description_mentions_movies(self, tool):
        assert "movie" in tool.description.lower()

    def test_parameters_has_action(self, tool):
        props = tool.parameters["properties"]
        assert "action" in props
        assert set(props["action"]["enum"]) == {
            "search_movie",
            "add_movie",
            "check_library",
            "delete_movie",
            "get_queue",
        }

    def test_required_fields(self, tool):
        assert tool.parameters["required"] == ["action"]

    def test_to_schema(self, tool):
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "radarr"
        assert "parameters" in schema["function"]


class TestMissingConfig:
    """Error when Radarr is not configured."""

    @pytest.mark.asyncio
    async def test_missing_url(self):
        tool = RadarrTool(base_url="", api_key="key")
        result = await tool.execute(action="search_movie", title="test")
        assert "must be configured" in result

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        tool = RadarrTool(base_url="http://radarr:7878", api_key="")
        result = await tool.execute(action="search_movie", title="test")
        assert "must be configured" in result


class TestSearchMovie:
    """Tests for the search_movie action."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self, tool):
        with patch("tools.radarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SEARCH_RESULTS)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="search_movie", title="Inception")

            assert "Inception" in result
            assert "2010" in result
            assert "27205" in result
            assert "2 result(s)" in result

    @pytest.mark.asyncio
    async def test_search_no_results(self, tool):
        with patch("tools.radarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=[])
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="search_movie", title="Nonexistentmovie123")

            assert "No movies found" in result

    @pytest.mark.asyncio
    async def test_search_missing_title(self, tool):
        result = await tool.execute(action="search_movie")
        assert "title is required" in result

    @pytest.mark.asyncio
    async def test_search_invalid_api_key(self, tool):
        with patch("tools.radarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 401
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="search_movie", title="Inception")

            assert "Invalid" in result


class TestAddMovie:
    """Tests for the add_movie action."""

    @pytest.mark.asyncio
    async def test_add_success(self, tool):
        with patch("tools.radarr.aiohttp.ClientSession") as mock_cls:
            mock_session = mock_cls.return_value

            # Sequence: lookup → qualityprofile → rootfolder → add
            lookup_resp = AsyncMock(status=200)
            lookup_resp.json = AsyncMock(return_value=SAMPLE_MOVIE_LOOKUP)

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

            result = await tool.execute(action="add_movie", tmdb_id=27205)

            assert "Added" in result
            assert "Inception" in result
            assert "2010" in result

    @pytest.mark.asyncio
    async def test_add_missing_tmdb_id(self, tool):
        result = await tool.execute(action="add_movie", title="Inception")
        assert "tmdb_id is required" in result

    @pytest.mark.asyncio
    async def test_add_already_exists(self, tool):
        with patch("tools.radarr.aiohttp.ClientSession") as mock_cls:
            mock_session = mock_cls.return_value

            lookup_resp = AsyncMock(status=200)
            lookup_resp.json = AsyncMock(return_value=SAMPLE_MOVIE_LOOKUP)

            profile_resp = AsyncMock(status=200)
            profile_resp.json = AsyncMock(return_value=SAMPLE_QUALITY_PROFILES)

            folder_resp = AsyncMock(status=200)
            folder_resp.json = AsyncMock(return_value=SAMPLE_ROOT_FOLDERS)

            add_resp = AsyncMock(status=400)
            add_resp.text = AsyncMock(
                return_value='[{"errorMessage":"This movie has already been added"}]'
            )

            mock_session.get.return_value.__aenter__.side_effect = [
                lookup_resp,
                profile_resp,
                folder_resp,
            ]
            mock_session.post.return_value.__aenter__.return_value = add_resp

            result = await tool.execute(action="add_movie", tmdb_id=27205)

            assert "already" in result.lower()


class TestCheckLibrary:
    """Tests for the check_library action."""

    @pytest.mark.asyncio
    async def test_check_found_downloaded(self, tool):
        with patch("tools.radarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_LIBRARY)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="check_library", title="Inception")

            assert "Inception" in result
            assert "Downloaded" in result
            assert "Bluray-1080p" in result
            assert "8.0 GB" in result

    @pytest.mark.asyncio
    async def test_check_found_missing(self, tool):
        with patch("tools.radarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_LIBRARY)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="check_library", title="Dark Knight")

            assert "Dark Knight" in result
            assert "Missing" in result

    @pytest.mark.asyncio
    async def test_check_not_in_library(self, tool):
        with patch("tools.radarr.aiohttp.ClientSession") as mock_cls:
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


class TestDeleteMovie:
    """Tests for the delete_movie action."""

    @pytest.mark.asyncio
    async def test_delete_success(self, tool):
        with patch("tools.radarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_cls.return_value.delete.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="delete_movie", movie_id=1)

            assert "Removed" in result

    @pytest.mark.asyncio
    async def test_delete_with_files(self, tool):
        with patch("tools.radarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_cls.return_value.delete.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="delete_movie", movie_id=1, delete_files=True
            )

            assert "deleted files from disk" in result

    @pytest.mark.asyncio
    async def test_delete_not_found(self, tool):
        with patch("tools.radarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 404
            mock_cls.return_value.delete.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="delete_movie", movie_id=999)

            assert "not found" in result

    @pytest.mark.asyncio
    async def test_delete_missing_id(self, tool):
        result = await tool.execute(action="delete_movie")
        assert "movie_id is required" in result


class TestGetQueue:
    """Tests for the get_queue action."""

    @pytest.mark.asyncio
    async def test_queue_with_items(self, tool):
        with patch("tools.radarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_QUEUE)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="get_queue")

            assert "Matrix" in result
            assert "downloading" in result
            assert "80.0%" in result
            assert "00:15:30" in result

    @pytest.mark.asyncio
    async def test_queue_empty(self, tool):
        with patch("tools.radarr.aiohttp.ClientSession") as mock_cls:
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
        with patch("tools.radarr.aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.get.return_value.__aenter__.side_effect = (
                aiohttp.ClientError("Connection refused")
            )

            result = await tool.execute(action="search_movie", title="test")

            assert "Error" in result

    @pytest.mark.asyncio
    async def test_timeout_error(self, tool):
        with patch("tools.radarr.aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.get.return_value.__aenter__.side_effect = (
                TimeoutError()
            )

            result = await tool.execute(action="search_movie", title="test")

            assert "timed out" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
