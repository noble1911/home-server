-- Invite Code Management & Auth System
-- Adds role-based access, DB-managed invite codes, and refresh token tracking.
--
-- Usage:
--   docker exec immich-postgres psql -U postgres -d immich -f /app/migrations/004_invite_auth.sql

-- ===================
-- 1. Add role column to users
-- ===================

ALTER TABLE butler.users
    ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';

-- ===================
-- 2. Invite codes table
-- ===================

CREATE TABLE IF NOT EXISTS butler.invite_codes (
    code        TEXT PRIMARY KEY,                                          -- 6-char alphanumeric (e.g. "A3BK9F")
    created_by  TEXT REFERENCES butler.users(id) ON DELETE SET NULL,       -- Admin who generated it (NULL for bootstrap)
    used_by     TEXT REFERENCES butler.users(id) ON DELETE SET NULL,       -- User who redeemed it (NULL until used)
    expires_at  TIMESTAMPTZ NOT NULL,                                     -- Code expiry (default 7 days from creation)
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    used_at     TIMESTAMPTZ                                               -- When the code was redeemed
);

CREATE INDEX IF NOT EXISTS idx_invite_codes_created_by
    ON butler.invite_codes(created_by);

-- Fast lookup for valid unused codes
CREATE INDEX IF NOT EXISTS idx_invite_codes_valid
    ON butler.invite_codes(code)
    WHERE used_by IS NULL;

-- ===================
-- 3. Refresh tokens table
-- ===================

CREATE TABLE IF NOT EXISTS butler.refresh_tokens (
    id          SERIAL PRIMARY KEY,
    token_hash  TEXT NOT NULL UNIQUE,                                      -- SHA-256 hash (never store raw tokens)
    user_id     TEXT NOT NULL REFERENCES butler.users(id) ON DELETE CASCADE,
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ,                                              -- NULL = active, set = revoked
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id
    ON butler.refresh_tokens(user_id);

-- Fast lookup for active tokens
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_active
    ON butler.refresh_tokens(token_hash)
    WHERE revoked_at IS NULL;
