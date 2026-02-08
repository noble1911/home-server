"""User profile routes.

These endpoints match the PWA's userStore.ts calls exactly:
  GET  /api/user/profile           -> fetchProfile()
  PUT  /api/user/profile           -> updateProfile()
  PUT  /api/user/butler            -> updateButlerName()
  PUT  /api/user/soul              -> updateSoul()
  PUT  /api/user/notifications     -> updateNotifications()
  POST /api/user/notifications/test -> testWhatsAppNotification()
  POST /api/user/onboarding        -> completeOnboarding()
  POST /api/user/facts             -> addFact()
  DELETE /api/user/facts/{id}      -> removeFact()

Also implements GET /api/users/me from issue #30 spec.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Response

from tools import DatabasePool, Tool, WhatsAppTool

from ..crypto import decrypt_password
from ..deps import get_current_user, get_db_pool, get_tools
from ..models import (
    AddFactRequest,
    NotificationPrefs,
    OnboardingRequest,
    ServiceCredentialsResponse,
    SoulConfig,
    UpdateButlerNameRequest,
    UpdateNotificationsRequest,
    UpdateProfileRequest,
    UserFact,
    UserProfile,
)
from ..oauth import revoke_google_token
from ..provisioning import provision_user_accounts

logger = logging.getLogger(__name__)

router = APIRouter()


def _parse_notification_prefs(raw) -> NotificationPrefs:
    """Parse notification_prefs JSONB column into the API model."""
    if raw is None:
        return NotificationPrefs()
    data = json.loads(raw) if isinstance(raw, str) else raw
    return NotificationPrefs(
        enabled=data.get("enabled", True),
        categories=data.get("categories", [
            "download", "reminder", "weather",
            "smart_home", "calendar", "general",
        ]),
        quietHoursStart=data.get("quiet_hours_start"),
        quietHoursEnd=data.get("quiet_hours_end"),
    )


async def _get_profile(user_id: str, pool: DatabasePool) -> UserProfile:
    """Shared logic for fetching a user profile."""
    db = pool.pool

    user = await db.fetchrow(
        "SELECT id, name, soul, role, permissions, phone, notification_prefs, created_at "
        "FROM butler.users WHERE id = $1",
        user_id,
    )
    if not user:
        raise HTTPException(404, "User not found")

    facts = await db.fetch(
        """
        SELECT id, fact, category, created_at FROM butler.user_facts
        WHERE user_id = $1 AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY created_at DESC
        """,
        user_id,
    )

    soul = user["soul"] or {}
    raw_perms = user["permissions"]
    permissions = (
        json.loads(raw_perms) if isinstance(raw_perms, str) else raw_perms
    ) if raw_perms is not None else ["media", "home"]

    return UserProfile(
        id=user["id"],
        name=user["name"],
        phone=user["phone"],
        butlerName=soul.get("butler_name", "Butler"),
        role=user["role"],
        permissions=permissions,
        createdAt=user["created_at"].isoformat(),
        soul=SoulConfig(
            personality=soul.get("personality", "balanced"),
            verbosity=soul.get("verbosity", "moderate"),
            humor=soul.get("humor", "subtle"),
            customInstructions=soul.get("customInstructions"),
        ),
        facts=[
            UserFact(
                id=str(row["id"]),
                content=row["fact"],
                category=row["category"] or "other",
                createdAt=row["created_at"].isoformat(),
            )
            for row in facts
        ],
        notificationPrefs=_parse_notification_prefs(user["notification_prefs"]),
    )


@router.get("/user/profile", response_model=UserProfile)
@router.get("/users/me", response_model=UserProfile)
async def get_profile(
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Get the authenticated user's profile, soul config, and facts."""
    return await _get_profile(user_id, pool)


@router.put("/user/profile", response_model=UserProfile)
async def update_profile(
    req: UpdateProfileRequest,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Update basic profile fields (name, email)."""
    db = pool.pool
    if req.name:
        await db.execute(
            "UPDATE butler.users SET name = $2 WHERE id = $1", user_id, req.name
        )
    return await _get_profile(user_id, pool)


@router.put("/user/butler")
async def update_butler_name(
    req: UpdateButlerNameRequest,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Update the butler's display name (stored in soul JSONB)."""
    db = pool.pool
    await db.execute(
        """
        UPDATE butler.users
        SET soul = COALESCE(soul, '{}'::jsonb) || jsonb_build_object('butler_name', $2::text)
        WHERE id = $1
        """,
        user_id,
        req.butlerName,
    )
    return {"status": "ok"}


@router.put("/user/soul")
async def update_soul(
    soul: SoulConfig,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Update soul/personality configuration (merged with existing)."""
    db = pool.pool
    soul_dict = soul.model_dump(exclude_none=True)
    await db.execute(
        """
        UPDATE butler.users
        SET soul = COALESCE(soul, '{}'::jsonb) || $2::jsonb
        WHERE id = $1
        """,
        user_id,
        json.dumps(soul_dict),
    )
    return {"status": "ok"}


@router.put("/user/notifications", response_model=UserProfile)
async def update_notifications(
    req: UpdateNotificationsRequest,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Update phone number and/or notification preferences."""
    async with pool.pool.acquire() as conn:
        async with conn.transaction():
            if req.phone is not None:
                await conn.execute(
                    "UPDATE butler.users SET phone = $2 WHERE id = $1",
                    user_id,
                    req.phone if req.phone else None,
                )

            if req.notificationPrefs is not None:
                prefs_dict = {
                    "enabled": req.notificationPrefs.enabled,
                    "categories": req.notificationPrefs.categories,
                    "quiet_hours_start": req.notificationPrefs.quietHoursStart,
                    "quiet_hours_end": req.notificationPrefs.quietHoursEnd,
                }
                await conn.execute(
                    "UPDATE butler.users SET notification_prefs = $2::jsonb WHERE id = $1",
                    user_id,
                    json.dumps(prefs_dict),
                )

    return await _get_profile(user_id, pool)


@router.post("/user/notifications/test")
async def test_whatsapp_notification(
    user_id: str = Depends(get_current_user),
    tools: dict[str, Tool] = Depends(get_tools),
):
    """Send a test WhatsApp message to the authenticated user."""
    whatsapp: WhatsAppTool | None = tools.get("whatsapp")
    if not whatsapp:
        raise HTTPException(503, "WhatsApp notifications are not configured")

    result = await whatsapp.execute(
        action="send_message",
        user_id=user_id,
        message="This is a test notification from Butler.",
        category="general",
    )
    return {"result": result}


@router.post("/user/onboarding")
async def complete_onboarding(
    req: OnboardingRequest,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Save onboarding data and auto-provision service accounts."""
    db = pool.pool
    soul_dict = req.soul.model_dump(exclude_none=True)
    soul_dict["butler_name"] = req.butlerName

    await db.execute(
        """
        UPDATE butler.users SET name = $2, soul = $3::jsonb WHERE id = $1
        """,
        user_id,
        req.name,
        json.dumps(soul_dict),
    )

    # Auto-provision service accounts if credentials were provided
    service_accounts: list[dict] = []
    if req.serviceUsername and req.servicePassword:
        # Get user permissions (default to ["media", "home"] for new users)
        raw_perms = await db.fetchval(
            "SELECT permissions FROM butler.users WHERE id = $1", user_id
        )
        permissions = (
            json.loads(raw_perms) if isinstance(raw_perms, str) else raw_perms
        ) if raw_perms is not None else ["media", "home"]

        try:
            service_accounts = await provision_user_accounts(
                user_id, req.serviceUsername, req.servicePassword, permissions, pool
            )
        except Exception:
            logger.exception("Service provisioning failed for user %s", user_id)
            service_accounts = [
                {"service": "all", "username": req.serviceUsername,
                 "status": "failed", "error": "Provisioning service unavailable"}
            ]

    return {"status": "ok", "serviceAccounts": service_accounts}


@router.get("/user/service-credentials", response_model=ServiceCredentialsResponse)
async def get_service_credentials(
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Retrieve the user's auto-provisioned service account credentials."""
    db = pool.pool
    rows = await db.fetch(
        """SELECT service, username, password_encrypted, status, error_message, created_at
           FROM butler.service_credentials
           WHERE user_id = $1
           ORDER BY service""",
        user_id,
    )

    credentials = []
    for row in rows:
        cred: dict = {
            "service": row["service"],
            "username": row["username"],
            "password": None,
            "status": row["status"],
            "createdAt": row["created_at"].isoformat(),
        }
        if row["password_encrypted"] and row["status"] == "active":
            try:
                cred["password"] = decrypt_password(row["password_encrypted"])
            except Exception:
                cred["password"] = None
                cred["status"] = "decrypt_error"
        if row["error_message"]:
            cred["errorMessage"] = row["error_message"]
        credentials.append(cred)

    return {"credentials": credentials}


@router.post("/user/facts", response_model=UserFact, status_code=201)
async def add_fact(
    req: AddFactRequest,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Add a user fact (explicit, from the profile settings page)."""
    db = pool.pool
    row = await db.fetchrow(
        """
        INSERT INTO butler.user_facts (user_id, fact, category, source)
        VALUES ($1, $2, $3, 'explicit')
        RETURNING id, fact, category, created_at
        """,
        user_id,
        req.content,
        req.category,
    )
    return UserFact(
        id=str(row["id"]),
        content=row["fact"],
        category=row["category"],
        createdAt=row["created_at"].isoformat(),
    )


@router.delete("/user/facts", status_code=204)
async def clear_all_facts(
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Delete all facts for the authenticated user."""
    db = pool.pool
    await db.execute(
        "DELETE FROM butler.user_facts WHERE user_id = $1",
        user_id,
    )
    return Response(status_code=204)


@router.delete("/user/facts/{fact_id}", status_code=204)
async def remove_fact(
    fact_id: int,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Remove a user fact. Only allows deleting the user's own facts."""
    db = pool.pool
    result = await db.execute(
        "DELETE FROM butler.user_facts WHERE id = $1 AND user_id = $2",
        fact_id,
        user_id,
    )
    if result == "DELETE 0":
        raise HTTPException(404, "Fact not found")
    return Response(status_code=204)


@router.delete("/user/account", status_code=204)
async def delete_account(
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Permanently delete the authenticated user's account and all data.

    Order of operations:
    1. Revoke OAuth tokens at external providers (best-effort)
    2. Delete user row (CASCADE removes all child records)
    """
    db = pool.pool

    # 1. Best-effort revoke OAuth tokens at provider before cascade deletes them
    oauth_rows = await db.fetch(
        "SELECT provider, access_token, refresh_token FROM butler.oauth_tokens WHERE user_id = $1",
        user_id,
    )
    for row in oauth_rows:
        token_to_revoke = row["refresh_token"] or row["access_token"]
        if token_to_revoke:
            try:
                await revoke_google_token(token_to_revoke)
            except Exception:
                logger.warning(
                    "Failed to revoke %s token during account deletion for user=%s",
                    row["provider"],
                    user_id,
                )

    # 2. Delete user row — CASCADE handles all child tables
    result = await db.execute(
        "DELETE FROM butler.users WHERE id = $1",
        user_id,
    )
    if result == "DELETE 0":
        raise HTTPException(404, "User not found")

    return Response(status_code=204)
