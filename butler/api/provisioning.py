"""Auto-provision user accounts on downstream apps.

Called during onboarding to create per-user accounts on Jellyfin,
Audiobookshelf, Nextcloud, Immich, and Calibre-Web using the credentials
the user chose during the onboarding wizard.
"""

from __future__ import annotations

import base64
import logging
import re
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
    "media": ["jellyfin", "audiobookshelf", "immich", "calibreweb"],
}
# Services everyone gets (regardless of permissions)
UNIVERSAL_SERVICES: list[str] = ["nextcloud"]


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
        "calibreweb": bool(
            settings.calibreweb_url
            and settings.calibreweb_admin_user
            and settings.calibreweb_admin_password
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


async def _provision_calibreweb(username: str, password: str) -> str:
    """Create Calibre-Web user via admin form scraping.

    Calibre-Web has no REST API, so we log in as admin and submit
    the user creation form with CSRF tokens.
    """
    async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
        base = settings.calibreweb_url

        # 1. GET login page to extract CSRF token
        async with session.get(f"{base}/login") as resp:
            if resp.status != 200:
                raise RuntimeError(
                    f"Calibre-Web login page failed: HTTP {resp.status}"
                )
            html = await resp.text()

        csrf_token = _extract_csrf_token(html)

        # 2. POST login with admin credentials
        login_data = {
            "username": settings.calibreweb_admin_user,
            "password": settings.calibreweb_admin_password,
            "submit": "",
        }
        if csrf_token:
            login_data["csrf_token"] = csrf_token

        async with session.post(
            f"{base}/login",
            data=login_data,
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(
                    f"Calibre-Web admin login failed: HTTP {resp.status}"
                )
            # Verify login succeeded — a failed login redirects back to /login
            if resp.url and str(resp.url).rstrip("/").endswith("/login"):
                raise RuntimeError(
                    "Calibre-Web admin login failed: bad credentials (redirected back to login)"
                )

        # 3. GET new user page to extract CSRF token
        async with session.get(f"{base}/admin/user/new") as resp:
            # If we're not authenticated, this redirects to /login
            if resp.url and str(resp.url).rstrip("/").endswith("/login"):
                raise RuntimeError(
                    "Calibre-Web admin session invalid: not authenticated"
                )
            if resp.status != 200:
                raise RuntimeError(
                    f"Calibre-Web new user page failed: HTTP {resp.status}"
                )
            html = await resp.text()

        csrf_token = _extract_csrf_token(html)

        # 4. POST new user form
        user_data = {
            "name": username,
            "password": password,
            "email": f"{username}@homeserver.local",
            "submit": "",
        }
        if csrf_token:
            user_data["csrf_token"] = csrf_token

        async with session.post(
            f"{base}/admin/user/new",
            data=user_data,
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(
                    f"Calibre-Web user creation failed: HTTP {resp.status}"
                )
            # Check for error messages in the response
            body = await resp.text()
            if "flash_danger" in body or "already taken" in body.lower():
                raise RuntimeError("Calibre-Web user creation failed: username may already exist")

        return username


def _extract_csrf_token(html: str) -> str | None:
    """Extract CSRF token from a Flask/WTForms hidden input field."""
    match = re.search(
        r'<input[^>]*name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)["\']',
        html,
    )
    if match:
        return match.group(1)
    # Try alternate pattern (value before name)
    match = re.search(
        r'<input[^>]*value=["\']([^"\']+)["\'][^>]*name=["\']csrf_token["\']',
        html,
    )
    return match.group(1) if match else None


# Dispatch table
_PROVISIONERS: dict[str, Callable[[str, str], Awaitable[str]]] = {
    "jellyfin": _provision_jellyfin,
    "audiobookshelf": _provision_audiobookshelf,
    "nextcloud": _provision_nextcloud,
    "immich": _provision_immich,
    "calibreweb": _provision_calibreweb,
}
