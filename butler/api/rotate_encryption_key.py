"""Re-encrypt stored service passwords under a new ENCRYPTION_KEY.

Why this exists: crypto.py derives the Fernet key from ENCRYPTION_KEY, falling
back to JWT_SECRET. Deployments that never set ENCRYPTION_KEY have every
service password bound to the JWT secret, so rotating that secret would make
them unreadable. This script moves the rows to a dedicated key so the two can
rotate independently.

Usage (inside the butler-api container, BEFORE setting the new key in .env):

    python -m api.rotate_encryption_key --new-key "$NEW_KEY"          # rotate
    python -m api.rotate_encryption_key --new-key "$NEW_KEY" --verify # check only

The current key (whatever crypto.py resolves from the running settings) is
used to decrypt; --new-key is used to encrypt. Runs in one transaction and
verifies every row round-trips under the new key before committing. Then set
ENCRYPTION_KEY=<new key> in .env and recreate the container.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import sys

import asyncpg
from cryptography.fernet import Fernet, InvalidToken

from .config import settings
from .crypto import _derive_fernet_key

# (table, primary key column, encrypted column)
TARGETS = [
    ("butler.users", "id", "service_password_encrypted"),
    ("butler.service_credentials", "id", "password_encrypted"),
]


def _fernet_for(secret: str) -> Fernet:
    digest = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


async def rotate(new_key: str, *, verify_only: bool) -> int:
    old = Fernet(_derive_fernet_key())
    new = _fernet_for(new_key)

    conn = await asyncpg.connect(settings.database_url)
    try:
        async with conn.transaction():
            total = 0
            for table, pk, col in TARGETS:
                rows = await conn.fetch(
                    f"SELECT {pk} AS pk, {col} AS ct FROM {table} WHERE {col} IS NOT NULL"
                )
                for row in rows:
                    try:
                        plaintext = old.decrypt(row["ct"].encode())
                    except InvalidToken:
                        # Already under the new key? Then nothing to do for it.
                        try:
                            new.decrypt(row["ct"].encode())
                            print(f"  {table} {row['pk']}: already on new key")
                            continue
                        except InvalidToken:
                            print(
                                f"ABORT: {table} {row['pk']} decrypts with neither key",
                                file=sys.stderr,
                            )
                            raise
                    ct_new = new.encrypt(plaintext).decode()
                    assert new.decrypt(ct_new.encode()) == plaintext
                    if not verify_only:
                        await conn.execute(
                            f"UPDATE {table} SET {col} = $1 WHERE {pk} = $2",
                            ct_new,
                            row["pk"],
                        )
                    total += 1
                print(f"{table}: {len(rows)} row(s) processed")
            if verify_only:
                raise _Rollback(total)
            return total
    except _Rollback as r:
        return r.count
    finally:
        await conn.close()


class _Rollback(Exception):
    def __init__(self, count: int):
        self.count = count


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--new-key", required=True, help="the value ENCRYPTION_KEY will be set to")
    ap.add_argument("--verify", action="store_true", help="dry run: decrypt + re-encrypt, no writes")
    args = ap.parse_args()
    if len(args.new_key) < 32:
        sys.exit("refusing: --new-key should be at least 32 characters")
    n = asyncio.run(rotate(args.new_key, verify_only=args.verify))
    print(("verified" if args.verify else "rotated") + f" {n} row(s)")


if __name__ == "__main__":
    main()
