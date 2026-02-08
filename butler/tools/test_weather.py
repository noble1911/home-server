"""Tests for Weather tool.

Run with: pytest butler/tools/test_weather.py -v

These tests use mocked responses - no real API key required.
"""

import pytest
from unittest.mock import AsyncMock, patch

from .weather import WeatherTool


# Sample API responses for mocking
SAMPLE_CURRENT = {
    "name": "London",
    "sys": {"country": "GB", "sunrise": 1707204720, "sunset": 1707238020},
    "main": {"temp": 8.5, "feels_like": 6.2, "humidity": 82},
    "weather": [{"description": "light rain", "main": "Rain"}],
    "wind": {"speed": 4.1},
    "timezone": 0,
}

SAMPLE_FORECAST = {
    "city": {"name": "London", "country": "GB"},
    "list": [
        {
            "dt_txt": "2025-02-10 06:00:00",
            "main": {"temp": 7.0, "temp_min": 6.0, "temp_max": 8.0},
            "weather": [{"description": "overcast clouds"}],
            "pop": 0.1,
        },
        {
            "dt_txt": "2025-02-10 09:00:00",
            "main": {"temp": 8.0, "temp_min": 7.0, "temp_max": 9.0},
            "weather": [{"description": "light rain"}],
            "pop": 0.8,
        },
        {
            "dt_txt": "2025-02-10 12:00:00",
            "main": {"temp": 9.5, "temp_min": 8.5, "temp_max": 10.0},
            "weather": [{"description": "light rain"}],
            "pop": 0.7,
        },
        {
            "dt_txt": "2025-02-11 06:00:00",
            "main": {"temp": 5.0, "temp_min": 4.0, "temp_max": 6.0},
            "weather": [{"description": "clear sky"}],
            "pop": 0.0,
        },
        {
            "dt_txt": "2025-02-11 12:00:00",
            "main": {"temp": 7.0, "temp_min": 5.0, "temp_max": 8.0},
            "weather": [{"description": "clear sky"}],
            "pop": 0.05,
        },
        {
            "dt_txt": "2025-02-12 09:00:00",
            "main": {"temp": 10.0, "temp_min": 9.0, "temp_max": 12.0},
            "weather": [{"description": "scattered clouds"}],
            "pop": 0.15,
        },
    ],
}


@pytest.fixture
def tool():
    """Create a tool instance with test config."""
    return WeatherTool(api_key="test_key_123")


class TestWeatherTool:
    """Tests for the WeatherTool."""

    def test_tool_properties(self, tool):
        """Verify tool has required properties."""
        assert tool.name == "weather"
        assert "current weather" in tool.description or "forecast" in tool.description
        assert "action" in tool.parameters["properties"]
        assert "location" in tool.parameters["properties"]
        assert tool.parameters["required"] == ["action", "location"]

    def test_to_schema(self, tool):
        """Verify OpenAI function schema format."""
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "weather"
        assert "parameters" in schema["function"]

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Error when API key not configured."""
        tool = WeatherTool(api_key="")
        result = await tool.execute(action="current", location="London")
        assert "must be configured" in result

    @pytest.mark.asyncio
    async def test_current_weather(self, tool):
        """Test fetching current weather."""
        with patch("tools.weather.aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_CURRENT)

            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="current", location="London,GB")

            assert "London, GB" in result
            assert "8°C" in result
            assert "Light rain" in result
            assert "Humidity: 82%" in result
            assert "4.1 m/s" in result

    @pytest.mark.asyncio
    async def test_current_weather_not_found(self, tool):
        """Test handling of unknown location."""
        with patch("tools.weather.aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 404

            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="current", location="Nonexistentville")

            assert "not found" in result

    @pytest.mark.asyncio
    async def test_current_weather_invalid_key(self, tool):
        """Test handling of invalid API key."""
        with patch("tools.weather.aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 401

            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="current", location="London")

            assert "Invalid API key" in result

    @pytest.mark.asyncio
    async def test_forecast(self, tool):
        """Test fetching multi-day forecast."""
        with patch("tools.weather.aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_FORECAST)

            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="forecast", location="London,GB", days=3)

            assert "London, GB" in result
            assert "forecast" in result.lower()
            # Should have entries for Feb 10, 11, 12
            assert "Mon 10 Feb" in result
            assert "Tue 11 Feb" in result
            assert "Wed 12 Feb" in result

    @pytest.mark.asyncio
    async def test_forecast_day_limit(self, tool):
        """Test that days parameter limits output."""
        with patch("tools.weather.aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_FORECAST)

            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="forecast", location="London", days=1)

            assert "Mon 10 Feb" in result
            assert "Tue 11 Feb" not in result  # Should be excluded

    @pytest.mark.asyncio
    async def test_forecast_aggregation(self, tool):
        """Test that forecast aggregates 3-hour blocks correctly."""
        with patch("tools.weather.aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=SAMPLE_FORECAST)

            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="forecast", location="London", days=3)

            # Feb 10: min=6, max=10 -> "6-10°C"
            assert "6-10°C" in result
            # Feb 10 has light rain twice, overcast once -> "Light rain" wins
            assert "Light rain" in result
            # Feb 10 has max pop=0.8 -> should show precip
            assert "80% precip" in result

    @pytest.mark.asyncio
    async def test_forecast_not_found(self, tool):
        """Test forecast with unknown location."""
        with patch("tools.weather.aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 404

            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(action="forecast", location="Nonexistentville")

            assert "not found" in result

    @pytest.mark.asyncio
    async def test_units_imperial(self, tool):
        """Test imperial units in output."""
        imperial_data = dict(SAMPLE_CURRENT)
        imperial_data["main"] = {"temp": 47.3, "feels_like": 43.2, "humidity": 82}
        imperial_data["wind"] = {"speed": 9.2}

        with patch("tools.weather.aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=imperial_data)

            mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

            result = await tool.execute(
                action="current", location="London", units="imperial"
            )

            assert "°F" in result
            assert "mph" in result

    @pytest.mark.asyncio
    async def test_unknown_action(self, tool):
        """Error on unknown action."""
        result = await tool.execute(action="explode", location="London")
        assert "Unknown action" in result

    @pytest.mark.asyncio
    async def test_connection_error(self, tool):
        """Test handling of connection errors."""
        import aiohttp

        with patch("tools.weather.aiohttp.ClientSession") as mock_session:
            mock_session.return_value.get.return_value.__aenter__.side_effect = (
                aiohttp.ClientError("Connection refused")
            )

            result = await tool.execute(action="current", location="London")

            assert "Error" in result

    @pytest.mark.asyncio
    async def test_timeout_error(self, tool):
        """Test handling of timeout errors."""
        with patch("tools.weather.aiohttp.ClientSession") as mock_session:
            mock_session.return_value.get.return_value.__aenter__.side_effect = (
                TimeoutError()
            )

            result = await tool.execute(action="current", location="London")

            assert "timed out" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
