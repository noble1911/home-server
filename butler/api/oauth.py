"""OAuth 2.0 token management for external service integrations.

Handles the OAuth dance (authorize URL, code exchange, token storage)
and transparent token refresh for per-user service connections.

Tokens are stored in butler.oauth_tokens and looked up by (user_id, provider).
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import aiohttp
import jwt

from .config import settings

logger = logging.getLogger(__name__)

# Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# Scopes
CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
USERINFO_EMAIL_SCOPE = "https://www.googleapis.com/auth/userinfo.email"
GOOGLE_SCOPES = f"{CALENDAR_READONLY_SCOPE} {GMAIL_READONLY_SCOPE} {USERINFO_EMAIL_SCOPE}"

# State JWT settings
_STATE_TTL_MINUTES = 10


# --- State parameter (CSRF protection) ---


def create_oauth_state(
    user_id: str,
    redirect_uri: str | None = None,
    frontend_url: str | None = None,
) -> str:
    """Create a signed JWT state parameter encoding the user_id.

    The state is short-lived (10 minutes) and includes a random nonce
    to prevent replay attacks. Signed with the existing jwt_secret.

    Optionally embeds redirect_uri and frontend_url so the callback
    can use the correct URLs regardless of how the user accessed the PWA
    (LAN vs Cloudflare Tunnel).
    """
    now = datetime.now(timezone.utc)
    payload: dict = {
        "sub": user_id,
        "nonce": secrets.token_hex(16),
        "iat": now,
        "exp": now + timedelta(minutes=_STATE_TTL_MINUTES),
        "type": "oauth_state",
    }
    if redirect_uri:
        payload["redirect_uri"] = redirect_uri
    if frontend_url:
        payload["frontend_url"] = frontend_url
    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def verify_oauth_state(state: str) -> dict:
    """Decode and validate the OAuth state JWT.

    Returns a dict with 'user_id' and optional 'redirect_uri'/'frontend_url'.

    Raises:
        jwt.InvalidTokenError: If state is invalid, expired, or wrong type.
    """
    payload = jwt.decode(
        state, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != "oauth_state":
        raise jwt.InvalidTokenError("Not an OAuth state token")
    return {
        "user_id": payload["sub"],
        "redirect_uri": payload.get("redirect_uri"),
        "frontend_url": payload.get("frontend_url"),
    }


# --- Google OAuth helpers ---


def build_google_authorize_url(state: str, redirect_uri: str | None = None) -> str:
    """Build the Google OAuth consent URL.

    Uses access_type=offline to get a refresh_token, and prompt=consent
    to ensure the consent screen always appears (guarantees refresh_token).

    If redirect_uri is provided, it overrides the configured default —
    this allows the OAuth flow to work via Cloudflare Tunnel or LAN.
    """
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri or settings.google_redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_google_code(code: str, redirect_uri: str | None = None) -> dict:
    """Exchange an authorization code for access and refresh tokens.

    The redirect_uri MUST match the one used in the authorize request —
    Google validates this. If not provided, falls back to the configured default.

    Returns the raw token response dict from Google:
        {access_token, refresh_token, expires_in, token_type, scope}
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri or settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                error = data.get("error_description", data.get("error", "Unknown"))
                raise RuntimeError(f"Google token exchange failed: {error}")
            return data


async def refresh_google_token(refresh_token: str) -> dict:
    """Refresh an expired Google access token.

    Returns dict with: {access_token, expires_in, token_type, scope}
    Note: Google does not return a new refresh_token on refresh.
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(
            GOOGLE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "grant_type": "refresh_token",
            },
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                error = data.get("error_description", data.get("error", "Unknown"))
                raise RuntimeError(f"Google token refresh failed: {error}")
            return data


async def get_google_user_email(access_token: str) -> str | None:
    """Fetch the Google account email for display purposes."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get("email")


async def revoke_google_token(token: str) -> None:
    """Revoke a Google token (access or refresh)."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            GOOGLE_REVOKE_URL,
            params={"token": token},
        ) as resp:
            if resp.status != 200:
                logger.warning("Google token revocation returned %d", resp.status)


# --- Token storage ---


async def store_tokens(
    pool,
    user_id: str,
    provider: str,
    token_data: dict,
    account_id: str | None = None,
) -> None:
    """Store or update OAuth tokens for a user/provider.

    Uses INSERT ... ON CONFLICT for upsert, so re-authorization
    cleanly replaces the existing tokens.
    """
    expires_in = token_data.get("expires_in", 3600)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    scopes = token_data.get("scope", "")

    await pool.pool.execute(
        """
        INSERT INTO butler.oauth_tokens
            (user_id, provider, access_token, refresh_token, token_expires_at, scopes, provider_account_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (user_id, provider) DO UPDATE SET
            access_token = EXCLUDED.access_token,
            refresh_token = COALESCE(EXCLUDED.refresh_token, butler.oauth_tokens.refresh_token),
            token_expires_at = EXCLUDED.token_expires_at,
            scopes = EXCLUDED.scopes,
            provider_account_id = COALESCE(EXCLUDED.provider_account_id, butler.oauth_tokens.provider_account_id)
        """,
        user_id,
        provider,
        token_data["access_token"],
        token_data.get("refresh_token"),
        expires_at,
        scopes,
        account_id,
    )


async def get_valid_token(pool, user_id: str, provider: str) -> str | None:
    """Get a valid access token, refreshing if expired.

    Returns the access_token string, or None if no connection exists
    or refresh fails.
    """
    row = await pool.pool.fetchrow(
        """
        SELECT access_token, refresh_token, token_expires_at
        FROM butler.oauth_tokens
        WHERE user_id = $1 AND provider = $2
        """,
        user_id,
        provider,
    )
    if not row:
        return None

    # Check if token is still valid (with 5 min buffer)
    expires_at = row["token_expires_at"]
    if expires_at and expires_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        return row["access_token"]

    # Token expired — try to refresh
    refresh_token = row["refresh_token"]
    if not refresh_token:
        return None

    try:
        token_data = await refresh_google_token(refresh_token)
        expires_in = token_data.get("expires_in", 3600)
        new_expires = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        await pool.pool.execute(
            """
            UPDATE butler.oauth_tokens
            SET access_token = $1, token_expires_at = $2
            WHERE user_id = $3 AND provider = $4
            """,
            token_data["access_token"],
            new_expires,
            user_id,
            provider,
        )
        return token_data["access_token"]
    except Exception:
        logger.exception("Failed to refresh token for user=%s provider=%s", user_id, provider)
        return None


async def list_connections(pool, user_id: str) -> list[dict]:
    """List all OAuth connections for a user."""
    rows = await pool.pool.fetch(
        """
        SELECT provider, provider_account_id, created_at
        FROM butler.oauth_tokens
        WHERE user_id = $1
        ORDER BY created_at
        """,
        user_id,
    )
    return [
        {
            "provider": row["provider"],
            "account_id": row["provider_account_id"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
        for row in rows
    ]


async def delete_connection(pool, user_id: str, provider: str) -> bool:
    """Delete an OAuth connection and revoke the token with Google.

    Returns True if a connection was deleted, False if none existed.
    """
    row = await pool.pool.fetchrow(
        """
        DELETE FROM butler.oauth_tokens
        WHERE user_id = $1 AND provider = $2
        RETURNING refresh_token, access_token
        """,
        user_id,
        provider,
    )
    if not row:
        return False

    # Best-effort revocation with Google
    token_to_revoke = row["refresh_token"] or row["access_token"]
    if token_to_revoke:
        try:
            await revoke_google_token(token_to_revoke)
        except Exception:
            logger.warning("Failed to revoke token for user=%s provider=%s", user_id, provider)

    return True
