"""Authentication routes: sign-in, invite redemption, password reset, tokens.

POST /api/auth/login          — Username + password, gets JWT tokens
POST /api/auth/redeem-invite  — New account from an invite code (then onboarding)
POST /api/auth/reset-password — One-time reset code + new password, gets JWT tokens
POST /api/auth/refresh        — Exchange refresh token for new token pair
POST /api/auth/logout         — Revoke this device's refresh token
POST /api/auth/token          — Authenticated user gets a LiveKit room token

Invite codes only create accounts. Signing back in uses the username and
password chosen at onboarding (the same login as Jellyfin and the other apps).
"""

from __future__ import annotations

import json
import secrets
import time
import uuid
from collections import defaultdict, deque

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Request

from tools import DatabasePool

from ..auth import (
    create_livekit_token,
    create_user_tokens,
    decode_refresh_jwt,
    hash_token,
)
from ..config import settings
from ..deps import DEFAULT_PERMISSIONS, get_current_user, get_db_pool
from ..models import (
    AuthTokens,
    LiveKitTokenResponse,
    LoginRequest,
    LogoutRequest,
    RedeemInviteRequest,
    RedeemInviteResponse,
    RefreshTokenRequest,
    ResetPasswordRequest,
)
from ..passwords import (
    MIN_PASSWORD_LENGTH,
    hash_code,
    hash_password,
    set_user_password,
    verify_password_async,
)
from ..ratelimit import _client_ip

router = APIRouter()

# Failed sign-ins per (username, client IP). Per username alone, anyone could
# keep a known user locked out by failing on purpose; per IP alone is the
# general auth limit. This blocks only whoever is guessing.
_FAILED_LOGIN_LIMIT = 5
_FAILED_LOGIN_WINDOW = 15 * 60  # seconds
_failed_logins: dict[str, deque[float]] = defaultdict(deque)

# Verified against when the username doesn't exist, so the answer takes as
# long either way and doesn't reveal which usernames are real.
_DUMMY_HASH = hash_password(secrets.token_hex(16))


def _recent_failures(username: str) -> int:
    attempts = _failed_logins.get(username)
    if not attempts:
        return 0
    cutoff = time.monotonic() - _FAILED_LOGIN_WINDOW
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
    if not attempts:
        del _failed_logins[username]  # don't keep every username ever tried
    return len(attempts)


async def _store_refresh_token(db, token: str, user_id: str) -> None:
    """Hash and store a refresh token in the database."""
    await db.execute(
        """INSERT INTO butler.refresh_tokens (token_hash, user_id, expires_at)
           VALUES ($1, $2, NOW() + make_interval(hours => $3))""",
        hash_token(token),
        user_id,
        settings.jwt_refresh_expire_hours,
    )


async def _issue_tokens(db, user_id: str) -> RedeemInviteResponse:
    """Sign the user in: a new token pair plus their role and onboarding state."""
    user = await db.fetchrow(
        "SELECT name, role, service_username FROM butler.users WHERE id = $1", user_id
    )
    access_token, refresh_token, expires_at = create_user_tokens(user_id, user["role"])
    await _store_refresh_token(db, refresh_token, user_id)
    return RedeemInviteResponse(
        tokens=AuthTokens(accessToken=access_token, refreshToken=refresh_token, expiresAt=expires_at),
        # Onboarding sets the display name; until then it's the id
        hasCompletedOnboarding=user["name"] != user_id,
        role=user["role"],
        username=user["service_username"],
    )


def _new_user_id() -> str:
    # Random, and unrelated to the invite code (ids show up in room names and logs)
    return f"user_{secrets.token_hex(6)}"


@router.post("/login", response_model=RedeemInviteResponse)
async def login(
    req: LoginRequest,
    request: Request,
    pool: DatabasePool = Depends(get_db_pool),
):
    """Sign in with the username and password chosen at onboarding."""
    username = req.username.strip().lower()
    attempt_key = f"{username}|{_client_ip(request)}"
    if _recent_failures(attempt_key) >= _FAILED_LOGIN_LIMIT:
        raise HTTPException(429, "Too many attempts. Wait a few minutes and try again.")

    db = pool.pool
    user = await db.fetchrow(
        "SELECT id, password_hash FROM butler.users WHERE lower(service_username) = $1",
        username,
    )
    ok = await verify_password_async(req.password, user["password_hash"] if user else _DUMMY_HASH)
    if not user or not user["password_hash"] or not ok:
        _failed_logins[attempt_key].append(time.monotonic())
        raise HTTPException(401, "Incorrect username or password")

    _failed_logins.pop(attempt_key, None)
    return await _issue_tokens(db, user["id"])


@router.post("/redeem-invite", response_model=RedeemInviteResponse)
async def redeem_invite(
    req: RedeemInviteRequest,
    pool: DatabasePool = Depends(get_db_pool),
):
    """Create a new account from an invite code; onboarding sets its login.

    - Bootstrap: while no real users exist, a code from INVITE_CODES creates
      the first user as admin. It stops working once anyone exists.
    - Normal: a single-use, unexpired code an admin generated. A used code
      only lets its own user back in while they're still onboarding (so
      someone signed out midway can finish); after that it's dead.
    """
    db = pool.pool
    code = req.code.strip().upper()

    user_count = await db.fetchval(
        "SELECT COUNT(*) FROM butler.users WHERE id NOT IN ('default', 'system')"
    )
    if user_count == 0:
        valid_codes = [c.strip().upper() for c in settings.invite_codes.split(",") if c.strip()]
        if code not in valid_codes:
            raise HTTPException(401, "Invalid invite code")
        user_id = _new_user_id()
        await db.execute(
            "INSERT INTO butler.users (id, name, role) VALUES ($1, $1, 'admin')", user_id,
        )
        return await _issue_tokens(db, user_id)

    invite = await db.fetchrow(
        """SELECT ic.permissions, ic.used_by, u.name = u.id AS onboarding, ic.expires_at > NOW() AS live
           FROM butler.invite_codes ic
           LEFT JOIN butler.users u ON u.id = ic.used_by
           WHERE ic.code = $1""",
        code,
    )
    if invite and invite["used_by"] and invite["onboarding"]:
        # Signed out before finishing onboarding: let them carry on
        return await _issue_tokens(db, invite["used_by"])
    if not invite or invite["used_by"] or not invite["live"]:
        raise HTTPException(
            401, "Invalid or expired invite code. Already have an account? Sign in with your username.",
        )

    raw_perms = invite["permissions"]
    perms = (
        json.loads(raw_perms) if isinstance(raw_perms, str) else raw_perms
    ) if raw_perms is not None else list(DEFAULT_PERMISSIONS)
    user_id = _new_user_id()
    async with db.acquire() as conn, conn.transaction():
        # Claim the code first so two people can't redeem it at once
        claimed = await conn.execute(
            "UPDATE butler.invite_codes SET used_at = NOW() "
            "WHERE code = $1 AND used_by IS NULL AND used_at IS NULL",
            code,
        )
        if claimed == "UPDATE 0":
            raise HTTPException(401, "That invite code was just used")
        await conn.execute(
            "INSERT INTO butler.users (id, name, role, permissions) VALUES ($1, $1, 'user', $2::jsonb)",
            user_id, json.dumps(perms),
        )
        await conn.execute(
            "UPDATE butler.invite_codes SET used_by = $1 WHERE code = $2", user_id, code,
        )
    return await _issue_tokens(db, user_id)


@router.post("/reset-password", response_model=RedeemInviteResponse)
async def reset_password(
    req: ResetPasswordRequest,
    pool: DatabasePool = Depends(get_db_pool),
):
    """Choose a new password with a one-time code from an admin (or the server).

    The new password goes to every linked app, all other sessions are signed
    out, and this device is signed in.
    """
    if len(req.newPassword) < MIN_PASSWORD_LENGTH:
        raise HTTPException(400, f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    db = pool.pool
    row = await db.fetchrow(
        """SELECT rc.user_id, u.service_username FROM butler.password_reset_codes rc
           JOIN butler.users u ON u.id = rc.user_id
           WHERE rc.code_hash = $1 AND rc.used_at IS NULL AND rc.expires_at > NOW()""",
        hash_code(req.code),
    )
    if not row:
        raise HTTPException(401, "That reset code is wrong, used or expired. Ask an admin for a new one.")
    if not row["service_username"]:
        raise HTTPException(400, "This account has no username yet. Ask an admin to set one.")

    user_id = row["user_id"]
    code_hash = hash_code(req.code)
    # Claim the code first so it can't be used twice at once...
    used = await db.execute(
        "UPDATE butler.password_reset_codes SET used_at = NOW() WHERE code_hash = $1 AND used_at IS NULL",
        code_hash,
    )
    if used == "UPDATE 0":
        raise HTTPException(401, "That reset code was just used")
    try:
        results = await set_user_password(user_id, req.newPassword, pool)
    except Exception:
        # ...but give it back if the change didn't happen, so it can be retried
        await db.execute("UPDATE butler.password_reset_codes SET used_at = NULL WHERE code_hash = $1", code_hash)
        raise
    # Whoever had the old password shouldn't stay signed in
    await db.execute(
        "UPDATE butler.refresh_tokens SET revoked_at = NOW() WHERE user_id = $1 AND revoked_at IS NULL",
        user_id,
    )
    response = await _issue_tokens(db, user_id)
    # Apps that refused it (e.g. Nextcloud's breached-password check) keep the old one
    response.passwordResults = results
    return response


@router.post("/refresh", response_model=RedeemInviteResponse)
async def refresh_tokens(
    req: RefreshTokenRequest,
    pool: DatabasePool = Depends(get_db_pool),
):
    """Exchange a valid refresh token for new access + refresh tokens.

    Implements refresh token rotation: the old refresh token is revoked
    and a new pair is issued. This limits the damage window if a refresh
    token is compromised.
    """
    try:
        payload = decode_refresh_jwt(req.refreshToken)
    except pyjwt.InvalidTokenError:
        raise HTTPException(401, "Invalid refresh token")

    user_id = payload["sub"]
    token_hash = hash_token(req.refreshToken)
    db = pool.pool

    # Verify token exists in DB, is not revoked, and not expired
    stored = await db.fetchrow(
        """SELECT id FROM butler.refresh_tokens
           WHERE token_hash = $1 AND user_id = $2
             AND revoked_at IS NULL AND expires_at > NOW()""",
        token_hash,
        user_id,
    )
    if not stored:
        raise HTTPException(401, "Refresh token revoked or expired")

    # Revoke old refresh token (rotation)
    await db.execute(
        "UPDATE butler.refresh_tokens SET revoked_at = NOW() WHERE token_hash = $1",
        token_hash,
    )

    if not await db.fetchval("SELECT 1 FROM butler.users WHERE id = $1", user_id):
        raise HTTPException(401, "User not found")
    # Role comes from the DB, not the stale token
    return await _issue_tokens(db, user_id)


@router.post("/logout", status_code=204)
async def logout(
    req: LogoutRequest,
    pool: DatabasePool = Depends(get_db_pool),
):
    """Revoke this device's refresh token. Unknown tokens are ignored."""
    await pool.pool.execute(
        "UPDATE butler.refresh_tokens SET revoked_at = NOW() WHERE token_hash = $1 AND revoked_at IS NULL",
        hash_token(req.refreshToken),
    )


@router.post("/token", response_model=LiveKitTokenResponse)
async def get_livekit_token(
    user_id: str = Depends(get_current_user),
):
    """Generate a LiveKit room token for the authenticated user.

    Each voice session gets a unique room so a fresh agent is always
    dispatched. Without this, reconnecting to the same static room
    reuses a dead agent session (close_on_disconnect kills it).
    """
    session_suffix = uuid.uuid4().hex[:8]
    room_name = f"butler_{user_id}_{session_suffix}"
    token = create_livekit_token(user_id, room_name)
    return LiveKitTokenResponse(livekit_token=token, room_name=room_name)
