"""The app's LiveKit token must let it do what the voice UI needs (#219).

Run with: pytest butler/api/test_livekit_token.py -v
"""

from __future__ import annotations

import jwt

from .auth import create_livekit_token
from .config import settings


def test_voice_token_grants():
    token = create_livekit_token("ron", "butler_ron_abc123")
    claims = jwt.decode(token, settings.livekit_api_secret, algorithms=["HS256"])
    video = claims["video"]
    assert claims["sub"] == "ron" and video["room"] == "butler_ron_abc123" and video["roomJoin"]
    assert video["canPublish"] and video["canSubscribe"]
    # The app sets speak_replies on itself; without this LiveKit refuses and voice
    # falls over on connect (what #217 shipped)
    assert video["canUpdateOwnMetadata"]
