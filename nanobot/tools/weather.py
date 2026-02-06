"""Weather integration tool for Butler.

This tool allows the agent to check current weather conditions and
multi-day forecasts via the OpenWeatherMap API.

Usage:
    The tool is automatically registered with Nanobot when the container starts.
    It requires OPENWEATHERMAP_API_KEY to be set in the application settings.

Example:
    tool = WeatherTool()
    result = await tool.execute(action="current", location="London,GB")

    # When shutting down
    await tool.close()

API Reference:
    https://openweathermap.org/current
    https://openweathermap.org/forecast5
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any

import aiohttp

from .base import Tool

# Default timeout for HTTP requests (seconds)
DEFAULT_TIMEOUT = 10

# OpenWeatherMap API base URL
OWM_BASE_URL = "https://api.openweathermap.org/data/2.5"


class WeatherTool(Tool):
    """Fetch current weather and forecasts from OpenWeatherMap.

    Supports two actions:
    - "current": Get current conditions for a location
    - "forecast": Get a multi-day forecast (up to 5 days)

    The tool reuses HTTP sessions for better performance and
    includes configurable timeouts for reliability.
    """

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Initialize the Weather tool.

        Args:
            api_key: OpenWeatherMap API key (passed from settings)
            timeout: HTTP request timeout in seconds (default: 10)
        """
        self.api_key = api_key or ""
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self) -> None:
        """Close the HTTP session.

        Should be called when shutting down to cleanly release connections.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return (
            "Get current weather conditions or a multi-day forecast for any location. "
            "Use 'current' for right now, 'forecast' for upcoming days (up to 5). "
            "Locations can be city names like 'London' or 'London,GB' for precision."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["current", "forecast"],
                    "description": (
                        "Action to perform: "
                        "'current' for current conditions, "
                        "'forecast' for multi-day forecast (up to 5 days)"
                    ),
                },
                "location": {
                    "type": "string",
                    "description": (
                        "City name, optionally with country code "
                        "(e.g., 'London', 'London,GB', 'Tokyo,JP')"
                    ),
                },
                "days": {
                    "type": "integer",
                    "description": (
                        "Number of forecast days (1-5, default: 3). "
                        "Only used with 'forecast' action."
                    ),
                    "minimum": 1,
                    "maximum": 5,
                },
                "units": {
                    "type": "string",
                    "enum": ["metric", "imperial"],
                    "description": (
                        "Temperature units: 'metric' for Celsius (default), "
                        "'imperial' for Fahrenheit"
                    ),
                },
            },
            "required": ["action", "location"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]
        location = kwargs["location"]
        days = kwargs.get("days", 3)
        units = kwargs.get("units", "metric")

        if not self.api_key:
            return "Error: OPENWEATHERMAP_API_KEY must be configured."

        try:
            if action == "current":
                return await self._get_current(location, units)
            elif action == "forecast":
                return await self._get_forecast(location, units, days)
            else:
                return f"Error: Unknown action '{action}'"
        except aiohttp.ClientError as e:
            return f"Error connecting to weather service: {e}"
        except TimeoutError:
            return "Error: Weather service request timed out"
        except Exception as e:
            return f"Error: {e}"

    async def _get_current(self, location: str, units: str) -> str:
        """Fetch current weather conditions."""
        session = await self._get_session()
        params = {"q": location, "appid": self.api_key, "units": units}

        async with session.get(f"{OWM_BASE_URL}/weather", params=params) as resp:
            if resp.status == 404:
                return (
                    f"Location '{location}' not found. "
                    "Try adding a country code (e.g., 'London,GB')."
                )
            if resp.status == 401:
                return "Error: Invalid API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            data = await resp.json()
            return self._format_current(data, units)

    async def _get_forecast(self, location: str, units: str, days: int) -> str:
        """Fetch and aggregate multi-day forecast."""
        session = await self._get_session()
        params = {"q": location, "appid": self.api_key, "units": units}

        async with session.get(f"{OWM_BASE_URL}/forecast", params=params) as resp:
            if resp.status == 404:
                return (
                    f"Location '{location}' not found. "
                    "Try adding a country code (e.g., 'London,GB')."
                )
            if resp.status == 401:
                return "Error: Invalid API key."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            data = await resp.json()
            return self._aggregate_forecast(data, units, days)

    def _format_current(self, data: dict, units: str) -> str:
        """Format current weather API response into readable text."""
        city = data.get("name", "Unknown")
        country = data.get("sys", {}).get("country", "")
        location_str = f"{city}, {country}" if country else city

        main = data.get("main", {})
        temp = main.get("temp", 0)
        feels_like = main.get("feels_like", 0)
        humidity = main.get("humidity", 0)

        weather = data.get("weather", [{}])[0]
        condition = weather.get("description", "unknown").capitalize()

        wind_speed = data.get("wind", {}).get("speed", 0)

        t_unit = self._temp_unit(units)
        s_unit = self._speed_unit(units)

        lines = [
            f"{location_str}: {temp:.0f}{t_unit} (feels like {feels_like:.0f}{t_unit})",
            condition,
            f"Humidity: {humidity}% | Wind: {wind_speed} {s_unit}",
        ]

        # Add sunrise/sunset if available
        sys_data = data.get("sys", {})
        tz_offset = data.get("timezone", 0)
        sunrise_ts = sys_data.get("sunrise")
        sunset_ts = sys_data.get("sunset")
        if sunrise_ts and sunset_ts:
            tz = timezone(timedelta(seconds=tz_offset))
            sunrise = datetime.fromtimestamp(sunrise_ts, tz=tz).strftime("%H:%M")
            sunset = datetime.fromtimestamp(sunset_ts, tz=tz).strftime("%H:%M")
            lines.append(f"Sunrise: {sunrise} | Sunset: {sunset}")

        return "\n".join(lines)

    def _aggregate_forecast(self, data: dict, units: str, days: int) -> str:
        """Aggregate 3-hour forecast blocks into daily summaries."""
        city_info = data.get("city", {})
        city = city_info.get("name", "Unknown")
        country = city_info.get("country", "")
        location_str = f"{city}, {country}" if country else city

        # Group forecast blocks by date
        daily: dict[str, list[dict]] = {}
        for block in data.get("list", []):
            dt_txt = block.get("dt_txt", "")
            date_str = dt_txt.split(" ")[0] if dt_txt else ""
            if date_str:
                daily.setdefault(date_str, []).append(block)

        t_unit = self._temp_unit(units)

        # Build daily summaries, limited to requested days
        day_lines = []
        for date_str in sorted(daily.keys())[:days]:
            blocks = daily[date_str]

            # Temperature range
            temps_min = [b["main"]["temp_min"] for b in blocks if "main" in b]
            temps_max = [b["main"]["temp_max"] for b in blocks if "main" in b]
            low = min(temps_min) if temps_min else 0
            high = max(temps_max) if temps_max else 0

            # Most frequent weather condition
            conditions = [
                b["weather"][0]["description"]
                for b in blocks
                if b.get("weather")
            ]
            condition = Counter(conditions).most_common(1)[0][0].capitalize() if conditions else "Unknown"

            # Max precipitation probability
            max_pop = max((b.get("pop", 0) for b in blocks), default=0)

            # Format date as "Mon 10 Feb"
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            date_label = date_obj.strftime("%a %d %b")

            line = f"{date_label}: {low:.0f}-{high:.0f}{t_unit}, {condition}"
            if max_pop > 0.2:
                line += f" ({max_pop:.0%} precip)"
            day_lines.append(line)

        if not day_lines:
            return f"No forecast data available for {location_str}."

        header = f"{days}-day forecast for {location_str}:"
        return header + "\n\n" + "\n".join(day_lines)

    def _temp_unit(self, units: str) -> str:
        """Return the temperature unit symbol."""
        return "\u00b0F" if units == "imperial" else "\u00b0C"

    def _speed_unit(self, units: str) -> str:
        """Return the wind speed unit."""
        return "mph" if units == "imperial" else "m/s"
