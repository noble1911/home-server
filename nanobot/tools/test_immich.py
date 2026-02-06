"""Tests for Immich photo search tool.

Run with: pytest nanobot/tools/test_immich.py -v

These tests use mocked responses — no real Immich instance required.
"""

import pytest
import aiohttp
from unittest.mock import AsyncMock, patch

from .immich import ImmichTool


# ---------------------------------------------------------------------------
# Sample API responses for mocking
# ---------------------------------------------------------------------------

SAMPLE_SMART_SEARCH_RESPONSE = {
    "assets": {
        "count": 2,
        "total": 2,
        "nextPage": None,
        "items": [
            {
                "id": "asset-uuid-001",
                "type": "IMAGE",
                "originalFileName": "IMG_20240904_173433.jpg",
                "localDateTime": "2024-09-04T17:34:33.000Z",
                "fileCreatedAt": "2024-09-04T17:34:33.000Z",
                "isFavorite": True,
                "exifInfo": {
                    "make": "Apple",
                    "model": "iPhone 15 Pro",
                    "city": "London",
                    "state": "England",
                    "country": "United Kingdom",
                },
                "people": [
                    {"id": "person-uuid-001", "name": "Ron"},
                ],
            },
            {
                "id": "asset-uuid-002",
                "type": "IMAGE",
                "originalFileName": "DSC_0042.jpg",
                "localDateTime": "2024-08-15T10:22:00.000Z",
                "fileCreatedAt": "2024-08-15T10:22:00.000Z",
                "isFavorite": False,
                "exifInfo": {
                    "make": "Sony",
                    "model": "A7III",
                    "city": "Tokyo",
                    "state": None,
                    "country": "Japan",
                },
                "people": [],
            },
        ],
    },
    "albums": {"count": 0, "total": 0, "items": []},
}

SAMPLE_SEARCH_EMPTY = {
    "assets": {
        "count": 0,
        "total": 0,
        "nextPage": None,
        "items": [],
    },
}

SAMPLE_SEARCH_WITH_NEXT_PAGE = {
    "assets": {
        "count": 10,
        "total": 25,
        "nextPage": "page-token-2",
        "items": [
            {
                "id": f"asset-uuid-{i:03d}",
                "type": "IMAGE",
                "originalFileName": f"photo_{i}.jpg",
                "localDateTime": f"2024-01-{i:02d}T12:00:00.000Z",
                "isFavorite": False,
                "exifInfo": {},
                "people": [],
            }
            for i in range(1, 11)
        ],
    },
}

SAMPLE_PERSON_RESULTS = [
    {
        "id": "person-uuid-001",
        "name": "Ron",
        "birthDate": "1990-05-15",
    },
    {
        "id": "person-uuid-002",
        "name": "Ronaldo",
        "birthDate": None,
    },
]

SAMPLE_VIDEO_RESULT = {
    "assets": {
        "count": 1,
        "total": 1,
        "nextPage": None,
        "items": [
            {
                "id": "asset-uuid-video",
                "type": "VIDEO",
                "originalFileName": "VID_20240101.mp4",
                "localDateTime": "2024-01-01T00:00:00.000Z",
                "isFavorite": False,
                "exifInfo": {},
                "people": [],
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tool():
    """Create a tool instance with test config."""
    return ImmichTool(base_url="http://immich-server:2283", api_key="test_key_123")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestImmichToolProperties:
    """Verify tool metadata."""

    def test_name(self, tool):
        assert tool.name == "immich"

    def test_description_mentions_photos(self, tool):
        assert "photo" in tool.description.lower()

    def test_description_mentions_read_only(self, tool):
        assert "read-only" in tool.description.lower()

    def test_parameters_has_action(self, tool):
        props = tool.parameters["properties"]
        assert "action" in props
        assert set(props["action"]["enum"]) == {
            "search_photos",
            "find_person",
        }

    def test_required_fields(self, tool):
        assert tool.parameters["required"] == ["action"]

    def test_to_schema(self, tool):
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "immich"
        assert "parameters" in schema["function"]


class TestMissingConfig:
    """Error when Immich is not configured."""

    @pytest.mark.asyncio
    async def test_missing_url(self):
        tool = ImmichTool(base_url="", api_key="key")
        result = await tool.execute(action="search_photos", query="test")
        assert "must be configured" in result

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        tool = ImmichTool(base_url="http://immich:2283", api_key="")
        result = await tool.execute(action="search_photos", query="test")
        assert "must be configured" in result


class TestSearchPhotos:
    """Tests for the search_photos action."""

    @pytest.mark.asyncio
    async def test_smart_search_with_query(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SMART_SEARCH_RESPONSE)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="search_photos", query="sunset beach")

            assert "2 photo(s)" in result
            assert "IMG_20240904_173433.jpg" in result
            assert "London" in result
            assert "Ron" in result
            assert "asset-uuid-001" in result

    @pytest.mark.asyncio
    async def test_metadata_search_by_date(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SMART_SEARCH_RESPONSE)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="search_photos",
                taken_after="2024-09-01",
                taken_before="2024-09-30",
            )

            assert "photo(s)" in result

    @pytest.mark.asyncio
    async def test_search_with_person_ids(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SMART_SEARCH_RESPONSE)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="search_photos",
                person_ids=["person-uuid-001"],
            )

            assert "photo(s)" in result

    @pytest.mark.asyncio
    async def test_smart_search_with_all_filters(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SMART_SEARCH_RESPONSE)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="search_photos",
                query="at the park",
                taken_after="2024-01-01",
                taken_before="2024-12-31",
                person_ids=["person-uuid-001"],
                city="London",
                country="United Kingdom",
            )

            assert "photo(s)" in result

    @pytest.mark.asyncio
    async def test_search_no_results(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SEARCH_EMPTY)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="search_photos", query="unicorn")

            assert "No photos found" in result
            assert "unicorn" in result

    @pytest.mark.asyncio
    async def test_search_no_filters_error(self, tool):
        result = await tool.execute(action="search_photos")
        assert "requires at least one filter" in result

    @pytest.mark.asyncio
    async def test_search_shows_pagination(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SEARCH_WITH_NEXT_PAGE)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="search_photos", query="photos")

            assert "page=2" in result

    @pytest.mark.asyncio
    async def test_search_shows_video_type(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_VIDEO_RESULT)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="search_photos", query="video")

            assert "video" in result.lower()

    @pytest.mark.asyncio
    async def test_search_shows_favorite(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SMART_SEARCH_RESPONSE)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="search_photos", query="test")

            assert "favorite" in result.lower()

    @pytest.mark.asyncio
    async def test_search_invalid_api_key(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 401
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="search_photos", query="test")

            assert "Invalid" in result

    @pytest.mark.asyncio
    async def test_search_includes_preview_url(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SMART_SEARCH_RESPONSE)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="search_photos", query="test")

            assert "/api/assets/asset-uuid-001/thumbnail" in result

    @pytest.mark.asyncio
    async def test_search_by_city(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SMART_SEARCH_RESPONSE)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="search_photos", city="London")

            assert "photo(s)" in result

    @pytest.mark.asyncio
    async def test_search_by_country(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SMART_SEARCH_RESPONSE)
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="search_photos", country="Japan")

            assert "photo(s)" in result


class TestFindPerson:
    """Tests for the find_person action."""

    @pytest.mark.asyncio
    async def test_find_person_success(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_PERSON_RESULTS)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="find_person", person_name="Ron")

            assert "2 person(s)" in result
            assert "Ron" in result
            assert "person-uuid-001" in result
            assert "1990-05-15" in result
            assert "Ronaldo" in result

    @pytest.mark.asyncio
    async def test_find_person_not_found(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=[])
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="find_person", person_name="Nobody")

            assert "No person found" in result

    @pytest.mark.asyncio
    async def test_find_person_missing_name(self, tool):
        result = await tool.execute(action="find_person")
        assert "person_name is required" in result

    @pytest.mark.asyncio
    async def test_find_person_includes_thumbnail_url(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_PERSON_RESULTS)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="find_person", person_name="Ron")

            assert "/api/people/person-uuid-001/thumbnail" in result

    @pytest.mark.asyncio
    async def test_find_person_invalid_api_key(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 401
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="find_person", person_name="Ron")

            assert "Invalid" in result


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_unknown_action(self, tool):
        result = await tool.execute(action="delete_photo")
        assert "Unknown action" in result

    @pytest.mark.asyncio
    async def test_connection_error(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.post.return_value.__aenter__.side_effect = (
                aiohttp.ClientError("Connection refused")
            )

            result = await tool.execute(action="search_photos", query="test")

            assert "Error" in result

    @pytest.mark.asyncio
    async def test_timeout_error(self, tool):
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.post.return_value.__aenter__.side_effect = (
                TimeoutError()
            )

            result = await tool.execute(action="search_photos", query="test")

            assert "timed out" in result


class TestDateNormalization:
    """Tests for date string normalization."""

    @pytest.mark.asyncio
    async def test_date_only_gets_time_appended(self, tool):
        """Verify that bare dates get start/end-of-day times."""
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SEARCH_EMPTY)
            mock_session = mock_cls.return_value
            mock_session.post.return_value.__aenter__.return_value = mock_resp

            await tool.execute(
                action="search_photos",
                taken_after="2024-12-25",
                taken_before="2024-12-31",
            )

            # Check the body passed to post()
            call_args = mock_session.post.call_args
            body = call_args.kwargs.get("json") or call_args[1].get("json")
            assert body["takenAfter"] == "2024-12-25T00:00:00.000Z"
            assert body["takenBefore"] == "2024-12-31T23:59:59.999Z"

    @pytest.mark.asyncio
    async def test_iso_datetime_passed_through(self, tool):
        """Verify that full ISO datetimes are not modified."""
        with patch("tools.immich.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SEARCH_EMPTY)
            mock_session = mock_cls.return_value
            mock_session.post.return_value.__aenter__.return_value = mock_resp

            await tool.execute(
                action="search_photos",
                taken_after="2024-12-25T08:00:00.000Z",
            )

            call_args = mock_session.post.call_args
            body = call_args.kwargs.get("json") or call_args[1].get("json")
            assert body["takenAfter"] == "2024-12-25T08:00:00.000Z"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
