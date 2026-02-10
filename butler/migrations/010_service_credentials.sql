-- Service Credentials: auto-provisioned app accounts per user.
-- Passwords are Fernet-encrypted at rest; status tracks provisioning outcome.

CREATE TABLE IF NOT EXISTS butler.service_credentials (
    id              SERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES butler.users(id) ON DELETE CASCADE,
    service         TEXT NOT NULL,           -- 'jellyfin', 'audiobookshelf', 'nextcloud', 'immich'
    username        TEXT NOT NULL,
    password_encrypted TEXT,                 -- Fernet-encrypted password (NULL on failure)
    external_id     TEXT,                    -- Service-specific user ID (for idempotency/future ops)
    status          TEXT NOT NULL DEFAULT 'active',  -- 'active', 'failed'
    error_message   TEXT,                    -- Error details if status = 'failed'
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (user_id, service)               -- One account per user per service
);

CREATE INDEX IF NOT EXISTS idx_service_credentials_user_id
    ON butler.service_credentials(user_id);
