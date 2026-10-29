-- Migration 019: the household's IPTV provider login (#223)
--
-- Admins set it in Settings; Butler pushes it into Dispatcharr as an M3U
-- account, which Jellyfin's Live TV reads. One row (id = 1).
--
-- Secrets are Fernet-encrypted like service_credentials.password_encrypted
-- (and rotated by api/rotate_encryption_key.py). M3U URLs usually embed the
-- login in their query string, so the URL is encrypted too.
--
-- Idempotent: safe to re-run (migrations run on every startup).

CREATE TABLE IF NOT EXISTS butler.iptv_provider (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    kind TEXT NOT NULL CHECK (kind IN ('xtream', 'm3u')),
    server_url TEXT,                 -- Xtream Codes server (kind = 'xtream')
    username TEXT,                   -- Xtream Codes username
    password_encrypted TEXT,         -- Xtream Codes password
    m3u_url_encrypted TEXT,          -- playlist URL (kind = 'm3u')
    max_streams INTEGER NOT NULL DEFAULT 1,
    dispatcharr_account_id INTEGER,  -- the M3U account Butler manages
    last_synced_at TIMESTAMPTZ,
    last_error TEXT,
    updated_by TEXT REFERENCES butler.users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
