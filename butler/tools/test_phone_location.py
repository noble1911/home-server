"""Tests for Phone Location tool.

Run with: pytest butler/tools/test_phone_location.py -v

These tests use mocked responses - no real Home Assistant required.
"""

import pytest
from unittest.mock import AsyncMock, patch

from .phone_location import PhoneLocationTool, _haversine


# Sample HA API responses
PERSON_RON_HOME = {
    "entity_id": "person.ron",
    "state": "home",
    "attributes": {
        "friendly_name": "Ron",
        "latitude": 51.5074,
        "longitude": -0.1278,
        "gps_accuracy": 10,
        "source": "device_tracker.ron_phone",
    },
}

PERSON_RON_AWAY = {
    "entity_id": "person.ron",
    "state": "work",
    "attributes": {
        "friendly_name": "Ron",
        "latitude": 51.5155,
        "longitude": -0.1419,
        "gps_accuracy": 15,
        "source": "device_tracker.ron_phone",
    },
}

PERSON_ALICE_HOME = {
    "entity_id": "person.alice",
    "state": "home",
    "attributes": {
        "friendly_name": "Alice",
        "latitude": 51.5074,
        "longitude": -0.1278,
        "gps_accuracy": 8,
        "source": "device_tracker.alice_phone",
    },
}

ZONE_HOME = {
    "entity_id": "zone.home",
    "state": "0",
    "attributes": {
        "latitude": 51.5074,
        "longitude": -0.1278,
        "radius": 100,
        "friendly_name": "Home",
    },
}

ALL_ENTITIES = [
    PERSON_RON_HOME,
    PERSON_ALICE_HOME,
    {"entity_id": "light.kitchen", "state": "on", "attributes": {}},
    {"entity_id": "switch.fan", "state": "off", "attributes": {}},
]


@pytest.fixture
def tool():
    """Create a tool instance with test config."""
    return PhoneLocationTool(
        base_url="http://homeassistant:8123",
        token="test_token_123",
    )


class TestToolProperties:
    """Test tool metadata."""

    def test_name(self, tool):
        assert tool.name == "phone_location"

    def test_description(self, tool):
        assert "phone location" in tool.description.lower()
        assert "read-only" in tool.description.lower()

    def test_parameters(self, tool):
        params = tool.parameters
        assert "action" in params["properties"]
        actions = params["properties"]["action"]["enum"]
        assert "locate" in actions
        assert "is_home" in actions
        assert "list_people" in actions
        assert "distance_from_home" in actions
        assert params["required"] == ["action"]

    def test_to_schema(self, tool):
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "phone_location"


class TestMissingConfig:
    """Test error handling when not configured."""

    @pytest.mark.asyncio
    async def test_missing_url(self):
        tool = PhoneLocationTool(base_url="", token="")
        result = await tool.execute(action="locate", name="ron")
        assert "must be configured" in result

    @pytest.mark.asyncio
    async def test_missing_name_locate(self, tool):
        result = await tool.execute(action="locate")
        assert "'name' is required" in result

    @pytest.mark.asyncio
    async def test_missing_name_is_home(self, tool):
        result = await tool.execute(action="is_home")
        assert "'name' is required" in result

    @pytest.mark.asyncio
    async def test_missing_name_distance(self, tool):
        result = await tool.execute(action="distance_from_home")
        assert "'name' is required" in result

    @pytest.mark.asyncio
    async def test_unknown_action(self, tool):
        result = await tool.execute(action="teleport")
        assert "Unknown action" in result


class TestLocate:
    """Test the locate action."""

    @pytest.mark.asyncio
    async def test_locate_home(self, tool):
        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=PERSON_RON_HOME)
            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="locate", name="ron")

            assert "Ron" in result
            assert "home" in result
            assert "51.5074" in result
            assert "GPS accuracy: 10m" in result

    @pytest.mark.asyncio
    async def test_locate_not_found(self, tool):
        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 404
            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="locate", name="nobody")

            assert "not found" in result
            assert "list_people" in result


class TestIsHome:
    """Test the is_home action."""

    @pytest.mark.asyncio
    async def test_is_home_yes(self, tool):
        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=PERSON_RON_HOME)
            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="is_home", name="ron")

            assert "Yes" in result
            assert "Ron" in result
            assert "is home" in result

    @pytest.mark.asyncio
    async def test_is_home_no(self, tool):
        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=PERSON_RON_AWAY)
            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="is_home", name="ron")

            assert "No" in result
            assert "not home" in result
            assert "work" in result


class TestListPeople:
    """Test the list_people action."""

    @pytest.mark.asyncio
    async def test_list_people(self, tool):
        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=ALL_ENTITIES)
            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="list_people")

            assert "Ron" in result
            assert "Alice" in result
            assert "2" in result  # count
            # Should NOT include non-person entities
            assert "kitchen" not in result
            assert "fan" not in result

    @pytest.mark.asyncio
    async def test_list_people_empty(self, tool):
        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=[
                {"entity_id": "light.kitchen", "state": "on", "attributes": {}},
            ])
            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="list_people")

            assert "No tracked people" in result


class TestDistanceFromHome:
    """Test the distance_from_home action."""

    @pytest.mark.asyncio
    async def test_distance_at_home(self, tool):
        """Person at home coords should report 'at home'."""
        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp_person = AsyncMock()
            mock_resp_person.status = 200
            mock_resp_person.json = AsyncMock(return_value=PERSON_RON_HOME)

            mock_resp_zone = AsyncMock()
            mock_resp_zone.status = 200
            mock_resp_zone.json = AsyncMock(return_value=ZONE_HOME)

            # First call = person state, second call = zone.home
            mock_session.return_value.get.return_value.__aenter__.side_effect = [
                mock_resp_person, mock_resp_zone,
            ]

            result = await tool.execute(action="distance_from_home", name="ron")

            assert "at home" in result

    @pytest.mark.asyncio
    async def test_distance_away(self, tool):
        """Person at different coords should report distance."""
        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp_person = AsyncMock()
            mock_resp_person.status = 200
            mock_resp_person.json = AsyncMock(return_value=PERSON_RON_AWAY)

            mock_resp_zone = AsyncMock()
            mock_resp_zone.status = 200
            mock_resp_zone.json = AsyncMock(return_value=ZONE_HOME)

            mock_session.return_value.get.return_value.__aenter__.side_effect = [
                mock_resp_person, mock_resp_zone,
            ]

            result = await tool.execute(action="distance_from_home", name="ron")

            assert "km from home" in result or "m from home" in result
            assert "Ron" in result

    @pytest.mark.asyncio
    async def test_distance_no_gps(self, tool):
        """Error when person has no GPS coordinates."""
        person_no_gps = {
            "entity_id": "person.ron",
            "state": "unknown",
            "attributes": {"friendly_name": "Ron"},
        }

        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=person_no_gps)
            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="distance_from_home", name="ron")

            assert "No GPS coordinates" in result

    @pytest.mark.asyncio
    async def test_distance_no_home_zone(self, tool):
        """Error when zone.home is not available."""
        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp_person = AsyncMock()
            mock_resp_person.status = 200
            mock_resp_person.json = AsyncMock(return_value=PERSON_RON_AWAY)

            mock_resp_zone = AsyncMock()
            mock_resp_zone.status = 404

            mock_session.return_value.get.return_value.__aenter__.side_effect = [
                mock_resp_person, mock_resp_zone,
            ]

            result = await tool.execute(action="distance_from_home", name="ron")

            assert "Could not determine home location" in result


class TestHaversine:
    """Test the Haversine distance formula directly."""

    def test_same_point(self):
        assert _haversine(51.5, -0.1, 51.5, -0.1) == 0.0

    def test_known_distance(self):
        # London (51.5074, -0.1278) to Paris (48.8566, 2.3522) ≈ 344 km
        dist = _haversine(51.5074, -0.1278, 48.8566, 2.3522)
        assert 340 < dist < 348

    def test_short_distance(self):
        # ~1 km apart
        dist = _haversine(51.5074, -0.1278, 51.5164, -0.1278)
        assert 0.9 < dist < 1.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
