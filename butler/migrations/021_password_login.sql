-- Migration 021: sign in with username + password
--
-- Invite codes used to double as passwords: a used code logged its user back in
-- forever, and the user id was built from it (invite_<code>), so anyone who saw
-- the id knew the code. Now an invite only creates the account; after that you
-- sign in with the username and password chosen at onboarding (the same login
-- as Jellyfin and the other apps), and an admin can issue a one-time reset code.
--
-- Idempotent: safe to re-run (migrations run on every startup).

-- Butler's own hash of the user's password (scrypt; see api/passwords.py)
ALTER TABLE butler.users
    ADD COLUMN IF NOT EXISTS password_hash TEXT;

-- Usernames sign people in, so they must be unique regardless of case
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_service_username_lower
    ON butler.users (lower(service_username))
    WHERE service_username IS NOT NULL;

-- One-time codes to choose a new password (forgotten password, first login)
CREATE TABLE IF NOT EXISTS butler.password_reset_codes (
    code_hash   TEXT PRIMARY KEY,                                         -- SHA-256 of the code (never stored raw)
    user_id     TEXT NOT NULL REFERENCES butler.users(id) ON DELETE CASCADE,
    created_by  TEXT REFERENCES butler.users(id) ON DELETE SET NULL,      -- NULL = made on the server (api.manage)
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_password_reset_codes_user_id
    ON butler.password_reset_codes(user_id);
