"""Server health monitoring tool for Butler.

Checks the health of all Docker services on the homeserver network via
HTTP endpoints.  Butler can call this on-demand ("how's the server?")
or a scheduled job can invoke it periodically.

Usage:
    alert_mgr = AlertStateManager(db_pool)
    tool = ServerHealthTool(db_pool=db_pool, alert_manager=alert_mgr)
    result = await tool.execute(action="check_all")

    # When shutting down
    await tool.close()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .alerting import AlertStateManager
from .base import Tool
from .memory import DatabasePool

logger = logging.getLogger(__name__)

# Per-service timeout for health checks (seconds)
DEFAULT_TIMEOUT = 5

# Service definitions keyed by logical name.
# Each entry has:
#   url     – health endpoint reachable from the homeserver Docker network
#   stack   – which compose stack it belongs to (for display grouping)
#   headers – optional dict of extra request headers (e.g. API key)
#
# API-key placeholders like {radarr_api_key} are resolved at init time
# from the constructor's ``api_keys`` dict.
DEFAULT_SERVICES: dict[str, dict[str, Any]] = {
    # Media stack
    "jellyfin": {
        "url": "http://jellyfin:8096/health",
        "stack": "media",
    },
    "radarr": {
        "url": "http://radarr:7878/api/v3/health",
        "stack": "media",
        "headers": {"X-Api-Key": "{radarr_api_key}"},
    },
    "sonarr": {
        "url": "http://sonarr:8989/api/v3/health",
        "stack": "media",
        "headers": {"X-Api-Key": "{sonarr_api_key}"},
    },
    "bazarr": {
        "url": "http://bazarr:6767/",
        "stack": "media",
    },
    "seerr": {
        "url": "http://seerr:5055/api/v1/status",
        "stack": "media",
    },
    # Download stack
    "qbittorrent": {
        "url": "http://qbittorrent:8081/",
        "stack": "download",
    },
    "prowlarr": {
        "url": "http://prowlarr:9696/api/v1/health",
        "stack": "download",
        "headers": {"X-Api-Key": "{prowlarr_api_key}"},
    },
    # Books stack
    "audiobookshelf": {
        "url": "http://audiobookshelf:80/healthcheck",
        "stack": "books",
    },
    "lazylibrarian": {
        "url": "http://lazylibrarian:5299/home",
        "stack": "books",
    },
    # Photos & files stack
    "immich-server": {
        "url": "http://immich-server:2283/api/server/ping",
        "stack": "photos-files",
    },
    "immich-machine-learning": {
        "url": "http://immich-machine-learning:3003/ping",
        "stack": "photos-files",
    },
    "nextcloud": {
        "url": "http://nextcloud:80/status.php",
        "stack": "photos-files",
    },
    # Smart home stack
    "homeassistant": {
        "url": "http://homeassistant:8123/manifest.json",
        "stack": "smart-home",
    },
    "cloudflared": {
        "url": "http://cloudflared:2000/ready",
        "stack": "smart-home",
    },
    # Voice stack
    "livekit": {
        "url": "http://livekit:7880",
        "stack": "voice",
    },
    "kokoro-tts": {
        "url": "http://kokoro-tts:8880/health",
        "stack": "voice",
    },
    # Butler stack (self-check via localhost since we're inside butler-api)
    "butler-api": {
        "url": "http://localhost:8000/health",
        "stack": "butler",
    },
    # Claude Code shim — host-side service, reachable via Docker bridge
    "claude-code-shim": {
        "url": "http://host.docker.internal:7100/health",
        "stack": "butler",
    },
}


def _format_size(value: str) -> str:
    """Format a header value safely for display."""
    if not value:
        return "(empty)"
    # Mask tokens/keys in output
    if len(value) > 8:
        return value[:4] + "..." + value[-4:]
    return "***"


class ServerHealthTool(Tool):
    """Check the health of all home server Docker services.

    Performs HTTP health checks against every service on the homeserver
    Docker network and manages alerts for services that go down.
    """

    def __init__(
        self,
        db_pool: DatabasePool,
        alert_manager: AlertStateManager,
        api_keys: dict[str, str] | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        services: dict[str, dict[str, Any]] | None = None,
    ):
        """Initialize the server health tool.

        Args:
            db_pool: Shared database pool (unused directly, kept for consistency).
            alert_manager: AlertStateManager for deduplication.
            api_keys: Dict mapping placeholder names to actual values, e.g.
                      {"radarr_api_key": "abc123", "ha_token": "xyz"}.
            timeout: Per-service HTTP timeout in seconds.
            services: Override default service registry (mainly for testing).
        """
        self._db_pool = db_pool
        self._alert_manager = alert_manager
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._services = self._resolve_services(
            services or DEFAULT_SERVICES, api_keys or {},
        )
        self._session: aiohttp.ClientSession | None = None

    @staticmethod
    def _resolve_services(
        services: dict[str, dict[str, Any]],
        api_keys: dict[str, str],
    ) -> dict[str, dict[str, Any]]:
        """Replace {placeholder} tokens in header values with actual keys."""
        resolved = {}
        for name, svc in services.items():
            svc_copy = dict(svc)
            if "headers" in svc_copy:
                resolved_headers = {}
                for k, v in svc_copy["headers"].items():
                    for placeholder, key_val in api_keys.items():
                        v = v.replace(f"{{{placeholder}}}", key_val)
                    # Skip services whose API keys weren't provided
                    if "{" in v:
                        break
                    resolved_headers[k] = v
                else:
                    svc_copy["headers"] = resolved_headers
                    resolved[name] = svc_copy
                    continue
                # Header had unresolved placeholder — skip the service
                logger.debug("Skipping %s: missing API key", name)
                continue
            resolved[name] = svc_copy
        return resolved

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # -- Tool interface -------------------------------------------------------

    @property
    def name(self) -> str:
        return "server_health"

    @property
    def description(self) -> str:
        return (
            "Check the health of home server services. "
            "Use 'check_all' to see overall status, 'check_service' to probe "
            "a specific service, or 'get_alerts' to see active health alerts."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["check_all", "check_service", "get_alerts"],
                    "description": (
                        "check_all: Health-check every known service. "
                        "check_service: Check one service by name. "
                        "get_alerts: List active health alerts."
                    ),
                },
                "service": {
                    "type": "string",
                    "description": (
                        "Service name for check_service "
                        f"(one of: {', '.join(DEFAULT_SERVICES)})."
                    ),
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")

        try:
            if action == "check_all":
                return await self._check_all()
            elif action == "check_service":
                service = kwargs.get("service", "")
                if not service:
                    return "Error: 'service' parameter is required for check_service."
                return await self._check_service(service)
            elif action == "get_alerts":
                return await self._get_alerts()
            else:
                return f"Error: Unknown action '{action}'. Use check_all, check_service, or get_alerts."
        except Exception as e:
            logger.exception("Server health check failed")
            return f"Error running health check: {e}"

    # -- Internals ------------------------------------------------------------

    async def _probe(self, svc_name: str, svc: dict[str, Any]) -> dict[str, Any]:
        """Probe a single service and return its status."""
        session = await self._get_session()
        headers = svc.get("headers", {})
        try:
            async with session.get(svc["url"], headers=headers) as resp:
                if 200 <= resp.status < 300:
                    return {"name": svc_name, "status": "healthy", "code": resp.status,
                            "stack": svc.get("stack", "")}
                else:
                    return {"name": svc_name, "status": "degraded", "code": resp.status,
                            "stack": svc.get("stack", ""),
                            "detail": f"HTTP {resp.status}"}
        except aiohttp.ClientConnectorError:
            return {"name": svc_name, "status": "unreachable",
                    "stack": svc.get("stack", ""),
                    "detail": "Connection refused"}
        except asyncio.TimeoutError:
            return {"name": svc_name, "status": "unreachable",
                    "stack": svc.get("stack", ""),
                    "detail": f"Timeout after {self._timeout.total}s"}
        except Exception as e:
            return {"name": svc_name, "status": "unreachable",
                    "stack": svc.get("stack", ""),
                    "detail": str(e)}

    async def _check_all(self) -> str:
        """Health-check all registered services concurrently."""
        tasks = [
            self._probe(name, svc)
            for name, svc in self._services.items()
        ]
        results = await asyncio.gather(*tasks)

        # Classify results
        healthy = []
        unhealthy = []
        for r in results:
            if r["status"] == "healthy":
                healthy.append(r)
            else:
                unhealthy.append(r)

        # Update alerts
        for r in results:
            alert_key = f"health:{r['name']}:down"
            if r["status"] == "healthy":
                await self._alert_manager.resolve_alert(alert_key)
            else:
                await self._alert_manager.trigger_alert(
                    alert_key=alert_key,
                    alert_type="service_down",
                    severity="critical",
                    message=f"{r['name']} ({r['stack']}-stack): {r.get('detail', 'unavailable')}",
                    metadata={"service": r["name"], "stack": r["stack"],
                              "detail": r.get("detail", "")},
                )

        # Format output
        total = len(results)
        lines = [f"Server Health Report ({len(healthy)}/{total} healthy):"]

        if healthy:
            names = ", ".join(r["name"] for r in healthy)
            lines.append(f"  Healthy: {names}")

        if unhealthy:
            lines.append("")
            for r in unhealthy:
                label = r["status"].capitalize()
                lines.append(f"  {label}: {r['name']} ({r['stack']}-stack) — {r.get('detail', '')}")

        # Active alert count
        active = await self._alert_manager.get_active_alerts("service_down")
        lines.append(f"\n  Active Health Alerts: {len(active)}")

        return "\n".join(lines)

    async def _check_service(self, service: str) -> str:
        """Health-check a single service by name."""
        if service not in self._services:
            available = ", ".join(sorted(self._services))
            return f"Unknown service '{service}'. Available: {available}"

        result = await self._probe(service, self._services[service])

        # Update alerts
        alert_key = f"health:{service}:down"
        if result["status"] == "healthy":
            await self._alert_manager.resolve_alert(alert_key)
            return f"{service}: healthy (HTTP {result.get('code', '?')})"
        else:
            await self._alert_manager.trigger_alert(
                alert_key=alert_key,
                alert_type="service_down",
                severity="critical",
                message=f"{service} ({result['stack']}-stack): {result.get('detail', 'unavailable')}",
            )
            return f"{service}: {result['status']} — {result.get('detail', 'unavailable')}"

    async def _get_alerts(self) -> str:
        """List all active health alerts."""
        alerts = await self._alert_manager.get_active_alerts("service_down")
        if not alerts:
            return "No active health alerts."

        lines = [f"Active Health Alerts ({len(alerts)}):"]
        for a in alerts:
            lines.append(f"  [{a['severity'].upper()}] {a['message']}")
        return "\n".join(lines)
