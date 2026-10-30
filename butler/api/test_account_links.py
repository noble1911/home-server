"""Linking existing service logins (no network, no database).

Run with: pytest butler/api/test_account_links.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from . import account_links
from .provisioning import services_for_account


def test_users_get_services_from_their_permissions():
    assert services_for_account("user", ["media"]) == ["audiobookshelf", "immich", "jellyfin", "nextcloud"]
    assert services_for_account("user", ["home", "email"]) == ["homeassistant", "nextcloud"]
    assert services_for_account("user", []) == ["nextcloud"]


def test_admins_get_every_service_including_the_admin_tools():
    services = services_for_account("admin", [])
    for s in ("jellyfin", "immich", "homeassistant", "nextcloud", "radarr", "sonarr", "prowlarr", "dispatcharr"):
        assert s in services
    # Shared account / no login: deliberately never linked or changed
    assert "qbittorrent" not in services and "bazarr" not in services


def _pool(user: dict, known: list[str]):
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=user)
    db.fetch = AsyncMock(return_value=[{"service": s} for s in known])
    db.execute = AsyncMock()
    pool = MagicMock()
    pool.pool = db
    return pool


@pytest.mark.asyncio
async def test_links_found_accounts_and_reports_the_rest():
    pool = _pool(
        {"role": "user", "permissions": json.dumps(["media"]), "service_username": "Tanaka", "email": None},
        known=["nextcloud"],
    )
    finders = {
        "jellyfin": AsyncMock(return_value="jf-1"),
        "audiobookshelf": AsyncMock(return_value=None),
        "immich": AsyncMock(side_effect=RuntimeError("down")),
    }
    with patch.object(account_links, "_finders", return_value=finders), \
         patch.object(account_links, "_service_is_configured", return_value=True):
        results = await account_links.link_existing_accounts("u1", pool)

    by_service = {r["service"]: r["status"] for r in results}
    assert by_service == {
        "audiobookshelf": "not_found", "immich": "unavailable", "jellyfin": "linked", "nextcloud": "already",
    }
    # Usernames are matched lower-case; only the found account is recorded
    finders["jellyfin"].assert_awaited_once()
    assert finders["jellyfin"].await_args.args[1] == "tanaka"
    pool.pool.execute.assert_awaited_once()
    assert pool.pool.execute.await_args.args[1:] == ("u1", "jellyfin", "Tanaka", "jf-1")


@pytest.mark.asyncio
async def test_immich_is_recorded_under_the_email_login():
    pool = _pool(
        {"role": "user", "permissions": ["media"], "service_username": "ron", "email": "Ron@Example.com"},
        known=["nextcloud", "jellyfin", "audiobookshelf"],
    )
    finders = {"immich": AsyncMock(return_value="im-1")}
    with patch.object(account_links, "_finders", return_value=finders), \
         patch.object(account_links, "_service_is_configured", return_value=True):
        await account_links.link_existing_accounts("u1", pool)
    assert finders["immich"].await_args.args[2] == "ron@example.com"
    assert pool.pool.execute.await_args.args[1:] == ("u1", "immich", "ron@example.com", "im-1")


@pytest.mark.asyncio
async def test_user_without_a_username_is_refused():
    pool = _pool({"role": "user", "permissions": [], "service_username": None, "email": None}, known=[])
    with pytest.raises(ValueError):
        await account_links.link_existing_accounts("u1", pool)
