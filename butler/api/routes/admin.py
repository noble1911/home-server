"""Admin routes: invite codes and user management.

POST   /api/admin/invite-codes                  — Generate a new invite code
GET    /api/admin/invite-codes                  — List all codes and their status
DELETE /api/admin/invite-codes/{code}           — Revoke an unused code
GET    /api/admin/users                         — List all users with permissions
PUT    /api/admin/users/{user_id}/permissions   — Update a user's tool permissions
POST   /api/admin/users/{user_id}/reprovision   — Re-provision service accounts
POST   /api/admin/users/{user_id}/link-accounts — Link logins made outside onboarding
DELETE /api/admin/users/{user_id}               — Delete a user + their service accounts
GET    /api/admin/model                         — Butler's chat model and the choices
PUT    /api/admin/model                         — Choose the chat model
GET    /api/admin/iptv                          — The IPTV provider synced to Dispatcharr
PUT    /api/admin/iptv                          — Save the IPTV provider and push it to Dispatcharr
POST   /api/admin/iptv/sync                     — Push the saved provider to Dispatcharr again
"""

from __future__ import annotations

import json
import logging
import secrets
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response

from tools import DatabasePool

from ..deps import ALL_PERMISSION_GROUPS, DEFAULT_PERMISSIONS, get_admin_user, get_db_pool
from .. import iptv, model_settings
from ..config import settings
from ..account_links import link_existing_accounts
from ..crypto import decrypt_password
from ..provisioning import deprovision_user_accounts, provision_user_accounts

logger = logging.getLogger(__name__)
from ..models import (
    ChatModelOption,
    ChatModelSettings,
    SetChatModelRequest,
    IptvProviderSettings,
    SetIptvProviderRequest,
    AdminUserInfo,
    AdminUserListResponse,
    CreateInviteCodeRequest,
    CreateInviteCodeResponse,
    InviteCodeInfo,
    InviteCodeListResponse,
    UpdatePermissionsRequest,
)

router = APIRouter()

# Exclude ambiguous characters: 0/O, 1/I/L
_CODE_ALPHABET = "".join(
    c
    for c in string.ascii_uppercase + string.digits
    if c not in "0OI1L"
)


def _generate_code(length: int = 6) -> str:
    """Generate a random alphanumeric code (uppercase, no ambiguous chars)."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


@router.post("/invite-codes", response_model=CreateInviteCodeResponse, status_code=201)
async def create_invite_code(
    req: CreateInviteCodeRequest = CreateInviteCodeRequest(),
    admin_id: str = Depends(get_admin_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Generate a new invite code with optional permissions. Admin only."""
    db = pool.pool
    expires_at = datetime.now(timezone.utc) + timedelta(days=req.expiresInDays)

    # Resolve and validate permissions
    perms = req.permissions if req.permissions is not None else list(DEFAULT_PERMISSIONS)
    # Non-admin users cannot grant admin tool access via invite codes
    perms = [p for p in perms if p != "admin"]
    invalid = set(perms) - set(ALL_PERMISSION_GROUPS)
    if invalid:
        raise HTTPException(
            400, f"Unknown permission groups: {', '.join(sorted(invalid))}"
        )

    # Retry on collision (extremely unlikely with 6 chars from 31-char alphabet)
    for _ in range(10):
        code = _generate_code()
        existing = await db.fetchval(
            "SELECT 1 FROM butler.invite_codes WHERE code = $1", code
        )
        if not existing:
            await db.execute(
                """INSERT INTO butler.invite_codes (code, created_by, expires_at, permissions)
                   VALUES ($1, $2, $3, $4::jsonb)""",
                code,
                admin_id,
                expires_at,
                json.dumps(perms),
            )
            return CreateInviteCodeResponse(
                code=code, expiresAt=expires_at.isoformat(), permissions=perms
            )

    raise HTTPException(500, "Failed to generate unique code")


@router.get("/invite-codes", response_model=InviteCodeListResponse)
async def list_invite_codes(
    admin_id: str = Depends(get_admin_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """List all invite codes with their status. Admin only."""
    db = pool.pool
    rows = await db.fetch(
        """SELECT ic.code, ic.created_by, ic.used_by, ic.expires_at,
                  ic.created_at, ic.used_at, ic.permissions,
                  u.name AS used_by_name,
                  u.permissions AS user_permissions
           FROM butler.invite_codes ic
           LEFT JOIN butler.users u ON ic.used_by = u.id
           ORDER BY ic.created_at DESC"""
    )
    now = datetime.now(timezone.utc)
    codes = []
    for r in rows:
        # For used codes: show the user's CURRENT permissions (single source of truth)
        # For unused codes: show the code's own permissions (what will be granted)
        raw = r["user_permissions"] if r["used_by"] is not None else r["permissions"]
        perms = (
            json.loads(raw) if isinstance(raw, str) else raw
        ) if raw is not None else list(DEFAULT_PERMISSIONS)
        # Show actual display name if user has onboarded, otherwise fall back to ID
        used_by_display = None
        if r["used_by"] is not None:
            name = r["used_by_name"]
            used_by_display = name if name and name != r["used_by"] else r["used_by"]
        codes.append(
            InviteCodeInfo(
                code=r["code"],
                createdBy=r["created_by"],
                usedBy=used_by_display,
                expiresAt=r["expires_at"].isoformat(),
                createdAt=r["created_at"].isoformat(),
                usedAt=r["used_at"].isoformat() if r["used_at"] else None,
                isExpired=r["expires_at"] < now,
                isUsed=r["used_by"] is not None,
                permissions=perms,
            )
        )
    return InviteCodeListResponse(codes=codes)


@router.delete("/invite-codes/{code}", status_code=204)
async def revoke_invite_code(
    code: str,
    admin_id: str = Depends(get_admin_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Revoke an unused invite code. Admin only."""
    db = pool.pool
    result = await db.execute(
        "DELETE FROM butler.invite_codes WHERE code = $1 AND used_by IS NULL",
        code.upper(),
    )
    if result == "DELETE 0":
        raise HTTPException(404, "Code not found or already used")
    return Response(status_code=204)


# ── User & permission management ─────────────────────────────────────


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    admin_id: str = Depends(get_admin_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """List all users with their roles and permissions. Admin only."""
    db = pool.pool
    rows = await db.fetch(
        "SELECT id, name, role, permissions, service_username FROM butler.users "
        "WHERE id NOT IN ('default', 'system') ORDER BY created_at"
    )
    users = []
    for r in rows:
        raw = r["permissions"]
        perms = (
            json.loads(raw) if isinstance(raw, str) else raw
        ) if raw is not None else ["media", "home"]
        users.append(
            AdminUserInfo(
                id=r["id"], name=r["name"], role=r["role"], permissions=perms,
                username=r["service_username"],
            )
        )
    return AdminUserListResponse(users=users)


@router.put("/users/{user_id}/permissions")
async def update_user_permissions(
    user_id: str,
    req: UpdatePermissionsRequest,
    admin_id: str = Depends(get_admin_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Set a user's tool permissions. Admin only."""
    # Validate permission names
    invalid = set(req.permissions) - set(ALL_PERMISSION_GROUPS)
    if invalid:
        raise HTTPException(
            400, f"Unknown permission groups: {', '.join(sorted(invalid))}"
        )

    db = pool.pool
    result = await db.execute(
        "UPDATE butler.users SET permissions = $2::jsonb WHERE id = $1",
        user_id,
        req.permissions,
    )
    if result == "UPDATE 0":
        raise HTTPException(404, "User not found")
    return {"status": "ok", "permissions": req.permissions}


@router.post("/users/{user_id}/reprovision")
async def admin_reprovision_user(
    user_id: str,
    admin_id: str = Depends(get_admin_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Re-run service provisioning for a user using their stored credentials. Admin only."""
    db = pool.pool
    row = await db.fetchrow(
        "SELECT service_username, service_password_encrypted, permissions FROM butler.users WHERE id = $1",
        user_id,
    )
    if not row:
        raise HTTPException(404, "User not found")
    if not row["service_username"] or not row["service_password_encrypted"]:
        raise HTTPException(400, "User has no stored service credentials")

    password = decrypt_password(row["service_password_encrypted"])
    raw_perms = row["permissions"]
    permissions = (
        json.loads(raw_perms) if isinstance(raw_perms, str) else raw_perms
    ) if raw_perms is not None else list(DEFAULT_PERMISSIONS)

    results = await provision_user_accounts(
        user_id, row["service_username"], password, permissions, pool
    )
    return {"status": "ok", "serviceAccounts": results}


@router.post("/users/{user_id}/link-accounts")
async def admin_link_accounts(
    user_id: str,
    admin_id: str = Depends(get_admin_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Link a user's existing logins (made outside onboarding) so password changes reach them."""
    try:
        results = await link_existing_accounts(user_id, pool)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "ok", "results": results}


@router.delete("/users/{user_id}", status_code=204)
async def admin_delete_user(
    user_id: str,
    admin_id: str = Depends(get_admin_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Delete a user and their service accounts. Admin only."""
    if user_id == admin_id:
        raise HTTPException(400, "Cannot delete your own account from the admin panel")

    db = pool.pool
    exists = await db.fetchval(
        "SELECT 1 FROM butler.users WHERE id = $1", user_id
    )
    if not exists:
        raise HTTPException(404, "User not found")

    # Best-effort deprovision service accounts on downstream apps
    try:
        await deprovision_user_accounts(user_id, pool)
    except Exception:
        logger.warning(
            "Service deprovisioning failed during admin deletion for user=%s", user_id
        )

    # CASCADE handles all child tables (facts, credentials, tokens, etc.)
    await db.execute("DELETE FROM butler.users WHERE id = $1", user_id)
    return Response(status_code=204)


# --- Chat model (#215) ---


def _model_settings() -> ChatModelSettings:
    return ChatModelSettings(
        current=model_settings.current_model(),
        selected=model_settings.selected_model(),
        serverDefault=settings.anthropic_model,
        options=[ChatModelOption(id=k, **v) for k, v in model_settings.CHAT_MODELS.items()],
    )


@router.get("/model", response_model=ChatModelSettings)
async def get_chat_model(admin_id: str = Depends(get_admin_user)):
    """Which Claude model Butler chats with, and the choices."""
    return _model_settings()


@router.put("/model", response_model=ChatModelSettings)
async def set_chat_model(
    req: SetChatModelRequest,
    admin_id: str = Depends(get_admin_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Choose the household's chat model (null = server default). Takes effect on the next message."""
    try:
        await model_settings.set_model(pool, req.model, admin_id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return _model_settings()


# --- IPTV provider -> Dispatcharr (#223) ---


async def _iptv_settings(pool: DatabasePool) -> IptvProviderSettings:
    p = await iptv.get_provider(pool)
    if not p:
        return IptvProviderSettings(configured=False)
    return IptvProviderSettings(
        configured=True,
        kind=p["kind"],
        serverUrl=p["server_url"],
        username=p["username"],
        hasPassword=bool(p["password_encrypted"]),
        hasM3uUrl=bool(p["m3u_url_encrypted"]),
        maxStreams=p["max_streams"],
        dispatcharrUsername=p["dispatcharr_username"],
        hasDispatcharrPassword=bool(p["dispatcharr_password_encrypted"]),
        lastSyncedAt=p["last_synced_at"],
        lastError=p["last_error"],
    )


@router.get("/iptv", response_model=IptvProviderSettings)
async def get_iptv_provider(
    admin_id: str = Depends(get_admin_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """The household's IPTV provider (secrets withheld) and its last sync."""
    return await _iptv_settings(pool)


@router.put("/iptv", response_model=IptvProviderSettings)
async def set_iptv_provider(
    req: SetIptvProviderRequest,
    admin_id: str = Depends(get_admin_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Save the IPTV provider, then push it to Dispatcharr.

    The login is saved even if Dispatcharr can't take it; the failure is
    returned in ``lastError`` so the admin can fix it and sync again.
    """
    try:
        await iptv.save_provider(
            pool,
            kind=req.kind,
            server_url=(req.serverUrl or "").strip().rstrip("/") or None,
            username=(req.username or "").strip() or None,
            password=req.password or None,
            m3u_url=(req.m3uUrl or "").strip() or None,
            max_streams=req.maxStreams,
            dispatcharr_username=(req.dispatcharrUsername or "").strip() or None,
            dispatcharr_password=req.dispatcharrPassword or None,
            user_id=admin_id,
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    try:
        await iptv.sync(pool, admin_id)
    except iptv.DispatcharrError as e:
        logger.warning("IPTV provider saved but not synced: %s", e)
    return await _iptv_settings(pool)


@router.post("/iptv/sync", response_model=IptvProviderSettings)
async def sync_iptv_provider(
    admin_id: str = Depends(get_admin_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Push the saved provider to Dispatcharr again (e.g. after creating the Dispatcharr admin)."""
    try:
        await iptv.sync(pool, admin_id)
    except iptv.DispatcharrError as e:
        logger.warning("IPTV sync failed: %s", e)
    return await _iptv_settings(pool)
