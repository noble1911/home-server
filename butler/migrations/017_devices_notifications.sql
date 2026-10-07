-- Migration 017: Android app notifications without Firebase (#214)
--
-- The Butler Android app keeps a WebSocket open to /api/notifications/ws and
-- Butler pushes notifications down it. Each phone gets its own device
-- credential (only its SHA-256 is stored), separate from the user's login
-- tokens, so the background connection can never race the app's refresh-token
-- rotation. Notifications go through an outbox so a phone that was offline
-- catches up on reconnect.
--
-- Idempotent: safe to re-run (migrations run on every startup).

CREATE TABLE IF NOT EXISTS butler.devices (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES butler.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'Android phone',
    platform TEXT NOT NULL DEFAULT 'android',
    token_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_devices_user ON butler.devices (user_id);

CREATE TABLE IF NOT EXISTS butler.notifications (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES butler.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '/',
    category TEXT NOT NULL DEFAULT 'general',
    silent BOOLEAN NOT NULL DEFAULT FALSE,   -- quiet hours: show, but without sound
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON butler.notifications (user_id, id);
