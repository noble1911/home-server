"""User profile routes.

These endpoints match the PWA's userStore.ts calls exactly:
  GET  /api/user/profile      -> fetchProfile()
  PUT  /api/user/profile      -> updateProfile()
  PUT  /api/user/butler       -> updateButlerName()
  PUT  /api/user/soul         -> updateSoul()
  POST /api/user/onboarding   -> completeOnboarding()
  POST /api/user/facts        -> addFact()
  DELETE /api/user/facts/{id} -> removeFact()

Also implements GET /api/users/me from issue #30 spec.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Response

from tools import DatabasePool

from ..deps import get_current_user, get_db_pool
from ..oauth import revoke_google_token

logger = logging.getLogger(__name__)
from ..models import (
    AddFactRequest,
    OnboardingRequest,
    SoulConfig,
    UpdateButlerNameRequest,
    UpdateProfileRequest,
    UserFact,
    UserProfile,
)

router = APIRouter()


async def _get_profile(user_id: str, pool: DatabasePool) -> UserProfile:
    """Shared logic for fetching a user profile."""
    db = pool.pool

    user = await db.fetchrow(
        "SELECT id, name, soul, role, created_at FROM butler.users WHERE id = $1",
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

    return UserProfile(
        id=user["id"],
        name=user["name"],
        butlerName=soul.get("butler_name", "Butler"),
        role=user["role"],
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


@router.post("/user/onboarding")
async def complete_onboarding(
    req: OnboardingRequest,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Save onboarding data: name, butler name, and personality config."""
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
    return {"status": "ok"}


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
