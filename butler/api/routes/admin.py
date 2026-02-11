"""Admin routes: invite codes and user management.

POST   /api/admin/invite-codes                  — Generate a new invite code
GET    /api/admin/invite-codes                  — List all codes and their status
DELETE /api/admin/invite-codes/{code}           — Revoke an unused code
GET    /api/admin/users                         — List all users with permissions
PUT    /api/admin/users/{user_id}/permissions   — Update a user's tool permissions
DELETE /api/admin/users/{user_id}               — Delete a user + their service accounts
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
from ..provisioning import deprovision_user_accounts

logger = logging.getLogger(__name__)
from ..models import (
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
                  u.name AS used_by_name
           FROM butler.invite_codes ic
           LEFT JOIN butler.users u ON ic.used_by = u.id
           ORDER BY ic.created_at DESC"""
    )
    now = datetime.now(timezone.utc)
    codes = []
    for r in rows:
        raw = r["permissions"]
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
        "SELECT id, name, role, permissions FROM butler.users "
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
