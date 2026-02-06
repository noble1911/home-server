"""Home Assistant integration tool for Butler.

This tool allows the agent to control smart home devices via
Home Assistant's REST API, enabling voice and text-based home automation.

Usage:
    The tool is automatically registered with Nanobot when the container starts.
    It requires HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN environment variables.

Example:
    # Create and use the tool
    tool = HomeAssistantTool()
    result = await tool.execute(action="turn_on", entity_id="light.kitchen")

    # When shutting down
    await tool.close()

API Reference:
    https://developers.home-assistant.io/docs/api/rest/
"""

from __future__ import annotations

from typing import Any
import os
import aiohttp

from .base import Tool


# Default timeout for HTTP requests (seconds)
DEFAULT_TIMEOUT = 10


class HomeAssistantTool(Tool):
    """Control Home Assistant devices and services.

    Supports turning devices on/off, getting device states,
    and calling arbitrary Home Assistant services.

    The tool reuses HTTP sessions for better performance and
    includes configurable timeouts for reliability.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Initialize the Home Assistant tool.

        Args:
            base_url: Home Assistant URL (default: HOME_ASSISTANT_URL env var)
            token: Long-lived access token (default: HOME_ASSISTANT_TOKEN env var)
            timeout: HTTP request timeout in seconds (default: 10)
        """
        self.base_url = (base_url or os.environ.get("HOME_ASSISTANT_URL", "")).rstrip("/")
        self.token = token or os.environ.get("HOME_ASSISTANT_TOKEN", "")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

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
        """Close the HTTP session.

        Should be called when shutting down to cleanly release connections.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    @property
    def name(self) -> str:
        return "home_assistant"

    @property
    def description(self) -> str:
        return (
            "Control smart home devices via Home Assistant. "
            "Can turn devices on/off, check their current state, "
            "or call any Home Assistant service (set brightness, play media, etc.)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["turn_on", "turn_off", "toggle", "get_state", "call_service"],
                    "description": (
                        "Action to perform: "
                        "turn_on/turn_off/toggle for simple control, "
                        "get_state to check current state, "
                        "call_service for advanced operations"
                    )
                },
                "entity_id": {
                    "type": "string",
                    "description": (
                        "The entity ID (e.g., 'light.living_room', 'switch.coffee_maker', "
                        "'media_player.tv'). Required for all actions except call_service "
                        "when targeting a domain-wide service."
                    )
                },
                "domain": {
                    "type": "string",
                    "description": (
                        "Service domain for call_service action (e.g., 'light', 'media_player'). "
                        "If not specified, extracted from entity_id."
                    )
                },
                "service": {
                    "type": "string",
                    "description": (
                        "Service name for call_service action (e.g., 'turn_on', 'set_volume_level'). "
                        "Required when action is 'call_service'."
                    )
                },
                "service_data": {
                    "type": "object",
                    "description": (
                        "Additional data for the service call (e.g., "
                        "{'brightness': 128} for lights, {'volume_level': 0.5} for media). "
                        "Entity_id is automatically included if provided."
                    )
                }
            },
            "required": ["action"]
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]
        entity_id = kwargs.get("entity_id")
        domain = kwargs.get("domain")
        service = kwargs.get("service")
        service_data = kwargs.get("service_data", {})

        if not self.base_url or not self.token:
            return "Error: HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN must be configured."

        try:
            if action == "get_state":
                return await self._get_state(entity_id)
            elif action in ("turn_on", "turn_off", "toggle"):
                return await self._simple_action(action, entity_id, service_data)
            elif action == "call_service":
                return await self._call_service(domain, service, entity_id, service_data)
            else:
                return f"Error: Unknown action '{action}'"
        except aiohttp.ClientError as e:
            return f"Error connecting to Home Assistant: {e}"
        except TimeoutError:
            return "Error: Home Assistant request timed out"
        except Exception as e:
            return f"Error: {e}"

    async def _get_state(self, entity_id: str | None) -> str:
        """Get the current state of an entity or list all entities."""
        session = await self._get_session()

        if entity_id:
            url = f"{self.base_url}/api/states/{entity_id}"
            async with session.get(url) as resp:
                if resp.status == 404:
                    return f"Entity '{entity_id}' not found."
                if resp.status != 200:
                    return f"Error: HTTP {resp.status}"

                data = await resp.json()
                return self._format_entity_state(data)
        else:
            # List all entities (summarized)
            url = f"{self.base_url}/api/states"
            async with session.get(url) as resp:
                if resp.status != 200:
                    return f"Error: HTTP {resp.status}"

                entities = await resp.json()
                return self._format_entity_list(entities)

    def _format_entity_state(self, entity: dict[str, Any]) -> str:
        """Format a single entity's state for display."""
        entity_id = entity.get("entity_id", "unknown")
        state = entity.get("state", "unknown")
        attrs = entity.get("attributes", {})
        friendly_name = attrs.get("friendly_name", entity_id)

        lines = [f"{friendly_name}: {state}"]

        # Add relevant attributes based on entity type
        if entity_id.startswith("light."):
            if brightness := attrs.get("brightness"):
                pct = round(brightness / 255 * 100)
                lines.append(f"  Brightness: {pct}%")
            if color_temp := attrs.get("color_temp"):
                lines.append(f"  Color temp: {color_temp}")
        elif entity_id.startswith("climate."):
            if temp := attrs.get("temperature"):
                lines.append(f"  Target: {temp}°")
            if current := attrs.get("current_temperature"):
                lines.append(f"  Current: {current}°")
        elif entity_id.startswith("media_player."):
            if media_title := attrs.get("media_title"):
                lines.append(f"  Playing: {media_title}")
            if volume := attrs.get("volume_level"):
                lines.append(f"  Volume: {round(volume * 100)}%")

        return "\n".join(lines)

    def _format_entity_list(self, entities: list[dict[str, Any]]) -> str:
        """Format a list of entities grouped by domain."""
        by_domain: dict[str, list[tuple[str, str, str]]] = {}

        for entity in entities:
            entity_id = entity.get("entity_id", "")
            state = entity.get("state", "unknown")
            friendly_name = entity.get("attributes", {}).get("friendly_name", entity_id)

            domain = entity_id.split(".")[0] if "." in entity_id else "other"
            if domain not in by_domain:
                by_domain[domain] = []
            by_domain[domain].append((entity_id, friendly_name, state))

        # Format output, prioritizing common domains
        priority_domains = ["light", "switch", "climate", "media_player", "cover", "fan"]
        lines = ["Home Assistant Entities:"]

        for domain in priority_domains:
            if domain in by_domain:
                count = len(by_domain[domain])
                domain_label = domain.replace("_", " ").title()
                # Proper pluralization
                if count == 1:
                    lines.append(f"\n{domain_label}:")
                else:
                    lines.append(f"\n{domain_label}s:")
                for entity_id, name, state in sorted(by_domain[domain]):
                    lines.append(f"  - {name}: {state} ({entity_id})")
                del by_domain[domain]

        # Add remaining domains
        for domain, items in sorted(by_domain.items()):
            if len(items) <= 10:  # Skip large domains like sensor
                lines.append(f"\n{domain.replace('_', ' ').title()}:")
                for entity_id, name, state in sorted(items):
                    lines.append(f"  - {name}: {state}")

        return "\n".join(lines)

    async def _simple_action(
        self,
        action: str,
        entity_id: str | None,
        service_data: dict[str, Any],
    ) -> str:
        """Execute turn_on, turn_off, or toggle."""
        if not entity_id:
            return f"Error: entity_id is required for {action}"

        domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"

        # Merge entity_id into service_data
        data = {**service_data, "entity_id": entity_id}

        session = await self._get_session()
        url = f"{self.base_url}/api/services/{domain}/{action}"
        async with session.post(url, json=data) as resp:
            if resp.status not in (200, 201):
                error_text = await resp.text()
                return f"Error: HTTP {resp.status} - {error_text}"

            # Get friendly name for response
            states = await resp.json()
            if states and isinstance(states, list):
                name = states[0].get("attributes", {}).get("friendly_name", entity_id)
                new_state = states[0].get("state", "unknown")
                return f"{name}: {action.replace('_', ' ')} -> {new_state}"

            return f"OK: {action} {entity_id}"

    async def _call_service(
        self,
        domain: str | None,
        service: str | None,
        entity_id: str | None,
        service_data: dict[str, Any],
    ) -> str:
        """Call an arbitrary Home Assistant service."""
        if not service:
            return "Error: 'service' is required for call_service action"

        # Infer domain from entity_id if not provided
        if not domain:
            if entity_id and "." in entity_id:
                domain = entity_id.split(".")[0]
            else:
                return "Error: 'domain' is required when entity_id doesn't specify one"

        # Build service data
        data = dict(service_data)
        if entity_id:
            data["entity_id"] = entity_id

        session = await self._get_session()
        url = f"{self.base_url}/api/services/{domain}/{service}"
        async with session.post(url, json=data) as resp:
            if resp.status not in (200, 201):
                error_text = await resp.text()
                return f"Error: HTTP {resp.status} - {error_text}"

            result = await resp.json()
            if result and isinstance(result, list) and len(result) > 0:
                # Return info about affected entities
                affected = [e.get("entity_id", "?") for e in result[:5]]
                return f"OK: {domain}.{service} -> affected: {', '.join(affected)}"

            return f"OK: {domain}.{service} called successfully"


class ListEntitiesByDomainTool(Tool):
    """List Home Assistant entities filtered by domain.

    Useful for discovering what devices are available in a specific category.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Initialize the tool.

        Args:
            base_url: Home Assistant URL (default: HOME_ASSISTANT_URL env var)
            token: Long-lived access token (default: HOME_ASSISTANT_TOKEN env var)
            timeout: HTTP request timeout in seconds (default: 10)
        """
        self.base_url = (base_url or os.environ.get("HOME_ASSISTANT_URL", "")).rstrip("/")
        self.token = token or os.environ.get("HOME_ASSISTANT_TOKEN", "")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

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
        return "list_ha_entities"

    @property
    def description(self) -> str:
        return (
            "List available Home Assistant entities, optionally filtered by domain. "
            "Use this to discover what devices can be controlled "
            "(e.g., 'light' for all lights, 'switch' for all switches)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": (
                        "Filter by domain (e.g., 'light', 'switch', 'climate', 'media_player'). "
                        "If not specified, returns a summary of all domains."
                    )
                }
            },
            "required": []
        }

    async def execute(self, **kwargs: Any) -> str:
        domain_filter = kwargs.get("domain")

        if not self.base_url or not self.token:
            return "Error: HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN must be configured."

        try:
            session = await self._get_session()
            url = f"{self.base_url}/api/states"
            async with session.get(url) as resp:
                if resp.status != 200:
                    return f"Error: HTTP {resp.status}"

                entities = await resp.json()

                if domain_filter:
                    # Filter to specific domain
                    filtered = [
                        e for e in entities
                        if e.get("entity_id", "").startswith(f"{domain_filter}.")
                    ]
                    if not filtered:
                        return f"No entities found in domain '{domain_filter}'"

                    lines = [f"{domain_filter.title()} entities:"]
                    for entity in sorted(filtered, key=lambda e: e.get("entity_id", "")):
                        entity_id = entity.get("entity_id", "")
                        state = entity.get("state", "unknown")
                        name = entity.get("attributes", {}).get("friendly_name", entity_id)
                        lines.append(f"  - {name}: {state} ({entity_id})")
                    return "\n".join(lines)
                else:
                    # Return domain summary
                    domains: dict[str, int] = {}
                    for entity in entities:
                        entity_id = entity.get("entity_id", "")
                        domain = entity_id.split(".")[0] if "." in entity_id else "other"
                        domains[domain] = domains.get(domain, 0) + 1

                    lines = ["Available domains:"]
                    for domain, count in sorted(domains.items()):
                        # Proper pluralization
                        entity_word = "entity" if count == 1 else "entities"
                        lines.append(f"  - {domain}: {count} {entity_word}")
                    return "\n".join(lines)

        except aiohttp.ClientError as e:
            return f"Error connecting to Home Assistant: {e}"
        except TimeoutError:
            return "Error: Home Assistant request timed out"
        except Exception as e:
            return f"Error: {e}"
