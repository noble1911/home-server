"""Authentication routes: invite code redemption and LiveKit token generation.

POST /api/auth/redeem-invite — PWA sends invite code, gets JWT tokens
POST /api/auth/token — Authenticated user gets a LiveKit room token for voice
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from tools import DatabasePool

from ..auth import create_livekit_token, create_user_tokens
from ..config import settings
from ..deps import get_current_user, get_db_pool
from ..models import (
    AuthTokens,
    LiveKitTokenResponse,
    RedeemInviteRequest,
    RedeemInviteResponse,
)

router = APIRouter()


@router.post("/redeem-invite", response_model=RedeemInviteResponse)
async def redeem_invite(
    req: RedeemInviteRequest,
    pool: DatabasePool = Depends(get_db_pool),
):
    """Validate invite code, create or find user, and return JWT tokens.

    Each invite code maps deterministically to a user_id. On first use,
    a stub user row is created. The PWA checks hasCompletedOnboarding
    to decide whether to show the onboarding flow.
    """
    valid_codes = [c.strip().upper() for c in settings.invite_codes.split(",")]
    if req.code.upper() not in valid_codes:
        raise HTTPException(401, "Invalid invite code")

    # Deterministic user_id from invite code
    user_id = f"invite_{req.code.lower().replace('-', '_')}"

    db = pool.pool
    user = await db.fetchrow(
        "SELECT id, name, soul FROM butler.users WHERE id = $1", user_id
    )

    # User has onboarded if they have a name different from their auto-generated id
    has_onboarded = user is not None and user["name"] != user_id

    if not user:
        await db.execute(
            "INSERT INTO butler.users (id, name) VALUES ($1, $1) ON CONFLICT (id) DO NOTHING",
            user_id,
        )

    access_token, refresh_token, expires_at = create_user_tokens(user_id)

    return RedeemInviteResponse(
        tokens=AuthTokens(
            accessToken=access_token,
            refreshToken=refresh_token,
            expiresAt=expires_at,
        ),
        hasCompletedOnboarding=has_onboarded,
    )


@router.post("/token", response_model=LiveKitTokenResponse)
async def get_livekit_token(
    user_id: str = Depends(get_current_user),
):
    """Generate a LiveKit room token for the authenticated user.

    Each user gets a dedicated room (butler_{user_id}) so conversations
    don't cross. The token is valid for 1 hour.
    """
    room_name = f"butler_{user_id}"
    token = create_livekit_token(user_id, room_name)
    return LiveKitTokenResponse(livekit_token=token, room_name=room_name)
