"""Phone location tool for Butler.

Read-only tool that queries Home Assistant person entities to determine
household members' locations, home/away status, and distance from home.

Usage:
    tool = PhoneLocationTool(
        base_url="http://homeassistant:8123",
        token="your-long-lived-access-token",
    )
    result = await tool.execute(action="is_home", name="ron")

    # When shutting down
    await tool.close()

Requires:
    - Home Assistant with Companion App installed on household phones
    - person.* entities configured in Home Assistant
    - Long-lived access token with read access

API Reference:
    https://developers.home-assistant.io/docs/api/rest/
"""

from __future__ import annotations

import math
from typing import Any

import aiohttp

from .base import Tool

# Default timeout for HTTP requests (seconds)
DEFAULT_TIMEOUT = 10

# Earth radius in kilometres (mean radius)
EARTH_RADIUS_KM = 6371.0


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in km."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class PhoneLocationTool(Tool):
    """Query household members' phone locations via Home Assistant.

    Uses HA person entities (which aggregate device_tracker sources like
    the Companion App, router presence, Bluetooth, etc.) to provide
    home/away status, GPS coordinates, and distance-from-home calculations.

    Strictly read-only — no location broadcasting or modification.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Initialize the phone location tool.

        Args:
            base_url: Home Assistant URL (e.g., http://homeassistant:8123)
            token: Long-lived access token
            timeout: HTTP request timeout in seconds (default: 10)
        """
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None
        self._home_coords: tuple[float, float] | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    @property
    def name(self) -> str:
        return "phone_location"

    @property
    def description(self) -> str:
        return (
            "Check household members' phone locations. "
            "Can determine if someone is home or away, get their current zone, "
            "list all tracked people, or calculate distance from home. Read-only."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["locate", "is_home", "list_people", "distance_from_home"],
                    "description": (
                        "locate: get a person's current location and zone. "
                        "is_home: check if a person is home (true/false). "
                        "list_people: show all tracked people with status. "
                        "distance_from_home: calculate km from home."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": (
                        "Person name as configured in Home Assistant "
                        "(e.g., 'ron', 'alice'). Required for locate, is_home, "
                        "and distance_from_home."
                    ),
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]

        if not self.base_url or not self.token:
            return "Error: HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN must be configured."

        try:
            if action == "locate":
                return await self._locate(kwargs.get("name"))
            elif action == "is_home":
                return await self._is_home(kwargs.get("name"))
            elif action == "list_people":
                return await self._list_people()
            elif action == "distance_from_home":
                return await self._distance_from_home(kwargs.get("name"))
            else:
                return f"Error: Unknown action '{action}'"
        except aiohttp.ClientError as e:
            return f"Error connecting to Home Assistant: {e}"
        except TimeoutError:
            return "Error: Home Assistant request timed out"
        except Exception as e:
            return f"Error: {e}"

    async def _get_person_state(self, name: str) -> dict[str, Any] | str:
        """Fetch a person entity's state. Returns dict on success, error string on failure."""
        session = await self._get_session()
        entity_id = f"person.{name}"
        url = f"{self.base_url}/api/states/{entity_id}"
        async with session.get(url) as resp:
            if resp.status == 404:
                return f"Person '{name}' not found. Use list_people to see available names."
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"
            return await resp.json()

    async def _get_home_coords(self) -> tuple[float, float] | None:
        """Get home zone coordinates, caching after first fetch."""
        if self._home_coords is not None:
            return self._home_coords

        session = await self._get_session()
        url = f"{self.base_url}/api/states/zone.home"
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            attrs = data.get("attributes", {})
            lat = attrs.get("latitude")
            lon = attrs.get("longitude")
            if lat is not None and lon is not None:
                self._home_coords = (float(lat), float(lon))
                return self._home_coords
        return None

    async def _locate(self, name: str | None) -> str:
        """Get a person's current location details."""
        if not name:
            return "Error: 'name' is required for locate action."

        data = await self._get_person_state(name)
        if isinstance(data, str):
            return data

        attrs = data.get("attributes", {})
        state = data.get("state", "unknown")
        friendly_name = attrs.get("friendly_name", name.title())
        lat = attrs.get("latitude")
        lon = attrs.get("longitude")
        gps_accuracy = attrs.get("gps_accuracy")

        lines = [f"{friendly_name}: {state}"]
        if lat is not None and lon is not None:
            lines.append(f"  Coordinates: {lat:.6f}, {lon:.6f}")
        if gps_accuracy is not None:
            lines.append(f"  GPS accuracy: {gps_accuracy}m")
        if source := attrs.get("source"):
            lines.append(f"  Source: {source}")

        return "\n".join(lines)

    async def _is_home(self, name: str | None) -> str:
        """Check whether a person is home."""
        if not name:
            return "Error: 'name' is required for is_home action."

        data = await self._get_person_state(name)
        if isinstance(data, str):
            return data

        state = data.get("state", "unknown")
        friendly_name = data.get("attributes", {}).get("friendly_name", name.title())
        is_home = state == "home"

        if is_home:
            return f"Yes, {friendly_name} is home."
        else:
            return f"No, {friendly_name} is not home (zone: {state})."

    async def _list_people(self) -> str:
        """List all tracked people with their home/away status."""
        session = await self._get_session()
        url = f"{self.base_url}/api/states"
        async with session.get(url) as resp:
            if resp.status != 200:
                return f"Error: HTTP {resp.status}"

            entities = await resp.json()
            people = [
                e for e in entities
                if e.get("entity_id", "").startswith("person.")
            ]

            if not people:
                return "No tracked people found in Home Assistant."

            lines = [f"Tracked people ({len(people)}):"]
            for person in sorted(people, key=lambda p: p.get("entity_id", "")):
                friendly_name = person.get("attributes", {}).get("friendly_name", "?")
                state = person.get("state", "unknown")
                entity_id = person.get("entity_id", "")
                person_name = entity_id.removeprefix("person.")
                icon = "🏠" if state == "home" else "📍"
                lines.append(f"  {icon} {friendly_name} ({person_name}): {state}")

            return "\n".join(lines)

    async def _distance_from_home(self, name: str | None) -> str:
        """Calculate distance from home for a person."""
        if not name:
            return "Error: 'name' is required for distance_from_home action."

        data = await self._get_person_state(name)
        if isinstance(data, str):
            return data

        attrs = data.get("attributes", {})
        state = data.get("state", "unknown")
        friendly_name = attrs.get("friendly_name", name.title())
        person_lat = attrs.get("latitude")
        person_lon = attrs.get("longitude")

        if person_lat is None or person_lon is None:
            return f"Error: No GPS coordinates available for {friendly_name}."

        home_coords = await self._get_home_coords()
        if home_coords is None:
            return "Error: Could not determine home location from zone.home entity."

        distance = _haversine(home_coords[0], home_coords[1], float(person_lat), float(person_lon))

        if distance < 0.1:
            return f"{friendly_name} is at home."
        elif distance < 1:
            return f"{friendly_name} is {distance * 1000:.0f}m from home (zone: {state})."
        else:
            return f"{friendly_name} is {distance:.1f} km from home (zone: {state})."
