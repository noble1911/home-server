-- Push notification subscriptions (Web Push API)
-- Each row represents one browser/device subscription for a user.

CREATE TABLE IF NOT EXISTS butler.push_subscriptions (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES butler.users(id) ON DELETE CASCADE,
    endpoint    TEXT NOT NULL,
    key_p256dh  TEXT NOT NULL,
    key_auth    TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, endpoint)
);

CREATE INDEX IF NOT EXISTS idx_push_subs_user
    ON butler.push_subscriptions(user_id);
