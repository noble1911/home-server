"""Server-side account tools: the way back in when nobody can sign in.

Run inside the butler-api container on the Mac Mini (needs shell access to
the server, so it's only usable by whoever runs the box):

    docker exec butler-api python -m api.manage list-users
    docker exec butler-api python -m api.manage reset-code ron
    docker exec butler-api python -m api.manage link-accounts ron
    docker exec butler-api python -m api.manage set-username <user-id> tanaka
    docker exec butler-api python -m api.manage backfill-password-hashes

reset-code prints a one-time code (24 hours). Enter it on the sign-in page
under "Have a reset code?" to choose a new password; it also signs out every
other session for that user.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from tools import DatabasePool

from .account_links import link_existing_accounts
from .config import settings
from .crypto import decrypt_password
from .passwords import create_reset_code, hash_password_async


async def _user_id(pool: DatabasePool, who: str) -> str:
    """Accept a username (any case) or a user id."""
    user_id = await pool.pool.fetchval(
        "SELECT id FROM butler.users WHERE lower(service_username) = lower($1) OR id = $1", who,
    )
    if not user_id:
        sys.exit(f"No user with username or id '{who}'. Try: python -m api.manage list-users")
    return user_id


async def list_users(pool: DatabasePool, _args) -> None:
    rows = await pool.pool.fetch(
        """SELECT id, name, role, service_username, password_hash IS NOT NULL AS has_password
           FROM butler.users WHERE id NOT IN ('default', 'system') ORDER BY created_at"""
    )
    for r in rows:
        print(f"{r['service_username'] or '-':<14} {r['name']:<20} {r['role']:<6} "
              f"{'password set' if r['has_password'] else 'NO PASSWORD':<13} {r['id']}")


async def reset_code(pool: DatabasePool, args) -> None:
    user_id = await _user_id(pool, args.user)
    username = await pool.pool.fetchval("SELECT service_username FROM butler.users WHERE id = $1", user_id)
    if not username:
        sys.exit("That user has no username yet, so they can't sign in with a password.")
    code, expires_at = await create_reset_code(user_id, pool, created_by=None)
    print(f"Reset code for {username}: {code}")
    print(f"Valid until {expires_at:%Y-%m-%d %H:%M} UTC. On the sign-in page choose \"Have a reset code?\".")


async def link_accounts(pool: DatabasePool, args) -> None:
    for r in await link_existing_accounts(await _user_id(pool, args.user), pool):
        print(f"{r['service']:<15} {r['status']}{' - ' + r['error'] if r.get('error') else ''}")


async def set_username(pool: DatabasePool, args) -> None:
    """For accounts from before the login was required (needed for reset codes)."""
    user_id = await _user_id(pool, args.user)
    username = args.username.strip().lower()
    taken = await pool.pool.fetchval(
        "SELECT 1 FROM butler.users WHERE lower(service_username) = $1 AND id <> $2", username, user_id,
    )
    if taken:
        sys.exit(f"'{username}' is already someone's username")
    await pool.pool.execute("UPDATE butler.users SET service_username = $2 WHERE id = $1", user_id, username)
    print(f"{user_id}: username set to {username}")


async def backfill_password_hashes(pool: DatabasePool, _args) -> None:
    """Give users who chose a login before password sign-in existed a hash of it."""
    rows = await pool.pool.fetch(
        """SELECT id, service_username, service_password_encrypted FROM butler.users
           WHERE password_hash IS NULL AND service_username IS NOT NULL
             AND service_password_encrypted IS NOT NULL"""
    )
    for r in rows:
        password = decrypt_password(r["service_password_encrypted"])
        await pool.pool.execute(
            "UPDATE butler.users SET password_hash = $2 WHERE id = $1 AND password_hash IS NULL",
            r["id"], await hash_password_async(password),
        )
        print(f"{r['service_username']}: password hash set")
    print(f"{len(rows)} user(s) updated")


COMMANDS = {
    "list-users": list_users,
    "reset-code": reset_code,
    "link-accounts": link_accounts,
    "set-username": set_username,
    "backfill-password-hashes": backfill_password_hashes,
}


async def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m api.manage", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list-users", help="Usernames, roles and who has a password")
    for name, help_text in (("reset-code", "Print a one-time code to choose a new password"),
                            ("link-accounts", "Link a user's existing app logins")):
        sub.add_parser(name, help=help_text).add_argument("user", help="Username or user id")
    p = sub.add_parser("set-username", help="Give an older account a username (so it can get a reset code)")
    p.add_argument("user", help="Current username or user id")
    p.add_argument("username", help="New username")
    sub.add_parser("backfill-password-hashes", help="Hash logins chosen before password sign-in")
    args = parser.parse_args(argv)

    pool = await DatabasePool.create(settings.database_url)
    try:
        await COMMANDS[args.command](pool, args)
    finally:
        await pool.pool.close()


if __name__ == "__main__":
    asyncio.run(main())
