"""Link a user's existing service accounts so password changes reach them.

Onboarding provisions accounts and records them in butler.service_credentials.
Accounts made another way (the first admin's, ones created by hand, the
single-login admin tools) are unknown to Butler, so changing the password in
Settings skipped them. This finds them by username (Immich: by email) and
records them without a password; the next password change sets them all.
"""

from __future__ import annotations

import base64
import json
import logging

import aiohttp

from tools import DatabasePool

from . import iptv
from .config import settings
from .provisioning import _ha_ws_call, _ha_ws_session, _service_is_configured, services_for_account

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)


async def _find_jellyfin(session: aiohttp.ClientSession, username: str, _email: str | None) -> str | None:
    headers = {"Authorization": f'MediaBrowser Token="{settings.jellyfin_api_key}"'}
    async with session.get(f"{settings.jellyfin_url}/Users", headers=headers) as resp:
        resp.raise_for_status()
        users = await resp.json()
    return next((u["Id"] for u in users if u["Name"].lower() == username), None)


async def _find_audiobookshelf(session: aiohttp.ClientSession, username: str, _email: str | None) -> str | None:
    headers = {"Authorization": f"Bearer {settings.audiobookshelf_admin_token}"}
    async with session.get(f"{settings.audiobookshelf_url}/api/users", headers=headers) as resp:
        resp.raise_for_status()
        users = (await resp.json())["users"]
    return next((u["id"] for u in users if u["username"].lower() == username), None)


async def _find_nextcloud(session: aiohttp.ClientSession, username: str, _email: str | None) -> str | None:
    auth = base64.b64encode(
        f"{settings.nextcloud_admin_user}:{settings.nextcloud_admin_password}".encode()
    ).decode()
    headers = {"Authorization": f"Basic {auth}", "OCS-APIRequest": "true"}
    async with session.get(
        f"{settings.nextcloud_url}/ocs/v1.php/cloud/users/{username}",
        headers=headers, params={"format": "json"},
    ) as resp:
        resp.raise_for_status()
        data = await resp.json()
    # The OCS user id is what the password changer addresses
    return username if data.get("ocs", {}).get("meta", {}).get("statuscode") == 100 else None


async def _find_immich(session: aiohttp.ClientSession, username: str, email: str | None) -> str | None:
    headers = {"x-api-key": settings.immich_api_key}
    async with session.get(f"{settings.immich_url}/api/admin/users", headers=headers) as resp:
        resp.raise_for_status()
        users = await resp.json()
    # Immich signs in by email: the user's own, or the one onboarding made up
    wanted = {e for e in (email, f"{username}@homeserver.local") if e}
    return next((u["id"] for u in users if u["email"].lower() in wanted), None)


async def _find_homeassistant(_session: aiohttp.ClientSession, username: str, _email: str | None) -> str | None:
    async with _ha_ws_session() as ws:
        users = await _ha_ws_call(ws, 1, {"type": "config/auth/list"})
    return next(
        (u["id"] for u in users if not u.get("system_generated") and (u.get("username") or "").lower() == username),
        None,
    )


def _find_arr(base_url: str, api_key: str, api_version: str):
    """Radarr/Sonarr/Prowlarr have a single login: link it if it's this user's."""
    async def find(session: aiohttp.ClientSession, username: str, _email: str | None) -> str | None:
        async with session.get(f"{base_url}/api/{api_version}/config/host", headers={"X-Api-Key": api_key}) as resp:
            resp.raise_for_status()
            host = await resp.json()
        return "host" if (host.get("username") or "").lower() == username else None
    return find


async def _find_dispatcharr(
    session: aiohttp.ClientSession, username: str, _email: str | None, *, pool: DatabasePool, user_id: str,
) -> str | None:
    base = settings.dispatcharr_url.rstrip("/")
    token = await iptv._login(session, base, pool, await iptv.get_provider(pool) or {}, user_id)
    async with session.get(f"{base}/api/accounts/users/", headers={"Authorization": f"Bearer {token}"}) as resp:
        resp.raise_for_status()
        data = await resp.json()
    users = data if isinstance(data, list) else data.get("results", [])
    return next((str(u["id"]) for u in users if u["username"].lower() == username), None)


def _finders(pool: DatabasePool, user_id: str) -> dict:
    async def dispatcharr(session, username, email):
        return await _find_dispatcharr(session, username, email, pool=pool, user_id=user_id)

    return {
        "jellyfin": _find_jellyfin,
        "audiobookshelf": _find_audiobookshelf,
        "nextcloud": _find_nextcloud,
        "immich": _find_immich,
        "homeassistant": _find_homeassistant,
        "radarr": _find_arr(settings.radarr_url, settings.radarr_api_key, "v3"),
        "sonarr": _find_arr(settings.sonarr_url, settings.sonarr_api_key, "v3"),
        "prowlarr": _find_arr(settings.prowlarr_url, settings.prowlarr_api_key, "v1"),
        "dispatcharr": dispatcharr,
    }


async def link_existing_accounts(user_id: str, pool: DatabasePool) -> list[dict]:
    """Link the user's existing logins on every service they should have.

    Returns one result per expected service, with status "linked" (newly
    recorded), "already" (Butler knew it), "not_found", or "unavailable".
    """
    db = pool.pool
    user = await db.fetchrow(
        "SELECT role, permissions, service_username, email FROM butler.users WHERE id = $1", user_id,
    )
    if not user or not user["service_username"]:
        raise ValueError("This user has no username yet")
    username = user["service_username"].lower()
    email = (user["email"] or "").lower() or None
    raw = user["permissions"]
    permissions = (json.loads(raw) if isinstance(raw, str) else raw) or []

    known = {r["service"] for r in await db.fetch(
        "SELECT service FROM butler.service_credentials WHERE user_id = $1", user_id,
    )}
    finders = _finders(pool, user_id)
    results: list[dict] = []
    async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
        for service in services_for_account(user["role"], permissions):
            if service in known:
                results.append({"service": service, "status": "already"})
                continue
            if not _service_is_configured(service) or service not in finders:
                results.append({"service": service, "status": "unavailable", "error": "Not configured"})
                continue
            try:
                external_id = await finders[service](session, username, email)
            except Exception as e:  # one service being down shouldn't stop the rest
                logger.warning("Couldn't look up %s account for %s: %s", service, user_id, e)
                results.append({"service": service, "status": "unavailable", "error": str(e)})
                continue
            if not external_id:
                results.append({"service": service, "status": "not_found"})
                continue
            login = email if service == "immich" and email else user["service_username"]
            await db.execute(
                """INSERT INTO butler.service_credentials (user_id, service, username, external_id, status)
                   VALUES ($1, $2, $3, $4, 'active')
                   ON CONFLICT (user_id, service) DO NOTHING""",
                user_id, service, login, external_id,
            )
            results.append({"service": service, "status": "linked"})
    return results
