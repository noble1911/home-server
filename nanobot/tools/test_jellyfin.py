"""Tests for Jellyfin tool.

Run with: pytest nanobot/tools/test_jellyfin.py -v

These tests use mocked responses — no real Jellyfin instance required.
"""

import pytest
import aiohttp
from unittest.mock import AsyncMock, patch

from .jellyfin import JellyfinTool


# ---------------------------------------------------------------------------
# Sample API responses for mocking
# ---------------------------------------------------------------------------

SAMPLE_USERS = [
    {
        "Id": "user123",
        "Name": "Admin",
        "Policy": {"IsAdministrator": True},
    },
    {
        "Id": "user456",
        "Name": "Guest",
        "Policy": {"IsAdministrator": False},
    },
]

SAMPLE_SEARCH_RESULTS = {
    "Items": [
        {
            "Id": "item001",
            "Name": "Inception",
            "Type": "Movie",
            "ProductionYear": 2010,
            "Overview": "A thief who steals corporate secrets through dream-sharing technology is given the task of planting an idea.",
        },
        {
            "Id": "item002",
            "Name": "Interstellar",
            "Type": "Movie",
            "ProductionYear": 2014,
            "Overview": "A team of explorers travel through a wormhole in space.",
        },
    ],
    "TotalRecordCount": 2,
}

SAMPLE_SEARCH_EMPTY = {"Items": [], "TotalRecordCount": 0}

SAMPLE_RESUME_ITEMS = {
    "Items": [
        {
            "Id": "item010",
            "Name": "Ozark",
            "Type": "Episode",
            "SeriesName": "Ozark",
            "ParentIndexNumber": 3,
            "IndexNumber": 5,
            "RunTimeTicks": 36000000000,  # 60 min
            "UserData": {"PlaybackPositionTicks": 18000000000},  # 30 min
        },
    ],
    "TotalRecordCount": 1,
}

SAMPLE_LATEST_ITEMS = [
    {
        "Id": "item020",
        "Name": "Dune: Part Two",
        "Type": "Movie",
        "ProductionYear": 2024,
        "Overview": "Follow the mythic journey of Paul Atreides.",
    },
]

SAMPLE_SESSIONS = [
    {
        "Id": "sess001",
        "DeviceName": "Living Room TV",
        "Client": "Jellyfin Web",
        "UserName": "Admin",
        "NowPlayingItem": {
            "Name": "Pilot",
            "Type": "Episode",
            "SeriesName": "Breaking Bad",
            "ParentIndexNumber": 1,
            "IndexNumber": 1,
        },
        "PlayState": {
            "IsPaused": False,
            "PositionTicks": 12000000000,  # 20 min
        },
    },
    {
        "Id": "sess002",
        "DeviceName": "iPhone",
        "Client": "Jellyfin Mobile",
        "UserName": "Guest",
    },
]

SAMPLE_SESSIONS_EMPTY = []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tool():
    """Create a tool instance with test config."""
    return JellyfinTool(base_url="http://jellyfin:8096", api_key="test_key_123")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestJellyfinToolProperties:
    """Verify tool metadata."""

    def test_name(self, tool):
        assert tool.name == "jellyfin"

    def test_description_mentions_media(self, tool):
        assert "media" in tool.description.lower()

    def test_parameters_has_action(self, tool):
        props = tool.parameters["properties"]
        assert "action" in props
        assert set(props["action"]["enum"]) == {
            "search_library",
            "get_resume",
            "get_latest",
            "get_sessions",
            "play_media",
            "playstate_command",
        }

    def test_required_fields(self, tool):
        assert tool.parameters["required"] == ["action"]

    def test_to_schema(self, tool):
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "jellyfin"
        assert "parameters" in schema["function"]


class TestMissingConfig:
    """Error when Jellyfin is not configured."""

    @pytest.mark.asyncio
    async def test_missing_url(self):
        tool = JellyfinTool(base_url="", api_key="key")
        result = await tool.execute(action="search_library", query="test")
        assert "must be configured" in result

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        tool = JellyfinTool(base_url="http://jellyfin:8096", api_key="")
        result = await tool.execute(action="search_library", query="test")
        assert "must be configured" in result


class TestSearchLibrary:
    """Tests for the search_library action."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self, tool):
        with patch("tools.jellyfin.aiohttp.ClientSession") as mock_cls:
            mock_session = mock_cls.return_value

            # Sequence: users → items
            users_resp = AsyncMock(status=200)
            users_resp.json = AsyncMock(return_value=SAMPLE_USERS)

            items_resp = AsyncMock(status=200)
            items_resp.json = AsyncMock(return_value=SAMPLE_SEARCH_RESULTS)

            mock_session.get.return_value.__aenter__.side_effect = [
                users_resp,
                items_resp,
            ]

            result = await tool.execute(action="search_library", query="Inception")

            assert "Inception" in result
            assert "2010" in result
            assert "item001" in result
            assert "2 item" in result

    @pytest.mark.asyncio
    async def test_search_no_results(self, tool):
        with patch("tools.jellyfin.aiohttp.ClientSession") as mock_cls:
            mock_session = mock_cls.return_value

            users_resp = AsyncMock(status=200)
            users_resp.json = AsyncMock(return_value=SAMPLE_USERS)

            items_resp = AsyncMock(status=200)
            items_resp.json = AsyncMock(return_value=SAMPLE_SEARCH_EMPTY)

            mock_session.get.return_value.__aenter__.side_effect = [
                users_resp,
                items_resp,
            ]

            result = await tool.execute(action="search_library", query="Nonexistent123")

            assert "No results found" in result

    @pytest.mark.asyncio
    async def test_search_missing_query(self, tool):
        result = await tool.execute(action="search_library")
        assert "query is required" in result

    @pytest.mark.asyncio
    async def test_search_invalid_api_key(self, tool):
        with patch("tools.jellyfin.aiohttp.ClientSession") as mock_cls:
            mock_session = mock_cls.return_value

            users_resp = AsyncMock(status=200)
            users_resp.json = AsyncMock(return_value=SAMPLE_USERS)

            items_resp = AsyncMock(status=401)

            mock_session.get.return_value.__aenter__.side_effect = [
                users_resp,
                items_resp,
            ]

            result = await tool.execute(action="search_library", query="test")

            assert "Invalid" in result


class TestGetResume:
    """Tests for the get_resume action."""

    @pytest.mark.asyncio
    async def test_resume_with_items(self, tool):
        with patch("tools.jellyfin.aiohttp.ClientSession") as mock_cls:
            mock_session = mock_cls.return_value

            users_resp = AsyncMock(status=200)
            users_resp.json = AsyncMock(return_value=SAMPLE_USERS)

            resume_resp = AsyncMock(status=200)
            resume_resp.json = AsyncMock(return_value=SAMPLE_RESUME_ITEMS)

            mock_session.get.return_value.__aenter__.side_effect = [
                users_resp,
                resume_resp,
            ]

            result = await tool.execute(action="get_resume")

            assert "Ozark" in result
            assert "S03E05" in result
            assert "50%" in result

    @pytest.mark.asyncio
    async def test_resume_empty(self, tool):
        with patch("tools.jellyfin.aiohttp.ClientSession") as mock_cls:
            mock_session = mock_cls.return_value

            users_resp = AsyncMock(status=200)
            users_resp.json = AsyncMock(return_value=SAMPLE_USERS)

            resume_resp = AsyncMock(status=200)
            resume_resp.json = AsyncMock(return_value=SAMPLE_SEARCH_EMPTY)

            mock_session.get.return_value.__aenter__.side_effect = [
                users_resp,
                resume_resp,
            ]

            result = await tool.execute(action="get_resume")

            assert "Nothing in continue watching" in result


class TestGetLatest:
    """Tests for the get_latest action."""

    @pytest.mark.asyncio
    async def test_latest_returns_items(self, tool):
        with patch("tools.jellyfin.aiohttp.ClientSession") as mock_cls:
            mock_session = mock_cls.return_value

            users_resp = AsyncMock(status=200)
            users_resp.json = AsyncMock(return_value=SAMPLE_USERS)

            latest_resp = AsyncMock(status=200)
            latest_resp.json = AsyncMock(return_value=SAMPLE_LATEST_ITEMS)

            mock_session.get.return_value.__aenter__.side_effect = [
                users_resp,
                latest_resp,
            ]

            result = await tool.execute(action="get_latest")

            assert "Dune" in result
            assert "2024" in result
            assert "Recently Added" in result

    @pytest.mark.asyncio
    async def test_latest_empty(self, tool):
        with patch("tools.jellyfin.aiohttp.ClientSession") as mock_cls:
            mock_session = mock_cls.return_value

            users_resp = AsyncMock(status=200)
            users_resp.json = AsyncMock(return_value=SAMPLE_USERS)

            latest_resp = AsyncMock(status=200)
            latest_resp.json = AsyncMock(return_value=[])

            mock_session.get.return_value.__aenter__.side_effect = [
                users_resp,
                latest_resp,
            ]

            result = await tool.execute(action="get_latest")

            assert "No recently added" in result


class TestGetSessions:
    """Tests for the get_sessions action."""

    @pytest.mark.asyncio
    async def test_sessions_with_playback(self, tool):
        with patch("tools.jellyfin.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SESSIONS)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="get_sessions")

            assert "Breaking Bad" in result
            assert "S01E01" in result
            assert "Living Room TV" in result
            assert "sess001" in result
            assert "Playing" in result
            assert "iPhone" in result

    @pytest.mark.asyncio
    async def test_sessions_empty(self, tool):
        with patch("tools.jellyfin.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_SESSIONS_EMPTY)
            mock_cls.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="get_sessions")

            assert "No active sessions" in result


class TestPlayMedia:
    """Tests for the play_media action."""

    @pytest.mark.asyncio
    async def test_play_success(self, tool):
        with patch("tools.jellyfin.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 204
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="play_media", session_id="sess001", item_id="item001"
            )

            assert "Started playback" in result

    @pytest.mark.asyncio
    async def test_play_missing_session_id(self, tool):
        result = await tool.execute(action="play_media", item_id="item001")
        assert "session_id is required" in result

    @pytest.mark.asyncio
    async def test_play_missing_item_id(self, tool):
        result = await tool.execute(action="play_media", session_id="sess001")
        assert "item_id is required" in result

    @pytest.mark.asyncio
    async def test_play_session_not_found(self, tool):
        with patch("tools.jellyfin.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 404
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="play_media", session_id="bad_id", item_id="item001"
            )

            assert "not found" in result


class TestPlaystateCommand:
    """Tests for the playstate_command action."""

    @pytest.mark.asyncio
    async def test_pause_success(self, tool):
        with patch("tools.jellyfin.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 204
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="playstate_command", session_id="sess001", command="Pause"
            )

            assert "Sent 'Pause'" in result

    @pytest.mark.asyncio
    async def test_seek_with_position(self, tool):
        with patch("tools.jellyfin.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 204
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="playstate_command",
                session_id="sess001",
                command="Seek",
                seek_position_ticks=300000000000,
            )

            assert "Sent 'Seek'" in result

    @pytest.mark.asyncio
    async def test_missing_session_id(self, tool):
        result = await tool.execute(action="playstate_command", command="Pause")
        assert "session_id is required" in result

    @pytest.mark.asyncio
    async def test_missing_command(self, tool):
        result = await tool.execute(
            action="playstate_command", session_id="sess001"
        )
        assert "command is required" in result

    @pytest.mark.asyncio
    async def test_invalid_command(self, tool):
        result = await tool.execute(
            action="playstate_command", session_id="sess001", command="Explode"
        )
        assert "Invalid command" in result

    @pytest.mark.asyncio
    async def test_session_not_found(self, tool):
        with patch("tools.jellyfin.aiohttp.ClientSession") as mock_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 404
            mock_cls.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="playstate_command", session_id="bad_id", command="Stop"
            )

            assert "not found" in result


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_unknown_action(self, tool):
        result = await tool.execute(action="explode")
        assert "Unknown action" in result

    @pytest.mark.asyncio
    async def test_connection_error(self, tool):
        with patch("tools.jellyfin.aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.get.return_value.__aenter__.side_effect = (
                aiohttp.ClientError("Connection refused")
            )

            result = await tool.execute(action="get_sessions")

            assert "Error" in result

    @pytest.mark.asyncio
    async def test_timeout_error(self, tool):
        with patch("tools.jellyfin.aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.get.return_value.__aenter__.side_effect = (
                TimeoutError()
            )

            result = await tool.execute(action="get_sessions")

            assert "timed out" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
