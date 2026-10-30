"""Butler sign-in passwords: hashing, setting, and one-time reset codes.

Butler is the one place a password is set. It keeps its own scrypt hash for
sign-in and pushes the password to every linked app (Jellyfin, Nextcloud, …)
through provisioning.update_service_passwords.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from tools import DatabasePool

from .crypto import encrypt_password

MIN_PASSWORD_LENGTH = 10  # Nextcloud's policy; shorter ones would fail there
RESET_CODE_TTL = timedelta(hours=24)

# scrypt cost: ~16 MB and tens of ms per hash; stdlib, so no new dependency
_N, _R, _P = 2**14, 8, 1

# Same alphabet as invite codes: no 0/O, 1/I/L
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        candidate = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
            dklen=len(digest) // 2,
        )
    except ValueError:
        return False
    return hmac.compare_digest(candidate.hex(), digest)


async def hash_password_async(password: str) -> str:
    """scrypt is deliberately slow: keep it off the event loop."""
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, stored: str | None) -> bool:
    return await asyncio.to_thread(verify_password, password, stored)


async def set_user_password(user_id: str, new_password: str, pool: DatabasePool) -> list[dict]:
    """Set the user's Butler password and push it to all their linked apps.

    Returns the per-app results from update_service_passwords.
    """
    from .provisioning import update_service_passwords  # provisioning imports iptv → heavier

    results = await update_service_passwords(user_id, new_password, pool)
    await pool.pool.execute(
        "UPDATE butler.users SET password_hash = $2, service_password_encrypted = $3 WHERE id = $1",
        user_id, await hash_password_async(new_password), encrypt_password(new_password),
    )
    return results


# ── Reset codes ──────────────────────────────────────────────────────


def normalise_code(code: str) -> str:
    return "".join(c for c in code.upper() if c.isalnum())


def hash_code(code: str) -> str:
    return hashlib.sha256(normalise_code(code).encode()).hexdigest()


async def create_reset_code(user_id: str, pool: DatabasePool, created_by: str | None) -> tuple[str, datetime]:
    """A one-time code (e.g. "K7QM-2XRP") that lets the user choose a new password.

    Replaces any earlier unused code for the user. Only the hash is stored.
    """
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
    code = f"{raw[:4]}-{raw[4:]}"
    expires_at = datetime.now(timezone.utc) + RESET_CODE_TTL
    db = pool.pool
    await db.execute(
        "DELETE FROM butler.password_reset_codes WHERE user_id = $1 AND used_at IS NULL", user_id,
    )
    await db.execute(
        """INSERT INTO butler.password_reset_codes (code_hash, user_id, created_by, expires_at)
           VALUES ($1, $2, $3, $4)""",
        hash_code(code), user_id, created_by, expires_at,
    )
    return code, expires_at
