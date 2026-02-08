"""JWT authentication and LiveKit token generation.

Two separate token types:
- User JWT: issued on invite code redemption, validated on every PWA request
  - Access token (short-lived, 1 hour): carries user_id + role
  - Refresh token (long-lived, 180 days): used to get new access tokens
- LiveKit JWT: short-lived room token for WebRTC voice connections
"""

import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from livekit.api import AccessToken, VideoGrants

from .config import settings


# --- User JWT ---


def create_user_tokens(user_id: str, role: str = "user") -> tuple[str, str, int]:
    """Create access + refresh tokens for a user.

    The access token embeds the user's role so the frontend can check
    admin status without an extra API call.

    Returns:
        (access_token, refresh_token, expires_at_ms)
    """
    now = datetime.now(timezone.utc)
    access_expires = now + timedelta(hours=settings.jwt_expire_hours)
    refresh_expires = now + timedelta(hours=settings.jwt_refresh_expire_hours)
    expires_at_ms = int(access_expires.timestamp() * 1000)

    access_token = jwt.encode(
        {"sub": user_id, "role": role, "iat": now, "exp": access_expires, "type": "access"},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    refresh_token = jwt.encode(
        {
            "sub": user_id,
            "iat": now,
            "exp": refresh_expires,
            "type": "refresh",
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    return access_token, refresh_token, expires_at_ms


def decode_user_jwt(token: str) -> dict:
    """Decode and validate a user access token.

    Raises:
        jwt.InvalidTokenError: If token is invalid, expired, or wrong type.
    """
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Not an access token")
    return payload


def decode_refresh_jwt(token: str) -> dict:
    """Decode and validate a refresh token.

    Raises:
        jwt.InvalidTokenError: If token is invalid, expired, or wrong type.
    """
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != "refresh":
        raise jwt.InvalidTokenError("Not a refresh token")
    return payload


def hash_token(token: str) -> str:
    """SHA-256 hash a token for safe DB storage."""
    return hashlib.sha256(token.encode()).hexdigest()


# --- LiveKit Token ---


def create_livekit_token(user_id: str, room_name: str) -> str:
    """Create a scoped LiveKit room access token for WebRTC.

    The token grants the user permission to join and publish/subscribe
    in a specific room. TTL is 1 hour.
    """
    token = AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
    token.identity = user_id
    token.name = user_id
    token.video_grants = VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,
        can_subscribe=True,
    )
    token.ttl = timedelta(hours=1)
    return token.to_jwt()
