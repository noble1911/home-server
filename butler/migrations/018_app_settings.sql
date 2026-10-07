-- Migration 018: household-wide settings that admins change from the app (#215)
--
-- First key: 'chat_model' — the Claude model Butler chats with. Absent means
-- the server default (ANTHROPIC_MODEL).
--
-- Idempotent: safe to re-run (migrations run on every startup).

CREATE TABLE IF NOT EXISTS butler.app_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_by TEXT REFERENCES butler.users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
