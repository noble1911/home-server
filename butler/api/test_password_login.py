"""Username + password sign-in, invite redemption and reset codes (no database).

Run with: pytest butler/api/test_password_login.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from . import passwords
from .routes import auth as auth_routes

PASSWORD_HASH = passwords.hash_password("correct horse")


class FakeDb:
    """Answers fetchrow/fetchval by matching a fragment of the SQL."""

    def __init__(self, rows: dict[str, object]):
        self.rows = rows
        self.executed: list[tuple] = []

    def _answer(self, sql: str):
        for fragment, value in self.rows.items():
            if fragment in sql:
                return value
        return None

    async def fetchrow(self, sql, *args):
        return self._answer(sql)

    async def fetchval(self, sql, *args):
        return self._answer(sql)

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "UPDATE 1"

    # asyncpg: pool.acquire() → connection, connection.transaction()
    def acquire(self):
        return _Ctx(self)

    def transaction(self):
        return _Ctx(self)


class _Ctx:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *exc):
        return False


def _client(db: FakeDb) -> TestClient:
    app = FastAPI()
    app.include_router(auth_routes.router, prefix="/api/auth")
    pool = MagicMock()
    pool.pool = db
    app.dependency_overrides[auth_routes.get_db_pool] = lambda: pool
    return TestClient(app)


ISSUED_USER = {"name": "Ron", "role": "admin", "service_username": "ron"}


@pytest.fixture(autouse=True)
def _reset_failures():
    auth_routes._failed_logins.clear()
    yield
    auth_routes._failed_logins.clear()


# ── Hashing ─────────────────────────────────────────────────────────


def test_hash_round_trip():
    stored = passwords.hash_password("correct horse")
    assert stored.startswith("scrypt$") and "correct horse" not in stored
    assert passwords.verify_password("correct horse", stored)
    assert not passwords.verify_password("wrong", stored)
    assert not passwords.verify_password("x", None)
    assert not passwords.verify_password("x", "garbage")


def test_reset_codes_normalise():
    assert passwords.hash_code("k7qm-2xrp") == passwords.hash_code("K7QM2XRP ")


# ── Sign-in ─────────────────────────────────────────────────────────


def test_login_with_username_and_password():
    db = FakeDb({
        "lower(service_username) = $1": {"id": "user_1", "password_hash": PASSWORD_HASH},
        "SELECT name, role, service_username": ISSUED_USER,
    })
    r = _client(db).post("/api/auth/login", json={"username": " Ron ", "password": "correct horse"})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "admin" and body["username"] == "ron" and body["tokens"]["accessToken"]


@pytest.mark.parametrize("user", [
    {"id": "user_1", "password_hash": PASSWORD_HASH},  # wrong password
    None,                                              # no such user
    {"id": "user_1", "password_hash": None},           # no password set yet
])
def test_login_refused_with_one_message(user):
    db = FakeDb({"lower(service_username) = $1": user})
    r = _client(db).post("/api/auth/login", json={"username": "ron", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect username or password"


def test_repeated_failures_lock_the_username():
    db = FakeDb({"lower(service_username) = $1": {"id": "user_1", "password_hash": PASSWORD_HASH}})
    client = _client(db)
    for _ in range(auth_routes._FAILED_LOGIN_LIMIT):
        assert client.post("/api/auth/login", json={"username": "ron", "password": "nope"}).status_code == 401
    # Even the right password waits now
    r = client.post("/api/auth/login", json={"username": "RON", "password": "correct horse"})
    assert r.status_code == 429


# ── Invites ─────────────────────────────────────────────────────────


def test_setup_code_only_works_before_anyone_exists():
    db = FakeDb({"COUNT(*)": 3, "FROM butler.invite_codes ic": None})
    with patch.object(auth_routes.settings, "invite_codes", "RON-6969"):
        r = _client(db).post("/api/auth/redeem-invite", json={"code": "ron-6969"})
    assert r.status_code == 401


def test_setup_code_creates_the_first_admin():
    db = FakeDb({"COUNT(*)": 0, "SELECT name, role, service_username": {**ISSUED_USER, "name": "x"}})
    with patch.object(auth_routes.settings, "invite_codes", "RON-6969"):
        r = _client(db).post("/api/auth/redeem-invite", json={"code": "ron-6969"})
    assert r.status_code == 200
    sql, args = db.executed[0]
    assert "'admin'" in sql and args[0].startswith("user_") and "6969" not in args[0]


def test_used_invite_no_longer_signs_in():
    db = FakeDb({
        "COUNT(*)": 3,
        "FROM butler.invite_codes ic": {"permissions": None, "used_by": "user_1", "onboarding": False, "live": False},
    })
    r = _client(db).post("/api/auth/redeem-invite", json={"code": "X9JU2E"})
    assert r.status_code == 401
    assert "Sign in with your username" in r.json()["detail"]


def test_used_invite_dead_even_without_a_password_once_onboarded():
    # e.g. someone who skipped choosing a login back when it was optional
    db = FakeDb({
        "COUNT(*)": 3,
        "FROM butler.invite_codes ic": {"permissions": None, "used_by": "user_1", "onboarding": False, "live": True},
    })
    assert _client(db).post("/api/auth/redeem-invite", json={"code": "X9JU2E"}).status_code == 401


def test_used_invite_lets_an_unfinished_signup_continue():
    db = FakeDb({
        "COUNT(*)": 3,
        "FROM butler.invite_codes ic": {"permissions": None, "used_by": "user_9", "onboarding": True, "live": True},
        "SELECT name, role, service_username": {"name": "user_9", "role": "user", "service_username": None},
    })
    r = _client(db).post("/api/auth/redeem-invite", json={"code": "X9JU2E"})
    assert r.status_code == 200
    assert r.json()["hasCompletedOnboarding"] is False


def test_new_invite_creates_a_user_unrelated_to_the_code():
    db = FakeDb({
        "COUNT(*)": 3,
        "FROM butler.invite_codes ic": {"permissions": '["media"]', "used_by": None, "onboarding": None, "live": True},
        "SELECT name, role, service_username": {"name": "x", "role": "user", "service_username": None},
    })
    r = _client(db).post("/api/auth/redeem-invite", json={"code": "q7pk2m"})
    assert r.status_code == 200
    insert = next(args for sql, args in db.executed if "INSERT INTO butler.users" in sql)
    assert insert[0].startswith("user_") and "q7pk2m" not in insert[0].lower()
    assert insert[1] == '["media"]'
    claim, link = [args for sql, args in db.executed if "invite_codes" in sql]
    assert claim == ("Q7PK2M",) and link == (insert[0], "Q7PK2M")


def test_expired_invite_refused():
    db = FakeDb({
        "COUNT(*)": 3,
        "FROM butler.invite_codes ic": {"permissions": None, "used_by": None, "onboarding": None, "live": False},
    })
    assert _client(db).post("/api/auth/redeem-invite", json={"code": "AAAAAA"}).status_code == 401


# ── Reset codes ─────────────────────────────────────────────────────


def test_reset_code_sets_password_and_signs_out_elsewhere():
    db = FakeDb({
        "FROM butler.password_reset_codes rc": {"user_id": "user_1", "service_username": "ron"},
        "SELECT name, role, service_username": ISSUED_USER,
    })
    with patch.object(auth_routes, "set_user_password", AsyncMock(return_value=[])) as set_pw:
        r = _client(db).post("/api/auth/reset-password", json={"code": "k7qm-2xrp", "newPassword": "a much longer one"})
    assert r.status_code == 200 and r.json()["username"] == "ron"
    set_pw.assert_awaited_once()
    assert set_pw.await_args.args[:2] == ("user_1", "a much longer one")
    assert any("refresh_tokens SET revoked_at" in sql for sql, _ in db.executed)


def test_reset_code_wrong_or_expired():
    db = FakeDb({"FROM butler.password_reset_codes rc": None})
    r = _client(db).post("/api/auth/reset-password", json={"code": "NOPE-NOPE", "newPassword": "a much longer one"})
    assert r.status_code == 401


def test_reset_needs_ten_characters():
    db = FakeDb({"FROM butler.password_reset_codes rc": {"user_id": "user_1", "service_username": "ron"}})
    r = _client(db).post("/api/auth/reset-password", json={"code": "K7QM-2XRP", "newPassword": "short"})
    assert r.status_code == 400
