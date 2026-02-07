"""Symmetric encryption for service credentials.

Uses Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from JWT_SECRET.
"""

import base64
import hashlib

from cryptography.fernet import Fernet

from .config import settings


def _derive_fernet_key() -> bytes:
    """Derive a 32-byte Fernet key from JWT_SECRET via SHA-256."""
    digest = hashlib.sha256(settings.jwt_secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_password(plaintext: str) -> str:
    """Encrypt a password for storage. Returns base64-encoded ciphertext."""
    f = Fernet(_derive_fernet_key())
    return f.encrypt(plaintext.encode()).decode()


def decrypt_password(ciphertext: str) -> str:
    """Decrypt a stored password. Returns plaintext."""
    f = Fernet(_derive_fernet_key())
    return f.decrypt(ciphertext.encode()).decode()
