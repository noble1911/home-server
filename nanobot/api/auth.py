"""JWT authentication and LiveKit token generation.

Two separate token types:
- User JWT: issued on invite code redemption, validated on every PWA request
- LiveKit JWT: short-lived room token for WebRTC voice connections
"""

from datetime import datetime, timedelta, timezone

import jwt
from livekit.api import AccessToken, VideoGrants

from .config import settings


# --- User JWT ---


def create_user_tokens(user_id: str) -> tuple[str, str, int]:
    """Create access + refresh tokens for a user.

    Returns:
        (access_token, refresh_token, expires_at_ms)
    """
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=settings.jwt_expire_hours)
    expires_at_ms = int(expires.timestamp() * 1000)

    access_token = jwt.encode(
        {"sub": user_id, "iat": now, "exp": expires, "type": "access"},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    refresh_token = jwt.encode(
        {
            "sub": user_id,
            "iat": now,
            "exp": now + timedelta(hours=settings.jwt_expire_hours * 2),
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
