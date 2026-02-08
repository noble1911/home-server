-- OAuth Token Storage
-- Stores per-user OAuth tokens for external service integrations (Google Calendar, Gmail, etc.)
--
-- Usage:
--   docker exec immich-postgres psql -U postgres -d immich -f /app/migrations/002_oauth_tokens.sql

CREATE TABLE IF NOT EXISTS butler.oauth_tokens (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES butler.users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,                  -- 'google', 'microsoft', etc.
    access_token TEXT NOT NULL,
    refresh_token TEXT,                      -- NULL for providers that don't issue refresh tokens
    token_expires_at TIMESTAMPTZ,            -- When access_token expires
    scopes TEXT NOT NULL,                    -- Space-separated scopes granted
    provider_account_id TEXT,                -- e.g., Google email for display
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, provider)                -- One connection per provider per user
);

-- Note: UNIQUE(user_id, provider) already creates an index covering
-- both (user_id, provider) lookups and (user_id)-only lookups (leftmost prefix).

-- Reuse existing updated_at trigger function from migration 001
DROP TRIGGER IF EXISTS oauth_tokens_updated_at ON butler.oauth_tokens;
CREATE TRIGGER oauth_tokens_updated_at
    BEFORE UPDATE ON butler.oauth_tokens
    FOR EACH ROW
    EXECUTE FUNCTION butler.update_updated_at();
