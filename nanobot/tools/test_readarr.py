"""Tests for Readarr tool.

Run with: pytest nanobot/tools/test_readarr.py -v

These tests use mocked responses — no real Readarr instance required.
"""

import pytest
import aiohttp
from unittest.mock import AsyncMock, patch

from .readarr import ReadarrTool


# ---------------------------------------------------------------------------
# Sample API responses for mocking
# ---------------------------------------------------------------------------

SAMPLE_SEARCH_RESULTS = [
    {
        "title": "Project Hail Mary",
        "foreignBookId": "54493401",
        "overview": "Ryland Grace is the sole survivor on a desperate, last-chance mission.",
        "author": {"authorName": "Andy Weir"},
    },
    {
        "title": "The Martian",
        "foreignBookId": "18007564",
        "overview": "Six days ago, astronaut Mark Watney became one of the first people to walk on Mars.",
        "author": {"authorName": "Andy Weir"},
    },
]

SAMPLE_BOOK_LOOKUP = [
    {
        "title": "Project Hail Mary",
        "foreignBookId": "54493401",
        "overview": "Ryland Grace is the sole survivor...",
        "author": {
            "authorName": "Andy Weir",
            "foreignAuthorId": "6540057",
        },
    },
]

SAMPLE_ADD_RESPONSE = {
    "id": 1,
    "title": "Project Hail Mary",
    "foreignBookId": "54493401",
    "author": {"authorName": "Andy Weir"},
}

SAMPLE_LIBRARY = [
    {
        "id": 1,
        "title": "Project Hail Mary",
        "author": {"authorName": "Andy Weir"},
        "monitored": True,
        "bookFiles": [
            {
                "quality": {"quality": {"name": "EPUB"}},
                "size": 2097152,  # ~2 MB
            },
        ],
    },
    {
        "id": 2,
        "title": "Dune",
        "author": {"authorName": "Frank Herbert"},
        "monitored": True,
        "bookFiles": [],
    },
]

SAMPLE_QUALITY_PROFILES = [
    {"id": 1, "name": "eBook"},
    {"id": 2, "name": "Audiobook"},
]

SAMPLE_METADATA_PROFILES = [
    {"id": 1, "name": "Standard"},
]

SAMPLE_ROOT_FOLDERS = [
    {"id": 1, "path": "/books"},
]

SAMPLE_QUEUE = {
    "records": [
        {
            "title": "The Hitchhiker's Guide to the Galaxy",
            "status": "downloading",
            "size": 524288000,
            "sizeleft": 104857600,
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
    return ReadarrTool(base_url="http://readarr:8787", api_key="test_key_123")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReadarrToolProperties:
    """Verify tool metadata."""

    def test_name(self, tool):
        assert tool.name == "readarr"

    def test_description_mentions_books(self, tool):
        assert "book" in tool.description.lower()

    def test_parameters_has_action(self, tool):
        props = tool.parameters["properties"]
        assert "action" in props
        assert set(props["action"]["enum"]) == {
            "search_book",
            "add_book",
            "check_library",
            "delete_book",
            "get_queue",
        }

    def test_required_fields(self, tool):
        assert tool.parameters["required"] == ["action"]

    def test_to_schema(self, tool):
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "readarr"
        assert "parameters" in schema["function"]


class TestMissingConfig:
    """Error when Readarr is not configured."""

    @pytest.mark.asyncio
    async def test_missing_url(self):
        tool = ReadarrTool(base_url="", api_key="key")
        result = await tool.execute(action="search_book", title="test")
        assert "must be configured" in result

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        tool = ReadarrTool(base_url="http://readarr:8787", api_key="")
        result = await tool.execute(action="search_book", title="test")
        assert "must be configured" in result


class TestSearchBook:
    """Tests for the search_book action."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self, tool):
        with patch("tools.readarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SEARCH_RESULTS)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="search_book", title="Andy Weir")

            assert "Project Hail Mary" in result
            assert "Andy Weir" in result
            assert "54493401" in result
            assert "2 result(s)" in result

    @pytest.mark.asyncio
    async def test_search_no_results(self, tool):
        with patch("tools.readarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=[])
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="search_book", title="Nonexistentbook123"
            )

            assert "No books found" in result

    @pytest.mark.asyncio
    async def test_search_missing_title(self, tool):
        result = await tool.execute(action="search_book")
        assert "title is required" in result

    @pytest.mark.asyncio
    async def test_search_invalid_api_key(self, tool):
        with patch("tools.readarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 401
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="search_book", title="test")

            assert "Invalid" in result


class TestAddBook:
    """Tests for the add_book action."""

    @pytest.mark.asyncio
    async def test_add_success(self, tool):
        with patch("tools.readarr.aiohttp.ClientSession") as mock_cls:
            mock_session = mock_cls.return_value

            # Sequence: lookup → qualityprofile → metadataprofile → rootfolder → add
            lookup_resp = AsyncMock(status=200)
            lookup_resp.json = AsyncMock(return_value=SAMPLE_BOOK_LOOKUP)

            profile_resp = AsyncMock(status=200)
            profile_resp.json = AsyncMock(return_value=SAMPLE_QUALITY_PROFILES)

            metadata_resp = AsyncMock(status=200)
            metadata_resp.json = AsyncMock(return_value=SAMPLE_METADATA_PROFILES)

            folder_resp = AsyncMock(status=200)
            folder_resp.json = AsyncMock(return_value=SAMPLE_ROOT_FOLDERS)

            add_resp = AsyncMock(status=201)
            add_resp.json = AsyncMock(return_value=SAMPLE_ADD_RESPONSE)

            mock_session.get.return_value.__aenter__.side_effect = [
                lookup_resp,
                profile_resp,
                metadata_resp,
                folder_resp,
            ]
            mock_session.post.return_value.__aenter__.return_value = add_resp

            result = await tool.execute(
                action="add_book", book_foreign_id="54493401"
            )

            assert "Added" in result
            assert "Project Hail Mary" in result
            assert "Andy Weir" in result

    @pytest.mark.asyncio
    async def test_add_missing_foreign_id(self, tool):
        result = await tool.execute(action="add_book", title="Some Book")
        assert "book_foreign_id is required" in result

    @pytest.mark.asyncio
    async def test_add_already_exists(self, tool):
        with patch("tools.readarr.aiohttp.ClientSession") as mock_cls:
            mock_session = mock_cls.return_value

            lookup_resp = AsyncMock(status=200)
            lookup_resp.json = AsyncMock(return_value=SAMPLE_BOOK_LOOKUP)

            profile_resp = AsyncMock(status=200)
            profile_resp.json = AsyncMock(return_value=SAMPLE_QUALITY_PROFILES)

            metadata_resp = AsyncMock(status=200)
            metadata_resp.json = AsyncMock(return_value=SAMPLE_METADATA_PROFILES)

            folder_resp = AsyncMock(status=200)
            folder_resp.json = AsyncMock(return_value=SAMPLE_ROOT_FOLDERS)

            add_resp = AsyncMock(status=400)
            add_resp.text = AsyncMock(
                return_value='[{"errorMessage":"This book has already been added"}]'
            )

            mock_session.get.return_value.__aenter__.side_effect = [
                lookup_resp,
                profile_resp,
                metadata_resp,
                folder_resp,
            ]
            mock_session.post.return_value.__aenter__.return_value = add_resp

            result = await tool.execute(
                action="add_book", book_foreign_id="54493401"
            )

            assert "already" in result.lower()


class TestCheckLibrary:
    """Tests for the check_library action."""

    @pytest.mark.asyncio
    async def test_check_found_downloaded(self, tool):
        with patch("tools.readarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_LIBRARY)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="check_library", title="Project Hail Mary"
            )

            assert "Project Hail Mary" in result
            assert "Downloaded" in result
            assert "EPUB" in result
            assert "2.0 MB" in result

    @pytest.mark.asyncio
    async def test_check_found_missing(self, tool):
        with patch("tools.readarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_LIBRARY)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="check_library", title="Dune")

            assert "Dune" in result
            assert "Missing" in result

    @pytest.mark.asyncio
    async def test_check_by_author_name(self, tool):
        with patch("tools.readarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_LIBRARY)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="check_library", title="Andy Weir")

            assert "Project Hail Mary" in result

    @pytest.mark.asyncio
    async def test_check_not_in_library(self, tool):
        with patch("tools.readarr.aiohttp.ClientSession") as mock_cls:
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


class TestDeleteBook:
    """Tests for the delete_book action."""

    @pytest.mark.asyncio
    async def test_delete_success(self, tool):
        with patch("tools.readarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_cls.return_value.delete.return_value.__aenter__.return_value = (
                mock_resp
            )

            result = await tool.execute(action="delete_book", book_id=1)

            assert "Removed" in result

    @pytest.mark.asyncio
    async def test_delete_with_files(self, tool):
        with patch("tools.readarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_cls.return_value.delete.return_value.__aenter__.return_value = (
                mock_resp
            )

            result = await tool.execute(
                action="delete_book", book_id=1, delete_files=True
            )

            assert "deleted files from disk" in result

    @pytest.mark.asyncio
    async def test_delete_not_found(self, tool):
        with patch("tools.readarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 404
            mock_cls.return_value.delete.return_value.__aenter__.return_value = (
                mock_resp
            )

            result = await tool.execute(action="delete_book", book_id=999)

            assert "not found" in result

    @pytest.mark.asyncio
    async def test_delete_missing_id(self, tool):
        result = await tool.execute(action="delete_book")
        assert "book_id is required" in result


class TestGetQueue:
    """Tests for the get_queue action."""

    @pytest.mark.asyncio
    async def test_queue_with_items(self, tool):
        with patch("tools.readarr.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_QUEUE)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="get_queue")

            assert "Hitchhiker" in result
            assert "downloading" in result
            assert "80.0%" in result
            assert "00:05:30" in result

    @pytest.mark.asyncio
    async def test_queue_empty(self, tool):
        with patch("tools.readarr.aiohttp.ClientSession") as mock_cls:
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
        with patch("tools.readarr.aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.get.return_value.__aenter__.side_effect = (
                aiohttp.ClientError("Connection refused")
            )

            result = await tool.execute(action="search_book", title="test")

            assert "Error" in result

    @pytest.mark.asyncio
    async def test_timeout_error(self, tool):
        with patch("tools.readarr.aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.get.return_value.__aenter__.side_effect = (
                TimeoutError()
            )

            result = await tool.execute(action="search_book", title="test")

            assert "timed out" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
