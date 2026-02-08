"""Tests for Home Assistant tool.

Run with: pytest butler/tools/test_home_assistant.py -v

These tests use mocked responses - no real Home Assistant required.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from .home_assistant import HomeAssistantTool, ListEntitiesByDomainTool


@pytest.fixture
def tool():
    """Create a tool instance with test config."""
    return HomeAssistantTool(
        base_url="http://homeassistant:8123",
        token="test_token_123"
    )


@pytest.fixture
def list_tool():
    """Create a list entities tool instance."""
    return ListEntitiesByDomainTool(
        base_url="http://homeassistant:8123",
        token="test_token_123"
    )


class TestHomeAssistantTool:
    """Tests for the main HomeAssistantTool."""

    def test_tool_properties(self, tool):
        """Verify tool has required properties."""
        assert tool.name == "home_assistant"
        assert "Control smart home" in tool.description
        assert "action" in tool.parameters["properties"]
        assert tool.parameters["required"] == ["action"]

    def test_to_schema(self, tool):
        """Verify OpenAI function schema format."""
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "home_assistant"
        assert "parameters" in schema["function"]

    @pytest.mark.asyncio
    async def test_missing_config(self):
        """Error when URL/token not configured."""
        tool = HomeAssistantTool(base_url="", token="")
        result = await tool.execute(action="get_state", entity_id="light.test")
        assert "must be configured" in result

    @pytest.mark.asyncio
    async def test_get_state_single_entity(self, tool):
        """Test getting state of a single entity."""
        mock_response = {
            "entity_id": "light.living_room",
            "state": "on",
            "attributes": {
                "friendly_name": "Living Room Light",
                "brightness": 128
            }
        }

        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=mock_response)

            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="get_state", entity_id="light.living_room")

            assert "Living Room Light" in result
            assert "on" in result
            assert "Brightness: 50%" in result  # 128/255 ≈ 50%

    @pytest.mark.asyncio
    async def test_get_state_not_found(self, tool):
        """Test handling of missing entity."""
        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 404

            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="get_state", entity_id="light.nonexistent")

            assert "not found" in result

    @pytest.mark.asyncio
    async def test_turn_on(self, tool):
        """Test turning on a device."""
        mock_response = [{
            "entity_id": "light.kitchen",
            "state": "on",
            "attributes": {"friendly_name": "Kitchen Light"}
        }]

        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=mock_response)

            mock_session.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="turn_on", entity_id="light.kitchen")

            assert "Kitchen Light" in result
            assert "turn on" in result
            assert "on" in result

    @pytest.mark.asyncio
    async def test_turn_off(self, tool):
        """Test turning off a device."""
        mock_response = [{
            "entity_id": "switch.coffee_maker",
            "state": "off",
            "attributes": {"friendly_name": "Coffee Maker"}
        }]

        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=mock_response)

            mock_session.return_value.post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="turn_off", entity_id="switch.coffee_maker")

            assert "Coffee Maker" in result

    @pytest.mark.asyncio
    async def test_turn_on_missing_entity_id(self, tool):
        """Error when entity_id missing for turn_on."""
        result = await tool.execute(action="turn_on")
        assert "entity_id is required" in result

    @pytest.mark.asyncio
    async def test_call_service_with_data(self, tool):
        """Test calling a service with extra data."""
        mock_response = [{
            "entity_id": "light.bedroom",
            "state": "on"
        }]

        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=mock_response)
            mock_post = mock_session.return_value.post
            mock_post.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="call_service",
                entity_id="light.bedroom",
                service="turn_on",
                service_data={"brightness": 200}
            )

            assert "OK" in result

    @pytest.mark.asyncio
    async def test_call_service_missing_service(self, tool):
        """Error when service name missing."""
        result = await tool.execute(
            action="call_service",
            entity_id="light.test"
        )
        assert "'service' is required" in result

    @pytest.mark.asyncio
    async def test_unknown_action(self, tool):
        """Error on unknown action."""
        result = await tool.execute(action="explode", entity_id="light.test")
        assert "Unknown action" in result


class TestListEntitiesByDomainTool:
    """Tests for ListEntitiesByDomainTool."""

    def test_tool_properties(self, list_tool):
        """Verify tool properties."""
        assert list_tool.name == "list_ha_entities"
        assert "List available" in list_tool.description
        assert list_tool.parameters["required"] == []

    @pytest.mark.asyncio
    async def test_list_by_domain(self, list_tool):
        """Test listing entities filtered by domain."""
        mock_response = [
            {"entity_id": "light.living_room", "state": "on", "attributes": {"friendly_name": "Living Room"}},
            {"entity_id": "light.kitchen", "state": "off", "attributes": {"friendly_name": "Kitchen"}},
            {"entity_id": "switch.fan", "state": "off", "attributes": {"friendly_name": "Fan"}},
        ]

        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=mock_response)

            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await list_tool.execute(domain="light")

            assert "Living Room" in result
            assert "Kitchen" in result
            assert "Fan" not in result  # switch, not light

    @pytest.mark.asyncio
    async def test_list_domain_summary(self, list_tool):
        """Test getting domain summary when no filter specified."""
        mock_response = [
            {"entity_id": "light.a", "state": "on", "attributes": {}},
            {"entity_id": "light.b", "state": "off", "attributes": {}},
            {"entity_id": "switch.c", "state": "on", "attributes": {}},
            {"entity_id": "sensor.d", "state": "25", "attributes": {}},
        ]

        with patch("aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=mock_response)

            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await list_tool.execute()

            assert "light: 2 entities" in result
            assert "switch: 1 entity" in result
            assert "sensor: 1 entity" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
