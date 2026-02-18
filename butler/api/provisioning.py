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
from .crypto import decrypt_password, encrypt_password

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

# NOTE: LazyLibrarian (books) and Seerr (media requests) are NOT auto-provisioned.
# - Seerr: uses Jellyfin SSO — users log in with their Jellyfin credentials.
# - LazyLibrarian: no multi-user support. Household shares the single instance.


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
    *,
    email: str | None = None,
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
            if service == "immich":
                external_id = await provisioner(username, password, email=email)
            else:
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
                   (user_id, service, username, password_encrypted, status, error_message)
                   VALUES ($1, $2, $3, $4, 'failed', $5)
                   ON CONFLICT (user_id, service) DO UPDATE SET
                     username = EXCLUDED.username,
                     password_encrypted = COALESCE(EXCLUDED.password_encrypted, butler.service_credentials.password_encrypted),
                     status = 'failed',
                     error_message = EXCLUDED.error_message""",
                user_id,
                service,
                username,
                encrypt_password(password),
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


async def _provision_immich(username: str, password: str, *, email: str | None = None) -> str:
    """Create Immich user. Returns the Immich user ID."""
    async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
        headers = {"x-api-key": settings.immich_api_key}

        # Use the user's real email if provided, otherwise generate a local one
        email = email or f"{username}@homeserver.local"

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


# ── De-provisioning (delete service accounts) ────────────────────────


async def deprovision_user_accounts(
    user_id: str,
    pool: DatabasePool,
) -> list[dict]:
    """Delete user accounts on downstream services. Best-effort.

    Reads active credentials from DB and calls per-service delete APIs.
    Returns a list of result dicts with keys: service, status, error.
    """
    db = pool.pool
    rows = await db.fetch(
        """SELECT service, username, external_id, status
           FROM butler.service_credentials
           WHERE user_id = $1 AND status = 'active'""",
        user_id,
    )
    results: list[dict] = []
    for row in rows:
        service = row["service"]
        external_id = row["external_id"]
        username = row["username"]
        if not external_id and service != "nextcloud":
            logger.warning("No external_id for %s/%s, skipping delete", user_id, service)
            results.append({"service": service, "status": "skipped", "error": "No external ID"})
            continue
        deprovisioner = _DEPROVISIONERS.get(service)
        if not deprovisioner or not _service_is_configured(service):
            results.append({"service": service, "status": "skipped", "error": "Not configured"})
            continue
        try:
            await deprovisioner(external_id or username, username)
            await db.execute(
                "UPDATE butler.service_credentials SET status = 'revoked' WHERE user_id = $1 AND service = $2",
                user_id, service,
            )
            results.append({"service": service, "status": "revoked"})
            logger.info("Deprovisioned %s account for user %s", service, user_id)
        except Exception as e:
            logger.error("Failed to deprovision %s for user %s: %s", service, user_id, e)
            results.append({"service": service, "status": "failed", "error": str(e)})
    return results


async def _deprovision_jellyfin(external_id: str, _username: str) -> None:
    async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
        headers = {"Authorization": f'MediaBrowser Token="{settings.jellyfin_api_key}"'}
        async with session.delete(
            f"{settings.jellyfin_url}/Users/{external_id}", headers=headers,
        ) as resp:
            if resp.status not in (200, 204, 404):
                raise RuntimeError(f"Jellyfin delete failed: HTTP {resp.status}")


async def _deprovision_audiobookshelf(external_id: str, _username: str) -> None:
    async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
        headers = {"Authorization": f"Bearer {settings.audiobookshelf_admin_token}"}
        async with session.delete(
            f"{settings.audiobookshelf_url}/api/users/{external_id}", headers=headers,
        ) as resp:
            if resp.status not in (200, 204, 404):
                raise RuntimeError(f"Audiobookshelf delete failed: HTTP {resp.status}")


async def _deprovision_nextcloud(_external_id: str, username: str) -> None:
    async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
        auth_str = f"{settings.nextcloud_admin_user}:{settings.nextcloud_admin_password}"
        auth_header = base64.b64encode(auth_str.encode()).decode()
        headers = {
            "Authorization": f"Basic {auth_header}",
            "OCS-APIRequest": "true",
        }
        async with session.delete(
            f"{settings.nextcloud_url}/ocs/v1.php/cloud/users/{username}",
            headers=headers, params={"format": "json"},
        ) as resp:
            if resp.status not in (200, 404):
                raise RuntimeError(f"Nextcloud delete failed: HTTP {resp.status}")


async def _deprovision_immich(external_id: str, _username: str) -> None:
    async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
        headers = {"x-api-key": settings.immich_api_key}
        async with session.delete(
            f"{settings.immich_url}/api/admin/users/{external_id}", headers=headers,
        ) as resp:
            if resp.status not in (200, 204, 404):
                raise RuntimeError(f"Immich delete failed: HTTP {resp.status}")


async def _deprovision_homeassistant(external_id: str, _username: str) -> None:
    ws_url = settings.home_assistant_url.replace("https://", "wss://").replace(
        "http://", "ws://"
    )
    ws_url = f"{ws_url}/api/websocket"
    ws_timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=ws_timeout) as session:
        async with session.ws_connect(ws_url) as ws:
            msg = await ws.receive_json()
            if msg.get("type") != "auth_required":
                raise RuntimeError(f"HA WebSocket unexpected: {msg.get('type')}")
            await ws.send_json({"type": "auth", "access_token": settings.home_assistant_token})
            msg = await ws.receive_json()
            if msg.get("type") != "auth_ok":
                raise RuntimeError(f"HA WebSocket auth failed: {msg}")
            await ws.send_json({"id": 1, "type": "config/auth/delete", "user_id": external_id})
            msg = await ws.receive_json()
            if not msg.get("success"):
                error = msg.get("error", {}).get("message", str(msg))
                raise RuntimeError(f"HA user deletion failed: {error}")


_DEPROVISIONERS: dict[str, Callable[[str, str], Awaitable[None]]] = {
    "jellyfin": _deprovision_jellyfin,
    "audiobookshelf": _deprovision_audiobookshelf,
    "nextcloud": _deprovision_nextcloud,
    "immich": _deprovision_immich,
    "homeassistant": _deprovision_homeassistant,
}


# ── Password change propagation ──────────────────────────────────────


async def update_service_passwords(
    user_id: str,
    new_password: str,
    pool: DatabasePool,
) -> list[dict]:
    """Change password on all active service accounts for a user.

    Returns a list of result dicts with keys: service, status, error.
    """
    db = pool.pool
    rows = await db.fetch(
        """SELECT service, username, external_id
           FROM butler.service_credentials
           WHERE user_id = $1 AND status = 'active'""",
        user_id,
    )
    results: list[dict] = []
    encrypted = encrypt_password(new_password)
    for row in rows:
        service = row["service"]
        external_id = row["external_id"]
        username = row["username"]
        changer = _PASSWORD_CHANGERS.get(service)
        if not changer or not _service_is_configured(service):
            results.append({"service": service, "status": "skipped", "error": "Not configured"})
            continue
        if not external_id and service != "nextcloud":
            results.append({"service": service, "status": "skipped", "error": "No external ID"})
            continue
        try:
            await changer(external_id or username, username, new_password)
            await db.execute(
                "UPDATE butler.service_credentials SET password_encrypted = $3 WHERE user_id = $1 AND service = $2",
                user_id, service, encrypted,
            )
            results.append({"service": service, "status": "updated"})
            logger.info("Updated %s password for user %s", service, user_id)
        except Exception as e:
            logger.error("Failed to update %s password for user %s: %s", service, user_id, e)
            results.append({"service": service, "status": "failed", "error": str(e)})

    # Also update the stored master password on the user record
    if any(r["status"] == "updated" for r in results):
        await db.execute(
            "UPDATE butler.users SET service_password_encrypted = $2 WHERE id = $1",
            user_id, encrypted,
        )

    return results


async def _change_password_jellyfin(external_id: str, _username: str, new_password: str) -> None:
    async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
        headers = {"Authorization": f'MediaBrowser Token="{settings.jellyfin_api_key}"'}
        async with session.post(
            f"{settings.jellyfin_url}/Users/{external_id}/Password",
            json={"NewPw": new_password}, headers=headers,
        ) as resp:
            if resp.status not in (200, 204):
                raise RuntimeError(f"Jellyfin password change failed: HTTP {resp.status}")


async def _change_password_audiobookshelf(external_id: str, _username: str, new_password: str) -> None:
    async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
        headers = {"Authorization": f"Bearer {settings.audiobookshelf_admin_token}"}
        async with session.patch(
            f"{settings.audiobookshelf_url}/api/users/{external_id}",
            json={"password": new_password}, headers=headers,
        ) as resp:
            if resp.status not in (200, 204):
                raise RuntimeError(f"Audiobookshelf password change failed: HTTP {resp.status}")


async def _change_password_nextcloud(_external_id: str, username: str, new_password: str) -> None:
    async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
        auth_str = f"{settings.nextcloud_admin_user}:{settings.nextcloud_admin_password}"
        auth_header = base64.b64encode(auth_str.encode()).decode()
        headers = {
            "Authorization": f"Basic {auth_header}",
            "OCS-APIRequest": "true",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        async with session.put(
            f"{settings.nextcloud_url}/ocs/v1.php/cloud/users/{username}",
            data={"key": "password", "value": new_password},
            headers=headers, params={"format": "json"},
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Nextcloud password change failed: HTTP {resp.status}")


async def _change_password_immich(external_id: str, _username: str, new_password: str) -> None:
    async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
        headers = {"x-api-key": settings.immich_api_key}
        async with session.put(
            f"{settings.immich_url}/api/admin/users/{external_id}",
            json={"password": new_password}, headers=headers,
        ) as resp:
            if resp.status not in (200, 204):
                raise RuntimeError(f"Immich password change failed: HTTP {resp.status}")


_PASSWORD_CHANGERS: dict[str, Callable[[str, str, str], Awaitable[None]]] = {
    "jellyfin": _change_password_jellyfin,
    "audiobookshelf": _change_password_audiobookshelf,
    "nextcloud": _change_password_nextcloud,
    "immich": _change_password_immich,
    # Home Assistant: no admin API to change another user's password
}
