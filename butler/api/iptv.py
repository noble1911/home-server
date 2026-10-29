"""The household's IPTV provider, pushed into Dispatcharr (#223).

Admins enter the provider login (Xtream Codes server/username/password, or an
M3U URL) in Settings. It's stored encrypted in butler.iptv_provider and synced
to Dispatcharr as one M3U account named ``ACCOUNT_NAME``; Jellyfin's Live TV
reads the channels from Dispatcharr.

Butler signs in to Dispatcharr with the Dispatcharr login saved alongside the
provider, or, when that's blank, the saving admin's service login (the
username/password from onboarding that Butler propagates to every service).
Dispatcharr's admin account is created by hand to match.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

from tools import DatabasePool

from .config import settings
from .crypto import decrypt_password, encrypt_password

logger = logging.getLogger(__name__)

ACCOUNT_NAME = "Butler IPTV"
_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=20)


class DispatcharrError(RuntimeError):
    """Dispatcharr rejected or couldn't take the sync. Message is admin-facing."""


async def get_provider(pool: DatabasePool) -> dict[str, Any] | None:
    """The saved provider row (secrets still encrypted), or None."""
    row = await pool.pool.fetchrow("SELECT * FROM butler.iptv_provider WHERE id = 1")
    return dict(row) if row else None


async def save_provider(
    pool: DatabasePool,
    *,
    kind: str,
    server_url: str | None,
    username: str | None,
    password: str | None,
    m3u_url: str | None,
    max_streams: int,
    dispatcharr_username: str | None,
    dispatcharr_password: str | None,
    user_id: str,
) -> None:
    """Save the provider. A blank password / M3U URL keeps the stored one.

    A blank Dispatcharr username clears the Dispatcharr login (sign in with
    the service login instead); a blank Dispatcharr password keeps the saved one.
    """
    existing = await get_provider(pool) or {}
    if dispatcharr_username:
        dispatcharr_password_enc = (
            encrypt_password(dispatcharr_password) if dispatcharr_password
            else existing.get("dispatcharr_password_encrypted")
        )
        if not dispatcharr_password_enc:
            raise ValueError("Enter the Dispatcharr password too")
    else:
        dispatcharr_username = dispatcharr_password_enc = None
    if kind == "xtream":
        password_enc = encrypt_password(password) if password else existing.get("password_encrypted")
        if not (server_url and username and password_enc):
            raise ValueError("Xtream Codes needs a server URL, username and password")
        m3u_enc = None
    elif kind == "m3u":
        m3u_enc = encrypt_password(m3u_url) if m3u_url else existing.get("m3u_url_encrypted")
        if not m3u_enc:
            raise ValueError("An M3U playlist URL is required")
        server_url = username = password_enc = None
    else:
        raise ValueError(f"Unknown provider type: {kind}")

    await pool.pool.execute(
        """
        INSERT INTO butler.iptv_provider
            (id, kind, server_url, username, password_encrypted, m3u_url_encrypted,
             max_streams, dispatcharr_username, dispatcharr_password_encrypted,
             updated_by, updated_at)
        VALUES (1, $1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
        ON CONFLICT (id) DO UPDATE SET
            kind = EXCLUDED.kind,
            server_url = EXCLUDED.server_url,
            username = EXCLUDED.username,
            password_encrypted = EXCLUDED.password_encrypted,
            m3u_url_encrypted = EXCLUDED.m3u_url_encrypted,
            max_streams = EXCLUDED.max_streams,
            dispatcharr_username = EXCLUDED.dispatcharr_username,
            dispatcharr_password_encrypted = EXCLUDED.dispatcharr_password_encrypted,
            updated_by = EXCLUDED.updated_by,
            updated_at = NOW()
        """,
        kind, server_url, username, password_enc, m3u_enc, max_streams,
        dispatcharr_username, dispatcharr_password_enc, user_id,
    )


async def sync(pool: DatabasePool, admin_id: str) -> None:
    """Push the saved provider into Dispatcharr and start a playlist refresh.

    Records the outcome on the row (last_synced_at / last_error) and raises
    DispatcharrError on failure.
    """
    provider = await get_provider(pool)
    if not provider:
        raise DispatcharrError("No IPTV provider saved yet")
    try:
        account_id = await _push(pool, provider, admin_id)
    except DispatcharrError as e:
        await pool.pool.execute(
            "UPDATE butler.iptv_provider SET last_error = $1 WHERE id = 1", str(e),
        )
        raise
    except aiohttp.ClientError as e:
        msg = f"Couldn't reach Dispatcharr at {settings.dispatcharr_url}: {e}"
        await pool.pool.execute("UPDATE butler.iptv_provider SET last_error = $1 WHERE id = 1", msg)
        raise DispatcharrError(msg) from e
    await pool.pool.execute(
        """UPDATE butler.iptv_provider
           SET dispatcharr_account_id = $1, last_synced_at = $2, last_error = NULL
           WHERE id = 1""",
        account_id, datetime.now(timezone.utc),
    )


async def _push(pool: DatabasePool, provider: dict[str, Any], admin_id: str) -> int:
    base = settings.dispatcharr_url.rstrip("/")
    body: dict[str, Any] = {
        "name": ACCOUNT_NAME,
        "max_streams": provider["max_streams"],
        "is_active": True,
    }
    if provider["kind"] == "xtream":
        body.update(
            account_type="XC",
            server_url=provider["server_url"],
            username=provider["username"],
            password=decrypt_password(provider["password_encrypted"]),
        )
    else:
        body.update(
            account_type="STD",
            server_url=decrypt_password(provider["m3u_url_encrypted"]),
            username=None,
            password=None,
        )

    async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
        headers = {"Authorization": f"Bearer {await _login(session, base, pool, provider, admin_id)}"}
        account_id = await _find_account(session, base, headers, provider["dispatcharr_account_id"])

        if account_id is None:
            async with session.post(f"{base}/api/m3u/accounts/", json=body, headers=headers) as resp:
                if resp.status != 201:
                    raise DispatcharrError(f"Dispatcharr refused the account: HTTP {resp.status} - {await resp.text()}")
                account_id = (await resp.json())["id"]
        else:
            async with session.patch(f"{base}/api/m3u/accounts/{account_id}/", json=body, headers=headers) as resp:
                if resp.status != 200:
                    raise DispatcharrError(f"Dispatcharr refused the update: HTTP {resp.status} - {await resp.text()}")

        # Refreshing is best effort: the account is saved, and Dispatcharr
        # refreshes on its own schedule too.
        async with session.post(f"{base}/api/m3u/refresh/{account_id}/", headers=headers) as resp:
            if resp.status >= 300:
                logger.warning("Dispatcharr refresh of account %s: HTTP %s", account_id, resp.status)
    return account_id


async def _login(
    session: aiohttp.ClientSession, base: str, pool: DatabasePool, provider: dict[str, Any], admin_id: str,
) -> str:
    """Sign in to Dispatcharr; returns a JWT access token."""
    if provider.get("dispatcharr_username") and provider.get("dispatcharr_password_encrypted"):
        username = provider["dispatcharr_username"]
        password = decrypt_password(provider["dispatcharr_password_encrypted"])
        source = "the Dispatcharr login saved in Settings"
    else:
        username, password = await _service_login(pool, admin_id)
        source = "your service login"
    async with session.post(f"{base}/api/accounts/token/", json={"username": username, "password": password}) as resp:
        if resp.status == 401:
            raise DispatcharrError(
                f"Dispatcharr didn't accept '{username}' ({source}). Usernames are case-sensitive; "
                "check it matches a Dispatcharr admin, or set the Dispatcharr login below."
            )
        if resp.status != 200:
            raise DispatcharrError(f"Dispatcharr sign-in failed: HTTP {resp.status}")
        return (await resp.json())["access"]


async def _service_login(pool: DatabasePool, admin_id: str) -> tuple[str, str]:
    """The admin's service username and password.

    Accounts created before the shared login was stored on butler.users only
    have per-service credentials, so fall back to the newest of those.
    """
    row = await pool.pool.fetchrow(
        "SELECT service_username, service_password_encrypted FROM butler.users WHERE id = $1",
        admin_id,
    )
    if row and row["service_username"] and row["service_password_encrypted"]:
        return row["service_username"], decrypt_password(row["service_password_encrypted"])
    cred = await pool.pool.fetchrow(
        """SELECT username, password_encrypted FROM butler.service_credentials
           WHERE user_id = $1 AND status = 'active' AND password_encrypted IS NOT NULL
           ORDER BY created_at DESC LIMIT 1""",
        admin_id,
    )
    if cred:
        return cred["username"], decrypt_password(cred["password_encrypted"])
    raise DispatcharrError("You don't have a service login yet; set one under Service Password first")


async def _find_account(
    session: aiohttp.ClientSession, base: str, headers: dict[str, str], known_id: int | None,
) -> int | None:
    """The M3U account Butler manages: the remembered id, else one named ACCOUNT_NAME."""
    if known_id is not None:
        async with session.get(f"{base}/api/m3u/accounts/{known_id}/", headers=headers) as resp:
            if resp.status == 200:
                return known_id
    async with session.get(f"{base}/api/m3u/accounts/", headers=headers) as resp:
        if resp.status != 200:
            raise DispatcharrError(f"Couldn't list Dispatcharr's M3U accounts: HTTP {resp.status}")
        data = await resp.json()
    accounts = data.get("results", data) if isinstance(data, dict) else data
    for account in accounts:
        if account.get("name") == ACCOUNT_NAME:
            return account["id"]
    return None
