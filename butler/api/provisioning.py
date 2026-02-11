"""Auto-provision user accounts on downstream apps.

Called during onboarding to create per-user accounts on Jellyfin,
Audiobookshelf, Nextcloud, Immich, and Home Assistant using the
credentials the user chose during the onboarding wizard.
"""

from __future__ import annotations

import base64
import logging
from typing import Callable, Awaitable

import aiohttp

from tools import DatabasePool

from .config import settings
from .crypto import encrypt_password

logger = logging.getLogger(__name__)

# Timeout for external service API calls (seconds)
_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)

# Permission-to-service mapping
PERMISSION_SERVICE_MAP: dict[str, list[str]] = {
    "media": ["jellyfin", "audiobookshelf", "immich"],
    "home": ["homeassistant"],
}
# Services everyone gets (regardless of permissions)
UNIVERSAL_SERVICES: list[str] = ["nextcloud"]

# NOTE: Shelfarr (books) and Seerr (media requests) are NOT auto-provisioned.
# - Seerr: uses Jellyfin SSO — users log in with their Jellyfin credentials.
# - Shelfarr: Rails app with no REST API. Possible via direct SQLite DB insert
#   but fragile. See GitHub issue for tracking. Users create accounts manually.


def _services_for_user(permissions: list[str]) -> list[str]:
    """Determine which services to provision based on user permissions."""
    services = set(UNIVERSAL_SERVICES)
    for perm in permissions:
        services.update(PERMISSION_SERVICE_MAP.get(perm, []))
    return sorted(services)


def _service_is_configured(service: str) -> bool:
    """Check if the admin credentials for a service are configured."""
    checks: dict[str, bool] = {
        "jellyfin": bool(settings.jellyfin_url and settings.jellyfin_api_key),
        "audiobookshelf": bool(
            settings.audiobookshelf_url and settings.audiobookshelf_admin_token
        ),
        "nextcloud": bool(
            settings.nextcloud_url
            and settings.nextcloud_admin_user
            and settings.nextcloud_admin_password
        ),
        "immich": bool(settings.immich_url and settings.immich_api_key),
        "homeassistant": bool(
            settings.home_assistant_url and settings.home_assistant_token
        ),
    }
    return checks.get(service, False)


async def provision_user_accounts(
    user_id: str,
    username: str,
    password: str,
    permissions: list[str],
    pool: DatabasePool,
) -> list[dict]:
    """Create accounts on all permitted & configured services.

    Returns a list of result dicts with keys: service, username, status, error.
    Idempotent: skips services where the user already has a credential row.
    """
    db = pool.pool
    results: list[dict] = []
    target_services = _services_for_user(permissions)

    for service in target_services:
        if not _service_is_configured(service):
            logger.info("Skipping %s provisioning (not configured)", service)
            results.append(
                {"service": service, "username": username,
                 "status": "skipped", "error": "Not configured on this server"}
            )
            continue

        # Idempotency check — only skip if already active
        existing_status = await db.fetchval(
            "SELECT status FROM butler.service_credentials WHERE user_id = $1 AND service = $2",
            user_id,
            service,
        )
        if existing_status == "active":
            logger.info("User %s already has active %s credentials, skipping", user_id, service)
            continue

        try:
            provisioner = _PROVISIONERS[service]
            external_id = await provisioner(username, password)
            await db.execute(
                """INSERT INTO butler.service_credentials
                   (user_id, service, username, password_encrypted, external_id, status, error_message)
                   VALUES ($1, $2, $3, $4, $5, 'active', NULL)
                   ON CONFLICT (user_id, service) DO UPDATE SET
                     username = EXCLUDED.username,
                     password_encrypted = EXCLUDED.password_encrypted,
                     external_id = EXCLUDED.external_id,
                     status = 'active',
                     error_message = NULL""",
                user_id,
                service,
                username,
                encrypt_password(password),
                external_id,
            )
            results.append(
                {"service": service, "username": username, "status": "active"}
            )
            logger.info("Provisioned %s account for user %s", service, user_id)
        except Exception as e:
            logger.error("Failed to provision %s for user %s: %s", service, user_id, e)
            await db.execute(
                """INSERT INTO butler.service_credentials
                   (user_id, service, username, status, error_message)
                   VALUES ($1, $2, $3, 'failed', $4)
                   ON CONFLICT (user_id, service) DO UPDATE SET
                     username = EXCLUDED.username,
                     status = 'failed',
                     error_message = EXCLUDED.error_message""",
                user_id,
                service,
                username,
                str(e),
            )
            results.append(
                {
                    "service": service,
                    "username": username,
                    "status": "failed",
                    "error": str(e),
                }
            )

    return results


# ── Per-service provisioners ────────────────────────────────────────


async def _provision_jellyfin(username: str, password: str) -> str:
    """Create Jellyfin user. Returns the Jellyfin user ID."""
    async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
        headers = {
            "Authorization": f'MediaBrowser Token="{settings.jellyfin_api_key}"',
        }

        # 1. Create user
        async with session.post(
            f"{settings.jellyfin_url}/Users/New",
            json={"Name": username},
            headers=headers,
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(
                    f"Jellyfin user creation failed: HTTP {resp.status} - {body}"
                )
            data = await resp.json()
            jellyfin_user_id = data["Id"]

        # 2. Set password (clean up orphaned user on failure)
        try:
            async with session.post(
                f"{settings.jellyfin_url}/Users/{jellyfin_user_id}/Password",
                json={"NewPw": password},
                headers=headers,
            ) as resp:
                if resp.status not in (200, 204):
                    raise RuntimeError(
                        f"Jellyfin password set failed: HTTP {resp.status}"
                    )
        except Exception:
            # Best-effort cleanup: delete the orphaned user so retries can succeed
            try:
                async with session.delete(
                    f"{settings.jellyfin_url}/Users/{jellyfin_user_id}",
                    headers=headers,
                ) as del_resp:
                    logger.info(
                        "Cleaned up orphaned Jellyfin user %s (HTTP %s)",
                        jellyfin_user_id, del_resp.status,
                    )
            except Exception:
                logger.warning(
                    "Failed to clean up orphaned Jellyfin user %s", jellyfin_user_id
                )
            raise

        # 3. Set policies (enable all libraries, disable admin)
        async with session.post(
            f"{settings.jellyfin_url}/Users/{jellyfin_user_id}/Policy",
            json={
                "IsAdministrator": False,
                "EnableAllFolders": True,
                "EnableMediaPlayback": True,
            },
            headers=headers,
        ) as resp:
            if resp.status not in (200, 204):
                logger.warning(
                    "Jellyfin policy set returned HTTP %s (non-fatal)", resp.status
                )

        return jellyfin_user_id


async def _provision_audiobookshelf(username: str, password: str) -> str:
    """Create Audiobookshelf user. Returns the ABS user ID."""
    async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
        headers = {"Authorization": f"Bearer {settings.audiobookshelf_admin_token}"}

        async with session.post(
            f"{settings.audiobookshelf_url}/api/users",
            json={"username": username, "password": password, "type": "user"},
            headers=headers,
        ) as resp:
            if resp.status not in (200, 201):
                body = await resp.text()
                raise RuntimeError(
                    f"Audiobookshelf user creation failed: HTTP {resp.status} - {body}"
                )
            data = await resp.json()
            return data.get("user", {}).get("id", data.get("id", ""))


async def _provision_nextcloud(username: str, password: str) -> str:
    """Create Nextcloud user via OCS API. Returns the username."""
    async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
        auth_str = (
            f"{settings.nextcloud_admin_user}:{settings.nextcloud_admin_password}"
        )
        auth_header = base64.b64encode(auth_str.encode()).decode()
        headers = {
            "Authorization": f"Basic {auth_header}",
            "OCS-APIRequest": "true",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async with session.post(
            f"{settings.nextcloud_url}/ocs/v1.php/cloud/users",
            data={"userid": username, "password": password},
            headers=headers,
            params={"format": "json"},
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(
                    f"Nextcloud user creation failed: HTTP {resp.status} - {body}"
                )
            data = await resp.json()
            meta = data.get("ocs", {}).get("meta", {})
            if meta.get("statuscode") not in (100, 200):
                raise RuntimeError(
                    f"Nextcloud OCS error: {meta.get('message', 'Unknown')}"
                )
            return username


async def _provision_immich(username: str, password: str) -> str:
    """Create Immich user. Returns the Immich user ID."""
    async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
        headers = {"x-api-key": settings.immich_api_key}

        # Immich requires an email for user creation
        email = f"{username}@homeserver.local"

        async with session.post(
            f"{settings.immich_url}/api/admin/users",
            json={"email": email, "password": password, "name": username},
            headers=headers,
        ) as resp:
            if resp.status not in (200, 201):
                body = await resp.text()
                raise RuntimeError(
                    f"Immich user creation failed: HTTP {resp.status} - {body}"
                )
            data = await resp.json()
            return data.get("id", "")


async def _provision_homeassistant(username: str, password: str) -> str:
    """Create Home Assistant user via WebSocket API. Returns the HA user ID."""
    # Convert HTTP URL to WebSocket URL
    ws_url = settings.home_assistant_url.replace("https://", "wss://").replace(
        "http://", "ws://"
    )
    ws_url = f"{ws_url}/api/websocket"

    # Use a longer timeout for the WebSocket handshake + user creation
    ws_timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(timeout=ws_timeout) as session:
        async with session.ws_connect(ws_url) as ws:
            # 1. Wait for auth_required
            msg = await ws.receive_json()
            if msg.get("type") != "auth_required":
                raise RuntimeError(f"HA WebSocket unexpected: {msg.get('type')}")

            # 2. Authenticate with long-lived access token
            await ws.send_json({
                "type": "auth",
                "access_token": settings.home_assistant_token,
            })
            msg = await ws.receive_json()
            if msg.get("type") != "auth_ok":
                raise RuntimeError(f"HA WebSocket auth failed: {msg}")

            # 3. Create user (non-admin, system-users group)
            await ws.send_json({
                "id": 1,
                "type": "config/auth/create",
                "name": username,
                "username": username,
                "password": password,
                "group_ids": ["system-users"],
                "local_only": False,
            })
            msg = await ws.receive_json()
            if not msg.get("success"):
                error = msg.get("error", {}).get("message", str(msg))
                raise RuntimeError(f"HA user creation failed: {error}")

            return msg.get("result", {}).get("user", {}).get("id", "")


# Dispatch table
_PROVISIONERS: dict[str, Callable[[str, str], Awaitable[str]]] = {
    "jellyfin": _provision_jellyfin,
    "audiobookshelf": _provision_audiobookshelf,
    "nextcloud": _provision_nextcloud,
    "immich": _provision_immich,
    "homeassistant": _provision_homeassistant,
}
